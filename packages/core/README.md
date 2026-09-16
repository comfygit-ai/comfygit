# ComfyGit Core

`comfygit-core` is the UI-independent library behind ComfyGit's CLI and runtime
adapters. It owns workspace discovery, environment manifests, custom nodes,
model metadata, dependency resolution, sync, import/export and materialization.
APIs are still evolving; integrations should pin a tested release.

## Installation

```bash
uv add 'comfygit-core==0.7.0'
```

Core does not require desktop keyring. For OS-backed credential persistence,
install the optional `comfygit-core[keyring]==0.7.0` extra. The CLI includes that
extra; headless library users can use environment credentials or inject their
own store instead.

## Open a workspace

```python
from pathlib import Path
from comfygit_core import Workspace

workspace = Workspace.open(Path.home() / "comfygit")
env = workspace.get_environment("my-project", auto_sync=False)
status = env.status()
```

`Workspace.create(path)` creates a workspace; `Workspace.open_or_create(path)`
handles either case. Opening with `auto_sync=False` above avoids reconciling the
environment just to inspect it.

## Create and reconcile an environment

```python
env = workspace.create_environment(
    name="experiment",
    python_version="3.12",
    torch_backend="auto",
    no_manager=True,
)
env.add_node("rgthree-comfy")
result = env.sync(model_strategy="required")
```

Creation and sync can download code and packages. Resolve an existing saved
workflow by its name, not an arbitrary JSON path:

```python
result = env.resolve_workflow("my-workflow")
```

For ambiguous resolution, supply implementations of the protocols in
[`models/protocols.py`](src/comfygit_core/models/protocols.py). Do not put prompts,
printing or CLI policy into Core. A successful dependency resolution is not proof
that a ComfyUI inference job succeeds.

## Credentials

Workspace entry points accept process-local `credential_overrides`, keyed by
`CredentialProvider`. A token overrides all discovery for that provider; `None`
explicitly selects anonymous access. Omitted providers use normal discovery.

```python
from comfygit_core.models.credentials import CredentialProvider

workspace = Workspace.open(
    Path.home() / "comfygit",
    credential_overrides={CredentialProvider.HUGGINGFACE: None},
)
```

Normal resolution uses provider environment variables, workspace secure storage,
provider-native credentials when available, then legacy workspace values during
migration. An unavailable keyring backend does not prevent environment/native
credentials from working. Saving a new credential requires a working secure store;
there is no new plaintext fallback. Callers may inject a `CredentialStore` through
the `credential_store` parameter.

## Portable and local state

The tracked `pyproject.toml`, `workflows/`, `workflow_api/`, shared overlays and
source metadata form the portable environment. Model bytes stay in the shared
model directory. ComfyUI/node checkouts, virtualenvs, `.cec/`, local overlays,
credentials and backend choices are derived or machine-local state.

Use ComfyGit operations to change the recipe; manual runtime edits may be
replaced on sync. For a headless recreation, use the materialization API or
[`cg materialize`](https://docs.comfygit.org/user-guide/collaboration/materialize/).

## API and development references

- [Workspace entry points](src/comfygit_core/core/workspace.py)
- [Environment operations](src/comfygit_core/core/environment.py)
- [Architecture](docs/architecture.md)
- [Normative contracts](../../docs/contracts/) and [specifications](../../docs/specs/)
- [Contributing](../../CONTRIBUTING.md)

From the monorepo root:

```bash
uv sync --frozen --all-packages
uv run pytest packages/core/tests -q
make lint
```

Core, Studio runtime and CLI releases use matched versions. See the root
[agent guide](../../AGENTS.md) for release ordering and package boundaries.
