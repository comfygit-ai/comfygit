# Custom-node development and workflow execution

## Register a local node checkout

```bash
cg -e NAME node dev-link my-pack --path /absolute/path/to/my-pack
```

The operation tracks the package, creates the runtime link, and preserves a
known identifier when converting an installed pack. Inspect replacement flags
before replacing existing materialized source. Include imported helper code and
Python requirements in the pack's reproducible dependencies; a symlink does not
capture code imported from an unrelated home directory.

Runtime registration and package ownership are distinct. If ComfyUI's
`/object_info` lists a class but resolution cannot identify its package, inspect
`python_module` and the actual installed source. Then map verified ownership:

```bash
cg -e NAME workflow node map WORKFLOW MyRegisteredClass my-pack
cg -e NAME workflow node list WORKFLOW --json
cg -e NAME workflow resolve WORKFLOW --auto --no-install --json --strict
```

`map` requires an existing workflow and tracked package. `unmap` removes an
override. Interactive resolution also offers manual package entry. On versions
without these CLI mapping commands, the public API is available:

```python
from pathlib import Path
from comfygit_core import Workspace

workspace = Workspace.open(Path('/absolute/workspace'))
env = workspace.get_environment('NAME', auto_sync=False)
env.set_workflow_custom_node_mapping('WORKFLOW', 'MyRegisteredClass', 'my-pack')
```

Do not mark a required unknown node optional just to hide its warning. Do not
invent a Comfy registry ID for a private development pack.

## Make hidden model requirements explicit

Graph analysis cannot infer every model loaded by arbitrary Python code.
After indexing existing artifacts, declare opaque-loader requirements:

```bash
cg -e NAME workflow model add WORKFLOW --path loras/artist.safetensors
cg -e NAME workflow model list WORKFLOW
```

Use real indexed paths or hashes. Directory-based models may require multiple
files; account for the entire model bundle through supported manifest model
requirements, rather than declaring only one weight file. Keep sources and
hashes alongside requirements for a portable handoff.

## Resolve, save and execute

`cg analyze workflow.json --json` is useful initial inspection. Resolution
mutates dependency declarations and may download selected artifacts. In the
current CLI, machine-readable resolution requires `--auto` and an explicit
`--install` or `--no-install` choice. Progress goes to stderr. `--strict` exits
nonzero if the final dependency state is incomplete; without it, partial
resolution remains an allowed interactive outcome.

Save the graph and use Manager's capture/resolve/Open flow. For reusable API
execution, author an I/O contract in Manager and capture ComfyUI's actual API
prompt. UI JSON and API prompts are different formats. Do not rebuild frontend
serialization yourself when the installed frontend can produce the prompt.
Use `cg serve`/Studio when appropriate and verify the installed capabilities;
these are optional application interfaces, not required for an editable graph.

## Runtime control

With an environment started by the matching current CLI:

```bash
cg -e NAME orch status --json
cg -e NAME orch restart --wait --timeout 180 --json
```

Status reports the environment, supervisor instance, launch generation, endpoint,
readiness and queue counts. Restart uses Manager's existing restart path and
refuses busy/unknown queues or mismatched ownership. Waiting requires a newer
launch generation and HTTP readiness; an unchanged supervisor PID is not
completion. Control is local-only. Manager must support its restart/ownership
API. A supervisor launched before this feature needs one normal relaunch by its
owner; don't replace it while it is generating.

If Manager reports a workspace-wide legacy orchestrator, the named restart is
refused because its proxy could target a different child. Use that runtime's
owner instead of bypassing the identity check.

`orch kill`/`clean` still target the legacy orchestrator. For a normal shutdown
of `cg run`, use its owning terminal/service after coordinating active jobs.

The queue guard is a preflight, not a transactional drain of other clients.
Coordinate submitters during restart. If a request times out or has uncertain
delivery, inspect status/logs before attempting another mutation. These commands
do not authorize interrupting another user's work. Preserve browser drafts; a
runtime restart does not itself establish that all browser tabs were saved.

Finally submit a short real workflow, inspect queue/history and the completed
artifact, then expand the run. Record seed, prompt, model/adapter selection and
source versions. Semantic correctness—such as preserving a supplied melody—is
validated at the model/output level, not by ComfyGit dependency readiness.
