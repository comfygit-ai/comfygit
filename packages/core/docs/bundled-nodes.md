# Bundled custom nodes

Use a bundled source when an environment should carry its custom-node code in
its own Git snapshot. Local development links remain a separate source type.

```bash
cg -e my-env node bundle my-custom-node --path /path/to/custom-node
cg -e my-env sync
cg -e my-env status
```

`Environment.bundle_node(name, source_path)` is the equivalent Core API. It
copies the source into `.cec/bundled_nodes/my-custom-node` and registers it;
`Environment.sync()` materializes the runtime copy and installs its requirements.
Existing tracked names and destination folders are rejected instead of replaced.
For an intentional source migration, edit the existing manifest declaration and
place the authored files at its bundle path before syncing in a clean runtime.

```toml
[tool.comfygit.nodes.my-custom-node]
name = "my-custom-node"
source = "bundled"
bundle_path = "bundled_nodes/my-custom-node"
criticality = "required"
```

The path is relative to the environment's `pyproject.toml`, always below
`bundled_nodes/`. Do not set remote repository, download, registry, or pinned
commit fields on this source type. The environment commit identifies the source.
Older experimental `source = "git"` plus `bundle_path` declarations are rejected
with a migration message instead of silently cloning a different source.

Edit the authored bundle and sync to update it. Core preserves conflicting edits
in `ComfyUI/custom_nodes` and reports an error; move those edits back to the
bundle before reconciling. Matching copies are safe to adopt. Deleting or
untracking a runtime node does not delete the authored bundle.

Source must contain `__init__.py`, use portable relative paths, and contain no
links or special files in its shipped file set. Git metadata, Python bytecode,
virtualenvs and tool caches are excluded. Bundles are limited to 20,000 files
and 256 MiB each; model bytes belong in the shared model store. Review the
source before committing or sharing it, just as with any custom-node package.

Directory imports, Git imports and tar exports carry declared bundles. Sync
refreshes their node dependency groups before resolving packages. A required
node failure leaves the environment incomplete; an optional missing node warns.

Cloud planners supply an immutable `BundleInventory` to Core's public
`validate_bundle_inventory` API through the build-readiness `bundle_validator`
hook. Declaring a path alone is not positive build evidence. Cloud should fetch
the tree of the selected environment commit, reject incomplete inventories,
and retain commit provenance. Runtime materialization validates actual files;
provider adapters must not overlay node code after sync. Boot/import validation
and a real workflow run are still needed to prove executable node compatibility.
