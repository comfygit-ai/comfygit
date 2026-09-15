"""Operating-system-backed credential persistence."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

from ..models.credentials import CredentialProvider
from ..models.exceptions import CDCredentialStoreError

KEYRING_SERVICE = "comfygit"


def _load_keyring() -> ModuleType:
    """Load optional persistence only when used; core imports stay headless-safe."""
    try:
        return import_module("keyring")
    except ImportError as exc:
        raise CDCredentialStoreError(
            "Secure credential storage requires the optional keyring dependency. "
            "Install 'comfygit-core[keyring]' into this Python environment, "
            "or use a provider environment variable or existing provider login."
        ) from exc


class KeyringCredentialStore:
    """Store workspace credentials in the active operating-system keyring."""

    @staticmethod
    def _account(workspace_id: str, provider: CredentialProvider) -> str:
        return f"workspace:{workspace_id}:provider:{provider.value}"

    def get(self, workspace_id: str, provider: CredentialProvider) -> str | None:
        keyring = _load_keyring()
        try:
            return keyring.get_password(KEYRING_SERVICE, self._account(workspace_id, provider))
        except keyring.errors.KeyringError as exc:
            raise CDCredentialStoreError(
                f"Secure credential storage is unavailable for {provider.value}. "
                "Configure an operating-system keyring or use a provider environment variable."
            ) from exc

    def set(self, workspace_id: str, provider: CredentialProvider, value: str) -> None:
        keyring = _load_keyring()
        try:
            keyring.set_password(KEYRING_SERVICE, self._account(workspace_id, provider), value)
        except keyring.errors.KeyringError as exc:
            raise CDCredentialStoreError(
                f"Could not save the {provider.value} credential in secure storage. "
                "Configure an operating-system keyring or use a provider environment variable."
            ) from exc

    def delete(self, workspace_id: str, provider: CredentialProvider) -> None:
        keyring = _load_keyring()
        try:
            keyring.delete_password(KEYRING_SERVICE, self._account(workspace_id, provider))
        except keyring.errors.PasswordDeleteError:
            return
        except keyring.errors.KeyringError as exc:
            raise CDCredentialStoreError(
                f"Could not clear the {provider.value} credential from secure storage."
            ) from exc
