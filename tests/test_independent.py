"""Explicit synthetic unit fixtures; real CLI/backend rehearsal is recorded separately."""

import json
from pathlib import Path
import shutil

import pytest
import yaml
from demo import report
from demo.sample import generate
from demo.session import package
from demo.cross_run import validate_reference
from demo import pipeline


def test_unresolved_previous_operation_blocks_new_workflow_without_edit_or_selection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("QMIND_PROJECT_ID", pipeline.PROJECT)
    files = tmp_path / "changed-files.json"
    files.write_text('["transaction_service/main.py"]')
    calls = []

    def qmind(arguments, output=None):
        calls.append(arguments)
        if arguments[:2] == ["near-miss", "controls"]:
            return {
                "last_operation_id": "prior-operation",
                "is_restoration": False,
                "revision": "a" * 64,
            }
        return {}

    with pytest.raises(RuntimeError, match="prior temporary"):
        pipeline.execute("off", files, tmp_path / "output", qmind=qmind)
    assert not any(
        call[0] == "subset" or call[:3] == ["near-miss", "influence", "set"]
        for call in calls
    )
    assert (
        json.loads((tmp_path / "output/restoration.json").read_text())["status"]
        == "PRIOR_OPERATION_REQUIRES_RECOVERY"
    )


def test_a_is_complete_without_b_and_links_are_optional(tmp_path):
    fixture = tmp_path / "fixture"
    generated = generate(fixture)
    value = report.bundle(fixture / "a")
    result = report.model(
        value,
        None,
        generated["changes"],
        generated["build"],
        execution="A",
        sample=True,
    )
    report.render(result, tmp_path / "standalone")
    assert set(result["runs"]) == {"A"}
    assert result["runs"]["A"]["manifest"]["complete"] is True
    assert result["runs"]["A"]["link"] is None
    assert "does not submit or schedule B" in result["attribution"]
    html = (tmp_path / "standalone/report.html").read_text()
    assert "Complete selected list" in html and "influence ON" not in html
    assert "seconds (p95)" in html and "requests/second" in html


def test_b_has_own_report_and_restoration_failure_is_prominent(tmp_path):
    fixture = tmp_path / "fixture"
    generated = generate(fixture)
    value = report.bundle(fixture / "b")
    value["restoration"] = {"status": "RESTORATION_REQUIRED"}
    result = report.model(
        None,
        value,
        generated["changes"],
        generated["build"],
        execution="B",
        sample=True,
    )
    assert set(result["runs"]) == {"B"}
    assert any(
        "RESTORATION REQUIRED" in limitation for limitation in result["limitations"]
    )
    report.render(result, tmp_path / "standalone")
    assert "RESTORATION_REQUIRED" in (tmp_path / "standalone/report.html").read_text()


def reference(tmp_path, monkeypatch):
    monkeypatch.setenv("QMIND_PROJECT_ID", pipeline.PROJECT)
    fixture = tmp_path / "fixture"
    generated = generate(fixture)
    source = tmp_path / "source"
    source.mkdir()
    plan = {
        **generated["changes"],
        "base": "1" * 40,
        "head": "2" * 40,
        "skip_selection": False,
    }
    (source / "changes.json").write_text(json.dumps(plan))
    (source / "changed-files.json").write_text(json.dumps(plan["changed_files"]))
    (source / "build.json").write_text(
        json.dumps({"mode": "real", "synthetic_unit_fixture": True})
    )
    execution = tmp_path / "execution"
    execution.mkdir()
    shutil.copytree(fixture / "a", execution / "bundle")
    (execution / "restoration.json").write_text('{"status":"restored"}')
    saved = report.bundle(execution / "bundle")
    (execution / "receipt.json").write_text(
        json.dumps({"run_id": saved["summary"]["run_id"]})
    )
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    archive = tmp_path / "artifact"
    pins = {"tooling_sha": "ab" * 20, "cli_sha": "cd" * 20, "wheel_sha": "3" * 64}
    package(source, execution, fixture, archive, "A", **pins)
    run = {
        "repository": {"full_name": "Quantik-Mind/banking-app"},
        "path": ".github/workflows/quantikmind-pipeline-demo.yml",
        "head_branch": "demo/pipeline",
        "conclusion": "success",
        "event": "push",
        "run_attempt": 1,
        "id": 123,
        "head_sha": plan["head"],
    }
    return archive, run, pins


def test_b_validates_actual_seal_and_refuses_wrong_origin_or_tamper(
    tmp_path, monkeypatch
):
    archive, run, pins = reference(tmp_path, monkeypatch)
    session = validate_reference(archive, run, **pins)
    assert session["head"] == run["head_sha"]
    for field, bad in (
        ("head_branch", "untrusted"),
        ("conclusion", "failure"),
        ("path", ".github/workflows/another.yml"),
        ("run_attempt", 2),
    ):
        with pytest.raises(AssertionError):
            validate_reference(archive, {**run, field: bad}, **pins)
    (archive / "source-build/changed-files.json").write_text('["tampered.py"]')
    with pytest.raises(AssertionError):
        validate_reference(archive, run, **pins)


def test_no_automatic_off_on_chain_and_publication_remains_gated():
    root = Path(__file__).parents[1]
    workflow = yaml.safe_load(
        (root / ".github/workflows/selection-demo.yml").read_text()
    )
    assert set(workflow["jobs"]) == {"build", "selection"}
    assert workflow["jobs"]["selection"]["needs"] == "build"
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert "workflow_dispatch" in str(workflow["jobs"]["build"]["steps"][0])
    assert (
        not list(
            (root.parent / "banking-cli/.github/workflows").glob("*pipeline-demo*")
        )
        if (root.parent / "banking-cli").exists()
        else True
    )
