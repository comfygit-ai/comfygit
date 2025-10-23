# Process Management Implementation Plan - REVISED

**Status:** Ready for Implementation
**Target:** ComfyDock v2.0.0
**Architecture:** Background-always with pseudo-foreground mode
**Breaking Changes:** Yes (background default, requires major version bump)

## Executive Summary

Implement background process management for ComfyUI with comprehensive logging. All `comfydock run` invocations start ComfyUI as a background daemon. The `--foreground` flag creates a pseudo-foreground experience by streaming logs while monitoring the background process.

**Key Benefits:**
- Eliminates foreground→background conversion complexity
- Enables seamless auto-restart for node operations
- Consistent cross-platform behavior
- Simplified multi-environment workflows
- Aligns with future Docker container architecture

**Architectural Decision:** Use **Return Value Pattern** to avoid circular dependencies. Node operations return `NodeOperationResult` with restart recommendations; CLI layer handles all restart logic.

---

## Architecture Overview

### Background-Always Pattern

```
User: comfydock run
    ↓
ComfyUI starts as background daemon (detached)
    ↓
stdout/stderr → workspace log file (~/.comfydock/logs/<env>/comfyui.log)
    ↓
State file written (.cec/.comfyui.state) with PID, port, log path, args
    ↓
Returns immediately with tip message
```

### Pseudo-Foreground Mode

```
User: comfydock run --foreground
    ↓
ComfyUI starts as background daemon (same as above)
    ↓
Foreground monitor process streams logs in real-time
    ↓
User hits Ctrl+C → Monitor kills ComfyUI → Both exit
```

### Restart Architecture (Avoiding Circular Dependencies)

**Pattern:** Return values instead of callbacks

```
User: comfydock node add <node>
    ↓
env.add_node() → NodeOperationResult(node_info, restart_recommended=True)
    ↓
CLI checks: if result.restart_recommended and env.is_running()
    ↓
CLI decides: prompt user / auto-restart / skip (based on flags)
    ↓
CLI calls: env.restart() if user confirms
```

**No circular dependency:** NodeManager doesn't know about Environment process methods.

---

## Log File Location (Already Implemented ✓)

**Path Structure:**
```
~/.comfydock/
├── logs/                          # Workspace-level logs
│   ├── prod/
│   │   ├── comfyui.log           # Current log
│   │   └── comfyui.log.old       # Rotated log
│   ├── dev/
│   │   ├── comfyui.log
│   │   └── comfyui.log.old
│   └── test/
│       ├── comfyui.log
│       └── comfyui.log.old
├── environments/
│   ├── prod/
│   │   ├── .cec/
│   │   │   ├── .gitignore        # Excludes .comfyui.state
│   │   │   └── .comfyui.state    # Process state (PID, port, args)
│   │   └── ComfyUI/
```

**Note:** `WorkspacePaths.logs` already exists in workspace.py:56-57. No changes needed.

---

## Implementation Phases

### Phase 0: Pre-Implementation
- Add `psutil>=5.9.0` to `packages/core/pyproject.toml`
- Update return types: `NodeInfo` → `NodeOperationResult`
- Add `.gitignore` initialization to GitManager

### Phase 1: Core Process Management
- Create `models/process.py` with `ProcessState` dataclass
- Create `utils/process.py` with platform-specific utilities
- Add process methods to `Environment` class
- Modify `Environment.run()` for background-always

### Phase 2: CLI Integration
- Add `logs`, `stop`, `restart` commands
- Update `run` command with `--foreground` flag
- Update `status` and `list` to show process info

### Phase 3: Auto-Restart Integration
- Add `--auto-restart`, `--no-restart` flags to node commands
- Implement restart handling in CLI (no NodeManager changes needed)
- Update `repair` command to clean stale state files

### Phase 4: Testing & Documentation
- Unit tests for process utilities
- Integration tests for Environment process methods
- CLI tests for new commands
- Update user documentation

---

## Detailed Implementation

### 1. ProcessState Model

**File:** `packages/core/src/comfydock_core/models/process.py` (NEW FILE)

```python
"""Process state management models."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class ProcessState:
    """State of a running ComfyUI process."""

    pid: int                    # Process ID
    host: str                   # From --listen arg (e.g., "0.0.0.0")
    port: int                   # From --port arg (e.g., 8188)
    args: list[str]             # Full args for restart
    started_at: str             # ISO timestamp
    log_path: str               # Absolute path to log file
    last_health_check: str | None = None
    health_status: str | None = None  # "healthy", "unhealthy", "unknown"

    def to_dict(self) -> dict:
        """Serialize to JSON for state file."""
        return {
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "args": self.args,
            "started_at": self.started_at,
            "log_path": self.log_path,
            "health": {
                "last_check": self.last_health_check,
                "status": self.health_status
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessState":
        """Deserialize from state file."""
        health = data.get("health", {})
        return cls(
            pid=data["pid"],
            host=data["host"],
            port=data["port"],
            args=data["args"],
            started_at=data["started_at"],
            log_path=data["log_path"],
            last_health_check=health.get("last_check"),
            health_status=health.get("status")
        )

    def get_uptime(self) -> timedelta:
        """Calculate uptime from started_at."""
        started = datetime.fromisoformat(self.started_at)
        return datetime.now() - started
```

**State File Location:** `environments/<env_name>/.cec/.comfyui.state`

---

### 2. NodeOperationResult (Return Value Pattern)

**File:** `packages/core/src/comfydock_core/models/shared.py`

**Add new dataclass:**

```python
@dataclass
class NodeOperationResult:
    """Result of a node operation with restart recommendation."""

    node_info: NodeInfo
    restart_recommended: bool = False
    restart_reason: str | None = None
```

**Update existing dataclasses:**

```python
@dataclass
class NodeRemovalResult:
    """Result from removing a node."""
    identifier: str
    name: str
    source: str  # 'development', 'registry', 'git'
    filesystem_action: str  # 'disabled', 'deleted'
    restart_recommended: bool = True  # NEW
    restart_reason: str = "Node removed - restart to unload node classes"  # NEW

@dataclass
class UpdateResult:
    """Result from updating a node."""
    node_name: str
    source: str
    changed: bool = False
    message: str = ""
    requirements_added: list[str] = field(default_factory=list)
    requirements_removed: list[str] = field(default_factory=list)
    old_version: str | None = None
    new_version: str | None = None
    restart_recommended: bool = False  # NEW
    restart_reason: str | None = None  # NEW
```

---

### 3. Background Process Utilities

**File:** `packages/core/src/comfydock_core/utils/process.py` (NEW FILE)

```python
"""Process management utilities for ComfyUI daemon."""

import os
import sys
import subprocess
from pathlib import Path
from typing import IO


def create_background_process(
    cmd: list[str],
    cwd: Path,
    log_file: IO,
    env: dict | None = None
) -> subprocess.Popen:
    """Start a process in background, detached from terminal.

    Cross-platform implementation.
    """
    kwargs = {
        'stdout': log_file,
        'stderr': subprocess.STDOUT,
        'stdin': subprocess.DEVNULL,
        'cwd': str(cwd),
        'env': env or os.environ.copy()
    }

    # Platform-specific detachment
    if sys.platform == 'win32':
        kwargs['creationflags'] = (
            subprocess.CREATE_NEW_PROCESS_GROUP |
            subprocess.DETACHED_PROCESS
        )
    else:
        kwargs['start_new_session'] = True

    return subprocess.Popen(cmd, **kwargs)


def is_process_alive(pid: int) -> bool:
    """Check if process exists and is a Python process."""
    try:
        import psutil
        process = psutil.Process(pid)
        if not process.is_running():
            return False
        # Verify it's Python (handles python, python3, python.exe, pythonw.exe)
        name_lower = process.name().lower()
        return 'python' in name_lower
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def is_port_bound(port: int, expected_pid: int | None = None) -> bool:
    """Check if port is in use, optionally verify which PID owns it."""
    try:
        import psutil
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == port and conn.status == 'LISTEN':
                if expected_pid:
                    return conn.pid == expected_pid
                return True
        return False
    except (psutil.AccessDenied, AttributeError):
        # Fallback for Windows without admin: try to bind
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            sock.close()
            return False  # Port not in use
        except OSError:
            return True  # Port in use


def check_http_health(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if ComfyUI HTTP endpoint is responding."""
    import urllib.request

    # Handle special host values
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"

    url = f"http://{host}:{port}/"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False
```

---

### 4. Environment Process Methods

**File:** `packages/core/src/comfydock_core/core/environment.py`

**Add imports:**

```python
from ..models.process import ProcessState
from ..utils.process import create_background_process, is_process_alive, check_http_health
```

**Add ComfyUI argument parser:**

```python
@dataclass
class ComfyUIConfig:
    """Parsed ComfyUI configuration from arguments."""
    host: str = "127.0.0.1"
    port: int = 8188

def _parse_comfyui_args(self, args: list[str]) -> ComfyUIConfig:
    """Extract host/port from ComfyUI arguments."""
    config = ComfyUIConfig()
    i = 0
    while i < len(args):
        if args[i] == "--listen":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                config.host = args[i + 1]
                i += 2
            else:
                config.host = "0.0.0.0"
                i += 1
        elif args[i] == "--port":
            if i + 1 < len(args):
                try:
                    config.port = int(args[i + 1])
                    i += 2
                except ValueError:
                    i += 1
            else:
                i += 1
        else:
            i += 1
    return config
```

**Add state file management:**

```python
@property
def _state_file(self) -> Path:
    """Path to process state file."""
    return self.cec_path / ".comfyui.state"

def _write_state(self, state: ProcessState) -> None:
    """Write process state to file."""
    import json
    self._state_file.write_text(json.dumps(state.to_dict(), indent=2))

def _read_state(self) -> ProcessState | None:
    """Read process state from file."""
    import json
    if not self._state_file.exists():
        return None
    try:
        data = json.loads(self._state_file.read_text())
        return ProcessState.from_dict(data)
    except Exception as e:
        logger.warning(f"Failed to read state file: {e}")
        return None

def _clear_state(self) -> None:
    """Remove state file."""
    if self._state_file.exists():
        self._state_file.unlink()
```

**Replace run() method:**

```python
def run(self, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run ComfyUI in background with logging.

    ALWAYS starts ComfyUI as a background daemon process.
    Output is written to workspace log file.
    """
    from datetime import datetime

    # Check if already running
    if self.is_running():
        state = self._read_state()
        raise CDEnvironmentError(
            f"ComfyUI is already running (PID {state.pid}, port {state.port})"
        )

    # Parse arguments for state tracking
    config = self._parse_comfyui_args(args or [])

    # Ensure workspace logs directory exists
    env_log_dir = self.workspace_paths.logs / self.name
    env_log_dir.mkdir(parents=True, exist_ok=True)

    # Log file path
    log_path = env_log_dir / "comfyui.log"

    # Simple log rotation (rename to .old if > 10MB)
    if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
        old_log = env_log_dir / "comfyui.log.old"
        if old_log.exists():
            old_log.unlink()
        log_path.rename(old_log)
        log_path.touch()

    # Open log file for writing (line buffered)
    log_file = open(log_path, "w", buffering=1)

    # Build command
    python = self.uv_manager.python_executable
    cmd = [str(python), "main.py"] + (args or [])

    logger.info(f"Starting ComfyUI in background: {' '.join(cmd)}")

    # Start background process
    process = create_background_process(
        cmd=cmd,
        cwd=self.comfyui_path,
        log_file=log_file
    )

    # Write state file
    state = ProcessState(
        pid=process.pid,
        host=config.host,
        port=config.port,
        args=args or [],
        started_at=datetime.now().isoformat(),
        log_path=str(log_path)
    )
    self._write_state(state)

    logger.info(f"ComfyUI started: PID {process.pid}, port {config.port}")

    # Return success immediately
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=0,
        stdout=f"Started on {config.host}:{config.port}",
        stderr=""
    )
```

**Add process management methods:**

```python
def is_running(self) -> bool:
    """Check if ComfyUI is running."""
    state = self._read_state()
    if not state:
        return False

    if not is_process_alive(state.pid):
        logger.debug(f"PID {state.pid} not alive, clearing state")
        self._clear_state()
        return False

    return True

def stop(self, timeout: int = 10) -> bool:
    """Stop ComfyUI gracefully."""
    import psutil

    state = self._read_state()
    if not state:
        logger.warning("No state file found, nothing to stop")
        return False

    try:
        process = psutil.Process(state.pid)
        process.terminate()
        logger.info(f"Sent SIGTERM to PID {state.pid}")

        try:
            process.wait(timeout=timeout)
            logger.info(f"Process {state.pid} exited gracefully")
        except psutil.TimeoutExpired:
            logger.warning(f"Process {state.pid} didn't exit, force killing")
            process.kill()
            process.wait(timeout=5)
            logger.info(f"Process {state.pid} force killed")

        self._clear_state()
        return True

    except psutil.NoSuchProcess:
        logger.info(f"Process {state.pid} already dead")
        self._clear_state()
        return True
    except Exception as e:
        logger.error(f"Failed to stop process {state.pid}: {e}")
        return False

def restart(self) -> bool:
    """Restart ComfyUI with same arguments."""
    state = self._read_state()
    if not state:
        raise CDEnvironmentError("Cannot restart: ComfyUI not running")

    # Save args before stopping
    args = state.args

    if not self.stop():
        raise CDEnvironmentError("Failed to stop ComfyUI for restart")

    # Wait for port to be released
    import time
    time.sleep(1)

    # Start with same args
    self.run(args)
    return True
```

**Update add_node signature:**

```python
def add_node(self, identifier: str, is_development: bool = False,
             no_test: bool = False, force: bool = False) -> NodeOperationResult:
    """Add a custom node to the environment."""
    node_info = self.node_manager.add_node(identifier, is_development, no_test, force)

    return NodeOperationResult(
        node_info=node_info,
        restart_recommended=True,
        restart_reason="Node added - ComfyUI needs to load new node classes"
    )
```

---

### 5. NodeManager Updates

**File:** `packages/core/src/comfydock_core/managers/node_manager.py`

**Update return types (no other changes):**

```python
def add_node(self, identifier: str, is_development: bool = False,
             no_test: bool = False, force: bool = False) -> NodeInfo:
    """Add a custom node to the environment."""
    # ... existing implementation unchanged ...
    return node_package.node_info

def remove_node(self, identifier: str) -> NodeRemovalResult:
    """Remove a custom node."""
    # ... existing implementation ...

    # Update return to include restart recommendation
    return NodeRemovalResult(
        identifier=identifier,
        name=node_name,
        source=source,
        filesystem_action=filesystem_action,
        restart_recommended=True,
        restart_reason="Node removed - restart to unload node classes"
    )

def update_node(self, identifier: str, confirmation_strategy=None,
                no_test: bool = False) -> UpdateResult:
    """Update a node based on its source type."""
    # ... existing implementation ...

    # Set restart_recommended if changed
    result.restart_recommended = result.changed
    if result.changed:
        result.restart_reason = f"Node '{result.node_name}' updated to {result.new_version}"

    return result
```

---

### 6. GitManager .gitignore Initialization

**File:** `packages/core/src/comfydock_core/managers/git_manager.py`

**Update initialize_environment_repo:**

```python
def initialize_environment_repo(self, message: str):
    """Initialize git repo for environment configuration."""
    # Existing initialization logic...

    # Create .gitignore for runtime files
    gitignore_path = self.repo_path / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "# ComfyUI process state (runtime only, not configuration)\n"
            ".comfyui.state\n"
        )
        logger.debug("Created .gitignore for runtime files")
```

---

### 7. CLI Run Command Handler

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Update run() method:**

```python
@with_env_logging("env run")
def run(self, args):
    """Run ComfyUI in background (or pseudo-foreground mode)."""
    env = self._get_env(args)
    comfyui_args = args.args if hasattr(args, 'args') else []

    # Parse config for display
    config = env._parse_comfyui_args(comfyui_args)

    print(f"🎮 Starting ComfyUI in environment: {env.name}")
    if comfyui_args:
        print(f"   Arguments: {' '.join(comfyui_args)}")

    # Start ComfyUI (always background)
    result = env.run(comfyui_args)

    # Show success message
    state = env._read_state()
    print(f"\n✓ ComfyUI started in background (PID {state.pid})")
    print(f"✓ Running on http://{config.host}:{config.port}")
    print(f"\nTip: View logs with 'comfydock logs'")

    # Pseudo-foreground mode: stream logs and monitor process
    if args.foreground:
        print("\n" + "=" * 60)
        print("Streaming logs (Ctrl+C to stop ComfyUI)...")
        print("=" * 60 + "\n")

        try:
            _stream_logs_with_monitoring(env, state)
        except KeyboardInterrupt:
            print("\n\n⏸  Stopping ComfyUI...")
            env.stop()
            print("✓ ComfyUI stopped")
            sys.exit(0)
```

**Add pseudo-foreground streaming:**

```python
import signal
import time
from pathlib import Path

def _stream_logs_with_monitoring(env, state):
    """Stream logs while monitoring process."""
    log_path = Path(state.log_path)

    # Register signal handler for cleanup
    def signal_handler(signum, frame):
        print(f"\n\nReceived signal {signum}, stopping ComfyUI...")
        env.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):  # Unix only
        signal.signal(signal.SIGTERM, signal_handler)

    # Stream logs
    with open(log_path, 'r') as f:
        print(f.read(), end='')

        while True:
            if not env.is_running():
                print("\n\n⚠️  ComfyUI process exited")
                break

            line = f.readline()
            if line:
                print(line, end='')
            else:
                time.sleep(0.1)
```

---

### 8. CLI New Commands

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Add logs command:**

```python
@with_env_logging("env logs")
def logs(self, args):
    """View ComfyUI logs."""
    env = self._get_env(args)

    state = env._read_state()
    if not state:
        print("No log file found. Start ComfyUI with: comfydock run")
        sys.exit(1)

    log_path = Path(state.log_path)
    if not log_path.exists():
        print(f"⚠️  Log file not found: {log_path}")
        sys.exit(1)

    # Show logs based on mode
    if args.follow:
        _stream_logs_follow(log_path, env)
    elif args.tail:
        _show_tail(log_path, args.tail)
    else:
        _show_all_logs(log_path)

def _stream_logs_follow(log_path: Path, env):
    """Stream logs in real-time."""
    print(f"Following logs (Ctrl+C to exit)...")
    print("=" * 60)

    with open(log_path, 'r') as f:
        print(f.read(), end='')

        try:
            while True:
                if not env.is_running():
                    print("\n\n⚠️  ComfyUI process exited")
                    break
                line = f.readline()
                if line:
                    print(line, end='')
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n")

def _show_tail(log_path: Path, n: int):
    """Show last N lines."""
    with open(log_path, 'r') as f:
        lines = f.readlines()
        for line in lines[-n:]:
            print(line, end='')

def _show_all_logs(log_path: Path):
    """Show all logs."""
    with open(log_path, 'r') as f:
        print(f.read(), end='')
```

**Add stop and restart commands:**

```python
@with_env_logging("env stop")
def stop(self, args):
    """Stop ComfyUI."""
    env = self._get_env(args)

    if not env.is_running():
        print(f"ComfyUI is not running in environment '{env.name}'")
        return

    state = env._read_state()
    print(f"⏸  Stopping ComfyUI (PID {state.pid})...")

    if env.stop():
        print("✓ ComfyUI stopped")
    else:
        print("✗ Failed to stop ComfyUI", file=sys.stderr)
        sys.exit(1)

@with_env_logging("env restart")
def restart(self, args):
    """Restart ComfyUI with same arguments."""
    env = self._get_env(args)

    if not env.is_running():
        print(f"ComfyUI is not running in environment '{env.name}'")
        print("Use 'comfydock run' to start it")
        return

    state = env._read_state()
    print(f"🔄 Restarting ComfyUI...")
    print(f"   Previous: PID {state.pid}, args: {' '.join(state.args)}")

    try:
        env.restart()
        new_state = env._read_state()
        print(f"✓ Restarted (new PID: {new_state.pid})")
    except Exception as e:
        print(f"✗ Failed to restart: {e}", file=sys.stderr)
        sys.exit(1)
```

---

### 9. CLI Auto-Restart Integration

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Update node_add command:**

```python
def node_add(self, args):
    """Add a custom node."""
    env = self._get_env(args)

    try:
        result = env.add_node(
            identifier=args.identifier,
            is_development=args.dev,
            no_test=args.no_test,
            force=args.force
        )

        print(f"✓ Added node: {result.node_info.name}")

        # Handle restart recommendation
        if result.restart_recommended and env.is_running():
            _handle_restart_recommendation(env, args, result.restart_reason)

    except CDNodeConflictError as e:
        # ... existing error handling ...
```

**Add restart handler helper:**

```python
def _handle_restart_recommendation(env, args, reason: str):
    """Handle restart recommendation based on CLI flags."""
    if args.no_restart:
        print(f"\n⚠️  ComfyUI is running. Changes won't take effect until restart.")
        print("   Restart with: comfydock restart")
        return

    if args.auto_restart:
        print(f"\n🔄 ComfyUI is running. Restarting to apply changes...")
        env.restart()
        print("✓ Restarted")
        return

    # Interactive prompt
    print(f"\n⚠️  ComfyUI is running. Restart to apply changes?")
    response = input("   (Y/n): ").strip().lower()

    if response in ('', 'y', 'yes'):
        print("🔄 Restarting...")
        env.restart()
        print("✓ Restarted")
    else:
        print("⚠️  Skipped restart. Changes won't take effect until you restart.")
```

---

### 10. CLI Argument Parsers

**File:** `packages/cli/comfydock_cli/cli.py`

**Update run parser:**

```python
run_parser = subparsers.add_parser("run", help="Run ComfyUI")
run_parser.add_argument(
    '--foreground', '-f',
    action='store_true',
    help='Stream logs in pseudo-foreground mode (Ctrl+C stops ComfyUI)'
)
run_parser.add_argument('--no-sync', action='store_true', help='Skip environment sync')
run_parser.set_defaults(func=env_cmds.run, args=[])
```

**Add logs parser:**

```python
logs_parser = subparsers.add_parser('logs', help='View ComfyUI logs')
logs_parser.add_argument('--follow', '-f', action='store_true', help='Follow log output')
logs_parser.add_argument('--tail', '-n', type=int, metavar='N', help='Show last N lines')
logs_parser.set_defaults(func=env_cmds.logs)
```

**Add stop and restart parsers:**

```python
stop_parser = subparsers.add_parser('stop', help='Stop running ComfyUI')
stop_parser.set_defaults(func=env_cmds.stop)

restart_parser = subparsers.add_parser('restart', help='Restart ComfyUI')
restart_parser.set_defaults(func=env_cmds.restart)
```

**Add auto-restart flags to node commands:**

```python
node_add_parser.add_argument('--auto-restart', action='store_true',
                             help='Automatically restart ComfyUI if running')
node_add_parser.add_argument('--no-restart', action='store_true',
                             help='Skip restart prompt')
```

---

### 11. Enhanced Repair Command

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Update repair() method:**

```python
@with_env_logging("env repair")
def repair(self, args, logger=None):
    """Repair environment to match pyproject.toml (+ clean stale process state)."""
    env = self._get_env(args)

    # NEW: Clean up stale process state files
    if env._state_file.exists():
        state = env._read_state()
        if state and not env.is_running():
            print("🧹 Cleaning up stale process state file...")
            env._clear_state()

    # Existing repair logic (unchanged)
    status = env.status()

    if status.is_synced:
        print("✓ No changes to apply")
        return

    # ... rest of existing repair implementation ...
```

---

### 12. Enhanced Status and List Commands

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Update status() to show process info:**

```python
@with_env_logging("env status")
def status(self, args):
    """Show environment status including process info."""
    env = self._get_env(args)
    status = env.status()

    print(f"Environment: {env.name}")

    # Process status section
    if env.is_running():
        state = env._read_state()
        uptime = state.get_uptime()
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        from comfydock_core.utils.process import check_http_health
        is_healthy = check_http_health(state.host, state.port, timeout=1.0)
        health_status = "✓ Healthy" if is_healthy else "⚠ Not responding"

        print("\n📋 Process:")
        print(f"   Status: Running ✓")
        print(f"   PID: {state.pid}")
        print(f"   URL: http://{state.host}:{state.port}")
        print(f"   Health: {health_status}")
        print(f"   Uptime: {uptime_str}")
        print(f"   Log: {state.log_path}")
    else:
        print("\n📋 Process:")
        print("   Status: Stopped")

    # ... rest of existing status output ...
```

**File:** `packages/cli/comfydock_cli/global_commands.py`

**Update list_envs() to show runtime status:**

```python
def list_envs(self, args):
    """List all environments with runtime status."""
    environments = self.workspace.list_environments()
    active_env = self.workspace.get_active_environment()
    active_name = active_env.name if active_env else None

    if not environments:
        print("No environments found.")
        print("Create one with: comfydock create <name>")
        return

    print("Environments:")
    for env in environments:
        marker = "✓" if env.name == active_name else " "
        active_label = "(active)" if env.name == active_name else "       "

        # Runtime status
        if env.is_running():
            state = env._read_state()
            host_display = "127.0.0.1" if state.host in ("0.0.0.0", "::") else state.host
            url = f"http://{host_display}:{state.port}"

            from comfydock_core.utils.process import check_http_health
            is_healthy = check_http_health(state.host, state.port, timeout=0.5)
            health_emoji = "✓" if is_healthy else "⚠"

            status = f"({health_emoji} running on {url}, PID {state.pid})"
        else:
            status = "(stopped)"

        print(f"  {marker} {env.name:15} {active_label} {status}")
```

---

## Cross-Platform Considerations

### Windows
- **Process Creation**: Use `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`
- **Signal Handling**: No SIGTERM support, rely on `process.terminate()` from psutil
- **Port Detection**: Falls back to socket binding test (no admin required)
- **File Handles**: Log file opened in parent but written by child (acceptable)

### Unix (Linux/macOS)
- **Process Creation**: Use `start_new_session=True`
- **Signal Handling**: SIGTERM → graceful shutdown, SIGKILL → force kill
- **Port Detection**: psutil works reliably

### All Platforms
- **Path Handling**: Use `pathlib.Path` exclusively
- **Log Line Endings**: Python text mode handles `\n` vs `\r\n` automatically

---

## Testing Strategy

### Unit Tests
- `test_process_utils.py`: Test PID checks, port binding, health checks
- `test_process_state.py`: Test ProcessState serialization
- `test_node_operation_result.py`: Test return value structures

### Integration Tests
- `test_environment_process.py`: Test run(), stop(), restart()
- `test_state_file_lifecycle.py`: Test state file creation/cleanup

### CLI Tests
- `test_run_command.py`: Test background and foreground modes
- `test_logs_command.py`: Test log viewing and streaming
- `test_auto_restart.py`: Test restart flags

---

## Implementation Checklist

### Phase 0: Pre-Implementation
- [ ] Add `psutil>=5.9.0` to `packages/core/pyproject.toml`
- [ ] Update GitManager to create `.cec/.gitignore`
- [ ] Add `NodeOperationResult` to `models/shared.py`

### Phase 1: Core
- [ ] Create `models/process.py` with `ProcessState`
- [ ] Create `utils/process.py` with platform utilities
- [ ] Add process methods to `Environment`
- [ ] Update `Environment.run()` for background mode
- [ ] Update `Environment.add_node()` return type

### Phase 2: CLI
- [ ] Add `logs`, `stop`, `restart` commands
- [ ] Update `run` command with `--foreground`
- [ ] Update `status` to show process info
- [ ] Update `list` to show runtime status

### Phase 3: Auto-Restart
- [ ] Add `--auto-restart`, `--no-restart` flags
- [ ] Implement `_handle_restart_recommendation()` helper
- [ ] Update `node_add`, `node_remove`, `node_update` commands
- [ ] Update `repair` command for stale state cleanup

### Phase 4: Testing & Docs
- [ ] Unit tests for process utilities
- [ ] Integration tests for Environment
- [ ] CLI tests for new commands
- [ ] Update user documentation
- [ ] Update CHANGELOG (breaking changes)

---

## Timeline Estimate

- **Phase 0:** 0.5 days (groundwork)
- **Phase 1:** 2-3 days (core process management)
- **Phase 2:** 1-2 days (CLI integration)
- **Phase 3:** 1 day (auto-restart)
- **Phase 4:** 1-2 days (testing and docs)

**Total:** ~6-9 days for full implementation

---

## Breaking Changes & Migration

### Breaking Changes
1. **`comfydock run` behavior**: Now starts in background (returns immediately)
2. **Return type change**: `add_node()` returns `NodeOperationResult` instead of `NodeInfo`

### Migration Path
- Use `--foreground` flag for old blocking behavior
- Version bump: 0.4.x → 0.5.0 (minor since pre-1.0)
- Document in CHANGELOG and user guide

---

**End of Implementation Plan**
