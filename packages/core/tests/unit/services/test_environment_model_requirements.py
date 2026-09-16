"""CGCORE-DEP-02C: environment requirements without saved workflow references."""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Literal

import pytest
from comfygit_core.models.manifest import ManifestModel
from comfygit_core.services.build_readiness import build_readiness_from_manifest_snapshot


def declare(test_env, *, model_hash="a" * 16, criticality: Literal["required", "optional"] | None = "required", sources=None, path="checkpoints/model.safetensors", size=16):
    model = ManifestModel(model_hash, path.rsplit("/", 1)[-1], size, path, "checkpoints", sources or [], criticality)
    test_env.pyproject.models.add_model(model)
    return model


def test_declaration_survives_enrichment_cleanup_and_appears_in_inventory(test_env, test_workspace):
    model = declare(test_env)
    enriched = ManifestModel.from_toml_dict(model.hash, model.to_toml_dict())
    enriched.criticality = None
    enriched.sources = ["https://example.test/model.safetensors"]
    test_env.pyproject.models.add_model(enriched)
    test_env.pyproject.models.cleanup_orphans()
    snapshot = test_env.get_manifest_snapshot()
    assert snapshot.models[model.hash].criticality == "required"
    readiness = build_readiness_from_manifest_snapshot(snapshot)
    assert len(readiness.environment_models) == 1
    assert readiness.environment_models[0].sources == tuple(enriched.sources)
    assert readiness.to_dict()["environment_models"][0]["hash"] == model.hash
    from comfygit_core.utils.environment_cleanup import mark_environment_complete
    mark_environment_complete(test_env.cec_path)
    inventory = test_workspace.get_resource_inventory().environments[0]
    assert len(inventory.model_dependencies) == 1
    assert inventory.model_dependencies[0].workflow_names == ()
    assert inventory.model_dependencies[0].relative_path == model.relative_path
    missing = test_env.model_manager.detect_missing_models()
    assert len(missing) == 1 and missing[0].criticality == "required"


def test_legacy_catalog_is_not_a_root_requirement_and_optional_does_not_block(test_env):
    declare(test_env, criticality=None)
    declare(test_env, model_hash="b" * 16, criticality="optional", path="checkpoints/optional.safetensors")
    readiness = build_readiness_from_manifest_snapshot(test_env.get_manifest_snapshot())
    assert len(readiness.environment_models) == 1
    proof = next(proof for proof in readiness.dependency_proof if proof.kind == "model")
    assert proof.status == "missing_optional" and not proof.required
    assert test_env.model_manager.download_environment_models("required") == []
    assert test_env.model_manager.download_environment_models("skip") == []
    assert not test_env.model_manager.download_environment_models("all")[0].success


def test_required_without_source_blocks_build_and_acquisition(test_env):
    declare(test_env)
    readiness = build_readiness_from_manifest_snapshot(test_env.get_manifest_snapshot())
    assert readiness.status == "blocked"
    result = test_env.model_manager.download_environment_models("required")[0]
    assert not result.success and "No download source" in result.error


@pytest.mark.parametrize("path", ["../escape.safetensors", "/tmp/escape.safetensors", "C:/escape.safetensors"])
def test_environment_model_rejects_unsafe_destination(test_env, path):
    declare(test_env, path=path, sources=["https://example.test/model.safetensors"])
    result = test_env.model_manager.download_environment_models()[0]
    assert not result.success and "relative" in result.error


def test_environment_model_rejects_symlink_escape(test_env, tmp_path):
    model_dir = test_env.model_manager.model_downloader.models_dir
    (model_dir / "escape").symlink_to(tmp_path, target_is_directory=True)
    declare(test_env, path="escape/model.safetensors", sources=["https://example.test/model.safetensors"])
    assert not test_env.model_manager.download_environment_models()[0].success
    assert not (tmp_path / "model.safetensors").exists()


def test_environment_model_download_real_http_and_reuse(test_env, test_workspace, tmp_path):
    payload = b"portable-environment-model" * 1024
    source = tmp_path / "source.safetensors"
    source.write_bytes(payload)
    expected_hash = test_workspace.model_repository.calculate_short_hash(source)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        declare(test_env, model_hash=expected_hash, size=len(payload), sources=[f"http://127.0.0.1:{server.server_port}/source.safetensors"])
        first = test_env.model_manager.download_environment_models("required")[0]
        assert first.success and not first.reused, first.error
        target = test_env.model_manager.model_downloader.models_dir / "checkpoints/model.safetensors"
        assert target.read_bytes() == payload
        assert test_env.model_manager.detect_missing_models() == []
        server.shutdown()
        second = test_env.model_manager.download_environment_models("required")[0]
        assert second.success and second.reused
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_invalid_criticality_rejected():
    with pytest.raises(ValueError, match="criticality"):
        ManifestModel.from_toml_dict("a" * 16, {"filename": "model", "size": 1, "relative_path": "model", "criticality": "suggested"})


def test_root_requirement_cannot_be_downgraded_by_optional_workflow(test_env, test_workspace):
    from comfygit_core.models.manifest import ManifestWorkflowModel
    from comfygit_core.utils.environment_cleanup import mark_environment_complete
    model = declare(test_env)
    test_env.pyproject.workflows.set_workflow_models("dynamic", [ManifestWorkflowModel(
        filename=model.filename, category=model.category, criticality="optional", status="resolved",
        nodes=[], hash=model.hash, declared_by="manual", relative_path=model.relative_path,
    )])
    readiness = build_readiness_from_manifest_snapshot(test_env.get_manifest_snapshot())
    assert all(proof.required for proof in readiness.dependency_proof if proof.kind == "model")
    mark_environment_complete(test_env.cec_path)
    dependencies = test_workspace.get_resource_inventory().environments[0].model_dependencies
    assert len(dependencies) == 1
    assert dependencies[0].criticality == "required" and dependencies[0].workflow_names == ("dynamic",)
    assert test_env.model_manager.detect_missing_models()[0].criticality == "required"


def test_acquired_manual_intent_resolves_without_editable_workflow(test_env, monkeypatch):
    from comfygit_core.models.manifest import ManifestWorkflowModel
    model = declare(test_env)
    test_env.pyproject.workflows.set_workflow_models("api-only", [ManifestWorkflowModel(
        filename=model.filename, category=model.category, criticality="required", status="unresolved",
        nodes=[], hash=model.hash, declared_by="manual", relative_path=model.relative_path,
        sources=["https://example.test/model.safetensors"],
    )])
    monkeypatch.setattr(test_env.model_manager, "_get_available_workflow_model", lambda model: True)
    assert test_env.model_manager.prepare_import_with_model_strategy("all") == []
    assert test_env.pyproject.workflows.get_workflow_models("api-only")[0].status == "resolved"


def test_sync_reports_failed_selected_environment_model(test_env):
    declare(test_env)
    result = test_env.sync(model_strategy="required")
    assert not result.success
    assert result.models_failed == [("model.safetensors", "No download source for environment model: model.safetensors")]
    assert not (test_env.cec_path / ".complete").exists()
