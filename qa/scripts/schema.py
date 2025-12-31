"""
Scenario YAML DSL Schema with Validation.

Provides Pydantic models for scenario files, enabling:
- Type-safe loading
- Validation with helpful error messages
- Serialization for reports
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OnFailure(str, Enum):
    """Behavior when a step fails."""

    INVESTIGATE = "investigate"  # Dig deeper before continuing
    SKIP = "skip"  # Note failure, continue
    ABORT = "abort"  # Stop scenario
    DOCUMENT = "document"  # Expected failure, just document it


class Priority(str, Enum):
    """Scenario priority level."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    """Scenario category for organization."""

    WORKSPACE = "workspace"
    WORKFLOW = "workflow"
    NODE = "node"
    MODEL = "model"
    COLLABORATION = "collaboration"
    EXPORT = "export"


class Requirements(BaseModel):
    """Environment requirements for a scenario."""

    comfygit: str | None = Field(None, description="ComfyGit version constraint")
    disk_space: str | None = Field(None, description="Minimum disk space")
    network: bool = Field(True, description="Whether network access is needed")


class SetupStep(BaseModel):
    """A setup/cleanup step."""

    command: str = Field(..., description="Shell command to run")
    description: str | None = Field(None, description="Human-readable description")
    ignore_errors: bool = Field(False, description="Continue on failure")
    timeout: int = Field(60, description="Timeout in seconds")


class ScenarioStep(BaseModel):
    """A test step in a scenario."""

    action: str = Field(..., description="Human-readable action description")
    command: str | None = Field(None, description="Shell command to execute")
    explore: str | None = Field(None, description="Free-form exploration prompt")
    expect: str | None = Field(None, description="Expected outcome")
    on_failure: OnFailure = Field(OnFailure.INVESTIGATE, description="Failure behavior")
    timeout: int = Field(60, description="Timeout in seconds")
    verify: list[str] = Field(default_factory=list, description="Verification commands")

    @model_validator(mode="after")
    def command_or_explore(self) -> "ScenarioStep":
        """Ensure step has either command or explore, not both or neither."""
        if self.command is None and self.explore is None:
            raise ValueError("Step must have either 'command' or 'explore'")
        if self.command is not None and self.explore is not None:
            raise ValueError("Step cannot have both 'command' and 'explore'")
        return self


class Scenario(BaseModel):
    """A complete test scenario."""

    name: str = Field(..., description="Scenario name")
    description: str | None = Field(None, description="Detailed description")
    category: Category | None = Field(None, description="Scenario category")
    priority: Priority = Field(Priority.MEDIUM, description="Priority level")
    requirements: Requirements = Field(default_factory=Requirements)
    setup: list[SetupStep] = Field(default_factory=list, description="Setup steps")
    steps: list[ScenarioStep] = Field(..., min_length=1, description="Test steps")
    cleanup: list[SetupStep] = Field(default_factory=list, description="Cleanup steps")
    success_criteria: str | None = Field(None, description="Success criteria")

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        """Ensure name is not empty."""
        if not v.strip():
            raise ValueError("Scenario name cannot be empty")
        return v.strip()


class StepStatus(str, Enum):
    """Result status for a step."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    INVESTIGATE = "investigate"


class StepResult(BaseModel):
    """Result from executing a single step."""

    action: str
    step_type: Literal["command", "explore"]
    command: str | None = None
    expected: str | None = None
    status: StepStatus
    output: str = ""
    error: str | None = None
    duration_seconds: float = 0.0
    exit_code: int | None = None
    verification_results: list[dict] = Field(default_factory=list)
    notes: str | None = None


class BugSeverity(str, Enum):
    """Bug severity level."""

    CRITICAL = "critical"  # Data loss, crash
    HIGH = "high"  # Major feature broken
    MEDIUM = "medium"  # Feature partially broken
    LOW = "low"  # Minor issue, cosmetic


class Bug(BaseModel):
    """A bug found during testing."""

    title: str
    severity: BugSeverity
    steps_to_reproduce: list[str]
    expected_behavior: str
    actual_behavior: str
    suggested_fix: str | None = None
    related_step: int | None = Field(None, description="Step number where found")


class UXIssue(BaseModel):
    """A UX issue (not a bug, but worth noting)."""

    title: str
    description: str
    suggestion: str | None = None


class ScenarioReport(BaseModel):
    """Complete report from a scenario execution."""

    # Metadata
    scenario_name: str
    scenario_file: str
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_id: str = Field(default="native")
    duration_seconds: float = 0.0

    # Environment
    comfygit_version: str | None = None
    python_version: str | None = None
    container_image: str | None = None

    # Results
    overall_status: Literal["pass", "fail", "partial"]
    steps_total: int
    steps_passed: int
    steps_failed: int
    step_results: list[StepResult] = Field(default_factory=list)

    # Findings
    bugs: list[Bug] = Field(default_factory=list)
    ux_issues: list[UXIssue] = Field(default_factory=list)
    test_recommendations: list[str] = Field(default_factory=list)

    # Summary
    summary: str = ""
    conclusion: str = ""

    def to_markdown(self) -> str:
        """Convert report to markdown format."""
        lines = [
            f"# QA Report: {self.scenario_name}",
            f"Date: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Agent: {self.agent_id}",
            f"Duration: {self.duration_seconds:.1f}s",
            "",
            "## Summary",
            self.summary or f"Executed {self.steps_total} steps: {self.steps_passed} passed, {self.steps_failed} failed.",
            "",
            "## Environment",
            f"- ComfyGit version: {self.comfygit_version or 'unknown'}",
            f"- Python version: {self.python_version or 'unknown'}",
            f"- Container: {self.container_image or 'unknown'}",
            "",
            "## Scenario Execution",
            "",
        ]

        for i, result in enumerate(self.step_results, 1):
            lines.extend([
                f"### Step {i}: {result.action}",
                f"**Type:** {result.step_type}",
                "",
            ])

            if result.command:
                lines.extend([
                    "**Command:**",
                    "```bash",
                    result.command,
                    "```",
                    "",
                ])

            if result.expected:
                lines.extend([
                    f"**Expected:** {result.expected.strip()}",
                    "",
                ])

            lines.extend([
                "**Actual:**",
                "```",
                result.output[:2000] if result.output else "(no output)",
                "```",
                "",
                f"**Status:** {result.status.value.upper()}",
                f"**Duration:** {result.duration_seconds:.2f}s",
                "",
            ])

            if result.error:
                lines.extend([
                    "**Error:**",
                    "```",
                    result.error,
                    "```",
                    "",
                ])

            if result.notes:
                lines.append(f"**Notes:** {result.notes}\n")

        lines.extend(["## Findings", ""])

        if self.bugs:
            lines.append("### Bugs Found")
            for i, bug in enumerate(self.bugs, 1):
                lines.extend([
                    f"{i}. **{bug.title}**",
                    f"   - Severity: {bug.severity.value}",
                    f"   - Steps to reproduce:",
                ])
                for j, step in enumerate(bug.steps_to_reproduce, 1):
                    lines.append(f"     {j}. {step}")
                lines.extend([
                    f"   - Expected: {bug.expected_behavior}",
                    f"   - Actual: {bug.actual_behavior}",
                ])
                if bug.suggested_fix:
                    lines.append(f"   - Suggested fix: {bug.suggested_fix}")
                lines.append("")
        else:
            lines.append("### Bugs Found\nNone found.\n")

        if self.ux_issues:
            lines.append("### UX Issues")
            for i, issue in enumerate(self.ux_issues, 1):
                lines.extend([
                    f"{i}. **{issue.title}**",
                    f"   - {issue.description}",
                ])
                if issue.suggestion:
                    lines.append(f"   - Suggestion: {issue.suggestion}")
                lines.append("")
        else:
            lines.append("### UX Issues\nNone noted.\n")

        if self.test_recommendations:
            lines.append("### Test Recommendations")
            for rec in self.test_recommendations:
                lines.append(f"- {rec}")
            lines.append("")
        else:
            lines.append("### Test Recommendations\nNo additional tests recommended.\n")

        lines.extend([
            "## Conclusion",
            self.conclusion or f"Scenario {self.overall_status.upper()}.",
        ])

        return "\n".join(lines)


def load_scenario(path: Path) -> Scenario:
    """Load and validate a scenario from a YAML file."""
    import yaml

    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError(f"Empty scenario file: {path}")

    return Scenario.model_validate(raw)


def validate_scenario_file(path: Path) -> list[str]:
    """Validate a scenario file and return list of errors (empty if valid)."""
    errors = []
    try:
        load_scenario(path)
    except FileNotFoundError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"Validation error: {e}")
    return errors
