# Process Management Implementation Plan - REVISED (Docker-Ready)

**Status:** Ready for Implementation
**Target:** ComfyDock v2.0.0
**Architecture:** Background-always with pseudo-foreground mode (Docker-compatible)
**Breaking Changes:** Yes (background default, requires major version bump)
**Docker Readiness:** Designed for seamless Docker runtime integration

## Executive Summary

Implement background process management for ComfyUI with comprehensive logging and **Docker-ready abstractions**. All `comfydock run` invocations start ComfyUI as a background daemon (host process now, container later). The `--foreground` flag creates a pseudo-foreground experience by streaming logs while monitoring the background runtime.

**Key Benefits:**
- Eliminates foreground→background conversion complexity
- Enables seamless auto-restart for node operations
- Consistent cross-platform behavior
- Simplified multi-environment workflows
- **Unified API surface for host and Docker runtimes** (critical for roadmap)
- **Container-like UX today, actual containers tomorrow** (seamless transition)

**Architectural Decisions:**
- **Return Value Pattern**: Node operations return `NodeOperationResult` with restart recommendations; CLI layer handles all restart logic (avoids circular dependencies)
- **PID-Only Process Checking**: `is_running()` checks only PID for host (fast, reliable). Docker will use container status checks. HTTP health checks are **optional** and used only for display
- **Runtime Abstraction**: Code structured for easy Docker transition via runtime_type field and swappable utility functions
- **Child-Managed Logging**: Child process opens own log file (works for Docker stdout redirection)
- **Pre-Customer MVP Context**: Major breaking change acceptable; no users yet, can make sweeping improvements

**Docker Architecture (Future):**
- Single image: `comfydock/comfyui:latest` (no rebuilds needed)
- Workspace mount: User's `~/.comfydock` mounted to container `/workspace`
- Shared caches: uv cache, model cache, registry cache persist between host and container
- Same commands: `comfydock run`, `logs`, `stop`, `restart` work identically for both runtimes

---

## Why Docker-Ready Architecture Matters

This plan implements **more than just background process management**—it creates a **unified runtime abstraction** that will seamlessly support Docker containers without major refactoring.

### The Problem Without Abstraction

**Bad approach (requires full rewrite for Docker):**
```python
# Environment.py - tightly coupled to host processes
def run(self):
    process = subprocess.Popen(["python", "main.py"])  # Host-only
    self.pid = process.pid
    return process
```

When Docker arrives, this requires:
- Rewriting all process management code
- Changing state file format
- Breaking existing environments
- ~2-3 weeks of refactoring + testing

### Our Approach (Docker-Ready Today)

**Good approach (Docker support is just a new code path):**
```python
# Environment.py - runtime-agnostic
def run(self):
    if runtime_type == "host":
        state = _run_host()  # Current implementation
    elif runtime_type == "docker":
        state = _run_docker()  # Future implementation (3-5 days to add)
    self._write_state(state)
```

When Docker arrives:
- Implement `_run_docker()` (1 day)
- Add `--runtime` flag (1 day)
- Test both modes (1-2 days)
- **Total: 3-5 days** (vs. 2-3 weeks for rewrite)

### Concrete Benefits

1. **Same user commands for both runtimes:**
   ```bash
   # Host mode (today)
   comfydock run --env prod
   comfydock logs --follow
   comfydock restart

   # Docker mode (tomorrow, same commands)
   comfydock run --env prod --runtime docker
   comfydock logs --follow  # Uses 'docker logs'
   comfydock restart  # Restarts container
   ```

2. **State file works for both:**
   ```json
   {
     "runtime_type": "host",  // or "docker"
     "pid": 12345,            // Process PID or container PID
     "log_path": "/path",     // File path or container name
     "container_id": null     // Populated for docker
   }
   ```

3. **Abstraction markers guide future work:**
   ```python
   def is_process_alive(pid):
       """Check if process exists (HOST RUNTIME).

       Docker equivalent:
           docker inspect --format='{{.State.Running}}' <container>
       """
   ```

### Investment Justification

**Extra effort for Docker-readiness:**
- +1 day design time (runtime_type schema, abstraction markers)
- +0.5 days implementation (dispatch logic, Docker comments)
- +0.5 days testing (ensure abstraction doesn't leak)

**Total extra cost:** ~2 days

**Savings when adding Docker:** ~10-15 days (avoiding rewrite)

**Net benefit:** ~8-13 days saved + cleaner codebase

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

### Process State Checking vs Health Checks

**Core Process Detection (`is_running()`):**
- **Only checks PID** using `psutil.Process(pid).is_running()`
- Verifies it's a Python process (prevents PID reuse false positives)
- Fast and reliable for determining if ComfyUI is running
- Used for all core logic (restart decisions, state cleanup, etc.)

**HTTP Health Checks (`check_http_health()`):**
- **Optional** - used ONLY for display in `status` and `list` commands
- Adds confidence by verifying ComfyUI HTTP server is responding
- Not used for core process management decisions
- Helps users distinguish between "process running" vs "server ready"

**Example Status Display:**
```
📋 Process:
   Status: Running ✓
   PID: 12345
   URL: http://127.0.0.1:8188
   Health: ✓ Healthy          ← HTTP check (optional, display only)
   Uptime: 15m
```

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
- ~~Add `psutil>=5.9.0` to `packages/core/pyproject.toml`~~ **SKIP** - Already present as `psutil>=7.0.0` ✓
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
- Add `--restart`, `--no-restart` flags to node commands
- Implement restart handling in CLI (no NodeManager changes needed)
- Update `repair` command to clean stale state files

### Phase 4: Testing & Documentation
- Unit tests for process utilities
- Integration tests for Environment process methods
- CLI tests for new commands
- Update user documentation

---

## Detailed Implementation

### 1. ProcessState Model (Docker-Ready)

**File:** `packages/core/src/comfydock_core/models/process.py` (NEW FILE)

```python
"""Process state management models."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal


@dataclass
class ProcessState:
    """State of a running ComfyUI process or container.

    This model supports both host processes (current) and Docker containers (future).
    The runtime_type field enables seamless transition between execution modes.
    """

    # Runtime identification
    runtime_type: Literal["host", "docker"] = "host"  # Docker support added later

    # Process/container identification (field name kept as 'pid' for host compatibility)
    pid: int                    # Process ID (host) or container PID (docker)

    # Network configuration
    host: str                   # From --listen arg (e.g., "0.0.0.0")
    port: int                   # From --port arg (e.g., 8188)

    # Runtime configuration
    args: list[str]             # Full args for restart (host: python args, docker: docker run args)
    started_at: str             # ISO timestamp
    log_path: str               # File path (host) or container name (docker logs <container>)

    # Optional health tracking
    last_health_check: str | None = None
    health_status: str | None = None  # "healthy", "unhealthy", "unknown"

    # Docker-specific fields (future, all optional for now)
    container_id: str | None = None      # Full container ID (docker only)
    image_tag: str | None = None         # Image used (docker only)

    def to_dict(self) -> dict:
        """Serialize to JSON for state file."""
        return {
            "runtime_type": self.runtime_type,
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "args": self.args,
            "started_at": self.started_at,
            "log_path": self.log_path,
            "health": {
                "last_check": self.last_health_check,
                "status": self.health_status
            },
            # Docker fields (optional)
            "container_id": self.container_id,
            "image_tag": self.image_tag,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessState":
        """Deserialize from state file.

        Handles both old format (no runtime_type) and new format.
        """
        health = data.get("health", {})
        return cls(
            runtime_type=data.get("runtime_type", "host"),  # Default to host for old state files
            pid=data["pid"],
            host=data["host"],
            port=data["port"],
            args=data["args"],
            started_at=data["started_at"],
            log_path=data["log_path"],
            last_health_check=health.get("last_check"),
            health_status=health.get("status"),
            container_id=data.get("container_id"),
            image_tag=data.get("image_tag"),
        )

    def get_uptime(self) -> timedelta:
        """Calculate uptime from started_at."""
        started = datetime.fromisoformat(self.started_at)
        return datetime.now() - started
```

**State File Location:** `environments/<env_name>/.cec/.comfyui.state`

**Docker Transition Notes:**
- `runtime_type="host"`: Current implementation (background Python process)
- `runtime_type="docker"`: Future implementation (container via Docker CLI)
- Same state file format works for both, just different field interpretations
- When Docker is added, `pid` becomes container PID, `log_path` becomes container name

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

### 3. Background Process Utilities (Docker-Ready)

**File:** `packages/core/src/comfydock_core/utils/process.py` (NEW FILE)

```python
"""Process management utilities for ComfyUI daemon.

This module is designed to support both host processes (current) and Docker
containers (future) with minimal changes. Functions are structured to be easily
swappable based on runtime_type.
"""

import os
import sys
import subprocess
from pathlib import Path


def create_background_process(
    cmd: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_to_stdout: bool = True,
    env: dict | None = None
) -> subprocess.Popen:
    """Start a background process with logging (HOST RUNTIME).

    IMPORTANT: This function does NOT pass file handles to the child.
    Instead, it uses subprocess redirection to have the child open the
    log file itself. This approach:
    - Works reliably on Windows (no file handle inheritance issues)
    - Translates cleanly to Docker (where logs go to stdout)
    - Prevents file handle leaks

    Args:
        cmd: Command and arguments to execute
        cwd: Working directory for process
        stdout_path: Path where stdout should be written
        stderr_to_stdout: Merge stderr into stdout
        env: Environment variables (defaults to parent's env)

    Returns:
        Subprocess.Popen object (detached from terminal)

    Docker equivalent:
        docker run -d \\
            --name <container> \\
            -v <workspace>:/workspace \\
            -w /workspace/ComfyUI \\
            comfydock/comfyui:latest \\
            python main.py <args>
        # Logs retrieved via: docker logs <container>
    """
    # Open log file for child to write to
    log_file = open(stdout_path, "w", buffering=1, encoding="utf-8")

    kwargs = {
        'stdout': log_file,
        'stderr': log_file if stderr_to_stdout else subprocess.PIPE,
        'stdin': subprocess.DEVNULL,
        'cwd': str(cwd),
        'env': env or os.environ.copy(),
        'close_fds': True,  # Close parent's file descriptors in child
    }

    # Platform-specific detachment
    if sys.platform == 'win32':
        kwargs['creationflags'] = (
            subprocess.CREATE_NEW_PROCESS_GROUP |
            subprocess.DETACHED_PROCESS
        )
    else:
        kwargs['start_new_session'] = True  # Unix: detach from terminal

    process = subprocess.Popen(cmd, **kwargs)

    # CRITICAL: Don't close log_file here - child needs it
    # File will be closed when child exits
    # This prevents Windows file locking issues

    return process


def is_process_alive(pid: int, cwd: Path | None = None) -> bool:
    """Check if process exists and is a Python process (HOST RUNTIME).

    Enhanced verification to prevent PID reuse false positives.

    Args:
        pid: Process ID to check
        cwd: Expected working directory (optional, for stronger verification)

    Returns:
        True if process is alive and verified

    Docker equivalent:
        docker inspect --format='{{.State.Running}}' <container_id>
    """
    try:
        import psutil
        process = psutil.Process(pid)

        if not process.is_running():
            return False

        # Verify it's Python (handles python, python3, python.exe, pythonw.exe)
        name_lower = process.name().lower()
        if 'python' not in name_lower:
            return False

        # Optional: Verify working directory matches (prevents PID reuse)
        if cwd:
            try:
                proc_cwd = process.cwd()
                if proc_cwd != str(cwd):
                    return False
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                # Can't verify cwd, but process exists
                pass

        return True

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def is_port_bound(port: int, expected_pid: int | None = None) -> bool:
    """Check if port is in use (HOST RUNTIME).

    Args:
        port: Port number to check
        expected_pid: If provided, verify this PID owns the port

    Returns:
        True if port is bound

    Docker equivalent:
        docker port <container> | grep <port>
    """
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
    """Check if ComfyUI HTTP endpoint is responding.

    NOTE: This is OPTIONAL - used only for display in status/list commands.
    Core process management (is_running, restart logic) uses PID/container checks only.

    Works for both host and Docker (containers expose ports to host).

    Args:
        host: Host to check (e.g., "127.0.0.1", "0.0.0.0")
        port: Port to check
        timeout: Request timeout in seconds

    Returns:
        True if endpoint responds with 200
    """
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


def stream_file_logs(log_path: Path, follow: bool = False) -> subprocess.Popen | None:
    """Stream log file efficiently (HOST RUNTIME).

    Uses platform-specific efficient methods instead of readline() polling.

    Args:
        log_path: Path to log file
        follow: If True, follow log file in real-time (like tail -f)

    Returns:
        Subprocess handle for background streaming, or None for one-shot

    Docker equivalent:
        docker logs <container> [--follow]
    """
    if not follow:
        # One-shot: just print the file
        print(log_path.read_text(), end='')
        return None

    # Follow mode: use platform-specific efficient tailing
    if sys.platform == 'win32':
        # Windows: PowerShell Get-Content -Wait
        cmd = ['powershell', '-Command', f'Get-Content "{log_path}" -Wait']
    else:
        # Unix: tail -f
        cmd = ['tail', '-f', str(log_path)]

    # Stream to stdout (no capture)
    process = subprocess.Popen(
        cmd,
        stdout=None,  # Inherit parent's stdout
        stderr=subprocess.DEVNULL
    )
    return process
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
    """Write process state to file atomically.

    Uses atomic write pattern to prevent corruption on power loss/crash.
    """
    import json
    import tempfile

    state_json = json.dumps(state.to_dict(), indent=2)

    # Write to temp file first, then atomic rename
    temp_path = self._state_file.with_suffix('.tmp')
    temp_path.write_text(state_json)
    temp_path.replace(self._state_file)  # Atomic on POSIX, near-atomic on Windows

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
    """Run ComfyUI in background with logging (HOST RUNTIME).

    ALWAYS starts ComfyUI as a background daemon process.
    Output is written to workspace log file.

    Docker equivalent:
        docker run -d \\
            --name comfydock-{env_name} \\
            -v {workspace}:/workspace \\
            -p {port}:8188 \\
            comfydock/comfyui:latest \\
            python main.py {args}
    """
    from datetime import datetime
    from ..utils.process import is_port_bound

    # Check if already running
    if self.is_running():
        state = self._read_state()
        raise CDEnvironmentError(
            f"ComfyUI is already running (PID {state.pid}, port {state.port})"
        )

    # Parse arguments for state tracking
    config = self._parse_comfyui_args(args or [])

    # Check for port conflicts BEFORE starting (early detection)
    if is_port_bound(config.port):
        raise CDEnvironmentError(
            f"Port {config.port} is already in use.\n\n"
            f"Possible solutions:\n"
            f"  • Stop the other service using this port\n"
            f"  • Use a different port: comfydock run --port <number>\n"
            f"  • Check what's using the port: lsof -i:{config.port} (Unix) or netstat -ano | findstr :{config.port} (Windows)"
        )

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

    # Build command
    python = self.uv_manager.python_executable
    cmd = [str(python), "main.py"] + (args or [])

    logger.info(f"Starting ComfyUI in background: {' '.join(cmd)}")

    # Start background process (child opens log file itself)
    process = create_background_process(
        cmd=cmd,
        cwd=self.comfyui_path,
        stdout_path=log_path,
        stderr_to_stdout=True
    )

    # Write state file atomically
    state = ProcessState(
        runtime_type="host",  # Docker runtime added later
        pid=process.pid,
        host=config.host,
        port=config.port,
        args=args or [],
        started_at=datetime.now().isoformat(),
        log_path=str(log_path)
    )
    self._write_state(state)

    logger.info(f"ComfyUI started: PID {process.pid}, port {config.port}")

    # Optional: Monitor startup for first few seconds (detect early failures)
    # This is a UX enhancement - if the process dies immediately (e.g., port
    # binding fails AFTER our check due to race condition), we can report it
    import time
    time.sleep(0.5)  # Give process time to fail on startup errors

    if not self.is_running():
        # Process died immediately - read last few lines of log for error
        try:
            log_lines = log_path.read_text().strip().split('\n')
            error_hint = '\n'.join(log_lines[-5:])  # Last 5 lines
            raise CDEnvironmentError(
                f"ComfyUI failed to start. Check logs at: {log_path}\n\n"
                f"Recent output:\n{error_hint}"
            )
        except Exception:
            raise CDEnvironmentError(
                f"ComfyUI failed to start. Check logs at: {log_path}"
            )

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
    """Check if ComfyUI is running (HOST RUNTIME: PID check).

    This method checks if the process is alive via PID with enhanced
    verification (working directory check) to prevent PID reuse false positives.

    It does NOT perform HTTP health checks - those are optional and used only
    for display purposes in status/list commands.

    Returns:
        True if process is alive, False otherwise

    Docker equivalent:
        docker inspect --format='{{.State.Running}}' comfydock-{env_name}
    """
    state = self._read_state()
    if not state:
        return False

    # Enhanced PID check with working directory verification
    if not is_process_alive(state.pid, cwd=self.comfyui_path):
        logger.debug(f"PID {state.pid} not alive or cwd mismatch, clearing state")
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
from comfydock_core.utils.process import stream_file_logs

def _stream_logs_with_monitoring(env, state):
    """Stream logs while monitoring process (efficient platform-specific tailing)."""
    log_path = Path(state.log_path)

    # Register signal handler for cleanup
    def signal_handler(signum, frame):
        print(f"\n\nReceived signal {signum}, stopping ComfyUI...")
        env.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):  # Unix only
        signal.signal(signal.SIGTERM, signal_handler)

    # Stream logs using platform-specific efficient method (tail -f / Get-Content -Wait)
    log_stream = stream_file_logs(log_path, follow=True)

    # Monitor process while streaming runs in background
    try:
        while True:
            # Check if ComfyUI process died
            if not env.is_running():
                print("\n\n⚠️  ComfyUI process exited")
                if log_stream:
                    log_stream.terminate()
                break

            # Check if log stream died (shouldn't happen)
            if log_stream and log_stream.poll() is not None:
                print("\n\n⚠️  Log stream ended unexpectedly")
                break

            time.sleep(1)  # Check every second
    except KeyboardInterrupt:
        # Handled by signal handler
        pass
    finally:
        if log_stream:
            log_stream.terminate()
```

---

### 8. CLI New Commands

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Add logs command:**

```python
from comfydock_core.utils.process import stream_file_logs

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
    """Stream logs in real-time (efficient platform-specific method)."""
    print(f"Following logs (Ctrl+C to exit)...")
    print("=" * 60)

    # Use efficient streaming (tail -f on Unix, Get-Content -Wait on Windows)
    log_stream = stream_file_logs(log_path, follow=True)

    try:
        # Wait for log stream to finish (or user Ctrl+C)
        while log_stream and log_stream.poll() is None:
            # Also check if ComfyUI died
            if not env.is_running():
                print("\n\n⚠️  ComfyUI process exited")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
    finally:
        if log_stream:
            log_stream.terminate()

def _show_tail(log_path: Path, n: int):
    """Show last N lines."""
    with open(log_path, 'r') as f:
        lines = f.readlines()
        for line in lines[-n:]:
            print(line, end='')

def _show_all_logs(log_path: Path):
    """Show all logs (one-shot, no streaming)."""
    stream_file_logs(log_path, follow=False)  # Efficient file read
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

    if args.restart:
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

**Add restart flags to node commands (mutually exclusive):**

```python
# Create mutually exclusive group to prevent both flags being used
restart_group = node_add_parser.add_mutually_exclusive_group()
restart_group.add_argument('--restart', action='store_true',
                           help='Automatically restart ComfyUI if running')
restart_group.add_argument('--no-restart', action='store_true',
                           help='Skip restart prompt')

# Apply same pattern to node_remove_parser and node_update_parser
```

---

### 11. Enhanced Repair Command

**File:** `packages/cli/comfydock_cli/env_commands.py`

The `repair` command now handles two orthogonal concerns:

1. **Environment Repair (default)**: Syncs environment with pyproject.toml
   - Updates packages, nodes, workflows
   - **May modify/delete files in ComfyUI directory**
   - Existing behavior (no changes)

2. **Process Repair (`--orphan` flag)**: ONLY handles process/state issues
   - Cleans stale state files
   - Detects orphaned ComfyUI processes
   - **Does NOT touch environment files** (safe for users with uncommitted changes)

**Update repair() method:**

```python
@with_env_logging("env repair")
def repair(self, args, logger=None):
    """Repair environment or process state.

    Default: Sync environment with pyproject.toml (may modify ComfyUI files)
    --orphan: Only repair process state (safe, no environment changes)
    """
    env = self._get_env(args)

    # Orphan mode: ONLY handle process/state issues
    if args.orphan:
        _repair_orphaned_processes(env)
        return

    # Default mode: Full environment repair + state cleanup

    # Clean up stale process state files (safe to do in any mode)
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


def _repair_orphaned_processes(env):
    """Repair process state without touching environment files.

    This is SAFE to run even with uncommitted ComfyUI changes.
    """
    print("🔍 Checking for process/state issues...")

    # Check 1: Stale state file (PID dead)
    if env._state_file.exists():
        state = env._read_state()
        if state and not env.is_running():
            print("  Found stale state file (process dead)")
            env._clear_state()
            print("  ✓ Cleaned state file")

    # Check 2: Orphaned ComfyUI processes (future enhancement)
    # Detect Python processes running main.py in this environment's ComfyUI directory
    # that don't have a corresponding state file
    orphaned_pids = _detect_orphaned_comfyui_processes(env)

    if orphaned_pids:
        print(f"\n⚠️  Found {len(orphaned_pids)} orphaned ComfyUI process(es):")
        for pid in orphaned_pids:
            print(f"  • PID {pid}")

        response = input("\nKill orphaned processes? (y/N): ").strip().lower()
        if response == 'y':
            import psutil
            for pid in orphaned_pids:
                try:
                    psutil.Process(pid).terminate()
                    print(f"  ✓ Killed PID {pid}")
                except Exception as e:
                    print(f"  ✗ Failed to kill PID {pid}: {e}")
        else:
            print("  Skipped. Orphaned processes left running.")
    else:
        print("  ✓ No orphaned processes found")

    print("\n✓ Process repair complete (no environment changes made)")


def _detect_orphaned_comfyui_processes(env) -> list[int]:
    """Detect ComfyUI processes running without a state file.

    Returns:
        List of PIDs for orphaned processes
    """
    import psutil

    orphaned_pids = []

    # Get state file PID (if exists)
    state = env._read_state()
    tracked_pid = state.pid if state else None

    # Find all Python processes running main.py in this environment's ComfyUI path
    comfyui_path_str = str(env.comfyui_path)

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check if it's a Python process
            if 'python' not in proc.info['name'].lower():
                continue

            # Check if it's running main.py in our ComfyUI directory
            cmdline = proc.info.get('cmdline', [])
            if not cmdline:
                continue

            # Look for main.py in command line
            if 'main.py' not in ' '.join(cmdline):
                continue

            # Check if working directory matches our ComfyUI path
            if proc.cwd() != comfyui_path_str:
                continue

            # If we got here, it's a ComfyUI process for this environment
            # Check if it's tracked
            if proc.pid != tracked_pid:
                orphaned_pids.append(proc.pid)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return orphaned_pids
```

**Update CLI argument parser:**

```python
repair_parser = subparsers.add_parser('repair',
    help='Repair environment or process state')
repair_parser.add_argument('--orphan', action='store_true',
    help='Only repair orphaned processes/state (safe, no environment changes)')
repair_parser.set_defaults(func=env_cmds.repair)
```

**Design Rationale:**

The `--orphan` flag prevents accidental data loss:
- Users with uncommitted ComfyUI changes can safely run `repair --orphan`
- Regular `repair` might nuke their changes by syncing with pyproject.toml
- Separating concerns makes each operation's scope clear and predictable

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

### Critical Tests (Not Optional for MVP)

These tests are **essential** for process management reliability. Unlike typical feature development where 2-3 happy path tests suffice, process management requires rigorous edge case testing to prevent data loss and system instability.

#### Unit Tests (Required)
- `test_process_utils.py`:
  - **PID reuse prevention**: Start process, kill it, start unrelated Python process with recycled PID, verify state cleanup
  - **Port binding detection**: Verify port conflict detection before startup
  - **Enhanced process verification**: Verify working directory checks work correctly
  - **HTTP health checks**: Verify optional health checks don't block core logic

- `test_process_state.py`:
  - **Serialization round-trip**: Verify state file survives write/read cycle
  - **Backward compatibility**: Old state files (no runtime_type) load correctly
  - **Atomic writes**: Verify temp file → rename pattern works on all platforms

- `test_node_operation_result.py`:
  - **Return value pattern**: Verify restart recommendations propagate correctly

#### Integration Tests (Required)
- `test_environment_process.py`:
  - **run() → stop() → run()**: Verify clean restart cycle
  - **Startup failure detection**: Kill process immediately after start, verify error reporting
  - **Port conflict on startup**: Bind port, try to start ComfyUI, verify helpful error message

- `test_state_file_lifecycle.py`:
  - **Normal lifecycle**: State created on run(), cleared on stop()
  - **Crash recovery**: Kill process without stop(), verify stale state cleanup on next is_running()
  - **Corrupted state file**: Invalid JSON, verify graceful degradation

- `test_cross_platform.py` (run on Windows + Unix):
  - **Log file handling**: Verify child opens log file correctly on both platforms
  - **Process detachment**: Verify parent can exit without killing child
  - **Signal handling**: SIGTERM (Unix) vs process.terminate() (Windows)

#### CLI Tests (Standard)
- `test_run_command.py`: Background and foreground modes
- `test_logs_command.py`: Log viewing and streaming (verify tail -f / Get-Content -Wait work)
- `test_auto_restart.py`: Restart flags (mutually exclusive validation)
- `test_repair_orphan.py`: Orphaned process detection and cleanup

### Testing Philosophy for Process Management

Process management is **infrastructure code**, not application code. The cost of a bug is:
- **Data loss**: User's generated images corrupted during unclean restart
- **System instability**: Orphaned processes consuming GPU resources
- **Port conflicts**: ComfyUI failing to start with cryptic errors
- **File corruption**: State files corrupted on power loss

Therefore, we test **edge cases** and **failure modes**, not just happy paths. This is one area where the "2-3 tests per file" MVP guidance doesn't apply.

---

## Implementation Checklist

### Phase 0: Pre-Implementation (0.5 days)
- [x] ~~Add `psutil>=5.9.0`~~ **SKIP** - Already present as `psutil>=7.0.0` ✓
- [ ] Add `NodeOperationResult` to `models/shared.py`
- [ ] Update `NodeRemovalResult` and `UpdateResult` with restart fields
- [ ] Update GitManager to create `.cec/.gitignore` with `.comfyui.state`
- [ ] Add `ComfyUIConfig` dataclass to `models/process.py`

### Phase 1: Core Process Management (2-3 days)
- [ ] Create `models/process.py`:
  - [ ] `ProcessState` dataclass with serialization
  - [ ] `ComfyUIConfig` dataclass for argument parsing
- [ ] Create `utils/process.py` with platform-specific utilities:
  - [ ] `create_background_process()` - cross-platform detachment
  - [ ] `is_process_alive()` - PID check with Python process verification
  - [ ] `is_port_bound()` - port conflict detection with fallback
  - [ ] `check_http_health()` - optional HTTP endpoint check (display only)
- [ ] Add process methods to `Environment` class:
  - [ ] `_state_file` property
  - [ ] `_write_state()` - **atomic write using Path.replace()**
  - [ ] `_read_state()` - with validation and error handling
  - [ ] `_clear_state()` - remove state file
  - [ ] `_parse_comfyui_args()` - extract host/port from args
  - [ ] `run()` - **background-always with port conflict check and file handle cleanup**
  - [ ] `is_running()` - **PID-only check (no HTTP)**
  - [ ] `stop()` - graceful termination with timeout and force-kill fallback
  - [ ] `restart()` - stop + start with same args
- [ ] Update `Environment.add_node()` to wrap `NodeInfo` in `NodeOperationResult`

### Phase 2: CLI Integration (1-2 days)
- [ ] Add new commands:
  - [ ] `logs` command with `--follow` and `--tail` flags
  - [ ] `stop` command
  - [ ] `restart` command
- [ ] Update `run` command:
  - [ ] Add `--foreground` flag
  - [ ] Implement `_stream_logs_with_monitoring()` with signal handler
  - [ ] Add file handle cleanup after process start
- [ ] Update display commands:
  - [ ] `status` - show process info (PID, uptime) + optional HTTP health
  - [ ] `list` - show runtime status per environment + optional HTTP health

### Phase 3: Auto-Restart Integration (1 day)
- [ ] Add **mutually exclusive** `--restart` and `--no-restart` flags to:
  - [ ] `node add` command
  - [ ] `node remove` command
  - [ ] `node update` command
- [ ] Implement `_handle_restart_recommendation()` helper in CLI
- [ ] Update `repair` command:
  - [ ] Default mode: Clean stale state files + existing environment sync
  - [ ] Add `--orphan` flag for process-only repair (no environment changes)
  - [ ] Implement `_repair_orphaned_processes()` helper
  - [ ] Implement `_detect_orphaned_comfyui_processes()` helper

### Phase 4: Testing & Documentation (1-2 days)
- [ ] Unit tests:
  - [ ] `test_process_utils.py` - PID checks, port binding, health checks
  - [ ] `test_process_state.py` - ProcessState serialization
  - [ ] `test_node_operation_result.py` - Return value structures
  - [ ] `test_atomic_state_write.py` - Verify atomic writes work correctly
- [ ] Integration tests:
  - [ ] `test_environment_process.py` - run(), stop(), restart()
  - [ ] `test_state_file_lifecycle.py` - State file creation/cleanup/corruption recovery
  - [ ] `test_port_conflicts.py` - Port conflict detection
- [ ] CLI tests:
  - [ ] `test_run_command.py` - Background and foreground modes
  - [ ] `test_logs_command.py` - Log viewing and streaming
  - [ ] `test_auto_restart.py` - Restart flags (mutually exclusive validation)
  - [ ] `test_repair_orphan.py` - Orphaned process detection and cleanup
- [ ] Documentation:
  - [ ] Update user guide with new commands (`logs`, `stop`, `restart`, `repair --orphan`)
  - [ ] Document `comfydock run` behavior change (background-always)
  - [ ] Document known limitations (log rotation timing, no workflow execution protection)
  - [ ] Update CHANGELOG with breaking changes
  - [ ] Create migration guide for v1.0.0 → v2.0.0

---

## Timeline Estimate

- **Phase 0:** 0.5-1 days (groundwork + Docker-ready schema)
- **Phase 1:** 3-4 days (core process management + startup monitoring + enhanced verification)
- **Phase 2:** 1.5-2 days (CLI integration + efficient log streaming)
- **Phase 3:** 1 day (auto-restart integration)
- **Phase 4:** 2-3 days (comprehensive testing + cross-platform validation + docs)

**Total:** ~8-11 days for full Docker-ready implementation

**Rationale for timeline adjustments:**
- Added 0.5 days for Docker-ready schema design (runtime_type, container fields)
- Added 1 day for enhanced process verification (cwd checks, startup monitoring)
- Added 0.5 days for platform-specific log streaming (tail -f / Get-Content -Wait)
- Added 1 day for critical cross-platform testing (PID reuse, port conflicts, crash recovery)

**Docker Transition (Future):**
Once this implementation is stable, adding Docker runtime support should take ~3-5 days:
- 1 day: Implement Docker process utilities (container start/stop/logs)
- 1 day: Update Environment.run() to dispatch based on runtime_type
- 1 day: CLI flag for --runtime=docker
- 1-2 days: Testing and documentation

---

## Breaking Changes & Migration

### Breaking Changes

1. **`comfydock run` behavior**: Now starts in background (returns immediately)
   - **Old**: Blocking foreground process (Ctrl+C kills ComfyUI)
   - **New**: Background daemon (returns immediately, shows tip to view logs)
   - **Migration**: Use `comfydock run --foreground` for old behavior

2. **Return type change**: `Environment.add_node()` returns `NodeOperationResult` instead of `NodeInfo`
   - **Old**: `node_info = env.add_node(...)`
   - **New**: `result = env.add_node(...); node_info = result.node_info`
   - **Impact**: Any code calling `Environment.add_node()` directly needs update
   - **Note**: CLI already handles this internally, so most users unaffected

### Version Bump

**v1.0.0 → v2.0.0** (Major version bump)

**Context**: This is acceptable because:
- **Pre-customer MVP**: No production users yet, can make sweeping improvements
- **Major architectural improvement**: Background-always pattern is significantly better
- **Clear migration path**: `--foreground` flag provides backward compatibility

### Migration Guide

**For End Users (CLI):**
```bash
# Old behavior (blocking):
comfydock run

# New behavior (background):
comfydock run                    # Returns immediately
comfydock logs --follow          # View logs

# Want old behavior?
comfydock run --foreground       # Streams logs, Ctrl+C stops ComfyUI
```

**For Library Users (Python API):**
```python
# Old code:
node_info = env.add_node("rgthree-comfy")

# New code:
result = env.add_node("rgthree-comfy")
node_info = result.node_info
if result.restart_recommended:
    # Handle restart logic
    pass
```

**CHANGELOG Entry:**
```markdown
## v2.0.0 (BREAKING CHANGES)

### Changed
- **BREAKING**: `comfydock run` now starts ComfyUI in background by default
  - Use `--foreground` flag for old blocking behavior
  - Background mode enables better multi-environment workflows and auto-restart
- **BREAKING**: `Environment.add_node()` returns `NodeOperationResult` instead of `NodeInfo`
  - Access node info via `result.node_info`
  - New `restart_recommended` field enables smart restart handling

### Added
- Background process management with automatic state tracking
- New commands: `logs`, `stop`, `restart`
- Auto-restart support for node operations (`--restart`, `--no-restart` flags)
- `repair --orphan` flag for safe process repair without environment changes
- Process status in `status` and `list` commands with optional HTTP health checks

### Fixed
- State file corruption on power loss (now uses atomic writes)
- Port conflict detection prevents multiple ComfyUI instances on same port
- File handle leaks in background process spawning

### Migration
- See migration guide: docs/migration-v2.md
```

---

## Docker Runtime Preparation

This implementation is designed for **seamless Docker transition**. The abstraction points below enable adding Docker runtime support with minimal refactoring.

### Runtime Abstraction Strategy

**Current (Host Runtime):**
```python
# utils/process.py - All functions marked "HOST RUNTIME"
state = ProcessState(runtime_type="host", pid=12345, ...)
is_process_alive(state.pid, cwd=comfyui_path)  # PID check
create_background_process(cmd, cwd, stdout_path)  # Detached Python process
```

**Future (Docker Runtime):**
```python
# New file: utils/docker_process.py
def is_container_running(container_id: str) -> bool:
    """Check if container is running (DOCKER RUNTIME)."""
    result = subprocess.run(
        ["docker", "inspect", "--format={{.State.Running}}", container_id],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "true"

def create_docker_container(env_name: str, workspace_path: Path, args: list[str]) -> str:
    """Start ComfyUI in Docker container (DOCKER RUNTIME)."""
    cmd = [
        "docker", "run", "-d",
        "--name", f"comfydock-{env_name}",
        "-v", f"{workspace_path}:/workspace",
        "-p", "8188:8188",
        "comfydock/comfyui:latest",
        "python", "main.py", *args
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()  # Container ID

# State file with Docker runtime
state = ProcessState(
    runtime_type="docker",
    pid=container_pid,  # Container's main process PID
    container_id="abc123...",
    image_tag="comfydock/comfyui:latest",
    ...
)
```

**Unified Environment API (No Changes Needed):**
```python
# Environment class (works for both runtimes)
def is_running(self) -> bool:
    state = self._read_state()
    if not state:
        return False

    # Dispatch based on runtime_type
    if state.runtime_type == "host":
        return is_process_alive(state.pid, cwd=self.comfyui_path)
    elif state.runtime_type == "docker":
        return is_container_running(state.container_id)

def run(self, args):
    # Dispatch based on user's --runtime flag or environment config
    if self.runtime_type == "host":
        # Current implementation
        process = create_background_process(...)
        state = ProcessState(runtime_type="host", pid=process.pid, ...)
    elif self.runtime_type == "docker":
        # Future implementation
        container_id = create_docker_container(self.name, self.workspace_paths.root, args)
        state = ProcessState(runtime_type="docker", container_id=container_id, ...)

    self._write_state(state)
```

### Docker Architecture Details

**Single Image + Workspace Mount (No Rebuilds):**
```dockerfile
# comfydock/comfyui:latest
FROM python:3.11-slim
RUN pip install uv
WORKDIR /workspace/environment/ComfyUI
ENTRYPOINT ["python", "main.py"]
```

**Container Run Command:**
```bash
docker run -d \
  --name comfydock-prod \
  -v ~/.comfydock:/workspace \
  -v ~/.comfydock/cache:/workspace/cache \
  -p 8188:8188 \
  comfydock/comfyui:latest \
  --listen 0.0.0.0 --port 8188
```

**Why This Works:**
- User's entire workspace (`~/.comfydock`) is mounted to `/workspace`
- Container sees the environment's ComfyUI directory, custom nodes, models
- uv cache is shared (fast package installs)
- No image rebuilds needed for node operations - just restart container
- `comfydock node add` updates pyproject.toml → `uv sync` → `comfydock restart` → container picks up changes

### Migration Path (When Adding Docker)

**Phase 1: Add Docker Utilities (1 day)**
- Create `utils/docker_process.py` with container equivalents of host functions
- Add `--runtime=docker` flag to CLI (defaults to `host`)

**Phase 2: Update Environment Dispatch (1 day)**
- Modify `Environment.run()` to check `runtime_type` and dispatch
- Modify `Environment.is_running()`, `stop()`, `restart()` similarly

**Phase 3: CLI Changes (1 day)**
- `comfydock logs` → dispatch to `docker logs <container>` for Docker runtime
- `comfydock status` → parse `docker inspect` output for Docker runtime

**Phase 4: Testing (1-2 days)**
- Test both runtimes side-by-side
- Verify workspace mount works correctly
- Validate cache sharing

**Total Docker Addition:** ~3-5 days (thanks to abstraction)

### Abstraction Markers in Current Code

Throughout the implementation, look for these markers:
```python
# (HOST RUNTIME) - Function only works for host processes
# Docker equivalent: <command> - Shows what the Docker version would be
```

These comments make future refactoring trivial - just implement the Docker equivalent and add the dispatch logic.

---

## Known Limitations (Documented as Acceptable for MVP)

1. **No workflow execution protection**: Restarting during workflow execution may cause data loss
   - Future: Add workflow execution detection via ComfyUI API
   - Workaround: User responsibility to not restart during long-running workflows

2. **Log rotation only on process start**: Logs don't rotate while ComfyUI is running
   - Future: Add background log rotation or manual `logs --rotate` command
   - Workaround: Stop and restart ComfyUI to trigger rotation

3. **No background health monitoring**: HTTP health check only runs on demand (`status`/`list`)
   - Future: Add optional background health monitor with crash detection
   - Workaround: Use `status` command to check health manually

4. **Orphan process detection requires psutil admin access**: On some systems, detecting orphaned processes may fail without elevated permissions
   - Future: Improve detection with fallback methods
   - Workaround: Use `ps`/`tasklist` commands to manually find orphaned processes

---

**End of Implementation Plan**
