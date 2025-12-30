#!/usr/bin/env python3
"""
QA Scenario Runner for ComfyGit.

Runs a single scenario using Claude as the test executor.
Designed for Phase 1 PoC - manual triggering, single agent.

Usage:
    # Run inside container
    python run_scenario.py scenarios/01_basic_workspace_setup.yaml

    # From host (via docker)
    docker run --rm -v ./reports:/reports comfygit-qa \
        scenarios/01_basic_workspace_setup.yaml
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Installing PyYAML...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml


def load_scenario(scenario_path: Path) -> dict:
    """Load and validate a scenario YAML file."""
    if not scenario_path.exists():
        print(f"Error: Scenario not found: {scenario_path}")
        sys.exit(1)

    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    required_fields = ["name", "steps"]
    for field in required_fields:
        if field not in scenario:
            print(f"Error: Scenario missing required field: {field}")
            sys.exit(1)

    return scenario


def build_prompt(scenario: dict, instructions_dir: Path) -> str:
    """Build the complete prompt for Claude from scenario and instructions."""
    # Load base system instructions
    base_system = (instructions_dir / "base_system.md").read_text()
    scenario_runner = (instructions_dir / "scenario_runner.md").read_text()

    # Format scenario as context
    scenario_yaml = yaml.dump(scenario, default_flow_style=False, sort_keys=False)

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
5. Save the report to /reports/{scenario['name'].lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md

Begin execution now.
"""
    return prompt


def run_claude(prompt: str, timeout_minutes: int = 30) -> tuple[int, str]:
    """
    Run Claude CLI with the given prompt.

    Returns (exit_code, output).
    """
    # Write prompt to temp file for Claude to read
    prompt_file = Path("/tmp/qa_prompt.md")
    prompt_file.write_text(prompt)

    # Run Claude with the prompt
    cmd = [
        "claude",
        "--print",  # Print conversation to stdout
        "--dangerously-skip-permissions",  # Allow all tools
        "-p", prompt,  # Pass prompt directly
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_minutes * 60,
            env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "qa-runner"},
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, f"Error: Scenario timed out after {timeout_minutes} minutes"
    except FileNotFoundError:
        return 1, "Error: Claude CLI not found. Ensure @anthropic-ai/claude-code is installed."


def run_scenario_native(scenario: dict, dry_run: bool = False) -> dict:
    """
    Run scenario steps directly (without Claude) for testing.

    Returns a result dict with step outcomes.
    """
    results = {
        "scenario": scenario["name"],
        "started": datetime.now().isoformat(),
        "steps": [],
        "success": True,
    }

    # Run setup
    if "setup" in scenario:
        print(f"\n=== Setup ===")
        for step in scenario["setup"]:
            cmd = step.get("command", "")
            print(f"$ {cmd}")
            if not dry_run:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0 and not step.get("ignore_errors"):
                    print(f"  Error: {result.stderr}")

    # Run main steps
    print(f"\n=== Steps ===")
    for i, step in enumerate(scenario["steps"], 1):
        action = step.get("action", f"Step {i}")
        print(f"\n[{i}] {action}")

        if "command" in step:
            cmd = step["command"]
            # Handle multiline commands
            if isinstance(cmd, str) and "\n" in cmd:
                cmd = cmd.strip()
            print(f"$ {cmd[:80]}..." if len(str(cmd)) > 80 else f"$ {cmd}")

            if not dry_run:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=step.get("timeout", 60)
                )
                step_result = {
                    "action": action,
                    "command": cmd,
                    "exit_code": result.returncode,
                    "stdout": result.stdout[:1000],  # Truncate
                    "stderr": result.stderr[:1000],
                }
                results["steps"].append(step_result)

                if result.returncode != 0:
                    print(f"  Exit code: {result.returncode}")
                    print(f"  Stderr: {result.stderr[:200]}")
                    if step.get("on_failure") == "abort":
                        results["success"] = False
                        break
            else:
                results["steps"].append({"action": action, "command": cmd, "dry_run": True})

        elif "explore" in step:
            print(f"  [Explore step - skipped in native mode]")
            results["steps"].append({"action": action, "explore": True, "skipped": True})

        # Run verify commands
        if "verify" in step and not dry_run:
            for verify_cmd in step["verify"]:
                print(f"  Verify: {verify_cmd}")
                subprocess.run(verify_cmd, shell=True)

    results["completed"] = datetime.now().isoformat()
    return results


def main():
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
        """
    )
    parser.add_argument("scenario", help="Path to scenario YAML file")
    parser.add_argument("--native", action="store_true", help="Run without Claude (direct execution)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be executed")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in minutes (default: 30)")
    parser.add_argument("--instructions-dir", default="/qa/agent_instructions",
                        help="Directory containing agent instructions")
    parser.add_argument("--reports-dir", default="/reports",
                        help="Directory to write reports")

    args = parser.parse_args()

    # Handle paths - support both absolute and relative
    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        # Try relative to /qa/scenarios first
        qa_path = Path("/qa/scenarios") / args.scenario
        if qa_path.exists():
            scenario_path = qa_path
        elif not scenario_path.exists():
            # Try relative to current directory
            scenario_path = Path.cwd() / args.scenario

    instructions_dir = Path(args.instructions_dir)
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print(f"ComfyGit QA Runner")
    print(f"==================")
    print(f"Scenario: {scenario_path}")
    print(f"Mode: {'dry-run' if args.dry_run else 'native' if args.native else 'claude-agent'}")

    # Load scenario
    scenario = load_scenario(scenario_path)
    print(f"Name: {scenario['name']}")
    print(f"Category: {scenario.get('category', 'unknown')}")
    print(f"Steps: {len(scenario.get('steps', []))}")

    if args.native or args.dry_run:
        # Run without Claude
        results = run_scenario_native(scenario, dry_run=args.dry_run)
        print(f"\n=== Results ===")
        print(f"Success: {results['success']}")
        print(f"Steps completed: {len(results['steps'])}")

        # Write results
        if not args.dry_run:
            report_name = f"{scenario['name'].lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            report_path = reports_dir / report_name
            with open(report_path, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"Report: {report_path}")

        return 0 if results["success"] else 1

    else:
        # Run with Claude
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("\nError: ANTHROPIC_API_KEY not set")
            print("Set it via: export ANTHROPIC_API_KEY=your-key")
            print("Or run with --native for direct execution")
            return 1

        print(f"\nBuilding prompt for Claude...")
        prompt = build_prompt(scenario, instructions_dir)

        print(f"Starting Claude agent (timeout: {args.timeout}m)...")
        print(f"=" * 60)

        exit_code, output = run_claude(prompt, timeout_minutes=args.timeout)

        print(f"=" * 60)
        print(f"\nClaude exit code: {exit_code}")

        # Save raw output
        output_path = reports_dir / f"raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        output_path.write_text(output)
        print(f"Raw output: {output_path}")

        return exit_code


if __name__ == "__main__":
    sys.exit(main())
