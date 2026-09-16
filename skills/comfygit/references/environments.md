# Environments, versions and shared assets

## Discover before creating

Use `cg list`, `cg inventory --json`, `cg model index status`, and the selected
environment's `status`/`manifest`. Confirm the actual workspace and model root;
reuse existing indexed files before downloading. Do not change another active
project's workspace configuration without considering that shared scope.

`cg model index dir /absolute/model-store` selects the workspace's model root.
Use the host's configured directory. `cg model index sync` refreshes discovery
after external downloads or file moves. It does not justify deleting duplicate
locations automatically. `cg inventory --storage` is a more expensive optional
storage scan.

## Compare versions in separate environments

```bash
cg create experiment-old --comfyui OLD_TAG_OR_COMMIT --torch-backend auto
cg create experiment-new --comfyui NEW_TAG_OR_COMMIT --torch-backend auto
cg -e experiment-old run -- --port 8188
cg -e experiment-new run -- --port 8191
```

Replace placeholders with verified versions. Use separate ports when both
runtimes are needed, and consider GPU capacity before running both. Do not
upgrade the original environment in place for a comparison. ComfyUI source can
also be selected explicitly with `--comfyui-repository`; record its immutable
revision for reproducibility. Environment creation needs more than bare Python:
custom-node dependencies and the chosen PyTorch backend must match the host.

There is no assumed `cg clone` command. To reproduce a reviewed environment,
commit its intended changes, export a bundle and import it under another name,
or use `cg materialize` with a reviewed directory/Git/bundle source. Discover
the current flags with help. For example:

```bash
cg -e experiment-old export /tmp/experiment-old.tar.gz
cg import /tmp/experiment-old.tar.gz --name experiment-copy --models required
```

Exports carry dependency metadata and workflows, not another full copy of the
model store. Readiness warnings about missing sources are useful evidence;
`--allow-issues` is an explicit incomplete handoff, not a repair. A local model
file is usable here but does not by itself provide a recovery source elsewhere.

## What is shared and what remains isolated

Models are external to environment snapshots. uv's cache reuses Python package
downloads/artifacts where possible. ComfyGit also caches node downloads, but
materialized custom-node source and virtualenvs may still consume per-environment
space. Do not promise zero duplication or one universal Python environment.

Use `node dev-link` deliberately for editable source sharing. Sharing one
mutable checkout across environments means edits affect every linked consumer;
use separate checkouts when testing different node versions. Preserve the
dependency isolation that makes comparisons useful.

Record extra Python dependencies with `cg -e NAME py add PACKAGE`. Keep local
source overrides and hardware-specific settings in supported local
configuration/overlays. Manual `pip install` into a managed venv can be lost on
sync and is not a reproducible dependency declaration.
