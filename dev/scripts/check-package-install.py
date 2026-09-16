"""Build and exercise release wheels in a fresh, non-editable environment.

Checks core without keyring first, then the CLI with its optional storage extra.
Run: uv run python dev/scripts/check-package-install.py --python 3.10
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("comfygit-core", "comfygit-studio", "comfygit")


CORE_ONLY_CHECK = r"""
import importlib.util
import os
import sys
from pathlib import Path
from comfygit_core import Workspace
from comfygit_core.models import CDCredentialStoreError, CredentialProvider, CredentialSource
assert importlib.util.find_spec('keyring') is None, 'Core unexpectedly installed keyring'
assert 'keyring' not in sys.modules
workspace = Workspace.create(Path.cwd() / 'core-workspace')
assert workspace.get_civitai_token() is None
assert workspace.get_huggingface_token() is None
assert not workspace.get_credential_status(CredentialProvider.CIVITAI).storage_available
os.environ['HF_TOKEN'] = 'synthetic-environment-token'
assert workspace.get_huggingface_token() == 'synthetic-environment-token'
del os.environ['HF_TOKEN']
# Exercise the actual Hub token-file resolver using only a synthetic local login.
token_path = Path(os.environ['HF_TOKEN_PATH'])
token_path.parent.mkdir(parents=True, exist_ok=True)
token_path.write_text('synthetic-native-token')
assert workspace.get_huggingface_token() == 'synthetic-native-token'
assert workspace.get_credential_status(CredentialProvider.HUGGINGFACE).source == CredentialSource.PROVIDER_NATIVE
anonymous = Workspace.open(workspace.path, credential_overrides={CredentialProvider.HUGGINGFACE: None})
assert anonymous.get_huggingface_token() is None
assert anonymous.workspace_config_manager.get_huggingface_download_token() is False
explicit = Workspace.open(workspace.path, credential_overrides={CredentialProvider.HUGGINGFACE: 'synthetic-explicit-token'})
assert explicit.get_huggingface_token() == 'synthetic-explicit-token'
try:
    workspace.set_civitai_token('synthetic-must-not-persist')
except CDCredentialStoreError as exc:
    assert 'comfygit-core[keyring]' in str(exc)
else:
    raise AssertionError('Missing package must produce an actionable storage error')
assert 'synthetic-' not in workspace.paths.workspace_file.read_text()
assert 'keyring' not in sys.modules
token_path.unlink()
print('Core-only wheel: no keyring, workspace operations, environment/native/explicit/anonymous auth passed.')
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default="3.10")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="comfygit-install-") as directory:
        temp = Path(directory)
        wheels = temp / "wheels"
        for package in PACKAGES:
            subprocess.run([
                "uv", "build", "--package", package, "--wheel", "--no-sources",
                "--out-dir", str(wheels),
            ], cwd=ROOT, check=True)
        venv = temp / "venv"
        subprocess.run(["uv", "venv", "--python", args.python, str(venv)], check=True)
        executable = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        environment = {
            key: value for key, value in os.environ.items()
            if key not in (
                "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "CIVITAI_API_TOKEN", "CIVITAI_API_KEY",
                "GH_TOKEN", "GITHUB_TOKEN",
            )
        }
        environment.update({
            "PYTHON_KEYRING_BACKEND": "keyring.backends.fail.Keyring",
            "HF_HOME": str(temp / "hf"),
            "HF_TOKEN_PATH": str(temp / "hf" / "token"),
        })
        core_wheel = next(wheels.glob("comfygit_core-*.whl"))
        subprocess.run([
            "uv", "pip", "install", "--python", str(executable), str(core_wheel),
        ], check=True)
        subprocess.run(["uv", "pip", "check", "--python", str(executable)], check=True)
        subprocess.run([str(executable), "-I", "-c", CORE_ONLY_CHECK], cwd=temp, env=environment, check=True)
        subprocess.run([
            "uv", "pip", "install", "--python", str(executable),
            *map(str, sorted(wheels.glob("*.whl"))),
        ], check=True)
        subprocess.run(["uv", "pip", "check", "--python", str(executable)], check=True)
        # -I prevents workspace/PYTHONPATH imports from masking missing wheel dependencies.
        subprocess.run([str(executable), "-I", "-c", """
import importlib.metadata
import sys
from pathlib import Path
from comfygit_core import Workspace
from comfygit_core.models import CDCredentialStoreError, CredentialProvider
from comfygit_core.repositories.credential_store import KeyringCredentialStore
from comfygit_cli.cli import create_parser
import comfygit_core, comfygit_studio, keyring
assert Path(comfygit_core.__file__).is_relative_to(Path(sys.prefix))
assert importlib.metadata.version('comfygit') == importlib.metadata.version('comfygit-core')
assert importlib.metadata.version('comfygit') == importlib.metadata.version('comfygit-studio')
create_parser().parse_args(['workflow', 'resolve', 'sample', '--auto', '--no-install', '--json', '--strict'])
try:
    KeyringCredentialStore().get('package-smoke-fixture', CredentialProvider.CIVITAI)
except CDCredentialStoreError:
    pass
else:
    raise AssertionError('Missing OS keyring backend must produce a structured error')
print('Clean wheel imports, CLI parser, lockstep versions and headless keyring behavior passed.')
"""], cwd=temp, env=environment, check=True)


if __name__ == "__main__":
    main()
