# ComfyGit CLI - Codebase Map

## Overview
The CLI package provides command-line interface for ComfyGit, enabling environment and workspace management for ComfyUI. It handles user interactions through environment and global commands, with support for interactive node/model resolution, error handling, and structured logging.

## Core CLI (`comfygit_cli/`)

### Entry Points
- **__init__.py** - Package initialization exposing the main CLI entry point function for external imports
- **__main__.py** - Package entry point allowing CLI to run as `python -m comfygit_cli`
- **cli.py** - Main CLI parser and command router using argparse with argcomplete support; creates argument parser and dispatches to environment, global, or completion commands

### Command Handlers
- **env_commands.py** - Environment-specific commands including activate, status, node management, model operations, workflow handling, and Python dependency management
- **global_commands.py** - Workspace-level commands for init, import/export, model downloads, model search, and workspace operations
- **cli_utils.py** - Shared utilities for workspace detection, workspace validation, and CLI helper functions
- **completion_commands.py** - Shell completion setup and management supporting bash, zsh, and fish with detection and installation

### Resolution & Interaction
- **resolution_strategies.py** - Model resolution strategies for CLI interaction with interactive model resolution support
- **completers.py** - Custom argcomplete completers providing environment names, installed nodes, and workflow names for shell tab completion

## Logging (`comfygit_cli/logging/`)
Structured logging system with environment-specific handlers, compression, and rotation support.

- **logging_config.py** - Core logging setup with rotating file handlers, configurable levels, and format customization for console and file output
- **environment_logger.py** - Environment-specific logging with automatic handler management, context managers, and decorator support for tracking operations across environments
- **log_compressor.py** - Real-time log compression engine that reduces token count while preserving semantic content using timestamp deltas and module abbreviations
- **compressed_handler.py** - Dual rotating file handler that writes both full verbose logs and compressed versions simultaneously for debugging

## Strategies (`comfygit_cli/strategies/`)
Interactive and automatic resolution strategies for user-guided dependency handling.

- **interactive.py** - Interactive node and model resolution strategies with unified search UI, selection interfaces, and optional node handling
- **rollback.py** - Rollback confirmation logic with user prompts for destructive operations and automatic approval for --yes flag

## Formatters (`comfygit_cli/formatters/`)
Error and output formatting utilities.

- **error_formatter.py** - Converts core library errors to CLI-friendly command suggestions for user guidance and resolution recommendations

## Utilities (`comfygit_cli/utils/`)
General-purpose utilities for CLI operations.

- **progress.py** - Download progress callbacks and statistics display showing download speed, total size, and completion percentage
- **pagination.py** - Terminal pagination for displaying large lists with page navigation and user interaction
- **civitai_errors.py** - CivitAI authentication error messages and setup guidance for API key configuration

## Interactive (`comfygit_cli/interactive/`)
Placeholder module for future interactive components.

- **__init__.py** - Empty module initializer for potential future interactive utilities

## Tests (`tests/`)
Comprehensive test coverage for CLI components with fixtures for environment and workflow testing.

- **conftest.py** - Pytest fixtures and test configuration that re-exports core test fixtures for workspace and environment setup
- **test_error_formatter.py** - Tests for node action error formatting and conflict error conversion
- **test_interactive_optional_strategy.py** - Tests for interactive optional node resolution strategy behavior
- **test_status_displays_uninstalled_nodes.py** - Tests for status command displaying uninstalled package detection
- **test_status_uninstalled_reporting.py** - Tests for accurate uninstalled node reporting in environment status
- **test_status_real_bug_scenario.py** - Regression tests for real-world bug scenarios in status display
- **test_status_suggestions.py** - Tests for status command suggestions and recommendations
- **test_status_path_sync_display.py** - Tests for path synchronization status display in environment reporting
- **test_batch_node_add.py** - Tests for batch node add command handling and error aggregation
- **test_batch_node_remove.py** - Tests for batch node remove command functionality
- **test_py_commands.py** - Tests for Python dependency management (py add/remove/list) commands
- **test_completion_commands.py** - Tests for shell completion setup and installation
- **test_completers.py** - Tests for argcomplete completer functions and environment filtering
- **test_logging_structure.py** - Tests for logging configuration and handler structure

## Build and Registry Scripts (`scripts/`)
Utilities for building node registries and managing ComfyUI integrations (run during development/deployment).

### Registry Management
- **registry_client.py** - Async HTTP client for ComfyUI registry API interactions with concurrent request handling and pagination support
- **build_registry_cache.py** - Builds comprehensive registry cache with three-phase progressive enhancement and checkpoint recovery
- **build_global_mappings.py** - Constructs global node identifier mappings from cached registry data for node resolution

### Node Analysis
- **extract_builtin_nodes.py** - Extracts built-in ComfyUI nodes by parsing Python NODE_CLASS_MAPPINGS from source files
- **extract_node_modules.py** - Extracts python_module fields and creates module-to-nodes grouping from object_info data
- **augment_mappings.py** - Enhances node mappings with ComfyUI Manager extension data, creating synthetic packages for Manager-only extensions

### Utilities
- **registry.py** - Command-line interface for ComfyUI registry API with support for queries, searches, and REST operations
- **get_hash.py** - File hashing utility supporting BLAKE3, SHA256, and CRC32 algorithms with human-readable output
- **test_concurrent_api.py** - Tests concurrent API performance against ComfyUI registry with request timing and success tracking

## Configuration
- **pyproject.toml** - Package metadata, dependencies (comfygit-core, aiohttp, argcomplete), and CLI entry points (comfydock, cfd commands)

## Key Entry Points

### Command-Line Interface
- **comfygit / cfd** - Main CLI invocation points defined in pyproject.toml, routes to environment or global commands

### Handler Classes
- **EnvironmentCommands** - Primary handler for environment-scoped operations (nodes, models, workflows, Python packages)
- **GlobalCommands** - Primary handler for workspace-scoped operations (init, import/export, workspace management)
- **CompletionCommands** - Handler for shell completion setup and management

### CLI Architecture
- **cli.py main()** - Entry point that initializes logging, creates argument parser, registers completers, and dispatches commands
- **cli_utils.get_workspace_or_exit()** - Utility to get workspace with error handling and initialization

## Architecture Overview

### Structure
- **Library-first design**: Delegates to comfygit-core for all domain logic
- **Command routing**: CLI routes to appropriate handler based on command structure
- **Logging integration**: Environment-specific logging via decorator pattern across handlers
- **Completion support**: Full shell tab completion for commands, environments, nodes, and workflows

### Dependencies
- **comfygit_core**: Core domain logic and environment management
- **aiohttp**: Async HTTP for registry API interactions
- **argcomplete**: Shell completion support
- **Standard library**: argparse, logging, pathlib, subprocess

### Logging System
- Root logger configured with rotating file handlers
- Environment-specific logging with automatic handler attachment
- Real-time compression for reduced token usage in debug logs
- Separate handlers for full and compressed output

### Testing Strategy
- MVP-focused with main happy path tested
- Core fixtures re-exported from comfygit-core tests
- Regression tests for real bug scenarios
- Command handler tests with mocking for core library
