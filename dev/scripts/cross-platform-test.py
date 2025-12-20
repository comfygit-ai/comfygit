#!/usr/bin/env python3
"""
Cross-platform test runner for ComfyGit.

Runs tests on multiple platforms (Linux, Windows, macOS) in parallel,
collecting results and providing a unified summary.

Usage:
    python cross-platform-test.py              # Run on all enabled platforms
    python cross-platform-test.py --platforms linux,windows  # Specific platforms
    python cross-platform-test.py --list       # List available platforms
    python cross-platform-test.py --no-sync    # Skip git sync on remote
    python cross-platform-test.py --test-path packages/core/tests/unit  # Custom test path

    # Pass arbitrary pytest arguments after --
    python cross-platform-test.py -- -k "test_workspace" -x
    python cross-platform-test.py --test-path packages/core/tests -- -k "test_git" --tb=short
    python cross-platform-test.py -- packages/core/tests/unit -k "test_env" -x

Configuration:
    - dev/cross-platform-test.toml - Template with defaults (checked into git)
    - dev/cross-platform-test.local.toml - Your local overrides (gitignored)

    Copy dev/cross-platform-test.local.example.toml to create your local config.
"""

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# tomllib is Python 3.11+, fallback to tomli for older versions
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: Please install tomli for Python < 3.11: uv pip install tomli")
        sys.exit(1)


@dataclass
class TestResult:
    """Result of a test run on a single platform."""
    platform: str
    success: bool
    duration: float
    output: str
    error: str = ""


@dataclass
class PlatformConfig:
    """Configuration for a single platform."""
    name: str
    type: Literal["local", "ssh", "wsl-interop"]
    enabled: bool
    host: str = ""
    user: str = ""
    port: int = 22
    repo_path: str = ""
    windows_repo_path: str = ""
    ssh_key: str = ""
    test_command: str = ""


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path) -> tuple[dict, dict[str, PlatformConfig]]:
    """Load configuration from TOML file, merging local overrides if present."""
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        print("Create it by copying the template or run: make test-cross-platform-init")
        sys.exit(1)

    # Load base config
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # Check for local overrides
    local_config_path = config_path.with_suffix(".local.toml")
    if local_config_path.exists():
        with open(local_config_path, "rb") as f:
            local_config = tomllib.load(f)
        # Deep merge local config on top of base
        config = deep_merge(config, local_config)

    settings = config.get("settings", {})
    platforms = {}

    for name, platform_config in config.get("platforms", {}).items():
        platforms[name] = PlatformConfig(
            name=name,
            type=platform_config.get("type", "local"),
            enabled=platform_config.get("enabled", False),
            host=platform_config.get("host", ""),
            user=platform_config.get("user", ""),
            port=platform_config.get("port", 22),
            repo_path=platform_config.get("repo_path", ""),
            windows_repo_path=platform_config.get("windows_repo_path", ""),
            ssh_key=platform_config.get("ssh_key", ""),
            test_command=platform_config.get("test_command", ""),
        )

    return settings, platforms


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def run_local_tests(test_command: str, timeout: int) -> TestResult:
    """Run tests on the local machine."""
    platform = "linux"
    start_time = time.time()

    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start_time

        return TestResult(
            platform=platform,
            success=result.returncode == 0,
            duration=duration,
            output=result.stdout,
            error=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            platform=platform,
            success=False,
            duration=timeout,
            output="",
            error=f"Test timed out after {timeout} seconds",
        )
    except Exception as e:
        return TestResult(
            platform=platform,
            success=False,
            duration=time.time() - start_time,
            output="",
            error=str(e),
        )


def run_ssh_tests(
    platform: PlatformConfig,
    test_command: str,
    timeout: int,
    sync: bool,
    branch: str,
) -> TestResult:
    """Run tests on a remote machine via SSH."""
    start_time = time.time()

    # Build SSH command
    ssh_opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if platform.ssh_key:
        key_path = os.path.expanduser(platform.ssh_key)
        ssh_opts.extend(["-i", key_path])

    ssh_target = f"{platform.user}@{platform.host}"
    if platform.port != 22:
        ssh_opts.extend(["-p", str(platform.port)])

    # Build remote command
    remote_commands = []

    # Change to repo directory
    remote_commands.append(f"cd {platform.repo_path}")

    # Optionally sync code
    if sync:
        remote_commands.append(f"git fetch origin {branch}")
        remote_commands.append(f"git checkout {branch}")
        remote_commands.append(f"git pull origin {branch}")

    # Run tests
    remote_commands.append(test_command)

    # Join commands with && for sequential execution
    full_remote_command = " && ".join(remote_commands)

    try:
        result = subprocess.run(
            ["ssh"] + ssh_opts + [ssh_target, full_remote_command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start_time

        return TestResult(
            platform=platform.name,
            success=result.returncode == 0,
            duration=duration,
            output=result.stdout,
            error=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            platform=platform.name,
            success=False,
            duration=timeout,
            output="",
            error=f"Test timed out after {timeout} seconds",
        )
    except Exception as e:
        return TestResult(
            platform=platform.name,
            success=False,
            duration=time.time() - start_time,
            output="",
            error=str(e),
        )


def run_wsl_interop_tests(
    platform: PlatformConfig,
    test_command: str,
    timeout: int,
) -> TestResult:
    """Run tests on Windows host from WSL using cmd.exe interop."""
    start_time = time.time()

    # Build Windows command
    windows_command = f'cd /d {platform.windows_repo_path} && {test_command}'

    try:
        result = subprocess.run(
            ["cmd.exe", "/c", windows_command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start_time

        return TestResult(
            platform=platform.name,
            success=result.returncode == 0,
            duration=duration,
            output=result.stdout,
            error=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            platform=platform.name,
            success=False,
            duration=timeout,
            output="",
            error=f"Test timed out after {timeout} seconds",
        )
    except Exception as e:
        return TestResult(
            platform=platform.name,
            success=False,
            duration=time.time() - start_time,
            output="",
            error=str(e),
        )


def run_platform_tests(
    platform: PlatformConfig,
    settings: dict,
    sync: bool,
    branch: str,
    test_path: str | None,
    pytest_args: list[str] | None = None,
) -> TestResult:
    """Run tests on a single platform."""
    # Determine test command
    test_command = platform.test_command or settings.get(
        "test_command", "uv run pytest packages/core/tests -v"
    )

    # Override test path if specified
    if test_path:
        # Replace the test path in the command
        test_command = f"uv run pytest {test_path} -v"

    # Append any additional pytest arguments
    if pytest_args:
        test_command = f"{test_command} {' '.join(pytest_args)}"

    timeout = settings.get("timeout", 600)

    print(f"  [{platform.name}] Starting tests...")

    if platform.type == "local":
        return run_local_tests(test_command, timeout)
    elif platform.type == "ssh":
        return run_ssh_tests(platform, test_command, timeout, sync, branch)
    elif platform.type == "wsl-interop":
        return run_wsl_interop_tests(platform, test_command, timeout)
    else:
        return TestResult(
            platform=platform.name,
            success=False,
            duration=0,
            output="",
            error=f"Unknown platform type: {platform.type}",
        )


def print_result_summary(results: list[TestResult], verbose: bool = False):
    """Print a summary of all test results."""
    print("\n" + "=" * 60)
    print("CROSS-PLATFORM TEST RESULTS")
    print("=" * 60)

    all_passed = True
    for result in results:
        status = "\u2713" if result.success else "\u2717"
        status_text = "PASSED" if result.success else "FAILED"
        print(f"  {status} {result.platform:15} {status_text} ({result.duration:.1f}s)")

        if not result.success:
            all_passed = False
            if result.error:
                # Show first few lines of error
                error_lines = result.error.strip().split("\n")[:5]
                for line in error_lines:
                    print(f"      {line}")
                if len(result.error.strip().split("\n")) > 5:
                    print("      ...")

    print("=" * 60)

    if all_passed:
        print("\u2713 All platforms passed!")
    else:
        print("\u2717 Some platforms failed")
        if verbose:
            print("\nFailed platform details:")
            for result in results:
                if not result.success:
                    print(f"\n--- {result.platform} ---")
                    if result.output:
                        print("STDOUT:")
                        print(result.output[-2000:])  # Last 2000 chars
                    if result.error:
                        print("STDERR:")
                        print(result.error[-2000:])

    return all_passed


def list_platforms(platforms: dict[str, PlatformConfig]):
    """List available platforms and their status."""
    print("Available platforms:")
    print()
    for name, platform in platforms.items():
        status = "\u2713 enabled" if platform.enabled else "\u2717 disabled"
        print(f"  {name:15} [{platform.type:12}] {status}")
        if platform.type == "ssh" and platform.enabled:
            print(f"                  Host: {platform.user}@{platform.host}:{platform.port}")
            print(f"                  Repo: {platform.repo_path}")
        elif platform.type == "wsl-interop" and platform.enabled:
            print(f"                  Repo: {platform.windows_repo_path}")
    print()
    print("Edit dev/cross-platform-test.toml to configure platforms.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run tests across multiple platforms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--platforms", "-p",
        help="Comma-separated list of platforms to test (default: all enabled)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available platforms and exit",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip git sync on remote platforms",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full output for failed tests",
    )
    parser.add_argument(
        "--test-path",
        help="Custom test path (e.g., packages/core/tests/unit)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run tests sequentially instead of in parallel",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Additional pytest arguments (after --). Example: -- -k 'test_name' -x",
    )

    args = parser.parse_args()

    # Clean up pytest_args - remove leading '--' if present
    pytest_args = args.pytest_args
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    # Find config file
    script_dir = Path(__file__).parent
    config_path = script_dir.parent / "cross-platform-test.toml"

    # Load configuration
    settings, platforms = load_config(config_path)

    # List platforms if requested
    if args.list:
        list_platforms(platforms)
        return 0

    # Determine which platforms to test
    if args.platforms:
        platform_names = [p.strip() for p in args.platforms.split(",")]
        # Validate platform names
        for name in platform_names:
            if name not in platforms:
                print(f"Error: Unknown platform '{name}'")
                print(f"Available: {', '.join(platforms.keys())}")
                return 1
        enabled_platforms = [platforms[name] for name in platform_names]
    else:
        enabled_platforms = [p for p in platforms.values() if p.enabled]

    if not enabled_platforms:
        print("No platforms enabled for testing.")
        print("Enable platforms in dev/cross-platform-test.toml or use --platforms")
        return 1

    # Get current branch for syncing
    try:
        branch = get_current_branch()
    except subprocess.CalledProcessError:
        branch = "main"

    sync = not args.no_sync and settings.get("sync_before_test", True)

    print(f"Running tests on {len(enabled_platforms)} platform(s)...")
    print(f"Branch: {branch}")
    print(f"Sync: {'yes' if sync else 'no'}")
    if args.test_path:
        print(f"Test path: {args.test_path}")
    if pytest_args:
        print(f"Pytest args: {' '.join(pytest_args)}")
    print()

    # Run tests
    results: list[TestResult] = []

    if args.sequential:
        # Sequential execution
        for platform in enabled_platforms:
            result = run_platform_tests(
                platform, settings, sync, branch, args.test_path, pytest_args
            )
            results.append(result)
            status = "\u2713" if result.success else "\u2717"
            print(f"  [{platform.name}] {status} Completed in {result.duration:.1f}s")
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=len(enabled_platforms)) as executor:
            future_to_platform = {
                executor.submit(
                    run_platform_tests,
                    platform,
                    settings,
                    sync,
                    branch,
                    args.test_path,
                    pytest_args,
                ): platform
                for platform in enabled_platforms
            }

            for future in as_completed(future_to_platform):
                platform = future_to_platform[future]
                try:
                    result = future.result()
                    results.append(result)
                    status = "\u2713" if result.success else "\u2717"
                    print(f"  [{platform.name}] {status} Completed in {result.duration:.1f}s")
                except Exception as e:
                    results.append(TestResult(
                        platform=platform.name,
                        success=False,
                        duration=0,
                        output="",
                        error=str(e),
                    ))
                    print(f"  [{platform.name}] \u2717 Error: {e}")

    # Sort results by platform name for consistent display
    results.sort(key=lambda r: r.platform)

    # Print summary
    all_passed = print_result_summary(results, verbose=args.verbose)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
