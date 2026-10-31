"""Hosted orchestration via the existing CLI. No direct selection/evaluation APIs."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = "90e48503-115d-4b34-be95-9f2f1b62767d"


def run_cli(arguments, *, output=None):
    result = subprocess.run(
        ["qmind", *arguments], capture_output=True, text=True, timeout=650
    )
    # CLI progress/structured errors are already sanitized; never print raw subprocess exceptions.
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if output and result.stdout:
        payload = json.loads(result.stdout)
        Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if result.returncode:
        raise RuntimeError(
            f"CLI exited {result.returncode}; preserve receipt and use saved-run recovery. Do not rerun submission."
        )
    return json.loads(result.stdout) if result.stdout else None


def execute(mode, files, output, *, qmind=run_cli):
    output.mkdir(parents=True, exist_ok=True)
    failure = {
        "schema_version": 1,
        "project_id": PROJECT,
        "expected_influence": mode,
        "status": "started",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "changed_files_sha256": hashlib.sha256(files.read_bytes()).hexdigest(),
    }
    failure["provenance"] = {
        key: os.environ.get(key)
        for key in (
            "GITHUB_RUN_ID",
            "GITHUB_SHA",
            "GITHUB_REPOSITORY",
            "QMIND_CLI_SOURCE_SHA",
            "QMIND_TOOLING_SHA",
            "QMIND_CLI_SHA256",
        )
    }
    failure_path = output / "attempt.json"
    control_state = output / "influence-state.json"
    restoration = {"status": "not_required"}
    try:
        values = json.loads(files.read_text())
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(p, str) or not p.strip() for p in values)
        ):
            raise ValueError(
                "Empty/malformed changed-file input: selection skipped, no history fallback."
            )
        if os.environ.get("QMIND_PROJECT_ID") != PROJECT:
            raise ValueError(
                "Configured project does not match approved validation project."
            )
        qmind(
            [
                "init",
                "--project-id",
                PROJECT,
                "--framework",
                "pytest",
                "--non-interactive",
            ]
        )
        controls = qmind(
            ["near-miss", "controls"], output=output / "original-controls.json"
        )
        if controls.get("last_operation_id") and not controls.get("is_restoration"):
            restoration = {
                "status": "PRIOR_OPERATION_REQUIRES_RECOVERY",
                "verified": False,
                "procedure": "Reconcile the prior run with qmind runs list/wait; use near-miss influence restore/recover before starting another workflow. No new control edit or selection was submitted.",
            }
            raise RuntimeError(
                "A prior temporary influence operation is unresolved; recover it before starting a new execution"
            )
        qmind(
            [
                "near-miss",
                "influence",
                "set",
                mode,
                "--if-revision",
                controls["revision"],
                "--state-file",
                str(control_state.resolve()),
            ],
            output=output / "applied-controls.json",
        )
        if mode == "on":
            status = qmind(["near-miss", "status"], output=output / "preflight.json")
            if status.get("evaluation_id"):
                qmind(
                    ["near-miss", "evaluation", status["evaluation_id"]],
                    output=output / "preflight-evaluation.json",
                )
            episode_ids = {
                item["episode"]["id"]
                for item in status.get("results", [])
                if item.get("state") == "active_near_miss"
                and isinstance(item.get("episode"), dict)
                and item["episode"].get("id")
            }
            for identity in sorted(episode_ids)[:20]:
                qmind(
                    ["near-miss", "episode", identity],
                    output=output / ("preflight-episode-" + identity + ".json"),
                )
            failure["preflight"] = {
                "state": status.get("state"),
                "reason": status.get("reason"),
                "active_episode_observed": any(
                    item.get("state") == "active_near_miss"
                    for item in status.get("results", [])
                ),
            }
            failure["preflight"]["episode_reads"] = min(20, len(episode_ids))
            failure["preflight"]["additional_episode_references"] = max(
                0, len(episode_ids) - 20
            )
            # Preflight is advisory: selection's captured eligibility remains authoritative.
            print(
                "Read-only preflight complete. No active near miss is a valid outcome; no selection loop will run."
            )
        receipt = output / "receipt.json"
        state = json.loads(control_state.read_text())
        state["selection_started"] = True
        control_state.write_text(json.dumps(state, indent=2), encoding="utf-8")
        qmind(
            [
                "subset",
                "--changed-files-file",
                str(files.resolve()),
                "--json",
                "--wait",
                "--timeout-seconds",
                "600",
                "--receipt-file",
                str(receipt.resolve()),
                "--expected-influence",
                mode,
            ],
            output=output / "completion.json",
        )
        run_id = json.loads(receipt.read_text())["run_id"]
        qmind(
            [
                "runs",
                "export",
                run_id,
                "--output-dir",
                str((output / "bundle").resolve()),
                "--expected-influence",
                mode,
            ],
            output=output / "export.json",
        )
        manifest_path = output / "bundle" / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            manifest["pipeline_provenance"] = failure["provenance"]
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        failure.update(status="completed", run_id=run_id)
    except Exception as exc:
        failure.update(
            status="failed_or_uncertain",
            error_type=type(exc).__name__,
            recovery="Inspect receipt. Known ID: qmind runs wait/export. Unknown outcome: reconcile existing runs; never resubmit blindly.",
        )
        raise
    finally:
        if control_state.exists():
            try:
                qmind(
                    [
                        "near-miss",
                        "influence",
                        "restore",
                        "--state-file",
                        str(control_state.resolve()),
                    ],
                    output=output / "restored-controls.json",
                )
                restoration = {"status": "restored", "verified": True}
            except Exception:
                restoration = {
                    "status": "RESTORATION_REQUIRED",
                    "verified": False,
                    "procedure": "qmind runs wait RUN_ID --json; qmind near-miss controls; qmind near-miss influence restore --state-file influence-state.json --run-id RUN_ID",
                    "uncertain_submission": "If no run ID is known, reconcile qmind runs list first. Never resubmit. Concurrent editor conflicts must be resolved explicitly; do not fetch a fresh revision and overwrite blindly.",
                }
                print(
                    "RESTORATION REQUIRED: preserve influence-state.json and receipt; wait/reconcile the run before conditional restore.",
                    file=sys.stderr,
                )
        (output / "restoration.json").write_text(
            json.dumps(restoration, indent=2), encoding="utf-8"
        )
        failure["restoration"] = restoration
        failure["finished_at"] = datetime.now(timezone.utc).isoformat()
        failure_path.write_text(json.dumps(failure, indent=2), encoding="utf-8")
        if (
            restoration["status"] == "RESTORATION_REQUIRED"
            and sys.exc_info()[0] is None
        ):
            raise RuntimeError(
                "Selection finished but original influence could not safely be restored. See restoration.json"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["off", "on"], required=True)
    parser.add_argument("--files", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # init emits human-readable output; use no JSON parsing for this one local setup call.
    def invoke(arguments, output=None):
        if arguments[0] == "init":
            result = subprocess.run(
                ["qmind", *arguments], capture_output=True, text=True, timeout=60
            )
            if result.returncode:
                raise RuntimeError(
                    "CLI initialization failed. Check project key and endpoint access."
                )
            return None
        return run_cli(arguments, output=output)

    execute(args.mode, args.files.resolve(), args.output.resolve(), qmind=invoke)


if __name__ == "__main__":
    main()
