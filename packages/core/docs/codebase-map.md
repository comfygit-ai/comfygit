# ComfyGit Core Package - Codebase Map

Comprehensive reference for the comfygit-core library (located at `/packages/core/src/comfygit_core/`). This is a library with no CLI coupling—all external communication happens through callback protocols and strategy patterns.

## Core API Layer

### Top-Level Components (`core/`)
The main public APIs for the library:

- **workspace.py** - Multi-environment workspace manager coordinating all environments, validating workspace structure, handling environment creation/removal, and delegating to Environment instances for operation execution
- **environment.py** - Single ComfyUI environment abstraction owning nodes, models, workflows, and Python dependencies with public methods for add/remove/update operations

## Domain Models (`models/`)

Type-safe data structures and contracts defining the architecture:

### Core Entities
- **environment.py** - EnvironmentStatus, EnvironmentState, NodeState, PackageSyncStatus, EnvironmentComparison, GitStatus data classes representing environment state snapshots
- **workflow.py** - Workflow, WorkflowNode, WorkflowNodeWidgetRef, WorkflowDependencies, DetailedWorkflowStatus, ResolutionResult structures for workflow analysis and resolution
- **shared.py** - Shared data models (NodeInfo, NodePackage, ModelWithLocation, ModelDetails, ModelSourceResult) used across multiple modules
- **sync.py** - SyncResult, SyncStatus data classes for environment synchronization operation results
- **manifest.py** - Environment manifest structures for serialization and persistent storage

### Integration Models
- **exceptions.py** - Custom exception hierarchy (ComfyDockError, CDEnvironmentError, CDNodeConflictError, DependencyConflictError) with context data classes (NodeAction, NodeConflictContext, DependencyConflictContext)
- **civitai.py** - CivitAI API response models, file metadata, and search result structures
- **commit.py** - Git commit tracking with hash and date information
- **registry.py** - ComfyUI node registry structures and package metadata
- **node_mapping.py** - Node identifier to package mapping data structures
- **system.py** - System information models (GPU capabilities, Python version, platform detection)

### Extension Points
- **protocols.py** - Type protocols for pluggable behavior (NodeResolutionStrategy, ModelResolutionStrategy, ConfirmationStrategy, RollbackStrategy, and callback protocols for sync/import/export operations)
- **workspace_config.py** - Workspace configuration schema with validation for paths and settings

## Management Layer

### Managers (`managers/`)
High-level orchestrators for operations on environments:

- **node_manager.py** - Install/update/remove custom nodes with conflict detection, resolution testing, and strategy-based confirmation
- **workflow_manager.py** - Load workflows, extract dependencies, resolve unknown nodes/models, track workflow changes across environments
- **git_manager.py** - High-level git operations (init, commit, checkout, status, diff parsing) wrapping git utilities with environment tracking
- **model_download_manager.py** - Coordinate model downloads from multiple sources, track download intents, manage interruption and resumption
- **model_symlink_manager.py** - Create/maintain symlinks from global model cache to environment-specific directories for efficient storage
- **pyproject_manager.py** - Read/write pyproject.toml files, manage node and model dependencies, parse Python package specifications
- **uv_project_manager.py** - Execute uv commands for Python environment management, dependency resolution, and lock file updates
- **export_import_manager.py** - Bundle environments for portability (export) and restore from bundles (import) with callbacks for progress tracking
- **workflow_manager.py** - All workflow operations including loading, parsing, dependency extraction, node/model resolution, and change tracking

### Services (`services/`)
Stateless, reusable business logic modules:

- **node_lookup_service.py** - Find nodes across registries, GitHub, and local caches; analyze node requirements; manage API/custom node caches
- **registry_data_manager.py** - Load, cache, and manage official ComfyUI node registry data with progressive enhancement
- **model_downloader.py** - Coordinate downloads from CivitAI, HuggingFace, and direct URLs; track download intents; handle queuing and resumption
- **import_analyzer.py** - Analyze and preview environment imports before applying changes; detect conflicts and missing packages

## Resolution & Analysis

### Analyzers (`analyzers/`)
Parse and extract information from workflows and environments:

- **workflow_dependency_parser.py** - Extract node and model dependencies from workflow JSON; classify node usage by category
- **custom_node_scanner.py** - Scan custom node directories for metadata, input schemas, and requirements files
- **model_scanner.py** - Scan models directory for available models, categorize by type, detect model locations
- **node_classifier.py** - Classify nodes as builtin vs custom; categorize builtin subtypes for resolution scoring
- **git_change_parser.py** - Parse git diffs to detect node additions/removals in repositories
- **node_git_analyzer.py** - Extract git repository info (URL, branch, commit) from node repository metadata
- **status_scanner.py** - Analyze environment state (package sync, missing dependencies, node availability, git status)

### Resolvers (`resolvers/`)
Determine what packages to install and where to get models:

- **global_node_resolver.py** - Map unknown workflow nodes to known packages using prebuilt mappings, handle GitHub URL resolution
- **model_resolver.py** - Resolve model references to download sources and file paths based on model name and type

### Repositories (`repositories/`)
Data access and persistence layer for caching and configuration:

- **node_mappings_repository.py** - Access prebuilt node-to-package mappings database; resolve GitHub URLs to packages; provide global node mappings
- **workflow_repository.py** - Load and cache workflow files with context-aware hashing for change detection
- **workspace_config_repository.py** - Persist and load workspace configuration from disk with validation
- **model_repository.py** - Index, query, and manage models across environments with SQLite backend
- **migrate_paths.py** - One-time migration utility for normalizing path separators in databases

## External Integration

### API Clients (`clients/`)
External service integration:

- **civitai_client.py** - Search and query CivitAI for models, metadata, and file information with pagination support
- **github_client.py** - Query GitHub API for custom node repository info, releases, and commit history
- **registry_client.py** - Fetch official ComfyUI node registry with async support and caching

### Factories (`factories/`)
Object construction and dependency injection:

- **workspace_factory.py** - Create and discover Workspace instances with fully initialized dependencies; handle path resolution from environment variables
- **environment_factory.py** - Create Environment instances for existing ComfyUI installations with all managers configured
- **uv_factory.py** - Create uv command executors with proper environment setup and Python interpreter configuration

## Utilities & Infrastructure

### Core Utilities (`utils/`)
General-purpose helper functions:

- **git.py** - Low-level git operations (clone, checkout, commit, status, diff), URL parsing, and validation
- **requirements.py** - Parse requirements.txt and pyproject.toml for dependencies with version constraint support
- **dependency_parser.py** - Parse Python dependency version constraints and resolve complex specifications
- **conflict_parser.py** - Detect and analyze dependency conflicts from error messages
- **version.py** - Version comparison, parsing, and compatibility checking with semantic versioning
- **input_signature.py** - Parse node input signatures for matching and compatibility validation
- **download.py** - File downloading with retry logic, progress callbacks, and resumption support
- **filesystem.py** - Cross-platform file and directory operations with permission handling
- **system_detector.py** - Detect OS, Python version, CUDA/GPU availability, and system capabilities
- **uv_error_handler.py** - Parse and handle uv command errors with helpful error messages
- **comfyui_ops.py** - ComfyUI-specific path operations and directory management
- **common.py** - General utilities (subprocess execution with timeout, logging helpers, JSON utilities)
- **model_categories.py** - ComfyUI model category mappings and classifications for model organization
- **retry.py** - Retry decorators and exponential backoff strategies for resilience
- **pytorch.py** - PyTorch-specific utilities for backend detection and pip index URL generation
- **environment_cleanup.py** - Cross-platform directory cleanup for damaged/incomplete environments
- **workflow_hash.py** - Hash workflows for caching and change detection
- **uuid.py** - UUID generation utilities for unique identifiers
- **constants.py** - Global constants for PyTorch packages, index URLs, and configuration values

### Caching (`caching/`)
Persistent and in-memory caching layer:

- **base.py** - Base classes for caching infrastructure with TTL expiration and validation hooks
- **api_cache.py** - Generic API response caching with time-to-live expiration for external API calls
- **custom_node_cache.py** - Specialized cache for custom node metadata, input schemas, and requirements
- **workflow_cache.py** - Persistent SQLite cache for workflow analysis and resolution results
- **comfyui_cache.py** - Cache for ComfyUI installations by version to avoid re-downloading large distributions

### Configuration (`configs/`)
Static configuration and reference data:

- **comfyui_builtin_nodes.py** - Registry of ComfyUI builtin node classes and identifier mappings
- **comfyui_models.py** - Model information, directory paths, and category definitions for all model types
- **model_config.py** - Model configuration schemas and loading strategies

### Infrastructure (`infrastructure/`)
External system interfaces and persistence:

- **sqlite_manager.py** - SQLite database operations, schema management, migrations, and query helpers

### Strategies (`strategies/`)
Pluggable behavior patterns for customizable operation handling:

- **confirmation.py** - Node/model conflict resolution strategies (auto-confirm, manual approval) implementing ConfirmationStrategy protocol
- **auto.py** - Automatic resolution strategies for non-interactive operations with intelligent fallbacks

### Validation (`validation/`)
Testing and verification utilities:

- **resolution_tester.py** - Test that resolved dependencies are valid and compatible with environment constraints

### Integrations (`integrations/`)
External tool integration:

- **uv_command.py** - Execute uv commands with proper environment setup, error handling, and output parsing

### Logging (`logging/`)
Structured logging infrastructure:

- **logging_config.py** - Configure logging with rotating file handlers, configurable levels, and formatting for debugging

## Architecture & Design

### Layering Strategy
1. **Core API** (Workspace, Environment) - Public interface
2. **Managers** - Orchestrate operations using services/analyzers
3. **Services** - Stateless business logic, can be reused across managers
4. **Analyzers** - Parse and extract information (stateless)
5. **Resolvers** - Determine what to install/download (stateless)
6. **Repositories** - Data access and persistence (with caching)
7. **Clients** - External service communication
8. **Factories** - Object construction
9. **Utilities** - Low-level helpers (git, filesystem, parsing)

### Key Patterns
- **Library-first**: No print statements or input() calls; all user interaction through callback protocols
- **Stateless Services**: Managers and services are immutable for testability and composability
- **Pluggable Strategies**: Confirmation and resolution behavior customizable via protocol implementations
- **Persistent Caching**: SQLite-backed caching reduces API calls; API responses cached with TTL
- **Error Context**: Exceptions carry structured context (NodeConflictContext, DependencyConflictContext) for precise error handling
- **Callback Protocols**: Import/export/sync operations use TYPE_CHECKING protocols for flexible caller integration

## Key Entry Points

**Public API Methods:**
- `Workspace.create()` - Create a new workspace with validation
- `Workspace.environments()` - List all environments
- `Workspace.get_environment()` - Get specific environment
- `Environment.add_node()` - Install custom node
- `Environment.remove_node()` - Remove custom node
- `Environment.add_model()` - Download and install model
- `Environment.sync_workflow()` - Install dependencies for workflow
- `Environment.export()` - Bundle environment for portability
- `WorkspaceFactory.find()` - Locate and load existing workspace
- `GlobalNodeResolver.resolve_workflow_nodes()` - Identify packages needed for workflow
- `ModelResolver.resolve_reference()` - Find download source for model

## Dependencies
- **aiohttp** - Async HTTP for API calls
- **requests** - Synchronous HTTP (CivitAI, GitHub)
- **uv** - Python environment management
- **pyyaml** - Configuration files
- **tomlkit** - pyproject.toml manipulation
- **blake3** - File hashing
- **requirements-parser** - Parse requirements.txt
- **packaging** - Version handling
- **psutil** - System monitoring

## Testing
Tests are located in `tests/` with integration tests covering real-world scenarios like workflow caching, model resolution, git operations, and environment rollback. MVP-focused testing covers main happy paths (2-3 tests per module).
