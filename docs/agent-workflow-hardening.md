# Agent workflow and installation hardening

Implemented on branch `codex/comfygit-agent-workflows`, based on `b6e36eb`, on
2026-09-15. This describes local source changes, not a published release.

## Changes

- Core accepts empty/null optional workflow definitions without losing the
  graph, and reports malformed definitions with field-specific errors.
- `cg workflow node map/unmap/list` exposes existing Environment mapping APIs.
  A map requires a saved workflow and tracked node package.
- `cg workflow resolve --auto --no-install --json --strict NAME` sends progress
  to stderr, reports the final dependency state as JSON, and exits nonzero for
  incomplete resolution. `--install` is also supported. Interactive partial
  resolution keeps its previous exit behavior unless strict mode is requested.
- `cg run` advertises environment-specific runtime control alongside its
  existing switch observer. `cg -e NAME orch status --json` reports readiness,
  identity, generation and queue counts. Restart verifies identity/ownership,
  refuses busy/unknown queues, and delegates to Manager's existing restart API.
  `--wait` requires a newer launch generation and responding ComfyUI API.
- Core now declares `tomli>=2.0.1` for Python below 3.11. This fixes a confirmed
  clean-install failure on supported Python 3.10.
- The repo includes an installable [ComfyGit skill](../skills/comfygit/SKILL.md)
  and a source-install procedure that installs the matched local packages.
- CI adds clean wheel installation checks on Linux Python 3.10/3.12 and
  macOS/Windows Python 3.12. These checks build all three wheels, install only
  runtime dependencies, check versions/imports and exercise an unavailable OS
  keyring backend.

## Keyring finding

At the initial audit, core metadata required `keyring>=25.7.0`. The historical
missing-module failure is consistent with stale dependencies in an editable
tool installation; editing source alone does not refresh that installation's
metadata/dependencies. This investigation did not reproduce the original
missing-keyring state. Clean wheel and source-tool installs now verified that
the required Python dependencies are installed.

The clean Python 3.10 check instead exposed a separate undeclared `tomli` import;
it failed before the fix and passed after adding the conditional requirement.
An unavailable OS keyring service is distinct from either missing Python
dependency. No plaintext credential fallback or OS keychain reconfiguration was
introduced.

## Validation

- Full core/CLI/Studio suite: **2,290 passed, 7 skipped**, 197.80 seconds.
- Additional real-child restart test: **passed**. It uses the actual
  `Environment.run` and CLI run loop with disposable stdlib HTTP children;
  sync/backend probing are stubbed. Exit 42 caused a different child PID and
  launch generation, followed by verified HTTP readiness. No GPU or live
  ComfyUI instance was involved.
- Focused parser, mapping, runtime and existing run-behavior tests passed;
  the final runtime regression run passed all **9 tests**, including refusal
  when Manager could proxy to a different legacy owner.
- Clean release-wheel installs on Linux with Python 3.10 and 3.12 passed,
  including `uv pip check` and simulated unavailable-keyring behavior.
- The documented editable source-tool command passed in temporary
  `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` directories, leaving the existing tool install
  untouched.
- Ruff passed; targeted core `ty` and Pyright checks for new runtime/serialization
  code plus changed CLI adapters passed; lockfile and lockstep version checks
  passed.
- Skill frontmatter, relative references and its local installation validated.

Tests: `test_workflow_subgraph.py`, `test_workflow_agent_commands.py`,
`test_managed_runtime_control.py`, `test_supervisor_control.py`, and
`dev/scripts/check-package-install.py`. The full suite was collected before the
additional real-child test; its separate pass is not included in the 2,290 count.

## Operating limits and follow-ups

Existing supervisors must be relaunched by their owner to advertise the new
control protocol. This work did not restart the active YuE2 service, run a new
generation, publish packages, or push a branch. macOS/Windows clean-install CI
is configured but was not executed locally.

Queue checks are a preflight, not an atomic drain against other clients. New
runtime writes are local/non-browser only; restart requires a compatible
Manager. `orch kill`/`clean` remain legacy-orchestrator operations. Structured
legacy status explicitly says that it does not establish current runtime state.

Manager's missing-dependency presentation and a browser workflow deep link are
separate UI follow-ups. This patch provides explicit mapping so local node
development no longer requires internal API calls; it does not claim to
automatically infer every node owner or hidden model dependency.

## Optional credential storage follow-up

Core now puts keyring in the `keyring` extra and loads it lazily. The CLI requests
that extra; standalone core and Studio runtime do not. Workspace constructors
accept process-local credential overrides, including explicit anonymous access.
Hugging Face calls preserve anonymous opt-out (`False`) through download retries
and model lookup. CivitAI clients defer to workspace resolution instead of
preempting an application override with an environment token. Provider-native
login precedes retained legacy plaintext even if keyring is unavailable.

The clean-wheel check now tests core-only with keyring absent, then adds the CLI
and verifies the optional dependency and unavailable OS backend. It isolates
provider environment variables and uses only synthetic saved-login fixtures.
The version checker and Makefile bump command preserve the CLI's extra pin.

Follow-up validation (2026-09-15): full core/CLI/Studio suite **2,312 passed,
7 skipped** in 220.52 seconds. Final credential tests **34 passed**, including
an additional explicit-migration regression added after full-suite collection.
Clean core-only then CLI wheel installs passed on Linux Python 3.10 and 3.12.
Ruff, targeted ty/Pyright, lock/version checks, Makefile extra-preservation check,
Git whitespace checks and skill validation passed. Existing CI includes macOS
and Windows install checks; those platforms were not executed locally. No
release, global tool replacement or live ComfyUI restart was performed.
