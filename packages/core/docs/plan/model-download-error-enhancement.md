# Model Download Error Enhancement - Implementation Plan

## Overview

Enhance model download error handling to provide provider-specific, actionable error messages to users instead of generic HTTP errors.

## Problem Statement

Currently, model download failures return generic error strings like "Download failed: 401 Client Error". Users don't know:
- Which provider failed (CivitAI vs HuggingFace vs custom URL)
- Whether they need an API key
- Whether their API key is invalid
- What action to take to fix the issue

## Goals

1. Preserve HTTP status codes and provider context through error chain
2. Distinguish between "no API key" vs "invalid API key" scenarios
3. Provide provider-specific error messages
4. Enable CLI to show actionable guidance (e.g., "Run: comfydock config --civitai-key <key>")

## Architecture Changes

### Phase 1: Core - Structured Error Models

**File**: `packages/core/src/comfydock_core/models/exceptions.py`
**Lines**: Add after line 217 (after UVCommandError)

Add new exception types and error context:

```python
# ===================================================
# Model Download exceptions
# ===================================================

@dataclass
class DownloadErrorContext:
    """Detailed context about a download failure."""
    provider: str  # 'civitai', 'huggingface', 'custom'
    error_category: str  # 'auth_missing', 'auth_invalid', 'forbidden', 'not_found', 'network', 'server', 'unknown'
    http_status: int | None
    url: str
    has_configured_auth: bool  # Was auth configured (even if invalid)?
    raw_error: str  # Original error message for debugging

    def get_user_message(self) -> str:
        """Generate user-friendly error message."""
        if self.provider == "civitai":
            if self.error_category == "auth_missing":
                return (
                    f"CivitAI model requires authentication (HTTP {self.http_status}). "
                    "No API key found. Get your key from https://civitai.com/user/account "
                    "and add it with: comfydock config --civitai-key <your-key>"
                )
            elif self.error_category == "auth_invalid":
                return (
                    f"CivitAI authentication failed (HTTP {self.http_status}). "
                    "Your API key may be invalid or expired. "
                    "Update it with: comfydock config --civitai-key <your-key>"
                )
            elif self.error_category == "forbidden":
                return (
                    f"CivitAI access forbidden (HTTP {self.http_status}). "
                    "This model may require special permissions or may not be publicly available."
                )
            elif self.error_category == "not_found":
                return f"CivitAI model not found (HTTP {self.http_status}). The URL may be incorrect or the model was removed."

        elif self.provider == "huggingface":
            if self.error_category in ("auth_missing", "auth_invalid"):
                return (
                    f"HuggingFace model requires authentication (HTTP {self.http_status}). "
                    "Set the HF_TOKEN environment variable with your HuggingFace token. "
                    "Get your token from: https://huggingface.co/settings/tokens"
                )
            elif self.error_category == "not_found":
                return f"HuggingFace model not found (HTTP {self.http_status}). Check the URL is correct."

        # Generic provider or fallback
        if self.error_category == "network":
            return f"Network error downloading from {self.provider}: {self.raw_error}"
        elif self.error_category == "server":
            return f"Server error from {self.provider} (HTTP {self.http_status}). Try again later."
        elif self.http_status:
            return f"Download failed from {self.provider} (HTTP {self.http_status}): {self.raw_error}"
        else:
            return f"Download failed from {self.provider}: {self.raw_error}"


class CDModelDownloadError(ComfyDockError):
    """Model download error with provider-specific context."""

    def __init__(self, message: str, context: DownloadErrorContext | None = None):
        super().__init__(message)
        self.context = context

    def get_user_message(self) -> str:
        """Get user-friendly error message."""
        if self.context:
            return self.context.get_user_message()
        return str(self)
```

**Why**: This creates a structured way to capture error context and generate provider-specific messages.

---

### Phase 2: Core - Enhanced DownloadResult

**File**: `packages/core/src/comfydock_core/services/model_downloader.py`
**Lines**: 34-40 (DownloadResult dataclass)

Enhance DownloadResult to carry structured error info:

```python
@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    model: ModelWithLocation | None = None
    error: str | None = None
    error_context: DownloadErrorContext | None = None  # NEW: Structured error info
```

**Why**: Allows CLI to access structured error information instead of just a string.

---

### Phase 3: Core - Provider-Aware Error Classification

**File**: `packages/core/src/comfydock_core/services/model_downloader.py`
**Lines**: Add new helper method after line 159 (`_extract_filename`)

```python
def _check_provider_auth(self, provider: str) -> bool:
    """Check if authentication is configured for a provider.

    Args:
        provider: Provider type ('civitai', 'huggingface', 'custom')

    Returns:
        True if auth credentials are configured
    """
    if provider == "civitai":
        if not self.workspace_config:
            return False
        api_key = self.workspace_config.get_civitai_token()
        return api_key is not None and api_key.strip() != ""
    elif provider == "huggingface":
        # Check HF_TOKEN environment variable
        import os
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        return token is not None and token.strip() != ""
    else:
        return False

def _classify_download_error(
    self,
    error: Exception,
    url: str,
    provider: str,
    has_auth: bool
) -> DownloadErrorContext:
    """Classify download error and create structured context.

    Args:
        error: The exception that occurred
        url: Download URL
        provider: Provider type
        has_auth: Whether auth was configured

    Returns:
        DownloadErrorContext with classification
    """
    import requests
    from urllib.error import URLError
    from socket import timeout as SocketTimeout

    http_status = None
    error_category = "unknown"
    raw_error = str(error)

    # Classify based on exception type
    if isinstance(error, requests.HTTPError):
        http_status = error.response.status_code

        if http_status == 401:
            # Unauthorized - check if we have auth
            if not has_auth:
                error_category = "auth_missing"
            else:
                error_category = "auth_invalid"
        elif http_status == 403:
            # Forbidden - could be rate limit, permissions, or invalid token
            if not has_auth and provider in ("civitai", "huggingface"):
                error_category = "auth_missing"
            else:
                error_category = "forbidden"
        elif http_status == 404:
            error_category = "not_found"
        elif http_status >= 500:
            error_category = "server"
        else:
            error_category = "unknown"

    elif isinstance(error, (URLError, SocketTimeout, requests.Timeout, requests.ConnectionError)):
        error_category = "network"

    return DownloadErrorContext(
        provider=provider,
        error_category=error_category,
        http_status=http_status,
        url=url,
        has_configured_auth=has_auth,
        raw_error=raw_error
    )
```

**Why**: Centralized logic to classify errors based on HTTP status, provider, and auth configuration.

---

### Phase 4: Core - Update Download Method Error Handling

**File**: `packages/core/src/comfydock_core/services/model_downloader.py`
**Lines**: 185-298 (download method)

Replace the generic exception handler at lines 285-288:

**BEFORE**:
```python
except Exception as e:
    error_msg = f"Download failed: {str(e)}"
    logger.error(error_msg)
    return DownloadResult(success=False, error=error_msg)
```

**AFTER**:
```python
except requests.HTTPError as e:
    # HTTP errors with status codes - classify them
    provider = self.detect_url_type(request.url)
    has_auth = self._check_provider_auth(provider)
    error_context = self._classify_download_error(e, request.url, provider, has_auth)

    # Generate user-friendly message
    user_message = error_context.get_user_message()
    logger.error(f"Download failed: {user_message}")

    return DownloadResult(
        success=False,
        error=user_message,
        error_context=error_context
    )

except (requests.Timeout, requests.ConnectionError) as e:
    # Network errors
    provider = self.detect_url_type(request.url)
    error_context = self._classify_download_error(e, request.url, provider, False)
    user_message = error_context.get_user_message()
    logger.error(f"Download failed: {user_message}")

    return DownloadResult(
        success=False,
        error=user_message,
        error_context=error_context
    )

except Exception as e:
    # Unexpected errors - still provide some context
    provider = self.detect_url_type(request.url)
    has_auth = self._check_provider_auth(provider)
    error_context = self._classify_download_error(e, request.url, provider, has_auth)
    user_message = error_context.get_user_message()
    logger.error(f"Unexpected download error: {user_message}")

    return DownloadResult(
        success=False,
        error=user_message,
        error_context=error_context
    )
```

**Why**: Separate handling for HTTP errors vs network errors vs unexpected errors, with provider-aware classification.

---

### Phase 5: CLI - Enhanced Error Display

**File**: `packages/cli/comfydock_cli/utils/progress.py`
**Lines**: 55-59 (on_file_complete)

Enhance to show provider-specific help:

**BEFORE**:
```python
def on_file_complete(name: str, success: bool, error: str | None) -> None:
    if success:
        print("  ✓ Complete")
    else:
        print(f"  ✗ Failed: {error}")
```

**AFTER**:
```python
def on_file_complete(name: str, success: bool, error: str | None) -> None:
    if success:
        print("  ✓ Complete")
    else:
        print(f"  ✗ Failed: {error}")
        # Note: error string now contains provider-specific guidance from DownloadErrorContext
```

**Why**: The enhanced error messages from core will automatically flow through. No CLI changes needed unless we want to add additional formatting.

**Optional Enhancement** - If we want to detect CivitAI errors and show the helper:

```python
def on_file_complete(name: str, success: bool, error: str | None) -> None:
    if success:
        print("  ✓ Complete")
    else:
        print(f"  ✗ Failed: {error}")

        # Show additional help for common cases
        if error and "comfydock config --civitai-key" in error:
            # Error message already contains instructions, no need for extra help
            pass
```

---

### Phase 6: Update Batch Download Results

**File**: `packages/core/src/comfydock_core/core/environment.py`
**Lines**: 800-810 (batch download results)

The batch download at line 788 uses `download_result.error`, which will now contain the enhanced message. No changes needed, but verify the flow:

```python
# Line 788
download_result = self.model_downloader.download(request, progress_callback=progress_callback)

# Line 803 - callback gets the enhanced error message
if callbacks and callbacks.on_file_complete:
    callbacks.on_file_complete(filename, False, download_result.error)
```

**Why**: Verify that error messages propagate correctly through the callback chain.

---

## Testing Strategy

### Unit Tests

**File**: `packages/core/tests/unit/test_model_downloader_errors.py` (new file)

```python
"""Test provider-specific error handling in ModelDownloader."""

import pytest
from requests import HTTPError, Response
from comfydock_core.services.model_downloader import ModelDownloader
from comfydock_core.models.exceptions import DownloadErrorContext


class TestErrorClassification:
    """Test error classification logic."""

    def test_civitai_401_no_key(self, model_downloader):
        """Test CivitAI 401 with no API key configured."""
        # Mock HTTPError with 401
        response = Response()
        response.status_code = 401
        error = HTTPError(response=response)

        context = model_downloader._classify_download_error(
            error=error,
            url="https://civitai.com/api/download/models/12345",
            provider="civitai",
            has_auth=False
        )

        assert context.error_category == "auth_missing"
        assert context.http_status == 401
        assert "API key" in context.get_user_message()
        assert "comfydock config --civitai-key" in context.get_user_message()

    def test_civitai_401_with_key(self, model_downloader):
        """Test CivitAI 401 with API key configured (invalid key)."""
        response = Response()
        response.status_code = 401
        error = HTTPError(response=response)

        context = model_downloader._classify_download_error(
            error=error,
            url="https://civitai.com/api/download/models/12345",
            provider="civitai",
            has_auth=True
        )

        assert context.error_category == "auth_invalid"
        assert "invalid" in context.get_user_message().lower()

    def test_huggingface_403_no_token(self, model_downloader):
        """Test HuggingFace 403 with no token."""
        response = Response()
        response.status_code = 403
        error = HTTPError(response=response)

        context = model_downloader._classify_download_error(
            error=error,
            url="https://huggingface.co/model/file.safetensors",
            provider="huggingface",
            has_auth=False
        )

        assert context.error_category == "auth_missing"
        assert "HF_TOKEN" in context.get_user_message()

    def test_404_error(self, model_downloader):
        """Test 404 not found error."""
        response = Response()
        response.status_code = 404
        error = HTTPError(response=response)

        context = model_downloader._classify_download_error(
            error=error,
            url="https://civitai.com/api/download/models/99999",
            provider="civitai",
            has_auth=True
        )

        assert context.error_category == "not_found"
        assert "not found" in context.get_user_message().lower()

    def test_network_timeout(self, model_downloader):
        """Test network timeout error."""
        from requests import Timeout
        error = Timeout("Connection timeout")

        context = model_downloader._classify_download_error(
            error=error,
            url="https://example.com/model.safetensors",
            provider="custom",
            has_auth=False
        )

        assert context.error_category == "network"
        assert "network" in context.get_user_message().lower()


class TestProviderAuthCheck:
    """Test provider authentication detection."""

    def test_civitai_has_key(self, model_downloader_with_civitai_key):
        """Test CivitAI auth detection when key is configured."""
        assert model_downloader_with_civitai_key._check_provider_auth("civitai") is True

    def test_civitai_no_key(self, model_downloader):
        """Test CivitAI auth detection when no key."""
        assert model_downloader._check_provider_auth("civitai") is False

    def test_huggingface_has_token(self, monkeypatch, model_downloader):
        """Test HuggingFace auth detection when HF_TOKEN is set."""
        monkeypatch.setenv("HF_TOKEN", "hf_test_token")
        assert model_downloader._check_provider_auth("huggingface") is True

    def test_huggingface_no_token(self, model_downloader):
        """Test HuggingFace auth detection when no token."""
        assert model_downloader._check_provider_auth("huggingface") is False
```

### Integration Tests

**File**: `packages/core/tests/integration/test_model_download_errors.py` (new file)

Test actual download failures with mocked HTTP responses:

```python
"""Integration tests for model download error handling."""

import pytest
from unittest.mock import Mock, patch
from requests import HTTPError, Response
from comfydock_core.services.model_downloader import ModelDownloader, DownloadRequest
from pathlib import Path


@pytest.mark.integration
class TestDownloadErrorFlow:
    """Test complete error flow from download to result."""

    @patch('requests.get')
    def test_civitai_401_no_key_full_flow(self, mock_get, tmp_path, workspace_config):
        """Test full flow: CivitAI 401 with no key -> structured error."""
        # Setup: No CivitAI key in workspace config
        workspace_config.get_civitai_token.return_value = None

        # Mock 401 response
        response = Response()
        response.status_code = 401
        mock_get.return_value.raise_for_status.side_effect = HTTPError(response=response)

        # Execute download
        downloader = ModelDownloader(
            model_repository=Mock(),
            workspace_config=workspace_config,
            models_dir=tmp_path
        )

        request = DownloadRequest(
            url="https://civitai.com/api/download/models/12345",
            target_path=tmp_path / "model.safetensors"
        )

        result = downloader.download(request)

        # Assertions
        assert result.success is False
        assert result.error is not None
        assert "API key" in result.error
        assert "comfydock config --civitai-key" in result.error
        assert result.error_context is not None
        assert result.error_context.provider == "civitai"
        assert result.error_context.error_category == "auth_missing"
        assert result.error_context.http_status == 401
```

---

## Edge Cases to Handle

1. **Multiple redirects**: URL starts as civitai.com but redirects to S3
   - Solution: Detect provider from original URL, not final URL

2. **Empty/whitespace API keys**: User sets `--civitai-key "  "`
   - Solution: `_check_provider_auth` should strip and check for empty string

3. **Mixed provider downloads**: Batch download with multiple providers
   - Solution: Already handled - each download classifies independently

4. **Network errors vs HTTP errors**: Timeout vs 503
   - Solution: Separate exception handlers for `requests.Timeout` vs `HTTPError`

5. **CivitAI 403 could be rate limit OR invalid token**
   - Solution: Treat as "forbidden" with generic message since we can't distinguish

---

## File Reference Summary

### Files to Modify

1. **`packages/core/src/comfydock_core/models/exceptions.py`**
   - Add: `DownloadErrorContext` dataclass
   - Add: `CDModelDownloadError` exception
   - Lines: After line 217

2. **`packages/core/src/comfydock_core/services/model_downloader.py`**
   - Modify: `DownloadResult` dataclass (lines 34-40)
   - Add: `_check_provider_auth()` method (after line 159)
   - Add: `_classify_download_error()` method (after `_check_provider_auth`)
   - Modify: `download()` exception handling (lines 285-298)

3. **`packages/cli/comfydock_cli/utils/progress.py`** (optional)
   - Modify: `on_file_complete()` if adding extra formatting (lines 55-59)

### Files to Create

1. **`packages/core/tests/unit/test_model_downloader_errors.py`**
   - Unit tests for error classification

2. **`packages/core/tests/integration/test_model_download_errors.py`**
   - Integration tests for error flow

### Files to Review (no changes needed)

1. **`packages/core/src/comfydock_core/core/environment.py`** (lines 788-810)
   - Verify error propagation through batch downloads

2. **`packages/cli/comfydock_cli/utils/civitai_errors.py`**
   - Existing helper (currently unused) - keep for future enhancements

---

## Implementation Order

1. **Phase 1**: Add exception models to `models/exceptions.py`
2. **Phase 2**: Update `DownloadResult` in `model_downloader.py`
3. **Phase 3**: Add helper methods (`_check_provider_auth`, `_classify_download_error`)
4. **Phase 4**: Update `download()` method error handling
5. **Phase 5**: Write unit tests
6. **Phase 6**: Write integration tests
7. **Phase 7**: Manual testing with real CivitAI/HuggingFace URLs

---

## Success Criteria

- [ ] User sees "No CivitAI API key found. Add with: comfydock config --civitai-key <key>" for 401 without key
- [ ] User sees "CivitAI API key invalid" for 401 with key configured
- [ ] User sees "HuggingFace requires HF_TOKEN" for HF auth errors
- [ ] Network timeouts show clear "Network error" message
- [ ] 404 errors show "Model not found" message
- [ ] Unit tests cover all error categories
- [ ] Integration tests verify error flow from exception to CLI
- [ ] No regression in successful download flow

---

## Future Enhancements (Post-MVP)

1. **Retry logic for transient errors**: Auto-retry 500 errors and timeouts
2. **Rate limit detection**: Detect CivitAI rate limits (429 or 403 with specific headers)
3. **HuggingFace token support**: Store HF token in workspace config (not just env var)
4. **Error analytics**: Track common error types to improve messaging
5. **Offline mode detection**: Detect complete network failure vs service-specific errors

---

## Notes

- Keep changes isolated to error handling - don't refactor download logic
- Preserve backward compatibility - existing code should work without changes
- Error messages should be actionable - always tell user what to do next
- Log technical details but show user-friendly messages to CLI
- Consider that error messages may be shown in batch contexts (multiple downloads)
