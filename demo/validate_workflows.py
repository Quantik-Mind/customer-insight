"""Local workflow contracts plus actionlint, with a narrow documented schema exception."""

import argparse
from pathlib import Path
import subprocess
import tempfile

import yaml

from .publication import generate


def validate(actionlint, reusable, caller_template):
    workflow = yaml.safe_load(reusable.read_text(encoding="utf-8"))
    event = workflow.get("on", workflow.get(True))
    contract = event["workflow_call"]
    assert workflow["concurrency"]["queue"] == "max"
    assert workflow["concurrency"]["cancel-in-progress"] is False
    # Synthetic pins only for syntax/interface validation. Never written into a repository workflow.
    generated = generate(caller_template.read_text(), "ab" * 20, "cd" * 20)
    caller = yaml.safe_load(generated)
    job = caller["jobs"]["demo"]
    assert set(job["with"]) <= set(contract["inputs"])
    assert {
        name for name, value in contract["inputs"].items() if value.get("required")
    } <= set(job["with"])
    assert set(job["secrets"]) == set(contract["secrets"])
    assert caller["permissions"] == {"contents": "read", "actions": "read"}
    assert set(workflow["jobs"]) == {"build", "selection"}
    assert workflow["jobs"]["selection"]["needs"] == "build"
    assert job["with"]["build_mode"] == "real"
    assert "execution" in contract["inputs"] and "a_run_id" in contract["inputs"]
    assert "demo/pipeline" in job["if"] and "Quantik-Mind/banking-app" in job["if"]
    with tempfile.TemporaryDirectory(prefix="qmind-workflow-validation-") as directory:
        path = Path(directory) / "synthetic-caller-validation.yml"
        path.write_text(generated, encoding="utf-8")
        # actionlint 1.7.12 predates GitHub's documented queue:max syntax. Ignore ONLY
        # this specific unknown-key diagnostic; validate its value/combination above.
        subprocess.run(
            [
                str(actionlint),
                "-shellcheck=",
                "-pyflakes=",
                "-ignore",
                r'^unexpected key "queue" for "concurrency" section\.',
                str(reusable),
                str(path),
            ],
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--actionlint", type=Path, required=True)
    parser.add_argument("--reusable", type=Path, required=True)
    parser.add_argument("--caller-template", type=Path, required=True)
    args = parser.parse_args()
    validate(
        args.actionlint.resolve(),
        args.reusable.resolve(),
        args.caller_template.resolve(),
    )
