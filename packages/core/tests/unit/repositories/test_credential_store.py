"""Operating-system keyring credential store tests."""

import pytest
from comfygit_core.models import CDCredentialStoreError, CredentialProvider
from comfygit_core.repositories.credential_store import (
    KEYRING_SERVICE,
    KeyringCredentialStore,
)

keyring = pytest.importorskip("keyring")
NoKeyringError = keyring.errors.NoKeyringError
PasswordDeleteError = keyring.errors.PasswordDeleteError


def test_keyring_store_scopes_credentials_by_workspace_and_provider(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "keyring.set_password",
        lambda service, account, value: captured.update(
            service=service,
            account=account,
            value=value,
        ),
    )

    KeyringCredentialStore().set("workspace-1", CredentialProvider.HUGGINGFACE, "secret")

    assert captured == {
        "service": KEYRING_SERVICE,
        "account": "workspace:workspace-1:provider:huggingface",
        "value": "secret",
    }


def test_keyring_backend_failure_is_structured(monkeypatch):
    def fail(*_args):
        raise NoKeyringError("no backend")

    monkeypatch.setattr(
        "keyring.get_password",
        fail,
    )

    with pytest.raises(CDCredentialStoreError, match="Secure credential storage is unavailable"):
        KeyringCredentialStore().get("workspace-1", CredentialProvider.CIVITAI)


def test_clearing_an_absent_keyring_entry_is_idempotent(monkeypatch):
    def missing(*_args):
        raise PasswordDeleteError("missing")

    monkeypatch.setattr(
        "keyring.delete_password",
        missing,
    )

    KeyringCredentialStore().delete("workspace-1", CredentialProvider.GITHUB)
