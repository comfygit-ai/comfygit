# Contributing to ComfyGit

ComfyGit is an actively developed, pre-customer project. Keep changes focused,
preserve cross-platform behavior, and discuss substantial architecture or new
dependencies in an issue before implementing them.

## Development setup

You need Git, uv, and Python 3.10 or newer. Studio development also needs Node.js
22 and npm. The public documentation project uses Python 3.12 or newer.

```bash
git clone https://github.com/comfygit-ai/comfygit.git
cd comfygit
uv sync --frozen --all-packages
uv run --frozen --package comfygit cg --help
```

The root is a uv workspace; do not install the root as a Python package. For a
user-installed editable CLI, see [the source installation instructions](README.md#install-from-a-source-checkout).

## Repository and architecture

- `packages/core/`: UI-independent environment, manifest, model and node library.
- `packages/cli/`: the `cg` / `comfygit` command-line interface.
- `packages/studio-runtime/`: shared HTTP runtime, uploads, execution and gallery state.
- `packages/studio/`: React/Vite Studio frontend bundled with the Python runtime.
- `docs/comfygit-docs/`: public documentation with its own uv lockfile.

Read [AGENTS.md](AGENTS.md) for repository conventions. Behavioral truth takes
precedence in this order: `docs/contracts/`, `docs/specs/`, package architecture
docs, then public user docs. Substantial behavior changes should update the
relevant contract/spec and tests together. Planned clauses are not implemented
features merely because they appear in a spec.

Core must not depend on CLI or UI rendering. Use typed results, callbacks and
strategies for frontend interaction. Keep credentials, local paths, hardware
choices and runtime state out of portable manifests.

Architecture entry points:

- [Core](packages/core/docs/architecture.md)
- [CLI](packages/cli/docs/architecture.md)
- [Studio](packages/studio/AGENTS.md)

## Test and review

```bash
make lint
uv run pytest packages/core/tests packages/studio-runtime/tests packages/cli/tests -q
make check-versions
make check-openapi
```

Run focused tests while iterating. Add regression coverage for behavior fixes,
including important failure paths. For frontend changes:

```bash
npm --prefix packages/studio ci
npm --prefix packages/studio run build
uv run python dev/scripts/sync-studio-static.py
```

Commit regenerated bundled static assets when the frontend changes. For docs,
run `make docs-build`; see the [documentation maintainer guide](docs/comfygit-docs/README.md).

For CLI experiments, use a disposable workspace and keep real environments safe:

```bash
export COMFYGIT_HOME=/path/to/test/workspace
uv run cg init
uv run cg debug --level ERROR
```

## Pull requests

Branch from and target `main`. Describe the problem, the resulting behavior, and
validation. Use a focused title such as `fix: preserve workflow mappings` or
`docs: clarify credential setup`. Check that your diff contains no generated
runtime state, credentials, or machine-specific configuration.

The reusable [ComfyGit skill](skills/comfygit/SKILL.md) documents operating the
tool; the agent guide documents developing it. Update the appropriate one when
behavior changes. Keep `AGENTS.md` and `CLAUDE.md` synchronized.

## Releases

Core, Studio runtime, CLI, and the Studio frontend use one version. Do not bump
packages independently:

```bash
make show-versions
make bump-version VERSION=<next-version>
uv lock
make check-versions
make build-all
```

A version change on `main` can trigger publishing. Coordinate release changes
with the maintainer. Publishing proceeds Core → Studio runtime → CLI so exact
pins resolve. Manager is a separate repository and can adopt those versions
after they are published. Documentation deploys through its own manual workflow;
it does not require a new Python package version.

## Questions and license

Use [issues](https://github.com/comfygit-ai/comfygit/issues) for bugs and proposals,
and [discussions](https://github.com/comfygit-ai/comfygit/discussions) for questions.
Contributions are licensed under the repository's [GPL-3.0](LICENSE.txt) license.
