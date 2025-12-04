"""Tests for CLI entry point and command routing.

TDD: These tests are written first and should FAIL until cli.py is implemented.
"""


import pytest
from comfygit_deploy.cli import create_parser, main


class TestCLIParser:
    """Tests for CLI argument parser."""

    def test_parser_has_runpod_subcommand(self) -> None:
        """Parser should have 'runpod' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["runpod", "config", "--show"])
        assert args.command == "runpod"
        assert args.runpod_command == "config"

    def test_parser_has_instances_subcommand(self) -> None:
        """Parser should have 'instances' subcommand."""
        parser = create_parser()
        args = parser.parse_args(["instances"])
        assert args.command == "instances"

    def test_parser_has_start_command(self) -> None:
        """Parser should have 'start' command."""
        parser = create_parser()
        args = parser.parse_args(["start", "inst_abc123"])
        assert args.command == "start"
        assert args.instance_id == "inst_abc123"

    def test_parser_has_stop_command(self) -> None:
        """Parser should have 'stop' command."""
        parser = create_parser()
        args = parser.parse_args(["stop", "inst_abc123"])
        assert args.command == "stop"
        assert args.instance_id == "inst_abc123"

    def test_parser_has_terminate_command(self) -> None:
        """Parser should have 'terminate' command."""
        parser = create_parser()
        args = parser.parse_args(["terminate", "inst_abc123"])
        assert args.command == "terminate"
        assert args.instance_id == "inst_abc123"

    def test_runpod_config_api_key(self) -> None:
        """Parser should accept --api-key for runpod config."""
        parser = create_parser()
        args = parser.parse_args(["runpod", "config", "--api-key", "rpa_test123"])
        assert args.api_key == "rpa_test123"

    def test_runpod_gpus_command(self) -> None:
        """Parser should have 'runpod gpus' command."""
        parser = create_parser()
        args = parser.parse_args(["runpod", "gpus"])
        assert args.command == "runpod"
        assert args.runpod_command == "gpus"

    def test_runpod_volumes_command(self) -> None:
        """Parser should have 'runpod volumes' command."""
        parser = create_parser()
        args = parser.parse_args(["runpod", "volumes"])
        assert args.command == "runpod"
        assert args.runpod_command == "volumes"

    def test_runpod_deploy_command(self) -> None:
        """Parser should have 'runpod deploy' command with required args."""
        parser = create_parser()
        args = parser.parse_args([
            "runpod", "deploy",
            "https://github.com/user/env.git",
            "--gpu", "RTX 4090",
        ])
        assert args.command == "runpod"
        assert args.runpod_command == "deploy"
        assert args.import_source == "https://github.com/user/env.git"
        assert args.gpu == "RTX 4090"


class TestCLIMain:
    """Tests for CLI main function."""

    def test_main_returns_zero_on_help(self) -> None:
        """main() with --help should exit 0."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_main_returns_zero_on_version(self) -> None:
        """main() with --version should exit 0."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
