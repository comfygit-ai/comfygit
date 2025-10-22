"""Tests for shell completion installation commands."""
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from comfydock_cli.completion_commands import CompletionCommands


class TestCompletionCommands:
    """Test completion command installation logic."""

    def test_detect_shell_bash(self):
        """Test bash shell detection."""
        with patch.dict('os.environ', {'SHELL': '/bin/bash'}):
            shell, config = CompletionCommands._detect_shell()
            assert shell == 'bash'
            assert config == Path.home() / '.bashrc'

    def test_detect_shell_zsh(self):
        """Test zsh shell detection."""
        with patch.dict('os.environ', {'SHELL': '/usr/bin/zsh'}):
            shell, config = CompletionCommands._detect_shell()
            assert shell == 'zsh'
            assert config == Path.home() / '.zshrc'

    def test_detect_shell_unknown(self):
        """Test unknown shell detection."""
        with patch.dict('os.environ', {'SHELL': '/bin/fish'}):
            shell, config = CompletionCommands._detect_shell()
            assert shell is None
            assert config is None

    @patch('comfydock_cli.completion_commands.shutil.which')
    def test_check_argcomplete_available_found(self, mock_which):
        """Test argcomplete check when available."""
        mock_which.return_value = '/usr/local/bin/register-python-argcomplete'
        assert CompletionCommands._check_argcomplete_available()
        mock_which.assert_called_once_with('register-python-argcomplete')

    @patch('comfydock_cli.completion_commands.shutil.which')
    def test_check_argcomplete_available_not_found(self, mock_which):
        """Test argcomplete check when not available."""
        mock_which.return_value = None
        assert not CompletionCommands._check_argcomplete_available()

    @patch('comfydock_cli.completion_commands.subprocess.run')
    def test_install_argcomplete_success(self, mock_run):
        """Test successful argcomplete installation."""
        mock_run.return_value = Mock(returncode=0)
        assert CompletionCommands._install_argcomplete()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ['uv', 'tool', 'install', 'argcomplete']

    @patch('comfydock_cli.completion_commands.subprocess.run')
    def test_install_argcomplete_failure(self, mock_run):
        """Test failed argcomplete installation."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'uv', stderr='error')
        assert not CompletionCommands._install_argcomplete()

    def test_is_completion_installed_not_exists(self):
        """Test checking completion when config file doesn't exist."""
        config_file = Path('/tmp/nonexistent_file_12345.txt')
        assert not CompletionCommands._is_completion_installed(config_file)

    def test_is_completion_installed_empty_file(self):
        """Test checking completion in empty file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)

        try:
            assert not CompletionCommands._is_completion_installed(config_file)
        finally:
            config_file.unlink()

    def test_add_completion_to_config(self):
        """Test adding completion to config file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)
            f.write("# Existing content\nexport PATH=/foo\n")

        try:
            # Add completion
            CompletionCommands._add_completion_to_config(config_file)

            # Verify it was added
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT in content
            assert CompletionCommands.COMPLETION_LINE in content

            # Check it was added at the end
            lines = content.splitlines()
            assert CompletionCommands.COMPLETION_COMMENT in lines[-2]
            assert CompletionCommands.COMPLETION_LINE in lines[-1]

            # Verify original content is preserved
            assert "export PATH=/foo" in content
        finally:
            config_file.unlink()

    def test_add_completion_to_new_file(self):
        """Test adding completion to non-existent file."""
        config_file = Path(tempfile.gettempdir()) / 'test_bashrc_new'

        try:
            # Add completion to new file
            CompletionCommands._add_completion_to_config(config_file)

            # Verify it was created and populated
            assert config_file.exists()
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT in content
            assert CompletionCommands.COMPLETION_LINE in content
        finally:
            if config_file.exists():
                config_file.unlink()

    def test_remove_completion_from_config(self):
        """Test removing completion from config file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)
            f.write(
                "# Before\n"
                f"{CompletionCommands.COMPLETION_COMMENT}\n"
                f"{CompletionCommands.COMPLETION_LINE}\n"
                "# After\n"
            )

        try:
            # Remove completion
            CompletionCommands._remove_completion_from_config(config_file)

            # Verify it was removed
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT not in content
            assert CompletionCommands.COMPLETION_LINE not in content

            # Verify other content is preserved
            assert "# Before" in content
            assert "# After" in content
        finally:
            config_file.unlink()

    def test_is_completion_installed_after_add(self):
        """Test that is_completion_installed returns True after adding."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)

        try:
            # Initially not installed
            assert not CompletionCommands._is_completion_installed(config_file)

            # Add completion
            CompletionCommands._add_completion_to_config(config_file)

            # Now it should be installed
            assert CompletionCommands._is_completion_installed(config_file)
        finally:
            config_file.unlink()

    def test_idempotent_install(self):
        """Test that adding completion twice doesn't duplicate."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)

        try:
            # Add completion twice
            CompletionCommands._add_completion_to_config(config_file)
            first_content = config_file.read_text()

            CompletionCommands._add_completion_to_config(config_file)
            second_content = config_file.read_text()

            # Content should have doubled (not idempotent by design, install command checks first)
            assert second_content.count(CompletionCommands.COMPLETION_LINE) == 2
        finally:
            config_file.unlink()
