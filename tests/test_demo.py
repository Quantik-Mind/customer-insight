"""Synthetic local fixtures. No API calls, selected-test execution or Git mutation."""

import json
from pathlib import Path
import subprocess

import pytest
import yaml

from demo import changes, pipeline, report
from demo.build import stage
from demo.install_cli import AssetRedirect
from demo.publication import generate
from demo.sample import generate as sample
from urllib.request import Request


def test_status_renames_deletions_and_spaces():
    result = changes.parse_status(
        b"R100\0transaction_service/old file.py\0transaction_service/new file.py\0D\0auth_service/a.py\0"
    )
    assert result[0]["paths"] == [
        "transaction_service/old file.py",
        "transaction_service/new file.py",
    ]
    assert result[1]["status"] == "D"


@pytest.mark.parametrize(
    "raw",
    [
        b"M\0../escape.py\0",
        b"M\0a\nb.py\0",
        b"M\0 trailing.py\0",
        b"R100\0a.py\0",
        b"M\0a.py",
        b"M\0/a.py\0",
    ],
)
def test_unsafe_or_incomplete_changed_paths(raw):
    with pytest.raises(ValueError):
        changes.parse_status(raw)


def test_new_branch_and_missing_history(monkeypatch):
    calls = []

    def fake(repo, *args, **kwargs):
        calls.append(args)
        return (
            b"a" * 40 if args[0] == "merge-base" and args[1] != "--is-ancestor" else b""
        )

    monkeypatch.setattr(changes, "git", fake)
    assert changes.resolve("repo", "0" * 40, "b" * 40) == ("a" * 40, "b" * 40, False)
    assert any(call[:2] == ("merge-base", "origin/main") for call in calls)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(changes, "git", fail)
    with pytest.raises(subprocess.CalledProcessError):
        changes.resolve("repo", "a" * 40, "b" * 40)
    with pytest.raises(ValueError):
        changes.resolve("repo", "a" * 40, "0" * 40)


def test_plan_expands_shared_and_skips_empty(monkeypatch):
    monkeypatch.setattr(changes, "resolve", lambda *a: ("a" * 40, "b" * 40, False))
    manifest = {
        "schema_version": 1,
        "services": ["auth_service", "transaction_service"],
        "shared_inputs": ["demo/Dockerfile.service"],
    }

    def fake(repo, *args):
        return b"M\0demo/Dockerfile.service\0" if args[0] == "diff" else b"main.py"

    monkeypatch.setattr(changes, "git", fake)
    assert (
        changes.plan("repo", "a" * 40, "b" * 40, manifest)["services"]
        == manifest["services"]
    )
    monkeypatch.setattr(changes, "git", lambda *a: b"")
    assert changes.plan("repo", "a" * 40, "b" * 40, manifest)["skip_selection"] is True


def test_allowlisted_context_and_invalid_source(tmp_path):
    repo = tmp_path / "repo"
    service = repo / "transaction_service"
    service.mkdir(parents=True)
    (repo / "demo").mkdir()
    (repo / "demo/Dockerfile.service").write_text(
        "FROM python@sha256:abc\nRUN pip install --require-hashes -r requirements-demo.lock\n"
    )
    (service / "main.py").write_text("x=1\n")
    (service / "requirements-demo.lock").write_text("# synthetic fixture\n")
    (service / ".env").write_text("do-not-copy")
    (service / "dburl.txt").write_text("do-not-copy")
    (service / "__pycache__").mkdir()
    target = tmp_path / "context"
    target.mkdir()
    stage(repo, "a" * 40, "transaction_service", target, local=True)
    assert sorted(p.name for p in target.iterdir()) == [
        ".dockerignore",
        "Dockerfile",
        "main.py",
        "requirements-demo.lock",
    ]
    (service / "main.py").write_bytes(b"x=1\x00")
    with pytest.raises(SyntaxError):
        stage(repo, "a" * 40, "transaction_service", target, local=True)


def test_pipeline_one_submission_read_only_preflight_and_empty_guard(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("QMIND_PROJECT_ID", pipeline.PROJECT)
    files = tmp_path / "files.json"
    files.write_text('["transaction_service/main.py"]')
    calls = []

    def fake(arguments, output=None):
        calls.append(arguments)
        if arguments[:2] == ["near-miss", "controls"]:
            return {"revision": "a" * 64}
        if arguments[:3] == ["near-miss", "influence", "set"]:
            state_path = Path(arguments[arguments.index("--state-file") + 1])
            state_path.write_text('{"schema_version":1}')
        if arguments[:2] == ["near-miss", "status"]:
            return {"state": "insufficient_evidence", "results": []}
        if arguments[0] == "subset":
            receipt = Path(arguments[arguments.index("--receipt-file") + 1])
            receipt.write_text('{"run_id":"11111111-1111-4111-8111-111111111111"}')
        return {}

    pipeline.execute("on", files, tmp_path / "out", qmind=fake)
    assert sum(call[0] == "subset" for call in calls) == 1
    assert any(call[:3] == ["near-miss", "influence", "restore"] for call in calls)
    assert all("evaluate" not in call for call in calls)
    files.write_text("[]")
    with pytest.raises(ValueError):
        pipeline.execute("off", files, tmp_path / "empty", qmind=fake)
    assert sum(call[0] == "subset" for call in calls) == 1


def test_offline_report_preserves_backend_zero_null_and_escapes(tmp_path):
    result = sample(tmp_path / "sample")
    assert (
        result["sample"] is True
        and result["contribution"]["counts"]["direct_addition"] == 0
    )
    result["changes"]["changed_files"] = ["<script>alert(1)</script>"]
    result["runs"]["B"]["summary"]["near_miss_explanation"]["counts"][
        "direct_addition"
    ] = None
    report.render(result, tmp_path / "escaped")
    html = (tmp_path / "escaped/report.html").read_text()
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "SYNTHETIC SAMPLE" in html and "<script src" not in html
    assert "Tests were recommended, not executed" in html
    assert report.scrub({"api_key": "hidden", "reason": "qm_live_sensitive"}) == {
        "reason": "[REDACTED]"
    }


def test_fixture_report_does_not_claim_gcp_or_live_provider_acceptance(tmp_path):
    result = sample(tmp_path / "fixture")
    html = (tmp_path / "fixture/report.html").read_text(encoding="utf-8")
    assert "GCP simulator telemetry" not in html
    assert "Explicitly synthetic fixtures; no live provider acceptance." in html
    assert "Saved source:" in html and "dataset:" in html
    assert result["data_scope"] in (tmp_path / "fixture/report.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/?token=x",
        "javascript:alert(1)",
        "https://example.com/path",
    ],
)
def test_report_rejects_unsafe_links(url):
    with pytest.raises(ValueError):
        report.valid_base(url)


def test_bundle_integrity_and_no_existing_result_dependency(tmp_path):
    sample(tmp_path)
    (tmp_path / "a/selected-tests.json").write_text("[]")
    with pytest.raises(ValueError):
        report.bundle(tmp_path / "a")
    missing = report.bundle(tmp_path / "missing")
    assert missing["manifest"]["complete"] is False


def test_publication_templates_and_workflow_contracts():
    root = Path(__file__).parents[1]
    workflow = yaml.safe_load(
        (root / ".github/workflows/selection-demo.yml").read_text(encoding="utf-8")
    )
    trigger = workflow.get("on", workflow.get(True))
    assert "workflow_call" in trigger
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert workflow["concurrency"]["queue"] == "max"
    assert set(workflow["jobs"]) == {"build", "selection"}
    assert "qm-demo-off" in workflow["jobs"]["selection"]["environment"]["name"]
    assert "qm-demo-on" in workflow["jobs"]["selection"]["environment"]["name"]
    assert workflow["jobs"]["selection"]["needs"] == "build"
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step:
                assert len(step["uses"].rsplit("@", 1)[1]) == 40
    template = "jobs:\n  demo:\n    uses: Quantik-Mind/quantikmind-pipeline-demo/.github/workflows/selection-demo.yml@__DEMO_SHA__\n    with:\n      cli_source_sha: __CLI_SOURCE_SHA__\n"
    generated = generate(template, "ab" * 20, "cd" * 20)
    caller = yaml.safe_load(generated)
    assert caller["jobs"]["demo"]["uses"].startswith(
        "Quantik-Mind/quantikmind-pipeline-demo/"
    )
    assert "__DEMO_SHA__" not in generated
    with pytest.raises(ValueError):
        generate(template, "0" * 40, "cd" * 20)


def test_download_redirect_strips_credentials():
    handler = AssetRedirect()
    req = Request(
        "https://api.github.com/path", headers={"Authorization": "Bearer synthetic"}
    )
    redirected = handler.redirect_request(
        req,
        None,
        302,
        "redirect",
        {},
        "https://release-assets.githubusercontent.com/asset",
    )
    assert redirected.get_header("Authorization") is None
    with pytest.raises(ValueError):
        handler.redirect_request(
            req, None, 302, "redirect", {}, "https://unapproved.example/asset"
        )


@pytest.mark.parametrize(
    "outcome",
    [
        "influence_disabled",
        "no_qualifying_evidence",
        "eligible_without_promotion",
        "promotion_without_additional_selection",
        "selection_changes",
        "comparison_unavailable",
        "evidence_unavailable",
    ],
)
def test_report_uses_backend_outcome_and_preserves_missing_counts(tmp_path, outcome):
    result = sample(tmp_path / "input")
    result["contribution"] = {
        "outcome": outcome,
        "comparison_status": "partial",
        "counts": {"direct_addition": None},
    }
    report.render(result, tmp_path / "output")
    assert outcome in (tmp_path / "output/report.html").read_text()
    assert (
        json.loads((tmp_path / "output/report.json").read_text())["contribution"][
            "counts"
        ]["direct_addition"]
        is None
    )


def test_frontend_newlines_cannot_inject_links():
    for url in ("https://example.com\n", "https://example.com)"):
        with pytest.raises(ValueError):
            report.valid_base(url)


def test_legacy_example_preserved_without_publication_side_effect():
    root = Path(__file__).parents[1]
    original = yaml.safe_load(
        (root / "legacy/customer-insight.yml").read_text(encoding="utf-8")
    )
    operational = yaml.safe_load(
        (root / ".github/workflows/customer-insight.yml").read_text(encoding="utf-8")
    )
    assert original["jobs"] == operational["jobs"]
    events = operational.get("on", operational.get(True))
    assert set(events) == {"workflow_dispatch"}
