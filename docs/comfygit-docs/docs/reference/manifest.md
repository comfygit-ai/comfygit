# Manifest Reference

The environment manifest is the tracked `pyproject.toml` file at the root of a
ComfyGit environment repository.

It is the portable recipe for the environment. Sync, repair, export, import,
materialize, Manager, and `cg serve` all read from this state.

## Major Manifest Responsibilities

The manifest records:

- project metadata and Python dependency declarations
- ComfyUI repository, version intent, and immutable commit provenance
- custom node package metadata
- custom node dependency groups
- workflow entries
- workflow model dependencies
- workflow execution contracts
- model metadata and source proof
- shared overlays, when intentionally committed

## Local State Is Separate

The manifest should not contain machine-local runtime state:

- credentials
- local model directory paths
- virtualenv contents
- installed runtime checkouts
- local-only overlays
- hardware-specific PyTorch backend choices

Those values are injected during sync/run/materialization from local
configuration.

## Inspecting The Manifest

```bash
cg manifest
cg manifest --pretty
cg manifest --section tool.comfygit
cg manifest --ide
```

Use ComfyGit commands or Manager actions for normal edits. Direct manifest edits
should be followed by `cg sync` or `cg repair` to reconcile runtime state.

## ComfyUI Source Pinning

Portable environments may select a fork while remaining exactly reproducible:

```toml
[tool.comfygit]
comfyui_repository = "https://github.com/kijai/ComfyUI.git"
comfyui_version = "vsa"
comfyui_version_type = "branch"
comfyui_commit_sha = "10febb01d7be73d1491cf5e5347b5ab8b6c2c09e"
```

The branch or tag is descriptive intent. When `comfyui_commit_sha` is present,
import and materialization clone and verify that exact commit from the declared
repository. Older manifests without `comfyui_repository` use canonical ComfyUI.

## Related Pages

- [Manifests concept](../concepts/manifests.md)
- [Environment history](../user-guide/environments/version-control.md)
- [Environment commands](../cli-reference/environment-commands.md)
