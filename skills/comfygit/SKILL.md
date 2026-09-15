---
name: comfygit
description: Manage ComfyUI environments and workflows with ComfyGit, including version comparisons, shared models, custom-node development, dependency resolution, and runtime validation. Use when setting up or operating ComfyUI through the cg CLI or ComfyGit Python API.
---

# ComfyGit

Use ComfyGit to own ComfyUI environment and dependency state. Keep experiment
code, datasets and outputs in their project; record which environment and source
revision produced them.

## Start with the relevant path

- **Install, repair dependencies, or diagnose keyring errors:** read
  [installation.md](references/installation.md).
- **Create environments, compare ComfyUI versions, reuse models, or reproduce a
  setup:** read [environments.md](references/environments.md).
- **Develop custom nodes, resolve a graph, run a workflow, or restart ComfyUI:**
  read [workflows.md](references/workflows.md).

Discover the installed capabilities with `cg --version`, `cg --help`, and the
specific subcommand's `--help`. This skill accompanies source that includes
`workflow node map`, resolution `--json --strict`, and environment-scoped
`orch` control. Older releases may lack these. Do not invent flags or treat
editable-install version metadata as proof of the imported source revision.

## Operating model

- Explicitly target `cg -e NAME ...` when more than one environment exists.
- A workspace shares a configured model store and caches. Each environment
  retains its own ComfyUI checkout, node state and Python virtualenv. uv reuses
  cached package artifacts; it does not eliminate environment isolation.
- Tracked `.cec/pyproject.toml` and workflow artifacts are portable dependency
  truth. Model bytes, indexes, local paths, backends and editable overrides are
  machine-local state. Avoid manually editing generated runtime configuration.
- Core's public entry points are `Workspace` and `Environment`; use their public
  methods instead of reaching through to managers or repositories.
- Separate dependency resolution, portable provenance, live node registration,
  and successful execution. None of those checks substitutes for the others.
- Preserve active jobs, browser drafts, experiment outputs and trained weights.
  Do not reset, overwrite an environment, or delete shared assets merely to make
  a setup appear clean. Follow the host's authorization rules for network Git,
  credentials and publication.

## Completion evidence

For setup work, report the environment, actual revisions, shared model root and
unresolved requirements. For generation work, also verify a real completed job
and an accessible output. Preserve the exact graph/API prompt and parameters
needed to reproduce the result. A successful install or CLI exit is not proof
of model quality or GPU compatibility.

## Maintain this skill

Update the relevant reference when a verified CLI/API behavior changes. Keep
host-specific paths and policies in the host's short `AGENTS.md` entry. Keep
model-specific prompting or training recipes in their experiment documentation.
Validate new examples against current help/source and a bounded runtime check
when behavior warrants it; do not accumulate old workarounds after fixes land.
