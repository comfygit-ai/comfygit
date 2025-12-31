#!/usr/bin/env python3
"""
Report Aggregator for ComfyGit QA.

Combines multiple QA reports into a single summary, identifying patterns
and common issues across test runs.

Usage:
    # Aggregate all reports in directory
    python aggregate_reports.py /reports

    # Output as JSON
    python aggregate_reports.py /reports --json

    # Filter by date
    python aggregate_reports.py /reports --since 2025-01-01
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class AggregatedResults:
    """Aggregated results from multiple QA reports."""

    total_reports: int = 0
    total_scenarios: int = 0
    passed: int = 0
    failed: int = 0
    partial: int = 0
    total_bugs: int = 0
    total_ux_issues: int = 0
    total_duration_seconds: float = 0.0

    # Breakdown by scenario
    scenario_results: dict[str, dict] = field(default_factory=dict)

    # Common patterns
    bug_titles: list[str] = field(default_factory=list)
    ux_issue_titles: list[str] = field(default_factory=list)
    test_recommendations: list[str] = field(default_factory=list)

    # Report metadata
    earliest_report: str | None = None
    latest_report: str | None = None
    agents_used: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_reports": self.total_reports,
                "total_scenarios": self.total_scenarios,
                "passed": self.passed,
                "failed": self.failed,
                "partial": self.partial,
                "pass_rate": f"{(self.passed / self.total_scenarios * 100):.1f}%" if self.total_scenarios > 0 else "N/A",
                "total_bugs": self.total_bugs,
                "total_ux_issues": self.total_ux_issues,
                "total_duration_seconds": self.total_duration_seconds,
            },
            "time_range": {
                "earliest": self.earliest_report,
                "latest": self.latest_report,
            },
            "agents_used": sorted(self.agents_used),
            "scenario_breakdown": self.scenario_results,
            "findings": {
                "bugs": self.bug_titles,
                "ux_issues": self.ux_issue_titles,
                "test_recommendations": self.test_recommendations,
            },
        }

    def to_markdown(self) -> str:
        """Generate markdown summary."""
        lines = [
            "# QA Aggregated Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            f"- **Reports analyzed**: {self.total_reports}",
            f"- **Scenarios run**: {self.total_scenarios}",
            f"- **Pass rate**: {(self.passed / self.total_scenarios * 100):.1f}%" if self.total_scenarios > 0 else "- **Pass rate**: N/A",
            f"- **Passed**: {self.passed}",
            f"- **Failed**: {self.failed}",
            f"- **Partial**: {self.partial}",
            f"- **Total bugs found**: {self.total_bugs}",
            f"- **Total UX issues**: {self.total_ux_issues}",
            f"- **Total duration**: {self.total_duration_seconds / 60:.1f} minutes",
            "",
            "## Time Range",
            f"- Earliest: {self.earliest_report or 'N/A'}",
            f"- Latest: {self.latest_report or 'N/A'}",
            "",
            "## Agents Used",
        ]

        if self.agents_used:
            for agent in sorted(self.agents_used):
                lines.append(f"- {agent}")
        else:
            lines.append("- None recorded")

        lines.extend([
            "",
            "## Scenario Breakdown",
            "",
            "| Scenario | Runs | Passed | Failed | Partial |",
            "|----------|------|--------|--------|---------|",
        ])

        for scenario, data in sorted(self.scenario_results.items()):
            lines.append(
                f"| {scenario} | {data['runs']} | {data['passed']} | {data['failed']} | {data['partial']} |"
            )

        lines.extend([
            "",
            "## Bugs Found",
            "",
        ])

        if self.bug_titles:
            bug_counts = Counter(self.bug_titles)
            for bug, count in bug_counts.most_common():
                lines.append(f"- {bug} (x{count})" if count > 1 else f"- {bug}")
        else:
            lines.append("No bugs found across all reports.")

        lines.extend([
            "",
            "## UX Issues",
            "",
        ])

        if self.ux_issue_titles:
            ux_counts = Counter(self.ux_issue_titles)
            for issue, count in ux_counts.most_common():
                lines.append(f"- {issue} (x{count})" if count > 1 else f"- {issue}")
        else:
            lines.append("No UX issues noted.")

        lines.extend([
            "",
            "## Test Recommendations",
            "",
        ])

        if self.test_recommendations:
            rec_counts = Counter(self.test_recommendations)
            for rec, count in rec_counts.most_common(10):  # Top 10
                lines.append(f"- {rec}")
        else:
            lines.append("No additional test recommendations.")

        return "\n".join(lines)


def parse_report(path: Path) -> dict | None:
    """Parse a single JSON report file."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not parse {path}: {e}", file=sys.stderr)
        return None


def aggregate_reports(
    reports_dir: Path,
    since: datetime | None = None,
) -> AggregatedResults:
    """Aggregate all reports in a directory."""
    result = AggregatedResults()

    # Find all JSON reports
    json_files = sorted(reports_dir.glob("*.json"))

    for path in json_files:
        # Skip non-report files
        if path.name.startswith("raw_"):
            continue

        report = parse_report(path)
        if not report:
            continue

        # Check date filter
        if since:
            try:
                report_date = datetime.fromisoformat(
                    report.get("timestamp", "").replace("Z", "+00:00")
                )
                if report_date < since:
                    continue
            except (ValueError, TypeError):
                pass  # Include if we can't parse the date

        result.total_reports += 1

        # Extract metadata
        scenario_name = report.get("scenario_name", "unknown")
        overall_status = report.get("overall_status", "unknown")
        agent_id = report.get("agent_id", "unknown")
        duration = report.get("duration_seconds", 0.0)
        timestamp = report.get("timestamp", "")

        result.total_scenarios += 1
        result.total_duration_seconds += duration
        result.agents_used.add(agent_id)

        # Track time range
        if timestamp:
            if result.earliest_report is None or timestamp < result.earliest_report:
                result.earliest_report = timestamp
            if result.latest_report is None or timestamp > result.latest_report:
                result.latest_report = timestamp

        # Track status
        if overall_status == "pass":
            result.passed += 1
        elif overall_status == "fail":
            result.failed += 1
        elif overall_status == "partial":
            result.partial += 1

        # Track scenario breakdown
        if scenario_name not in result.scenario_results:
            result.scenario_results[scenario_name] = {
                "runs": 0,
                "passed": 0,
                "failed": 0,
                "partial": 0,
            }
        result.scenario_results[scenario_name]["runs"] += 1
        if overall_status == "pass":
            result.scenario_results[scenario_name]["passed"] += 1
        elif overall_status == "fail":
            result.scenario_results[scenario_name]["failed"] += 1
        elif overall_status == "partial":
            result.scenario_results[scenario_name]["partial"] += 1

        # Collect bugs
        for bug in report.get("bugs", []):
            title = bug.get("title", "Unknown bug")
            result.bug_titles.append(title)
            result.total_bugs += 1

        # Collect UX issues
        for issue in report.get("ux_issues", []):
            title = issue.get("title", "Unknown issue")
            result.ux_issue_titles.append(title)
            result.total_ux_issues += 1

        # Collect test recommendations
        for rec in report.get("test_recommendations", []):
            result.test_recommendations.append(rec)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate QA reports into summary",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Aggregate all reports
    python aggregate_reports.py /reports

    # Output as JSON
    python aggregate_reports.py /reports --json

    # Filter by date
    python aggregate_reports.py /reports --since 2025-01-01

    # Save to file
    python aggregate_reports.py /reports -o summary.md
        """,
    )

    parser.add_argument(
        "reports_dir",
        type=Path,
        help="Directory containing JSON reports",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of markdown",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only include reports since date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    if not args.reports_dir.exists():
        print(f"Error: Reports directory not found: {args.reports_dir}", file=sys.stderr)
        return 1

    # Parse since filter
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError:
            print(f"Error: Invalid date format: {args.since}", file=sys.stderr)
            return 1

    # Aggregate
    result = aggregate_reports(args.reports_dir, since=since)

    if result.total_reports == 0:
        print("No reports found.", file=sys.stderr)
        return 1

    # Output
    if args.json:
        output = json.dumps(result.to_dict(), indent=2, default=str)
    else:
        output = result.to_markdown()

    if args.output:
        args.output.write_text(output)
        print(f"Summary written to: {args.output}")
    else:
        print(output)

    # Return code based on results
    if result.failed > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
