#!/usr/bin/env python3
"""
QA Orchestrator for ComfyGit.

Manages parallel execution of QA scenarios across multiple Docker containers.
Each container runs as a separate agent with its own workspace.

Usage:
    # Run all scenarios with 1 agent (testing mode)
    python orchestrate.py

    # Run specific scenario with 1 agent
    python orchestrate.py --scenarios 01_basic_workspace_setup

    # Run all scenarios with 3 parallel agents
    python orchestrate.py -n 3

    # Run with specific model
    python orchestrate.py --model haiku

    # Dry run (show what would execute)
    python orchestrate.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class AgentConfig:
    """Configuration for a single QA agent."""

    agent_id: int
    project_name: str
    comfyui_port: int
    model: str
    timeout_minutes: int


@dataclass
class ScenarioResult:
    """Result from running a single scenario."""

    scenario: str
    agent_id: int
    exit_code: int
    duration_seconds: float
    report_path: str | None = None
    error: str | None = None


@dataclass
class OrchestratorResult:
    """Aggregated results from all scenarios."""

    total_scenarios: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    scenario_results: list[ScenarioResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_scenarios": self.total_scenarios,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "scenario_results": [
                {
                    "scenario": r.scenario,
                    "agent_id": r.agent_id,
                    "exit_code": r.exit_code,
                    "duration_seconds": r.duration_seconds,
                    "report_path": r.report_path,
                    "error": r.error,
                }
                for r in self.scenario_results
            ],
        }


class Orchestrator:
    """Manages QA scenario execution across Docker containers."""

    def __init__(
        self,
        num_agents: int = 1,
        model: str = "sonnet",
        timeout_minutes: int = 30,
        qa_dir: Path | None = None,
        verbose: bool = False,
        dry_run: bool = False,
    ):
        self.num_agents = num_agents
        self.model = model
        self.timeout_minutes = timeout_minutes
        self.qa_dir = qa_dir or Path(__file__).parent.parent
        self.verbose = verbose
        self.dry_run = dry_run

        self.scenarios_dir = self.qa_dir / "scenarios"
        self.reports_dir = self.qa_dir / "reports"

        # Base port for ComfyUI (8191, 8192, etc. to avoid ACFS 8188-8190)
        self.base_port = 8191

    def log(self, msg: str, level: Literal["info", "error", "debug"] = "info") -> None:
        """Log a message."""
        if level == "debug" and not self.verbose:
            return
        prefix = {"info": "→", "error": "✗", "debug": "  "}[level]
        print(f"{prefix} {msg}")

    def get_scenarios(self, filter_patterns: list[str] | None = None) -> list[Path]:
        """Get list of scenario files to run."""
        all_scenarios = sorted(self.scenarios_dir.glob("*.yaml"))

        if not filter_patterns:
            return all_scenarios

        filtered = []
        for scenario in all_scenarios:
            name = scenario.stem
            for pattern in filter_patterns:
                # Match by prefix (e.g., "01" matches "01_basic_workspace_setup")
                # or by partial name match
                if name.startswith(pattern) or pattern in name:
                    filtered.append(scenario)
                    break

        return filtered

    def get_agent_config(self, agent_id: int) -> AgentConfig:
        """Create configuration for an agent."""
        return AgentConfig(
            agent_id=agent_id,
            project_name=f"qa-{agent_id}",
            comfyui_port=self.base_port + agent_id - 1,
            model=self.model,
            timeout_minutes=self.timeout_minutes,
        )

    def ensure_shared_volume(self) -> bool:
        """Ensure qa-shared volume exists."""
        result = subprocess.run(
            ["docker", "volume", "inspect", "qa-shared"],
            capture_output=True,
        )
        if result.returncode != 0:
            self.log("Creating qa-shared volume...")
            result = subprocess.run(
                ["docker", "volume", "create", "qa-shared"],
                capture_output=True,
            )
            if result.returncode != 0:
                self.log(f"Failed to create volume: {result.stderr.decode()}", "error")
                return False
        return True

    def build_image(self) -> bool:
        """Build the QA Docker image if needed."""
        self.log("Building QA image...")
        if self.dry_run:
            self.log("  [dry-run] Would build comfygit-qa:local", "debug")
            return True

        result = subprocess.run(
            ["docker", "compose", "build"],
            cwd=self.qa_dir,
            capture_output=not self.verbose,
        )
        if result.returncode != 0:
            self.log("Failed to build image", "error")
            if not self.verbose and result.stderr:
                self.log(result.stderr.decode()[:500], "error")
            return False
        return True

    def start_agent(self, config: AgentConfig) -> bool:
        """Start a QA agent container."""
        self.log(f"Starting agent {config.agent_id} (port {config.comfyui_port})...")

        if self.dry_run:
            self.log(f"  [dry-run] Would start {config.project_name}", "debug")
            return True

        env = os.environ.copy()
        env["AGENT_ID"] = str(config.agent_id)
        env["COMFYUI_PORT"] = str(config.comfyui_port)

        result = subprocess.run(
            ["docker", "compose", "-p", config.project_name, "up", "-d"],
            cwd=self.qa_dir,
            env=env,
            capture_output=True,
        )

        if result.returncode != 0:
            self.log(f"Failed to start agent {config.agent_id}", "error")
            self.log(result.stderr.decode()[:500], "error")
            return False

        # Wait for container to be ready
        time.sleep(2)
        return True

    def stop_agent(self, config: AgentConfig) -> None:
        """Stop a QA agent container."""
        self.log(f"Stopping agent {config.agent_id}...", "debug")

        if self.dry_run:
            return

        subprocess.run(
            ["docker", "compose", "-p", config.project_name, "down"],
            cwd=self.qa_dir,
            capture_output=True,
        )

    def run_scenario(
        self,
        config: AgentConfig,
        scenario: Path,
    ) -> ScenarioResult:
        """Run a single scenario on an agent."""
        scenario_name = scenario.stem
        self.log(f"Agent {config.agent_id}: Running {scenario_name}")

        start_time = time.time()

        if self.dry_run:
            return ScenarioResult(
                scenario=scenario_name,
                agent_id=config.agent_id,
                exit_code=0,
                duration_seconds=0.0,
            )

        # Build the command to run inside the container
        # Using --native mode for now (direct execution without Claude agent)
        # For full agent mode, remove --native
        cmd = [
            "docker", "compose", "-p", config.project_name,
            "exec", "-T", "qa",
            "python", "/qa/scripts/run_scenario.py",
            f"--model", config.model,
            f"--timeout", str(config.timeout_minutes),
            f"/qa/scenarios/{scenario.name}",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.qa_dir,
                capture_output=True,
                text=True,
                timeout=config.timeout_minutes * 60 + 60,  # Extra minute for overhead
            )

            duration = time.time() - start_time

            if self.verbose:
                if result.stdout:
                    print(result.stdout[:2000])
                if result.stderr:
                    print(result.stderr[:500])

            # Find the report file
            report_path = self._find_latest_report(scenario_name)

            return ScenarioResult(
                scenario=scenario_name,
                agent_id=config.agent_id,
                exit_code=result.returncode,
                duration_seconds=duration,
                report_path=str(report_path) if report_path else None,
            )

        except subprocess.TimeoutExpired:
            return ScenarioResult(
                scenario=scenario_name,
                agent_id=config.agent_id,
                exit_code=-1,
                duration_seconds=time.time() - start_time,
                error=f"Timeout after {config.timeout_minutes} minutes",
            )
        except Exception as e:
            return ScenarioResult(
                scenario=scenario_name,
                agent_id=config.agent_id,
                exit_code=-1,
                duration_seconds=time.time() - start_time,
                error=str(e),
            )

    def _find_latest_report(self, scenario_name: str) -> Path | None:
        """Find the most recent report for a scenario."""
        pattern = f"{scenario_name.lower().replace(' ', '_')}*.json"
        reports = sorted(
            self.reports_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return reports[0] if reports else None

    def run_sequential(
        self,
        scenarios: list[Path],
    ) -> OrchestratorResult:
        """Run scenarios sequentially on a single agent."""
        result = OrchestratorResult(total_scenarios=len(scenarios))
        start_time = time.time()

        config = self.get_agent_config(1)

        if not self.start_agent(config):
            result.errors = len(scenarios)
            return result

        try:
            for scenario in scenarios:
                scenario_result = self.run_scenario(config, scenario)
                result.scenario_results.append(scenario_result)

                if scenario_result.exit_code == 0:
                    result.passed += 1
                elif scenario_result.error:
                    result.errors += 1
                else:
                    result.failed += 1

        finally:
            self.stop_agent(config)

        result.duration_seconds = time.time() - start_time
        return result

    def run_parallel(
        self,
        scenarios: list[Path],
    ) -> OrchestratorResult:
        """Run scenarios in parallel across multiple agents."""
        result = OrchestratorResult(total_scenarios=len(scenarios))
        start_time = time.time()

        # Distribute scenarios across agents (round-robin)
        agent_scenarios: dict[int, list[Path]] = {
            i: [] for i in range(1, self.num_agents + 1)
        }
        for i, scenario in enumerate(scenarios):
            agent_id = (i % self.num_agents) + 1
            agent_scenarios[agent_id].append(scenario)

        # Start all agents
        configs = []
        for agent_id in range(1, self.num_agents + 1):
            config = self.get_agent_config(agent_id)
            if self.start_agent(config):
                configs.append(config)
            else:
                self.log(f"Failed to start agent {agent_id}, skipping", "error")

        if not configs:
            result.errors = len(scenarios)
            return result

        try:
            # Run scenarios in parallel
            with ThreadPoolExecutor(max_workers=self.num_agents) as executor:
                futures = []
                for config in configs:
                    for scenario in agent_scenarios[config.agent_id]:
                        future = executor.submit(self.run_scenario, config, scenario)
                        futures.append(future)

                for future in as_completed(futures):
                    scenario_result = future.result()
                    result.scenario_results.append(scenario_result)

                    if scenario_result.exit_code == 0:
                        result.passed += 1
                    elif scenario_result.error:
                        result.errors += 1
                    else:
                        result.failed += 1

        finally:
            # Stop all agents
            for config in configs:
                self.stop_agent(config)

        result.duration_seconds = time.time() - start_time
        return result

    def run(
        self,
        scenarios: list[Path],
        parallel: bool = True,
    ) -> OrchestratorResult:
        """Run all scenarios."""
        self.log(f"ComfyGit QA Orchestrator")
        self.log(f"========================")
        self.log(f"Scenarios: {len(scenarios)}")
        self.log(f"Agents: {self.num_agents}")
        self.log(f"Model: {self.model}")
        self.log(f"Mode: {'parallel' if parallel and self.num_agents > 1 else 'sequential'}")

        if self.dry_run:
            self.log("[DRY RUN MODE]")

        # Setup
        if not self.dry_run:
            if not self.ensure_shared_volume():
                return OrchestratorResult(errors=len(scenarios))

            if not self.build_image():
                return OrchestratorResult(errors=len(scenarios))

        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Run scenarios
        if parallel and self.num_agents > 1:
            result = self.run_parallel(scenarios)
        else:
            result = self.run_sequential(scenarios)

        # Summary
        self.log("")
        self.log(f"Results")
        self.log(f"-------")
        self.log(f"Total: {result.total_scenarios}")
        self.log(f"Passed: {result.passed}")
        self.log(f"Failed: {result.failed}")
        self.log(f"Errors: {result.errors}")
        self.log(f"Duration: {result.duration_seconds:.1f}s")

        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orchestrate QA scenario execution across Docker containers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all scenarios with 1 agent
    python orchestrate.py

    # Run specific scenario
    python orchestrate.py --scenarios 01_basic_workspace_setup

    # Run multiple specific scenarios
    python orchestrate.py --scenarios 01,02,03

    # Run with 3 parallel agents
    python orchestrate.py -n 3

    # Use haiku model (cheaper, faster)
    python orchestrate.py --model haiku

    # Dry run to see what would execute
    python orchestrate.py --dry-run

    # Native mode (no Claude, direct command execution)
    python orchestrate.py --native
        """,
    )

    parser.add_argument(
        "-n", "--agents",
        type=int,
        default=1,
        help="Number of parallel agents (default: 1)",
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default=None,
        help="Comma-separated scenario prefixes/names to run (default: all)",
    )
    parser.add_argument(
        "--model",
        default="sonnet",
        choices=["haiku", "sonnet", "opus"],
        help="Claude model to use (default: sonnet)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout per scenario in minutes (default: 30)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run sequentially even with multiple agents",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Write JSON results to file",
    )

    args = parser.parse_args()

    # Parse scenario filters
    scenario_filters = None
    if args.scenarios:
        scenario_filters = [s.strip() for s in args.scenarios.split(",")]

    # Create orchestrator
    orchestrator = Orchestrator(
        num_agents=args.agents,
        model=args.model,
        timeout_minutes=args.timeout,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )

    # Get scenarios
    scenarios = orchestrator.get_scenarios(scenario_filters)
    if not scenarios:
        print("No scenarios found matching filter")
        return 1

    print(f"Found {len(scenarios)} scenario(s):")
    for s in scenarios:
        print(f"  - {s.stem}")
    print()

    # Run
    result = orchestrator.run(
        scenarios=scenarios,
        parallel=not args.sequential,
    )

    # Output JSON if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\nResults written to: {output_path}")

    # Exit code based on results
    if result.errors > 0:
        return 2  # Infrastructure errors
    elif result.failed > 0:
        return 1  # Test failures
    return 0


if __name__ == "__main__":
    sys.exit(main())
