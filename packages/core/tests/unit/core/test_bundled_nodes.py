"""Portable bundles use the real manifest, materializer, scanner and archive paths."""

import tarfile
from unittest.mock import Mock

import pytest
from comfygit_core.factories.environment_factory import EnvironmentFactory
from comfygit_core.services.bundled_nodes import (
    install_bundle,
    snapshot_directory,
    validate_bundle_path,
)
from comfygit_core.services.environment_readiness import collect_node_provenance_warnings


def bundle(env, name="My Node"):
    source = env.cec_path / "bundled_nodes" / name
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("NODE_CLASS_MAPPINGS = {}\n")
    node = env.bundle_node(name, source)
    return source, node


def test_manifest_sync_status_and_requirements(test_env, monkeypatch):
    source, node = bundle(test_env)
    (source / "requirements.txt").write_text("example-package==1.0\n")
    download = Mock(side_effect=AssertionError("bundles must never resolve remotely"))
    monkeypatch.setattr(test_env.node_manager.node_lookup, "download_to_cache", download)
    # UV external resolution is the only seam; persist exactly what it would stage.
    calls = []

    def add(requirements, *, group, **kwargs):
        calls.append(requirements)
        test_env.pyproject.dependencies.add_to_group(group, requirements)

    monkeypatch.setattr(test_env.node_manager.uv, "add_requirements_with_sources", add)
    manager = test_env.node_manager
    manager.sync_nodes_to_filesystem()
    assert manager.provision_missing_node_dependencies()
    assert not manager.provision_missing_node_dependencies()
    reread = test_env.pyproject.nodes.get_existing()[node.name]
    assert reread.bundle_path == node.bundle_path
    assert (
        test_env.pyproject.get_manifest_snapshot().nodes[node.name].bundle_path == node.bundle_path
    )
    assert collect_node_provenance_warnings(test_env) == []
    from comfygit_core.analyzers.status_scanner import StatusScanner

    scanner = StatusScanner(
        test_env.uv_manager, test_env.pyproject, test_env.venv_path, test_env.comfyui_path
    )
    comparison = scanner.compare_states(scanner.scan_environment(), scanner.scan_manifest())
    assert comparison.version_mismatches == []
    (source / "requirements.txt").write_text("another-package==2.0\n")
    manager.sync_nodes_to_filesystem()
    assert manager.provision_missing_node_dependencies()
    group = test_env.pyproject.nodes.generate_group_name(node, node.name)
    assert test_env.pyproject.dependencies.get_groups()[group] == ["another-package==2.0"]
    assert len(calls) == 2
    download.assert_not_called()


def test_repeat_sync_source_edit_and_runtime_conflict(test_env):
    source, node = bundle(test_env)
    assert install_bundle(test_env.cec_path, test_env.custom_nodes_path, node)
    assert not install_bundle(test_env.cec_path, test_env.custom_nodes_path, node)
    (source / "new.py").write_text("value = 2")
    assert install_bundle(test_env.cec_path, test_env.custom_nodes_path, node)
    runtime = test_env.custom_nodes_path / node.name
    (runtime / "new.py").write_text("user change")
    with pytest.raises(ValueError, match="conflicting runtime edits"):
        test_env.node_manager.sync_nodes_to_filesystem()
    assert (runtime / "new.py").read_text() == "user change"


def test_missing_required_fails_optional_warns(test_env):
    _, node = bundle(test_env)
    node.bundle_path = "bundled_nodes/missing"
    test_env.pyproject.nodes.add(node, node.name)
    with pytest.raises(ValueError, match="Required custom-node"):
        test_env.node_manager.sync_nodes_to_filesystem()
    node.criticality = "optional"
    test_env.pyproject.nodes.add(node, node.name)
    test_env.node_manager.sync_nodes_to_filesystem()


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/tmp/node",
        "C:/node",
        "bundled_nodes/../x",
        "bundled_nodes//x",
        "bundled_nodes/x\\y",
        "bundled_nodes/CON",
        "bundled_nodes/x.",
    ],
)
def test_path_rejection(path):
    with pytest.raises(ValueError):
        validate_bundle_path(path)


def test_symlinks_and_cache_exclusion(tmp_path):
    (tmp_path / "__init__.py").write_text("")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "test.pyc").write_bytes(b"cache")
    first = snapshot_directory(tmp_path)
    assert first.files == ("__init__.py",)
    (tmp_path / "escape").symlink_to("/tmp")
    with pytest.raises(ValueError, match="link"):
        snapshot_directory(tmp_path)


def test_directory_and_tar_transport(test_env, test_workspace, tmp_path):
    source, node = bundle(test_env)
    (source / "requirements.txt").write_text("example-package==1.0\n")
    imported = EnvironmentFactory.import_from_directory(
        test_env.cec_path,
        "directory-copy",
        test_workspace.paths.environments / "directory-copy",
        test_workspace,
    )
    imported.custom_nodes_path.mkdir(parents=True)
    imported.node_manager.sync_nodes_to_filesystem()
    assert (
        snapshot_directory(imported.custom_nodes_path / node.name).digest
        == snapshot_directory(source).digest
    )
    archive = tmp_path / "portable.tar.gz"
    from comfygit_core.managers.export_import_manager import ExportImportManager

    ExportImportManager(test_env.cec_path, test_env.comfyui_path).create_export(
        archive, test_env.pyproject
    )
    with tarfile.open(archive) as tar:
        assert f"{node.bundle_path}/requirements.txt" in tar.getnames()
    from comfygit_core.managers.export_import_manager import ExportImportManager

    dest = tmp_path / "archive-copy"
    ExportImportManager(test_env.cec_path, test_env.comfyui_path).extract_import(archive, dest)
    assert snapshot_directory(dest / node.bundle_path).digest == snapshot_directory(source).digest


def test_failed_required_remote_node_is_not_success(test_env, monkeypatch):
    from comfygit_core.models.shared import NodeInfo

    test_env.pyproject.nodes.add(
        NodeInfo(
            name="private", source="git", repository="https://example.com/private", version="a" * 40
        ),
        "private",
    )
    monkeypatch.setattr(test_env.node_manager.node_lookup, "download_to_cache", lambda _: None)
    with pytest.raises(ValueError, match="private: download failed"):
        test_env.node_manager.sync_nodes_to_filesystem()


def test_dependencies_refresh_before_package_resolution(test_env, monkeypatch):
    from comfygit_core.models.sync import UVSyncOutcome

    source, node = bundle(test_env)
    group = test_env.pyproject.nodes.generate_group_name(node, node.name)
    test_env.pyproject.dependencies.add_to_group(group, ["obsolete-package==1.0"])
    events = []

    def resolve(**kwargs):
        assert test_env.pyproject.dependencies.get_groups()[group] == []
        events.append("resolved")
        return UVSyncOutcome(packages_synced=True)

    monkeypatch.setattr(test_env.uv_manager, "sync_dependencies_progressive", resolve)
    result = test_env.sync(model_strategy="skip")
    assert result.success, result.errors
    assert events == ["resolved"]


def test_sync_missing_bundle_fails_before_package_install(test_env, monkeypatch):
    _, node = bundle(test_env)
    node.bundle_path = "bundled_nodes/missing"
    test_env.pyproject.nodes.add(node, node.name)
    resolve = Mock(side_effect=AssertionError("invalid source must fail first"))
    monkeypatch.setattr(test_env.uv_manager, "sync_dependencies_progressive", resolve)
    result = test_env.sync(model_strategy="skip")
    assert not result.success
    assert "missing" in result.errors[0]
    resolve.assert_not_called()


def test_bundle_inventory_and_planner_require_evidence():
    from dataclasses import asdict
    from types import SimpleNamespace

    from comfygit_core.build_readiness import build_readiness_from_manifest_dict
    from comfygit_core.bundled_nodes import BundleEntry, BundleInventory, validate_bundle_inventory
    from comfygit_core.models.shared import NodeInfo

    node = NodeInfo(name="My Node", source="bundled", bundle_path="bundled_nodes/My Node")
    manifest = {
        "project": {"name": "test"},
        "tool": {"comfygit": {"nodes": {"node": asdict(node)}}},
    }
    plan = build_readiness_from_manifest_dict(manifest)
    assert plan.status == "blocked"
    inventory = BundleInventory(
        "a" * 40,
        (
            BundleEntry("bundled_nodes", "directory"),
            BundleEntry(node.bundle_path, "directory"),
            BundleEntry(node.bundle_path + "/__init__.py", "file", 3),
        ),
    )

    class Validator:
        def validate_source(self, *, source, kind, metadata):
            assert kind == "bundled_node"
            assert validate_bundle_inventory(source, inventory) == 1
            return SimpleNamespace(
                status="verified", detail="ok", to_dict=lambda: {"revision": inventory.revision}
            )

    ready = build_readiness_from_manifest_dict(manifest, bundle_validator=Validator())
    assert ready.status == "ready"
    assert ready.custom_nodes[0].to_dict()["bundle_path"] == node.bundle_path
    for bad in [
        BundleInventory("a" * 40, inventory.entries, False),
        BundleInventory("a" * 40, ()),
        BundleInventory(
            "a" * 40, (*inventory.entries, BundleEntry(node.bundle_path + "/escape", "symlink"))
        ),
    ]:
        with pytest.raises(ValueError):
            validate_bundle_inventory(node.bundle_path, bad)


def test_legacy_bundle_metadata_requires_migration():
    from comfygit_core.models.shared import NodeInfo

    with pytest.raises(ValueError, match="source='bundled'"):
        NodeInfo(name="node", source="git", bundle_path="bundled_nodes/node")


def test_git_import_uses_committed_bundle_and_repeat_sync(test_env, test_workspace, monkeypatch):
    import subprocess

    source, node = bundle(test_env)
    (source / "version.py").write_text("VALUE = 'committed'\n")
    subprocess.run(["git", "add", "."], cwd=test_env.cec_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "bundle fixture",
        ],
        cwd=test_env.cec_path,
        check=True,
        capture_output=True,
    )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_env.cec_path, text=True
    ).strip()
    (source / "version.py").write_text("VALUE = 'uncommitted'\n")
    imported = EnvironmentFactory.import_from_git(
        str(test_env.cec_path),
        "git-copy",
        test_workspace.paths.environments / "git-copy",
        test_workspace,
        branch=revision,
    )
    imported.custom_nodes_path.mkdir(parents=True)
    monkeypatch.setattr(
        imported.node_manager.node_lookup,
        "download_to_cache",
        Mock(side_effect=AssertionError("remote node lookup")),
    )
    imported.node_manager.sync_nodes_to_filesystem()
    imported.node_manager.sync_nodes_to_filesystem()
    assert (
        imported.custom_nodes_path / node.name / "version.py"
    ).read_text() == "VALUE = 'committed'\n"


def test_disabled_bundle_is_reenabled_without_duplicate(test_env):
    _, node = bundle(test_env)
    test_env.node_manager.sync_nodes_to_filesystem()
    target = test_env.custom_nodes_path / node.name
    disabled = target.with_name(target.name + ".disabled")
    target.rename(disabled)
    test_env.node_manager.sync_nodes_to_filesystem()
    assert target.is_dir() and not disabled.exists()


def test_bundle_registration_rejects_symlink_parent(test_env, tmp_path):
    (tmp_path / "__init__.py").write_text("")
    (test_env.cec_path / "bundled_nodes").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        test_env.bundle_node("unsafe", tmp_path)
    assert not (tmp_path / "unsafe").exists()


def test_excluded_metadata_symlink_is_not_copied(test_env, tmp_path):
    source, node = bundle(test_env)
    secret = tmp_path / "outside"
    secret.write_text("must stay outside")
    (source / ".venv").symlink_to(secret)
    test_env.node_manager.sync_nodes_to_filesystem()
    assert not (test_env.custom_nodes_path / node.name / ".venv").exists()


def test_failed_staging_does_not_leave_partial_runtime(test_env, monkeypatch):
    import shutil

    from comfygit_core.models.shared import NodeInfo

    node = NodeInfo(
        name="remote", source="git", repository="https://example.invalid/remote", version="a" * 40
    )
    test_env.pyproject.nodes.add(node, node.name)
    monkeypatch.setattr(
        test_env.node_manager.node_lookup, "download_to_cache", lambda _: test_env.cec_path
    )

    def failed_copy(source, target):
        target.mkdir()
        (target / "partial.py").write_text("partial")
        raise OSError("interrupted copy")

    monkeypatch.setattr(shutil, "copytree", failed_copy)
    with pytest.raises(ValueError, match="interrupted copy"):
        test_env.node_manager.sync_nodes_to_filesystem()
    assert not (test_env.custom_nodes_path / node.name).exists()
