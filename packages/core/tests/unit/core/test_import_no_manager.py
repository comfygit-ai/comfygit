"""Unit-style coverage for --no-manager import behavior."""

import tarfile
from pathlib import Path

from comfygit_core.core.environment import Environment


def _create_import_tarball(base_dir: Path, pyproject_content: str) -> Path:
    export_content = base_dir / "export_content"
    export_content.mkdir()
    (export_content / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

    tarball = base_dir / "import_headless.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(export_content / "pyproject.toml", arcname="pyproject.toml")
    return tarball


def test_finalize_import_no_manager_skips_manager_registration(
    test_workspace, tmp_path, mock_comfyui_clone, mock_github_api, mock_pytorch_probe, monkeypatch
):
    """finalize_import(no_manager=True) should not call _register_imported_manager."""
    pyproject_content = """
[project]
name = "comfygit-env-test"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.comfygit]
comfyui_version = "v0.3.20"
python_version = "3.12"
nodes = {}
"""
    tarball = _create_import_tarball(tmp_path, pyproject_content)

    def _fail_register(self):  # pragma: no cover - assertion path
        raise AssertionError("_register_imported_manager should not be called in headless mode")

    monkeypatch.setattr(Environment, "_register_imported_manager", _fail_register)

    env = test_workspace.import_environment(
        tarball_path=tarball,
        name="import-no-manager",
        model_strategy="skip",
        no_manager=True,
    )

    config = env.pyproject.load()
    assert config["tool"]["comfygit"]["headless"] is True



def test_failed_environment_model_acquisition_does_not_mark_import_complete(
    test_workspace, tmp_path, mock_comfyui_clone, mock_github_api, mock_pytorch_probe, monkeypatch
):
    import pytest
    from comfygit_core.models.exceptions import CDModelDownloadError
    from comfygit_core.utils.environment_cleanup import is_environment_complete

    recipe = '''
[project]
name = "comfygit-env-missing-model"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []
[tool.comfygit]
comfyui_version = "v0.3.20"
python_version = "3.12"
nodes = {}
[tool.comfygit.models.aaaaaaaaaaaaaaaa]
filename = "missing.safetensors"
size = 10
relative_path = "checkpoints/missing.safetensors"
category = "checkpoints"
criticality = "required"
'''
    tarball = _create_import_tarball(tmp_path, recipe)
    with pytest.raises(CDModelDownloadError):
        test_workspace.import_environment(
            tarball_path=tarball, name="missing-model", model_strategy="required", no_manager=True,
        )
    assert not is_environment_complete(test_workspace.paths.environments / "missing-model" / ".cec")
