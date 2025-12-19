# ComfyGit Core - Architecture Overview

ComfyGit Core is a **library-first Python package** providing environment management APIs for ComfyUI without UI coupling. All external interaction happens through callback protocols and strategy patterns.

## Layered Architecture

```
┌─────────────────────────────────────────┐
│  Public API Layer                       │
│  Workspace, Environment (core/)         │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Managers (managers/)                   │
│  Node, Workflow, Git, Model, PyProject  │
│  Orchestrate operations using services  │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Services & Analysis Layer              │
│  Analyzers, Resolvers, Services         │
│  Stateless business logic & parsing     │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Data Layer                             │
│  Repositories, Caching, Models          │
│  Persistence & type definitions         │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Integration Layer                      │
│  Clients (API), Factories, Utils        │
│  External tools & low-level operations  │
└─────────────────────────────────────────┘
```

## Core Modules

| Module | Purpose | Key Concepts |
|--------|---------|--------------|
| **core/** | Public API | Workspace (multi-env), Environment (single env) |
| **models/** | Type safety | Data classes, protocols, exceptions with context |
| **managers/** | Orchestration | Node, Workflow, Git, Model, PyProject operations |
| **analyzers/** | Analysis | Parse workflows/git/status; classify nodes |
| **resolvers/** | Resolution | Map workflow nodes to packages; resolve model sources |
| **services/** | Business logic | Lookup, registry, downloads, import analysis |
| **repositories/** | Persistence | SQLite caching, workflow cache, config storage |
| **clients/** | External APIs | CivitAI, GitHub, ComfyUI registry |
| **factories/** | DI | Create Workspace/Environment with dependencies |
| **utils/** | Low-level | Git, filesystem, parsing, version, download |
| **caching/** | Cache layer | API cache, custom node cache, workflow cache |
| **configs/** | Reference data | Builtin nodes, model categories |

## Architecture Patterns

**Library Design**
- No print/input - all UI through callback protocols (NodeResolutionStrategy, ConfirmationStrategy)
- Immutable managers - stateless for testability and composability
- Protocol-based plugins - strategies injected via constructor

**Data Flow**
- Environment → Managers → Services/Analyzers → Repositories → External APIs
- Caching at repository layer reduces API calls (TTL expiration)
- Error context carried through exceptions for precise handling

**Extensibility**
- `NodeResolutionStrategy` / `ModelResolutionStrategy` for custom resolution behavior
- `ConfirmationStrategy` / `RollbackStrategy` for interactive decisions
- Callback protocols (`SyncCallbacks`, `ExportCallbacks`) for operation progress tracking

## Key Entry Points

**Workspace Operations:**
- `Workspace.create()` - Create new workspace with validation
- `Workspace.environments()` / `get_environment()` - List/get environments
- `WorkspaceFactory.find()` - Discover existing workspace from environment variables

**Environment Operations:**
- `Environment.add_node()` / `remove_node()` - Install/uninstall custom nodes
- `Environment.add_model()` - Download and install models
- `Environment.sync_workflow()` - Install dependencies for workflow
- `Environment.export()` - Bundle for portability

**Resolution:**
- `GlobalNodeResolver.resolve_workflow_nodes()` - Map unknown nodes to packages
- `ModelResolver.resolve_reference()` - Find model download source

## Dependencies

**External:** aiohttp, requests, uv, pyyaml, tomlkit, blake3, packaging, psutil, requirements-parser
**Internal:** Protocol-based callbacks, type hints for IDE support (py.typed)

## Testing Strategy

Integration tests cover real-world flows (workflow caching, model resolution, git operations, rollback). MVP-focused with 2-3 tests per module covering happy paths.
