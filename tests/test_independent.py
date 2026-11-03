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
    assert "No frozen counterfactual is available" in html
    assert "Frozen baseline selected" not in html
    assert "Both frozen assessments use the same saved inputs" not in html


def test_production_demo_project_name_is_not_local_placeholder(tmp_path):
    fixture = tmp_path / "fixture"
    generated = generate(fixture)
    value = report.bundle(fixture / "a")
    value["summary"]["project_id"] = "456d2579-60bc-56a0-96b9-9c2dd41cc0da"
    value["summary"].pop("project_name", None)
    result = report.model(
        value,
        None,
        generated["changes"],
        generated["build"],
        execution="A",
        sample=True,
    )
    assert result["project_name"] == "Continuous Resilience"


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


def test_failed_b_uses_recovered_project_and_does_not_invent_selection(tmp_path):
    execution = tmp_path / "execution"
    bundle_dir = execution / "bundle"
    bundle_dir.mkdir(parents=True)
    (execution / "attempt.json").write_text(
        json.dumps(
            {
                "status": "failed_or_uncertain",
                "project_id": "456d2579-60bc-56a0-96b9-9c2dd41cc0da",
            }
        )
    )
    (execution / "receipt.json").write_text(
        json.dumps(
            {
                "status": "submitting",
                "submission_outcome": "unknown",
                "project_id": "456d2579-60bc-56a0-96b9-9c2dd41cc0da",
            }
        )
    )
    (execution / "restoration.json").write_text(
        json.dumps({"status": "RESTORATION_REQUIRED", "verified": False})
    )
    value = report.bundle(bundle_dir)
    generated = generate(tmp_path / "fixture")
    result = report.model(
        None,
        value,
        generated["changes"],
        generated["build"],
        execution="B",
        sample=False,
    )
    assert result["project_name"] == "Continuous Resilience"
    assert result["runs"]["B"]["membership"]["final_selected"] is None
    report.render(result, tmp_path / "failed-report")
    rendered = (tmp_path / "failed-report/report.md").read_text()
    assert "No frozen counterfactual is available" in rendered
    assert "Frozen baseline selected" not in rendered


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
    tooling_sha = "ab" * 20
    pins = {
        "a_tooling_sha": tooling_sha,
        "cli_sha": "cd" * 20,
        "wheel_sha": "3" * 64,
    }
    package(
        source,
        execution,
        fixture,
        archive,
        "A",
        tooling_sha=tooling_sha,
        cli_sha=pins["cli_sha"],
        wheel_sha=pins["wheel_sha"],
    )
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


def test_b_accepts_a_predecessor_tooling_provenance_without_resealing(
    tmp_path, monkeypatch
):
    archive, run, pins = reference(tmp_path, monkeypatch)
    current_tooling_sha = "ef" * 20
    assert current_tooling_sha != pins["a_tooling_sha"]
    session = validate_reference(archive, run, **pins)
    assert session["tooling_sha"] == pins["a_tooling_sha"]
    assert session["tooling_sha"] != current_tooling_sha


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
