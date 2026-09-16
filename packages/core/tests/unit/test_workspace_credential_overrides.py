"""CGCORE-AUTH-04: caller-scoped credentials reach actual provider boundaries."""

from unittest.mock import Mock, patch

import pytest
from comfygit_core import Workspace
from comfygit_core.clients.civitai_client import CivitAIClient
from comfygit_core.clients.github_client import GitHubClient
from comfygit_core.models import CredentialProvider, CredentialSource, MemoryCredentialStore
from comfygit_core.services.model_downloader import DownloadRequest, ModelDownloader
from comfygit_core.services.model_source_lookup import ModelSourceLookupService


@pytest.mark.parametrize("method", ["create", "open", "from_path", "open_or_create"])
@pytest.mark.parametrize("value", [None, "application-token"])
def test_public_workspace_entries_propagate_overrides(tmp_path, monkeypatch, method, value):
    path = tmp_path / "workspace"
    if method in ("open", "from_path"):
        Workspace.create(path)
    monkeypatch.setenv("HF_TOKEN", "environment-token")
    overrides = {CredentialProvider.HUGGINGFACE: value}
    workspace = getattr(Workspace, method)(path, credential_overrides=overrides)
    overrides.clear()  # Caller mutation must not change this workspace's policy.
    assert workspace.get_huggingface_token() == value
    assert workspace.get_credential_status(CredentialProvider.HUGGINGFACE).source == (
        CredentialSource.ANONYMOUS if value is None else CredentialSource.EXPLICIT
    )
    assert "application-token" not in workspace.paths.workspace_file.read_text()
    # open_or_create's existing-workspace branch must propagate too.
    reopened = Workspace.open_or_create(path, credential_overrides={CredentialProvider.HUGGINGFACE: value})
    assert reopened.get_huggingface_token() == value


@pytest.mark.parametrize("value", [None, "application-token"])
@pytest.mark.parametrize("progress", [False, True, "unsupported"])
def test_hf_download_preserves_override_at_sdk_boundary(tmp_path, monkeypatch, value, progress):
    monkeypatch.setenv("HF_TOKEN", "environment-token")
    workspace = Workspace.create(
        tmp_path / "workspace", credential_overrides={CredentialProvider.HUGGINGFACE: value},
    )
    repo = Mock()
    repo.find_by_source_url.return_value = None
    repo.calculate_short_hash.return_value = "abc123"
    target = workspace.paths.models / "sample.safetensors"
    target.write_bytes(b"test model")
    downloader = ModelDownloader(repo, workspace.workspace_config_manager)
    request = DownloadRequest(
        url="https://huggingface.co/example/model/resolve/main/sample.safetensors", target_path=target,
    )
    with patch("comfygit_core.services.model_downloader.hf_hub_download") as download:
        if progress == "unsupported":
            download.side_effect = [TypeError("unsupported tqdm_class"), str(target)]
        else:
            download.return_value = str(target)
        result = downloader._download_huggingface(request, target, Mock() if progress else None)
    assert result.success, result.error
    for call in download.call_args_list:
        token = call.kwargs["token"]
        if value is None:
            assert token is False
        else:
            assert token == value


@pytest.mark.parametrize("value", [None, "application-token"])
def test_provider_clients_honor_workspace_overrides(tmp_path, monkeypatch, value):
    for name in ("CIVITAI_API_TOKEN", "HF_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "environment-token")
    workspace = Workspace.create(
        tmp_path / "workspace", credential_store=MemoryCredentialStore(),
        credential_overrides=dict.fromkeys(CredentialProvider, value),
    )
    config = workspace.workspace_config_manager
    lookup = ModelSourceLookupService(cache_dir=tmp_path / "cache", workspace_config=config)
    assert lookup.hf_api.token == (value if value is not None else False)
    assert lookup.civitai._api_key == value
    github = GitHubClient(token_provider=config.get_github_token)
    assert github._resolve_token() == value
    # A direct per-client credential remains the highest-priority override.
    client = CivitAIClient(cache_manager=Mock(), api_key="request-token", workspace_config=config)
    assert client._api_key == "request-token"
