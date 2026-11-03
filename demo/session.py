"""Package only safe evidence; seal successful independently triggered executions."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from .report import bundle


def package(
    source, execution, report, output, label, *, tooling_sha, cli_sha, wheel_sha
):
    source, execution, report, output = map(Path, (source, execution, report, output))
    output.mkdir(parents=True, exist_ok=False)
    permitted = {
        "receipt.json",
        "attempt.json",
        "influence-state.json",
        "restoration.json",
        "original-controls.json",
        "applied-controls.json",
        "restored-controls.json",
    }
    for name in ("changes.json", "changed-files.json", "build.json"):
        if (source / name).exists():
            target = output / "source-build" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
    for folder, prefix in (
        (execution, "execution"),
        (execution / "bundle", "execution/bundle"),
        (report, "report"),
    ):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if not path.is_file() or (
                prefix == "execution" and path.name not in permitted
            ):
                continue
            if path.suffix not in {".json", ".csv", ".html", ".md"} or (
                prefix == "report"
                and path.name
                not in {"report.html", "report.md", "report.json", "manifest.json"}
            ):
                continue
            target = output / prefix / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    restoration = (
        json.loads((execution / "restoration.json").read_text())
        if (execution / "restoration.json").exists()
        else {}
    )
    saved = bundle(execution / "bundle")
    if (
        restoration.get("status") != "restored"
        or saved["manifest"].get("complete") is not True
    ):
        (output / "failure.json").write_text(
            json.dumps(
                {"status": "incomplete_or_restoration_required", "execution": label}
            )
        )
        return
    plan = json.loads((source / "changes.json").read_text())
    project_id = os.environ.get("QMIND_PROJECT_ID", "").strip()
    if not project_id:
        raise ValueError("QMIND_PROJECT_ID is required when sealing a demo execution")
    UUID(project_id)
    session = {
        "schema_version": 2,
        "execution": label,
        "session_id": str(uuid4()),
        "project_id": project_id,
        "repository": "Quantik-Mind/banking-app",
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local-fixture"),
        "head": plan["head"],
        "base": plan["base"],
        "selection_run_id": saved["summary"]["run_id"],
        "tooling_sha": tooling_sha,
        "cli_source_sha": cli_sha,
        "wheel_sha256": wheel_sha,
        "files": {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.rglob("*")
            if p.is_file()
        },
    }
    (output / "session.json").write_text(
        json.dumps(session, indent=2), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser()
    for name in ("source", "execution", "report", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--label", choices=["A", "B"], required=True)
    for name in ("tooling-sha", "cli-sha", "wheel-sha"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    package(
        args.source,
        args.execution,
        args.report,
        args.output,
        args.label,
        tooling_sha=args.tooling_sha,
        cli_sha=args.cli_sha,
        wheel_sha=args.wheel_sha,
    )


if __name__ == "__main__":
    main()
