from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from comfygit_core.utils import comfyui_ops


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_repository_defaults_and_rejects_embedded_credentials():
    assert comfyui_ops.normalize_comfyui_repository(None) == (
        "https://github.com/Comfy-Org/ComfyUI.git"
    )
    with pytest.raises(ValueError, match="credentials"):
        comfyui_ops.normalize_comfyui_repository(
            "https://token@example.com/owner/ComfyUI.git"
        )
    with pytest.raises(ValueError, match="fragments"):
        comfyui_ops.normalize_comfyui_repository(
            "https://github.com/owner/ComfyUI.git#subdirectory"
        )
    assert comfyui_ops.normalize_comfyui_commit_sha("A" * 40) == "a" * 40
    with pytest.raises(ValueError, match="40-character"):
        comfyui_ops.normalize_comfyui_commit_sha("abc123")


def test_verify_checkout_requires_matching_origin_and_commit(tmp_path: Path):
    checkout = tmp_path / "ComfyUI"
    checkout.mkdir()
    _git(checkout, "init", "--initial-branch=master")
    _git(checkout, "config", "user.email", "test@example.com")
    _git(checkout, "config", "user.name", "Test")
    (checkout / "main.py").write_text("# test\n", encoding="utf-8")
    _git(checkout, "add", "main.py")
    _git(checkout, "commit", "-m", "test")
    commit = _git(checkout, "rev-parse", "HEAD")
    _git(
        checkout,
        "remote",
        "add",
        "origin",
        "git@github.com:kijai/ComfyUI.git",
    )

    assert comfyui_ops.verify_comfyui_checkout(
        checkout,
        repository="https://github.com/kijai/ComfyUI.git",
        commit_sha=commit,
    ) == commit
    with pytest.raises(ValueError, match="origin mismatch"):
        comfyui_ops.verify_comfyui_checkout(
            checkout,
            repository="https://github.com/Comfy-Org/ComfyUI.git",
            commit_sha=commit,
        )
    with pytest.raises(ValueError, match="commit mismatch"):
        comfyui_ops.verify_comfyui_checkout(
            checkout,
            repository="https://github.com/kijai/ComfyUI.git",
            commit_sha="0" * 40,
        )


def test_clone_uses_declared_repository_ref_and_token(monkeypatch, tmp_path: Path):
    calls: list[dict[str, object]] = []

    def fake_clone(url, target_path, **kwargs):
        calls.append({"url": url, "target_path": target_path, **kwargs})
        target_path.mkdir()

    monkeypatch.setattr(comfyui_ops, "git_clone", fake_clone)
    monkeypatch.setattr(comfyui_ops, "get_comfyui_version", lambda _path: "test")
    target = tmp_path / "ComfyUI"

    assert comfyui_ops.clone_comfyui(
        target,
        "a" * 40,
        repository="https://github.com/kijai/ComfyUI.git",
        token="secret-token",
    ) == "test"
    assert calls == [{
        "url": "https://github.com/kijai/ComfyUI.git",
        "target_path": target,
        "depth": 1,
        "ref": "a" * 40,
        "timeout": 5 * 60,
        "token": "secret-token",
    }]
