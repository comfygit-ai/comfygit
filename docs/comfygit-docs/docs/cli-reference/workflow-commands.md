# Workflow Commands

Workflow commands inspect saved ComfyUI workflows, resolve dependencies, and
manage workflow-level model declarations.

## List And Resolve

```bash
cg workflow list
cg workflow resolve WORKFLOW [--auto] [--install|--no-install] [--json] [--strict]
```

`resolve` analyzes workflow JSON, maps custom nodes to packages, matches model
references to the model index, and records dependency metadata in the manifest.

For automation, choose installation behavior explicitly:

```bash
cg -e my-env workflow resolve my-workflow --auto --no-install --json --strict
```

`--json` requires `--auto` and either `--install` or `--no-install`. Results go to
stdout, progress goes to stderr. `--strict` exits nonzero if dependencies remain
unresolved or uninstalled. Resolution updates metadata even with `--no-install`;
it is not a read-only inspection or an inference test.

## Explicit Node Ownership

```bash
cg workflow node map WORKFLOW NODE_TYPE PACKAGE [--json]
cg workflow node unmap WORKFLOW NODE_TYPE [--json]
cg workflow node list WORKFLOW [--json]
```

Map a registered ComfyUI class name to an already tracked package. The class must
exist in the saved workflow. This supports unregistered or newly added node types
without editing cached registry data. See [workflow resolution](../user-guide/workflows/workflow-resolution.md).

## Workflow Models

List models declared for a workflow:

```bash
cg workflow model list [WORKFLOW]
```

Declare an already-indexed local model as a workflow dependency:

```bash
cg workflow model add WORKFLOW --path RELATIVE_MODEL_PATH [--importance required|flexible|optional]
cg workflow model add WORKFLOW --hash HASH [--importance required|flexible|optional]
```

Remove a manually declared workflow model:

```bash
cg workflow model remove WORKFLOW --path RELATIVE_MODEL_PATH
cg workflow model remove WORKFLOW --hash HASH
```

Change model importance:

```bash
cg workflow model importance [WORKFLOW] [MODEL] [required|flexible|optional]
```

Use `importance` in user-facing docs. It maps to model criticality in the
manifest.

## Related Guides

- [Workflow resolution](../user-guide/workflows/workflow-resolution.md)
- [Workflow model dependencies](../user-guide/workflows/model-dependencies.md)
- [Workflow contracts](../user-guide/workflows/workflow-contracts.md)
