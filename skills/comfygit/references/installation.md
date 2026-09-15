# Installation and dependency diagnosis

## Choose an installation that matches the intended source

For a published release, `uv tool install comfygit` installs the CLI and its
declared core/Studio dependencies into a dedicated tool environment.

For an existing source checkout, run from the monorepo root:

```bash
uv sync --frozen --all-packages
uv run --frozen --package comfygit cg --version
```

This uses the workspace's local core, CLI and Studio packages together. The root
is a uv workspace, not an installable Python project; `pip install .` at the root
is not the source-install path.

To expose that checkout as the user's `cg` tool:

```bash
uv tool install --force --editable ./packages/cli \
  --with-editable ./packages/core \
  --with-editable ./packages/studio-runtime
```

This replaces the existing tool installation. Use it when installing/updating
the user's CLI is within the requested scope; otherwise use `uv run` from the
checkout. If publishing wheels, keep core/Studio/CLI versions aligned and build
all three; installing only the CLI wheel may resolve its exact dependencies
from the package index instead of the intended checkout.

Editable Python source changes immediately, but installed dependency metadata
does not. Rerun the installation/sync command after dependency changes. Record
the executable, distribution versions and imported source path when diagnosing
different behavior between the shell, checkout and managed ComfyUI environment.

## Optional keyring and credential sources

Core installs (`comfygit-core`) do not require keyring. The default CLI requests
`comfygit-core[keyring]` so desktop users can save credentials with `cg auth set`.
Installing that extra provides the Python package, not an unlocked OS keychain.
Headless users can use provider environment variables or an existing provider
login without setting up desktop secure storage.

- **`ModuleNotFoundError: keyring` at startup:** current core imports keyring lazily
  and translates its absence into a storage error. Check for an older source or
  stale tool installation; refresh the matched install and run `uv pip check`
  against its interpreter. Installing into a ComfyUI venv will not repair a
  separate CLI tool environment.
- **Secure-storage dependency missing:** install `comfygit-core[keyring]` into the
  calling Python environment if persistence is wanted. Otherwise use an alternate
  credential source; no keyring install is required for public/local operations.
- **No usable OS backend:** the package is installed but secure storage is
  unavailable. Headless Linux may lack an unlocked Secret Service/D-Bus session.
  Use the deployment's credential provider; never add plaintext persistence to
  hide this error. Host credential policies take precedence.

Resolution order is caller override, provider environment variable, workspace
secure store, provider-native login, then retained legacy credentials. Existing
legacy values are removed only after verified secure migration. New credentials
are never saved to workspace metadata.

For application integrations, use the public workspace constructors:

```python
from comfygit_core import Workspace
from comfygit_core.models import CredentialProvider

workspace = Workspace.open(
    workspace_path,
    credential_overrides={CredentialProvider.HUGGINGFACE: supplied_token},
)
```

Overrides stay in this workspace object's memory. An omitted provider uses the
normal chain; an explicit `None` disables ComfyGit credential discovery for that
provider. HF downloads/search then pass `token=False`, preventing the Hub SDK
from rediscovering the saved login. This does not disable external git helpers,
SSH agents, or credentials embedded in supplied URLs. `get_credential_status`
reports `explicit` or `anonymous` without exposing the token. Credentials can
also be supplied through the existing injected `CredentialStore` protocol.

Python 3.10 needs the declared conditional `tomli` dependency; Python 3.11+
provides `tomllib`. Test package metadata outside the development environment:

```bash
uv run python dev/scripts/check-package-install.py --python 3.10
```

That source-tree check installs core alone and verifies keyring is absent,
exercises environment/native/explicit/anonymous resolution with synthetic
credentials, then installs the CLI and checks its keyring extra and unavailable
OS backend. It uses temporary environments and does not access real secrets.
It does not prove every OS's desktop keychain configuration or CUDA readiness.

## Apps consuming a development checkout

An editable CLI install does not update an app's bundled wheels or an already
running Python service. Inspect the actual interpreter, distribution metadata,
editable `direct_url.json`, imported module path, and service command. After
metadata or dependency changes, rerun the editable install or workspace sync.
Keep core, CLI and Studio versions aligned.

Application adapters may support a host-local development-source override.
Consult the consuming application's documentation and inspect its effective
interpreter; this is not a ComfyGit CLI flag. New commands import current source,
while running services need a safe restart. Keep source paths out of portable
app manifests.
A release must restore locked package archives and verified published wheels;
source version metadata alone does not prove a version has been released.
