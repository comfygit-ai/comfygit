# Workflow Resolution

Workflow resolution teaches ComfyGit what a workflow needs.

It can detect many custom node packages and model references automatically, then
record those dependencies in the environment manifest.

## Run Resolution

```bash
cg workflow resolve my-workflow
```

Install resolved missing nodes automatically:

```bash
cg workflow resolve my-workflow --install
```

Skip installation and only update metadata:

```bash
cg workflow resolve my-workflow --no-install
```

Use automatic choices when you do not want prompts:

```bash
cg workflow resolve my-workflow --auto
```

## Scripted Resolution

```bash
cg -e my-env workflow resolve my-workflow --auto --no-install --json --strict
```

Use `--install` instead of `--no-install` to install resolved missing packages.
JSON mode requires `--auto` and an explicit installation choice. Progress is on
stderr; stdout contains the JSON result. `--strict` returns a nonzero exit code
for remaining unresolved or uninstalled dependencies, so automation can stop
before attempting inference. `--no-install` still records resolution metadata.

A successful resolution does not prove that the nodes import or the workflow
runs. Restart when needed and execute the actual workflow to check its output.

## Explicit Node Mappings

For an unregistered package or a class added after the registry metadata was
published, track the package first and save the workflow in ComfyUI. Then map the
exact node class name from the workflow to that package:

```bash
cg workflow node map my-workflow MyCustomNode my-node-package --json
cg workflow node list my-workflow --json
cg workflow resolve my-workflow --auto --no-install --json --strict
```

Mappings are persisted for that workflow. To remove an incorrect mapping:

```bash
cg workflow node unmap my-workflow MyCustomNode --json
```

The package must already be tracked, and the node class must occur in the saved
workflow. Mapping ownership does not install dependencies or prove importability.

## What Resolution Can Detect

ComfyGit can usually detect:

- built-in ComfyUI nodes
- many custom node package mappings
- built-in model loader widget values
- model folder categories from active ComfyUI metadata
- previous workflow-specific node mappings
- previously declared workflow models

## What Resolution Cannot Know

Some custom nodes load files through code paths that are not visible in the
workflow JSON. ComfyGit should not guess those dependencies.

If the workflow needs a model that resolution does not find, declare it manually:

```bash
cg workflow model add my-workflow \
  --path frame_interpolation/film_net_fp16.safetensors \
  --importance required
```

Read more: [Workflow model dependencies](model-dependencies.md).

## Node Resolution

Custom node resolution maps workflow node types to installable node packages.
When multiple candidates are possible, ComfyGit may ask you to choose.

Persisted workflow node references use canonical manifest package IDs, not
display names or local directory aliases.

## Model Resolution

Model resolution matches workflow references to indexed local files and manifest
metadata.

Required unresolved models or required models without source proof should be
fixed before sharing or materializing a runtime.

## Path Sync

When ComfyGit knows a built-in loader widget and the selected indexed model path,
it can update the workflow JSON to use the correct relative model path.

For custom or unknown widgets, ComfyGit avoids rewriting values it cannot
understand safely.

## After Resolution

```bash
cg status
cg commit -m "Resolve workflow dependencies"
```
