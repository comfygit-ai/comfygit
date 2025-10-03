"""Tests for GlobalNodeResolver utilities."""

import tempfile
from pathlib import Path
from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver


class TestGitHubUrlNormalization:
    """Test GitHub URL normalization functionality."""

    def test_https_url_no_changes_needed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "https://github.com/owner/repo"
            result = resolver._normalize_github_url(url)
            assert result == "https://github.com/owner/repo"

    def test_https_url_with_git_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "https://github.com/owner/repo.git"
            result = resolver._normalize_github_url(url)
            assert result == "https://github.com/owner/repo"

    def test_ssh_url_git_at_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "git@github.com:owner/repo.git"
            result = resolver._normalize_github_url(url)
            assert result == "https://github.com/owner/repo"

    def test_ssh_url_git_at_format_no_git_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "git@github.com:owner/repo"
            result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_ssh_url_full_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "ssh://git@github.com/owner/repo.git"
            result = resolver._normalize_github_url(url)
            assert result == "https://github.com/owner/repo"

    def test_ssh_url_full_format_no_git_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "ssh://git@github.com/owner/repo"
            result = resolver._normalize_github_url(url)
            assert result == "https://github.com/owner/repo"

    def test_www_github_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "https://www.github.com/owner/repo"
            result = resolver._normalize_github_url(url)
            assert result == "https://github.com/owner/repo"

    def test_complex_github_url_with_extra_path_parts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "https://github.com/owner/repo/tree/main"
            result = resolver._normalize_github_url(url)
            assert result == "https://github.com/owner/repo"

    def test_empty_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            result = resolver._normalize_github_url("")
            assert result == ""

    def test_none_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            result = resolver._normalize_github_url(None)
            assert result == ""

    def test_non_github_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "https://gitlab.com/owner/repo.git"
            result = resolver._normalize_github_url(url)
            # Non-GitHub URLs still get .git removed
            assert result == "https://gitlab.com/owner/repo"

    def test_invalid_github_url_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text("{}")
            resolver = GlobalNodeResolver(mappings_path=mappings_path)
            url = "https://github.com/owner"  # Missing repo
            result = resolver._normalize_github_url(url)
            # Should return original URL since it doesn't have enough path parts
            assert result == "https://github.com/owner"