"""Download and archive extraction utilities."""

import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from ..logging.logging_config import get_logger

logger = get_logger(__name__)


def download_and_extract_archive(url: str, target_path: Path) -> None:
    """Download and extract an archive file with automatic format detection.
    
    Args:
        url: URL of the archive to download
        target_path: Directory to extract contents to
        
    Raises:
        OSError: If download fails
        ValueError: If archive format is unsupported or corrupted
    """
    temp_file_path = None
    try:
        # Download file first
        temp_file_path = download_file(url)
        # Extract with format detection
        extract_archive(temp_file_path, target_path)

    except (OSError, ValueError):
        # Re-raise download and extraction errors as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error during download/extract: {e}")
        raise OSError(f"Unexpected error during download/extract: {e}")
    finally:
        # Always clean up temp file
        if temp_file_path and temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except OSError:
                # Log but don't fail if cleanup fails
                logger.warning(f"Failed to clean up temp file: {temp_file_path}")


def download_file(url: str, suffix: str | None = None, timeout: int = 60) -> Path:
    """Download a file to a temporary location.

    Args:
        url: URL to download from
        suffix: Optional file suffix for the temp file
        timeout: Request timeout in seconds (default 60)

    Returns:
        Path to downloaded file

    Raises:
        OSError: If download fails
        urllib.error.URLError: If connection times out
    """
    try:
        if not suffix:
            suffix = Path(url).suffix

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            logger.info(f"Downloading from {url}")

            # Create request with User-Agent header (some servers reject requests without it)
            request = urllib.request.Request(
                url,
                headers={'User-Agent': 'ComfyGit/1.0 (https://github.com/comfygit-ai)'}
            )

            with urllib.request.urlopen(request, timeout=timeout) as response:
                # Read in chunks for large files
                chunk_size = 8192
                total_size = 0

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    tmp_file.write(chunk)
                    total_size += len(chunk)

            tmp_path = Path(tmp_file.name)
            logger.debug(f"Downloaded {total_size / 1024:.1f} KB to {tmp_path}")
            return tmp_path

    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise OSError(f"Download failed: {e}")


def extract_archive(archive_path: Path, target_path: Path) -> None:
    """Extract an archive with automatic format detection.
    
    Tries multiple archive formats until one succeeds:
    - ZIP
    - TAR.GZ (gzipped tar)
    - TAR (plain tar)
    - TAR.BZ2 (bzip2 tar)
    
    Args:
        archive_path: Path to archive file
        target_path: Directory to extract to
        
    Raises:
        ValueError: If file is not a supported archive format
        OSError: If file system operation fails (permissions, disk space, etc.)
    """
    # Ensure target directory exists
    target_path.mkdir(parents=True, exist_ok=True)

    # Try different extraction methods
    extractors = [
        (_try_extract_zip, "zip"),
        (_try_extract_tar_gz, "tar.gz"),
        (_try_extract_tar, "tar"),
        (_try_extract_tar_bz2, "tar.bz2"),
    ]

    extraction_errors = []

    for extractor, format_name in extractors:
        try:
            extractor(archive_path, target_path)
            logger.info(f"Successfully extracted as {format_name} format")
            return
        except (zipfile.BadZipFile, tarfile.ReadError):
            # Expected errors for wrong format, continue trying
            continue
        except Exception as e:
            # Unexpected errors, collect for reporting
            extraction_errors.append(f"{format_name}: {e}")

    # If nothing worked, log diagnostic info and raise exception
    _log_extraction_failure(archive_path)
    if extraction_errors:
        # Had OS-level errors during extraction attempts
        error_details = "; ".join(extraction_errors)
        raise OSError(f"Archive extraction failed due to system errors: {error_details}")
    else:
        # No format worked, likely unsupported/corrupted file
        raise ValueError(f"Unsupported or corrupted archive format: {archive_path}")


def _is_path_safe(member_path: str, target_path: Path) -> bool:
    """Check if an archive member path is safe (doesn't escape target directory).

    Prevents Zip Slip / Path Traversal attacks (CVE-2007-4559).

    Args:
        member_path: Path from archive member (filename)
        target_path: Target extraction directory

    Returns:
        True if path is safe to extract, False if it would escape target directory
    """
    # Resolve the full path that would be created
    # Use os.path.join first to handle absolute paths in member_path
    import os
    full_path = os.path.normpath(os.path.join(target_path, member_path))

    # Check if the resolved path is still within target_path
    target_resolved = os.path.normpath(target_path)
    return full_path.startswith(target_resolved + os.sep) or full_path == target_resolved


def _try_extract_archive(archive_path: Path, target_path: Path, format_info: tuple[str, str]) -> None:
    """Generic archive extraction helper.

    Args:
        archive_path: Path to archive file
        target_path: Directory to extract to
        format_info: Tuple of (format_type, format_name) where:
                    - format_type: 'zip' or tar mode like 'r:', 'r:gz', 'r:bz2'
                    - format_name: Display name like 'ZIP', 'TAR.GZ'

    Raises:
        zipfile.BadZipFile/tarfile.ReadError: If not a valid archive of this type
        OSError: If extraction fails
        ValueError: If archive contains unsafe paths (path traversal attempt)
    """
    format_type, format_name = format_info

    try:
        if format_type == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                # Validate all paths before extracting (prevent Zip Slip)
                for member in zip_ref.namelist():
                    if not _is_path_safe(member, target_path):
                        raise ValueError(
                            f"Unsafe path in archive (possible path traversal attack): {member}"
                        )
                zip_ref.extractall(target_path)
        else:
            # It's a tar format with the given mode
            with tarfile.open(archive_path, format_type) as tar:
                # Validate all paths before extracting (prevent path traversal)
                for member in tar.getmembers():
                    if not _is_path_safe(member.name, target_path):
                        raise ValueError(
                            f"Unsafe path in archive (possible path traversal attack): {member.name}"
                        )
                tar.extractall(target_path)
    except (zipfile.BadZipFile, tarfile.ReadError):
        # Expected errors for wrong format, let them propagate
        raise
    except ValueError:
        # Path traversal detected, propagate as-is
        raise
    except Exception as e:
        raise OSError(f"{format_name} extraction failed: {e}")


def _try_extract_zip(archive_path: Path, target_path: Path) -> None:
    """Try to extract as ZIP archive."""
    _try_extract_archive(archive_path, target_path, ('zip', 'ZIP'))


def _try_extract_tar_gz(archive_path: Path, target_path: Path) -> None:
    """Try to extract as gzipped TAR archive."""
    _try_extract_archive(archive_path, target_path, ('r:gz', 'TAR.GZ'))


def _try_extract_tar(archive_path: Path, target_path: Path) -> None:
    """Try to extract as plain TAR archive."""
    _try_extract_archive(archive_path, target_path, ('r:', 'TAR'))


def _try_extract_tar_bz2(archive_path: Path, target_path: Path) -> None:
    """Try to extract as bzip2 TAR archive."""
    _try_extract_archive(archive_path, target_path, ('r:bz2', 'TAR.BZ2'))


def _log_extraction_failure(archive_path: Path) -> None:
    """Log diagnostic information when extraction fails."""
    logger.error(f"Unable to extract archive: {archive_path}")

    # Read first few bytes for debugging
    try:
        with open(archive_path, 'rb') as f:
            header = f.read(32)
            logger.debug(f"File header (first 32 bytes): {header}")
    except Exception:
        pass
