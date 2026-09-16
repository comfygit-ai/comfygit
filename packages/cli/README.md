# ComfyGit CLI

The `comfygit` package provides the `cg` and `comfygit` commands for managing
ComfyUI environments. Version 0.7.0 depends on matched Core and Studio runtime
releases and includes the packaged Studio frontend.

## Install

```bash
uv tool install comfygit --upgrade
cg --version
```

For a source checkout, follow the root [installation guide](../../README.md#install-from-a-source-checkout)
so all workspace packages come from the same checkout.

## First environment

```bash
cg init --models-dir ~/ComfyUI/models --yes
cg create demo --use
cg run
```

Use an existing model directory to reuse model bytes across environments.
Each environment retains isolated mutable ComfyUI/node checkouts and a virtualenv;
uv caches can reuse package artifacts.

## Workflow automation

Save the workflow in ComfyUI, then resolve dependencies explicitly:

```bash
cg -e demo workflow resolve my-workflow --auto --no-install --json --strict
```

Use `--install` to install missing resolved packages. JSON mode requires `--auto`
and an explicit install choice. Strict mode fails if dependencies remain
unresolved or uninstalled. Run the actual workflow afterward to validate runtime
behavior and outputs.

Unregistered class ownership can be recorded against an already tracked package:

```bash
cg -e demo workflow node map my-workflow MyCustomNode my-package --json
cg -e demo workflow node list my-workflow --json
```

## Inspect and control

```bash
cg -e demo status --verbose
cg -e demo orch status --json
cg -e demo orch restart --wait --timeout 180 --json
cg inventory --json --storage
```

Named restart requires a current `cg run` supervisor, matching Manager ownership
and a verified idle queue. Processes started before the CLI upgrade need a relaunch.
The CLI never adopts arbitrary processes by guessing their PIDs.

## Authentication

```bash
cg auth status
cg auth set civitai
cg auth login huggingface
```

`auth set` uses a hidden prompt and needs working OS secure storage. The CLI ships
the optional keyring adapter; headless downloads can instead use environment or
provider-native credentials. Core itself has no hard keyring dependency.

Supported environment overrides include `CIVITAI_API_TOKEN` / `CIVITAI_API_KEY`,
`HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`, and `GITHUB_TOKEN` / `GH_TOKEN`. Credentials
are never portable manifest fields. Set `COMFYGIT_HOME` to select a different
workspace.

## Documentation and development

Use `cg -h` and `cg COMMAND -h` for the exact installed command options.

- [Quickstart](https://docs.comfygit.org/getting-started/quickstart/)
- [CLI reference](https://docs.comfygit.org/cli-reference/global-commands/)
- [Workflow resolution](https://docs.comfygit.org/user-guide/workflows/workflow-resolution/)
- [Studio/API serving](https://docs.comfygit.org/user-guide/serve-studio/serving-workflows/)
- [CLI architecture](docs/architecture.md)
- [Contributing](../../CONTRIBUTING.md)
- [Core library](../core/README.md)

The parser and router live in `comfygit_cli/cli.py`, handlers in
`global_commands.py` and `env_commands.py`, with strategies and formatting in
separate modules. Update the curated public docs when commands change. Generate
a parser-help snapshot with `make -C docs/comfygit-docs generate-cli` from the
monorepo root; it never overwrites those docs.

```bash
uv run pytest packages/cli/tests -q
make lint
```
