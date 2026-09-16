"""Provider credential resolution and loss-safe legacy migration."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..models.credentials import (
    CredentialMigrationResult,
    CredentialProvider,
    CredentialSource,
    CredentialStatus,
    CredentialStore,
)
from ..models.exceptions import CDCredentialStoreError

if TYPE_CHECKING:
    from ..repositories.workspace_config_repository import WorkspaceConfigRepository

logger = get_logger(__name__)

_PROVIDER_ENVIRONMENT_VARIABLES = {
    CredentialProvider.CIVITAI: ("CIVITAI_API_TOKEN", "CIVITAI_API_KEY"),
    CredentialProvider.HUGGINGFACE: ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
    CredentialProvider.GITHUB: ("GITHUB_TOKEN", "GH_TOKEN"),
}


def get_huggingface_native_token() -> str | None:
    """Return the active token managed by ``hf auth login``, when available."""
    try:
        from huggingface_hub import get_token
    except ImportError:
        return None
    return get_token()


class CredentialService:
    """Resolve provider credentials without exposing persistence details to callers."""

    def __init__(
        self,
        config_repository: WorkspaceConfigRepository,
        credential_store: CredentialStore,
        native_resolvers: dict[CredentialProvider, Callable[[], str | None]] | None = None,
        credential_overrides: Mapping[CredentialProvider, str | None] | None = None,
    ):
        self.config_repository = config_repository
        self.credential_store = credential_store
        self.native_resolvers = native_resolvers or {}
        self._overrides = dict(credential_overrides or {})
        if any(
            value is not None and (not isinstance(value, str) or not value.strip())
            for value in self._overrides.values()
        ):
            raise ValueError("Credential overrides must be nonempty tokens or None for anonymous access")

    def resolve(self, provider: CredentialProvider) -> str | None:
        if provider in self._overrides:
            return self._overrides[provider]
        if value := self._environment_value(provider):
            return value

        self.migrate_legacy_credentials(provider)
        workspace_id = self.config_repository.ensure_workspace_id()
        try:
            if value := self.credential_store.get(workspace_id, provider):
                return value
        except CDCredentialStoreError:
            # An unavailable desktop store must not block native/headless credentials.
            pass

        if value := self._native_value(provider):
            return value
        return self.config_repository.get_legacy_credential(provider)

    def set(self, provider: CredentialProvider, value: str) -> None:
        workspace_id = self.config_repository.ensure_workspace_id()
        self.credential_store.set(workspace_id, provider, value)
        stored = self.credential_store.get(workspace_id, provider)
        if stored is None or not secrets.compare_digest(value, stored):
            raise CDCredentialStoreError(
                f"Secure storage did not verify the saved {provider.value} credential."
            )
        self.config_repository.clear_legacy_credentials((provider,))

    def clear(self, provider: CredentialProvider) -> None:
        workspace_id = self.config_repository.ensure_workspace_id()
        store_error: CDCredentialStoreError | None = None
        try:
            self.credential_store.delete(workspace_id, provider)
        except CDCredentialStoreError as exc:
            store_error = exc
        self.config_repository.clear_legacy_credentials((provider,))
        if store_error is not None:
            raise store_error

    def is_anonymous(self, provider: CredentialProvider) -> bool:
        return provider in self._overrides and self._overrides[provider] is None

    def status(self, provider: CredentialProvider) -> CredentialStatus:
        if provider in self._overrides:
            configured = self._overrides[provider] is not None
            return CredentialStatus(
                provider, configured,
                CredentialSource.EXPLICIT if configured else CredentialSource.ANONYMOUS,
            )
        if self._environment_value(provider):
            return CredentialStatus(provider, True, CredentialSource.ENVIRONMENT)

        migration = self.migrate_legacy_credentials(provider)
        workspace_id = self.config_repository.ensure_workspace_id()
        storage_error = None
        try:
            if self.credential_store.get(workspace_id, provider):
                return CredentialStatus(provider, True, CredentialSource.SECURE_STORE)
        except CDCredentialStoreError as exc:
            storage_error = str(exc)

        if self._native_value(provider):
            source = CredentialSource.PROVIDER_NATIVE
        elif self.config_repository.get_legacy_credential(provider):
            source = CredentialSource.LEGACY_PLAINTEXT
        else:
            source = CredentialSource.UNAVAILABLE if storage_error else CredentialSource.NONE
        return CredentialStatus(
            provider=provider,
            configured=source in (CredentialSource.PROVIDER_NATIVE, CredentialSource.LEGACY_PLAINTEXT),
            source=source,
            storage_available=storage_error is None,
            migration_required=provider in migration.retained,
            message=storage_error or self._migration_error(provider, migration),
        )

    def migrate_legacy_credentials(
        self, provider: CredentialProvider | None = None,
    ) -> CredentialMigrationResult:
        """Migrate the requested provider, or all providers for an explicit migration."""
        legacy = {
            key: value for key, value in self.config_repository.get_legacy_credentials().items()
            if provider is None or key == provider
        }
        if not legacy:
            return CredentialMigrationResult()

        workspace_id = self.config_repository.ensure_workspace_id()
        stored: list[CredentialProvider] = []
        retained: list[CredentialProvider] = []
        errors: list[str] = []

        for provider, value in legacy.items():
            try:
                self.credential_store.set(workspace_id, provider, value)
                verified = self.credential_store.get(workspace_id, provider)
                if verified is None or not secrets.compare_digest(value, verified):
                    raise CDCredentialStoreError("secure storage read-back verification failed")
                stored.append(provider)
            except CDCredentialStoreError as exc:
                retained.append(provider)
                errors.append(f"{provider.value}: {exc}")

        if stored:
            try:
                self.config_repository.clear_legacy_credentials(tuple(stored))
            except Exception as exc:
                retained.extend(stored)
                errors.append(f"workspace metadata: {exc}")
                stored = []

        return CredentialMigrationResult(
            migrated=tuple(stored),
            retained=tuple(dict.fromkeys(retained)),
            errors=tuple(errors),
        )

    @staticmethod
    def _environment_value(provider: CredentialProvider) -> str | None:
        for name in _PROVIDER_ENVIRONMENT_VARIABLES[provider]:
            if value := os.environ.get(name):
                return value
        return None

    def _native_value(self, provider: CredentialProvider) -> str | None:
        resolver = self.native_resolvers.get(provider)
        if resolver is None:
            return None
        try:
            return resolver()
        except Exception as exc:
            logger.debug("Native %s credential resolution failed: %s", provider.value, exc)
            return None

    @staticmethod
    def _migration_error(
        provider: CredentialProvider,
        result: CredentialMigrationResult,
    ) -> str | None:
        prefix = f"{provider.value}:"
        return next((error for error in result.errors if error.startswith(prefix)), None)
