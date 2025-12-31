#!/usr/bin/env python3
"""
QA Scenario Runner for ComfyGit.

Runs a single scenario using Claude as the test executor.
Phase 2: Structured scenarios, JSON+markdown reports, better error handling.

Usage:
    # Run inside container
    python run_scenario.py scenarios/01_basic_workspace_setup.yaml

    # From host (via docker)
    docker run --rm -v ./reports:/reports comfygit-qa \
        scenarios/01_basic_workspace_setup.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure pydantic is available
try:
    from pydantic import ValidationError
except ImportError:
    print("Installing pydantic...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pydantic", "-q"], check=True)
    from pydantic import ValidationError

try:
    import yaml
except ImportError:
    print("Installing PyYAML...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"], check=True)
    import yaml

# Import schema after ensuring dependencies
from schema import (
    Bug,
    BugSeverity,
    OnFailure,
    Scenario,
    ScenarioReport,
    StepResult,
    StepStatus,
    UXIssue,
    load_scenario,
    validate_scenario_file,
)


class QARunnerError(Exception):
    """Base error for QA runner."""

    pass


class ScenarioLoadError(QARunnerError):
    """Failed to load scenario."""

    pass


class AgentExecutionError(QARunnerError):
    """Failed to execute agent."""

    pass


def get_environment_info() -> dict:
    """Gather environment information for reports."""
    info = {
        "comfygit_version": None,
        "python_version": sys.version.split()[0],
        "container_image": os.environ.get("CONTAINER_IMAGE", "unknown"),
    }

    # Try to get ComfyGit version
    try:
        result = subprocess.run(
            ["cg", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            info["comfygit_version"] = result.stdout.strip()
    except Exception:
        pass

    return info


def run_command(
    cmd: str,
    timeout: int = 60,
    capture: bool = True,
) -> tuple[int, str, str, float]:
    """
    Run a shell command with timeout.

    Returns (exit_code, stdout, stderr, duration_seconds).
    """
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start
        return result.returncode, result.stdout, result.stderr, duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return -1, "", f"Command timed out after {timeout}s", duration
    except Exception as e:
        duration = time.time() - start
        return -1, "", str(e), duration


def build_prompt(scenario: Scenario, instructions_dir: Path, report_path: str) -> str:
    """Build the complete prompt for Claude from scenario and instructions."""
    base_system = (instructions_dir / "base_system.md").read_text()
    scenario_runner = (instructions_dir / "scenario_runner.md").read_text()

    # Format scenario as context (excluding internal pydantic fields)
    scenario_dict = scenario.model_dump(mode="json", exclude_none=True)
    scenario_yaml = yaml.dump(scenario_dict, default_flow_style=False, sort_keys=False)

    prompt = f"""# QA Testing Session

## Instructions
{base_system}

## Scenario Execution Protocol
{scenario_runner}

## Scenario to Execute

```yaml
{scenario_yaml}
```

## Your Task

Execute the scenario above step by step. Follow the scenario runner protocol.

1. Start by announcing the scenario
2. Execute each step, documenting results
3. When you reach "explore" steps, use your judgment to find edge cases
4. Generate a complete report at the end
5. Save the report to {report_path}

IMPORTANT: When you finish, write the report file. The report MUST include:
- All steps executed with their outputs
- Any bugs found (with reproduction steps)
- Any UX issues noted
- Your overall assessment

Begin execution now.
"""
    return prompt


def run_claude(
    prompt: str,
    timeout_minutes: int = 30,
    model: str = "sonnet",
) -> tuple[int, str, str | None]:
    """
    Run Claude CLI with the given prompt.

    Returns (exit_code, output, error_message).
    """
    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "-p",
        prompt,
    ]

    if model:
        cmd.extend(["--model", model])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_minutes * 60,
            env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "qa-runner"},
        )
        return result.returncode, result.stdout + result.stderr, None
    except subprocess.TimeoutExpired:
        return 1, "", f"Scenario timed out after {timeout_minutes} minutes"
    except FileNotFoundError:
        return 1, "", "Claude CLI not found. Ensure @anthropic-ai/claude-code is installed."
    except Exception as e:
        return 1, "", f"Failed to run Claude: {e}"


def run_scenario_native(
    scenario: Scenario,
    dry_run: bool = False,
    verbose: bool = False,
) -> ScenarioReport:
    """
    Run scenario steps directly (without Claude) for testing.

    Returns a ScenarioReport with step outcomes.
    """
    env_info = get_environment_info()
    start_time = time.time()

    report = ScenarioReport(
        scenario_name=scenario.name,
        scenario_file="",  # Set by caller
        agent_id="native",
        comfygit_version=env_info["comfygit_version"],
        python_version=env_info["python_version"],
        container_image=env_info["container_image"],
        overall_status="pass",
        steps_total=len(scenario.steps),
        steps_passed=0,
        steps_failed=0,
    )

    # Run setup
    if scenario.setup:
        print("\n=== Setup ===")
        for setup_step in scenario.setup:
            cmd = setup_step.command
            print(f"$ {cmd}")
            if not dry_run:
                exit_code, stdout, stderr, duration = run_command(
                    cmd, timeout=setup_step.timeout
                )
                if exit_code != 0 and not setup_step.ignore_errors:
                    print(f"  Setup error: {stderr}")

    # Run main steps
    print("\n=== Steps ===")
    for i, step in enumerate(scenario.steps, 1):
        print(f"\n[{i}] {step.action}")

        if step.command:
            cmd = step.command.strip()
            display_cmd = cmd[:80] + "..." if len(cmd) > 80 else cmd
            print(f"$ {display_cmd}")

            if dry_run:
                result = StepResult(
                    action=step.action,
                    step_type="command",
                    command=cmd,
                    expected=step.expect,
                    status=StepStatus.SKIP,
                    output="[dry-run]",
                )
            else:
                exit_code, stdout, stderr, duration = run_command(
                    cmd, timeout=step.timeout
                )
                output = stdout + stderr

                if exit_code == 0:
                    status = StepStatus.PASS
                    report.steps_passed += 1
                elif step.on_failure == OnFailure.DOCUMENT:
                    status = StepStatus.INVESTIGATE
                else:
                    status = StepStatus.FAIL
                    report.steps_failed += 1
                    print(f"  Exit code: {exit_code}")
                    if verbose:
                        print(f"  Output: {output[:500]}")

                result = StepResult(
                    action=step.action,
                    step_type="command",
                    command=cmd,
                    expected=step.expect,
                    status=status,
                    output=output[:5000],  # Truncate for storage
                    exit_code=exit_code,
                    duration_seconds=duration,
                )

                # Run verification commands
                if step.verify:
                    for verify_cmd in step.verify:
                        print(f"  Verify: {verify_cmd}")
                        v_exit, v_stdout, v_stderr, v_dur = run_command(
                            verify_cmd, timeout=30
                        )
                        result.verification_results.append({
                            "command": verify_cmd,
                            "exit_code": v_exit,
                            "output": (v_stdout + v_stderr)[:1000],
                        })

                # Handle abort
                if status == StepStatus.FAIL and step.on_failure == OnFailure.ABORT:
                    report.overall_status = "fail"
                    report.step_results.append(result)
                    break

        elif step.explore:
            print(f"  [Explore step - skipped in native mode]")
            result = StepResult(
                action=step.action,
                step_type="explore",
                expected=step.explore,
                status=StepStatus.SKIP,
                notes="Explore steps require Claude agent mode",
            )

        report.step_results.append(result)

    # Run cleanup
    if scenario.cleanup and not dry_run:
        print("\n=== Cleanup ===")
        for cleanup_step in scenario.cleanup:
            cmd = cleanup_step.command
            print(f"$ {cmd}")
            run_command(cmd, timeout=cleanup_step.timeout)

    # Finalize report
    report.duration_seconds = time.time() - start_time

    if report.steps_failed > 0:
        report.overall_status = "fail" if report.steps_passed == 0 else "partial"

    report.summary = (
        f"Executed {report.steps_total} steps: "
        f"{report.steps_passed} passed, {report.steps_failed} failed."
    )
    report.conclusion = f"Scenario {'completed successfully' if report.overall_status == 'pass' else 'completed with issues'}."

    return report


def save_report(
    report: ScenarioReport,
    reports_dir: Path,
    scenario_name: str,
) -> tuple[Path, Path]:
    """
    Save report in both JSON and markdown formats.

    Returns (json_path, markdown_path).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{scenario_name.lower().replace(' ', '_')}_{timestamp}"

    json_path = reports_dir / f"{base_name}.json"
    md_path = reports_dir / f"{base_name}.md"

    # Save JSON (for programmatic parsing)
    with open(json_path, "w") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)

    # Save Markdown (for human reading)
    md_content = report.to_markdown()
    md_path.write_text(md_content)

    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run QA scenario with Claude agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with Claude agent (requires ANTHROPIC_API_KEY)
    python run_scenario.py scenarios/01_basic_workspace_setup.yaml

    # Run in native mode (without Claude, for testing)
    python run_scenario.py --native scenarios/01_basic_workspace_setup.yaml

    # Dry run to see what would execute
    python run_scenario.py --dry-run scenarios/01_basic_workspace_setup.yaml

    # Validate scenario without running
    python run_scenario.py --validate scenarios/01_basic_workspace_setup.yaml
        """,
    )
    parser.add_argument("scenario", help="Path to scenario YAML file")
    parser.add_argument(
        "--native", action="store_true", help="Run without Claude (direct execution)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be executed"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate scenario file only"
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="Timeout in minutes (default: 30)"
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        choices=["haiku", "sonnet", "opus"],
        help="Claude model to use (default: sonnet)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    parser.add_argument(
        "--instructions-dir",
        default="/qa/agent_instructions",
        help="Directory containing agent instructions",
    )
    parser.add_argument(
        "--reports-dir", default="/reports", help="Directory to write reports"
    )

    args = parser.parse_args()

    # Resolve scenario path
    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        qa_path = Path("/qa/scenarios") / args.scenario
        if qa_path.exists():
            scenario_path = qa_path
        elif not scenario_path.exists():
            scenario_path = Path.cwd() / args.scenario

    # Validate-only mode
    if args.validate:
        print(f"Validating: {scenario_path}")
        errors = validate_scenario_file(scenario_path)
        if errors:
            print("Validation FAILED:")
            for error in errors:
                print(f"  - {error}")
            return 1
        print("Validation PASSED")
        return 0

    # Load scenario with validation
    print(f"ComfyGit QA Runner")
    print(f"==================")
    print(f"Scenario: {scenario_path}")

    try:
        scenario = load_scenario(scenario_path)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except ValidationError as e:
        print(f"Scenario validation failed:")
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            print(f"  - {loc}: {error['msg']}")
        return 1
    except Exception as e:
        print(f"Failed to load scenario: {e}")
        return 1

    mode = "dry-run" if args.dry_run else "native" if args.native else "claude-agent"
    print(f"Mode: {mode}")
    print(f"Name: {scenario.name}")
    print(f"Category: {scenario.category.value if scenario.category else 'unknown'}")
    print(f"Priority: {scenario.priority.value}")
    print(f"Steps: {len(scenario.steps)}")

    instructions_dir = Path(args.instructions_dir)
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    if args.native or args.dry_run:
        # Run without Claude
        report = run_scenario_native(
            scenario, dry_run=args.dry_run, verbose=args.verbose
        )
        report.scenario_file = str(scenario_path)

        print(f"\n=== Results ===")
        print(f"Status: {report.overall_status.upper()}")
        print(f"Passed: {report.steps_passed}/{report.steps_total}")

        if not args.dry_run:
            json_path, md_path = save_report(report, reports_dir, scenario.name)
            print(f"JSON report: {json_path}")
            print(f"Markdown report: {md_path}")

        return 0 if report.overall_status == "pass" else 1

    else:
        # Run with Claude - check for either API key or OAuth credentials
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        creds_file = Path.home() / ".claude" / ".credentials.json"

        if not api_key and not creds_file.exists():
            print("\nError: No Claude authentication found")
            print("Either:")
            print("  - Set ANTHROPIC_API_KEY environment variable")
            print("  - Or ensure ~/.claude/.credentials.json exists (OAuth)")
            print("Or run with --native for direct execution")
            return 1

        auth_method = "API key" if api_key else "OAuth"
        print(f"Auth: {auth_method}")

        # Build report path for agent to write to
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_name = f"{scenario.name.lower().replace(' ', '_')}_{timestamp}.md"
        report_path = reports_dir / report_name

        print(f"\nBuilding prompt for Claude...")
        prompt = build_prompt(scenario, instructions_dir, str(report_path))

        print(f"Starting Claude agent (model: {args.model}, timeout: {args.timeout}m)...")
        print("=" * 60)

        exit_code, output, error = run_claude(
            prompt, timeout_minutes=args.timeout, model=args.model
        )

        print("=" * 60)

        if error:
            print(f"\nError: {error}")
            return 1

        print(f"\nClaude exit code: {exit_code}")

        # Save raw output
        raw_path = reports_dir / f"raw_{timestamp}.txt"
        raw_path.write_text(output)
        print(f"Raw output: {raw_path}")

        # Check if agent created report
        if report_path.exists():
            print(f"Agent report: {report_path}")
        else:
            print(f"Warning: Agent did not create report at {report_path}")

        return exit_code


if __name__ == "__main__":
    sys.exit(main())
