"""Tests for --torch-backend CLI flag support."""

import argparse
from unittest.mock import Mock, patch

import pytest

from comfygit_cli.cli import create_parser


class TestTorchBackendArguments:
    """Test that --torch-backend arguments are properly parsed."""

    def test_pull_command_accepts_torch_backend(self):
        """Pull command should accept --torch-backend flag."""
        parser = create_parser()
        args = parser.parse_args(["pull", "--torch-backend", "cu128"])

        assert hasattr(args, "torch_backend")
        assert args.torch_backend == "cu128"

    def test_pull_command_torch_backend_default_auto(self):
        """Pull command --torch-backend should default to 'auto'."""
        parser = create_parser()
        args = parser.parse_args(["pull"])

        assert hasattr(args, "torch_backend")
        assert args.torch_backend == "auto"

    def test_run_command_accepts_torch_backend(self):
        """Run command should accept --torch-backend flag."""
        parser = create_parser()
        args = parser.parse_args(["run", "--torch-backend", "cpu"])

        assert hasattr(args, "torch_backend")
        assert args.torch_backend == "cpu"

    def test_sync_command_exists(self):
        """Sync command should exist and accept --torch-backend."""
        parser = create_parser()
        args = parser.parse_args(["sync"])

        assert args.command == "sync"
        assert hasattr(args, "torch_backend")
        assert args.torch_backend == "auto"  # Default

    def test_sync_command_accepts_torch_backend(self):
        """Sync command should accept --torch-backend flag."""
        parser = create_parser()
        args = parser.parse_args(["sync", "--torch-backend", "rocm6.3"])

        assert args.torch_backend == "rocm6.3"


class TestConfigTorchBackendSubcommand:
    """Test cg config torch-backend subcommand."""

    def test_config_torch_backend_show(self):
        """Config torch-backend show should exist."""
        parser = create_parser()
        args = parser.parse_args(["config", "torch-backend", "show"])

        assert args.command == "config"
        assert args.config_command == "torch-backend"
        assert args.torch_command == "show"

    def test_config_torch_backend_set(self):
        """Config torch-backend set <backend> should exist."""
        parser = create_parser()
        args = parser.parse_args(["config", "torch-backend", "set", "cu128"])

        assert args.command == "config"
        assert args.config_command == "torch-backend"
        assert args.torch_command == "set"
        assert args.backend == "cu128"

    def test_config_torch_backend_detect(self):
        """Config torch-backend detect should exist."""
        parser = create_parser()
        args = parser.parse_args(["config", "torch-backend", "detect"])

        assert args.command == "config"
        assert args.config_command == "torch-backend"
        assert args.torch_command == "detect"
