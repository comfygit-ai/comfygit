#!/usr/bin/env python3
"""Write a complete parser-help snapshot without touching curated documentation.

Run from the monorepo uv workspace so imports use the matched local packages.
"""
from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path

from comfygit_cli.cli import create_parser


def parser_sections(parser: ArgumentParser, command: str = "cg") -> list[str]:
    """Include every nested command, retaining argparse's usage and defaults."""
    sections = [f"## `{command}`\n\n```text\n{parser.format_help().rstrip()}\n```\n"]
    for action in parser._actions:
        if isinstance(action, _SubParsersAction):
            seen = set()
            for name, child in action.choices.items():
                if id(child) not in seen:
                    seen.add(id(child))
                    sections.extend(parser_sections(child, f"{command} {name}"))
    return sections


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "generated-cli" / "reference.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    parser = create_parser()
    output.write_text(
        "# CLI parser reference\n\nGenerated for review; curated pages are unchanged.\n\n"
        + "\n".join(parser_sections(parser)),
        encoding="utf-8",
    )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
