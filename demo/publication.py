"""Generate pinned caller after publication; never mutates GitHub or Git."""

import argparse
from pathlib import Path
import re


def generate(template, demo_sha, cli_sha):
    for value in (demo_sha, cli_sha):
        if not re.fullmatch(r"[0-9a-f]{40}", value) or len(set(value)) == 1:
            raise ValueError(
                "Require actual reviewed published 40-character commit pins."
            )
    text = template.replace("__DEMO_SHA__", demo_sha).replace(
        "__CLI_SOURCE_SHA__", cli_sha
    )
    if re.search(r"__[A-Z_]+__", text):
        raise ValueError("Unresolved publication substitution.")
    return text


def main():
    parser = argparse.ArgumentParser(
        description="Prepare caller; independently verify both published commits before use."
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--demo-sha", required=True)
    parser.add_argument("--cli-source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--published-commits-verified", action="store_true")
    args = parser.parse_args()
    if not args.published_commits_verified:
        parser.error(
            "Verify published workflow/scripts and CLI release source before generating a runnable caller."
        )
    if args.output.exists():
        parser.error("Output already exists; do not overwrite a caller silently.")
    text = generate(args.template.read_text(), args.demo_sha, args.cli_source_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
