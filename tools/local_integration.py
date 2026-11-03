"""Opt-in REAL local integration; only an inspected, labelled disposable database.

No HTTP/CLI responses, selection algorithms or provider adapters are replaced.
The in-memory queue has no delivery loop: this harness delivers its persisted
queued run to the actual worker, explicitly recorded as local manual delivery.
Run with the backend validation Python 3.11 and --database-state/--output paths.
"""

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "platform"
BACKEND = PLATFORM / "backend"
DEMO = ROOT / "demo"
BANKING = ROOT / "banking-cli"
PROJECT = "90e48503-115d-4b34-be95-9f2f1b62767d"
PROM_IMAGE = "prom/prometheus@sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996"


def command(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def docker(*args):
    return command(["docker", *args], capture_output=True, text=True).stdout.strip()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_http(url, process=None):
    import httpx

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process and process.poll() is not None:
            raise RuntimeError("Local backend exited; inspect backend log")
        try:
            response = httpx.get(url, timeout=2)
            if response.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("Local HTTP startup deadline exceeded")


def prometheus(output):
    """Real Prometheus TSDB with explicitly synthetic, past event-time samples."""
    now = int(time.time())
    lines, all_series = [], {}
    for service in ("transaction_service-001", "notification_service-001"):
        labels = f'service="{service}",job="local-rehearsal",instance="synthetic-local"'
        series = {
            f"service_requests_total{{{labels}}}": lambda t: (t - now + 7200) * 10,
            f"service_errors_total{{{labels}}}": lambda t: (t - now + 7200) * 0.01,
            f"service_cpu_load{{{labels}}}": lambda t: 0.4,
        }
        for bucket, fraction in (("1", 0), ("2", 1), ("+Inf", 1)):
            series[
                f'service_response_time_seconds_bucket{{{labels},le="{bucket}"}}'
            ] = (lambda t, f=fraction: (t - now + 7200) * 10 * f)
        for signal in ("latency", "error_rate", "request_rate", "cpu"):
            series[
                f'service_measurement_updated_seconds{{{labels},signal="{signal}"}}'
            ] = (lambda t: t - 1)
        for name, value in series.items():
            lines.extend(f"{name} {value(t)} {t}\n" for t in range(now - 3600, now, 10))
        all_series.update(series)

    class Exporter(BaseHTTPRequestHandler):
        def do_GET(self):
            body = "".join(
                f"{name} {value(int(time.time()))}\n"
                for name, value in all_series.items()
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    # Docker Desktop reaches this synthetic-only exporter through its host gateway.
    # It serves no files, credentials, project API or application behavior.
    exporter = ThreadingHTTPServer(("0.0.0.0", 0), Exporter)
    Thread(target=exporter.serve_forever, daemon=True).start()
    metrics = output / "synthetic.openmetrics"
    metrics.write_text("".join(lines) + "# EOF\n", encoding="utf-8", newline="\n")
    config = output / "prometheus.yml"
    config.write_text(
        f"global:\n  scrape_interval: 10s\nscrape_configs:\n  - job_name: local-rehearsal\n    honor_labels: true\n    static_configs:\n      - targets: ['host.docker.internal:{exporter.server_port}']\n        labels:\n          instance: synthetic-local\n",
        encoding="utf-8",
        newline="\n",
    )
    name, port = "qm-rehearsal-prom-" + uuid4().hex[:10], free_port()
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "quantikmind.local-rehearsal=20261031",
        "--user",
        "0",
        "--tmpfs",
        "/fixture:rw",
        "-p",
        f"127.0.0.1:{port}:9090",
        "--entrypoint",
        "/bin/sh",
        PROM_IMAGE,
        "-c",
        "sleep 7200",
    )
    # docker cp does not reliably write mounted tmpfs on Docker Desktop.
    for source in (metrics, config):
        command(
            [
                "docker",
                "exec",
                "-i",
                name,
                "/bin/sh",
                "-c",
                "cat > /fixture/" + source.name,
            ],
            input=source.read_bytes(),
            capture_output=True,
        )
    docker(
        "exec",
        name,
        "/bin/promtool",
        "tsdb",
        "create-blocks-from",
        "openmetrics",
        "/fixture/synthetic.openmetrics",
        "/fixture/tsdb",
    )
    docker(
        "exec",
        "-d",
        name,
        "/bin/prometheus",
        "--config.file=/fixture/prometheus.yml",
        "--storage.tsdb.path=/fixture/tsdb",
        "--web.listen-address=0.0.0.0:9090",
    )
    url = f"http://127.0.0.1:{port}"
    wait_http(url + "/-/ready")
    return name, url, exporter


def seed(owner_url, prom_url):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    __import__("app.models")  # register the production ORM
    from app.models.user import Organization
    from app.models.project import Project
    from app.models.project_settings import ProjectSettings
    from app.models.service_account import ServiceAccount, ApiKey
    from app.models.functional_test_library import FunctionalTestLibrary
    from app.models.functional_test_results import FunctionalTestResult
    from app.core.api_keys import generate_api_key, get_key_prefix, hash_api_key, last4
    from app.schemas.default_observability_profile import (
        BUILTIN_PROMETHEUS_DEFAULT_PROFILE,
    )
    from app.db.repositories.observability_profile_repository import create_profile
    from app.services.licensing_service import set_organization_plan_for_testing

    engine = create_engine(owner_url)
    org, project = uuid4(), UUID(PROJECT)
    key = generate_api_key()
    influence_key = generate_api_key()
    with Session(engine) as db:
        assert db.query(Project).count() == 0, "Refuse to seed a nonempty database"
        db.add(
            Organization(
                id=org, name="LOCAL SYNTHETIC REHEARSAL", slug="local-rehearsal"
            )
        )
        db.flush()
        db.add(
            Project(
                id=project,
                organization_id=org,
                name="Continuous Resiliance [LOCAL SYNTHETIC]",
            )
        )
        db.flush()
        config = {
            "active_metrics_provider": "prometheus",
            "near_miss_generation": "initial",
            "near_miss_observation_config": {"enabled": False, "cadence_seconds": 60},
            "near_miss": {
                "detectionEnabled": True,
                "selectionInfluenceEnabled": False,
                "automaticObservationEnabled": False,
                "windowMinutes": 6,
                "projectRules": [
                    {
                        "id": "synthetic-latency",
                        "metric": "latency",
                        "entry": 1.8,
                        "breach": 2.0,
                        "recovery": 1.6,
                        "duration_seconds": 60,
                        "minimum_count": 2,
                        "recovery_seconds": 60,
                        "recovery_count": 2,
                        "minimum_traffic": 1,
                        "max_source_age_seconds": 300,
                        "max_evidence_age_seconds": 600,
                        "aggregation": "max_component_p95",
                    }
                ],
            },
            "runtime_inventory": {
                "version": 1,
                "source": "local-cli-rehearsal",
                "dataset": "synthetic",
                "prometheus_jobs": ["local-rehearsal"],
                "services": [
                    {"id": s, "components": [s]}
                    for s in ("transaction_service-001", "notification_service-001")
                ],
            },
        }
        db.add(
            ProjectSettings(
                project_id=project,
                observability_enabled=True,
                test_library_enabled=True,
                historical_data_enabled=True,
                additional_config=config,
            )
        )
        sa = ServiceAccount(
            id=uuid4(),
            organization_id=org,
            project_id=project,
            name="local synthetic CLI",
        )
        db.add(sa)
        db.flush()
        db.add(
            ApiKey(
                organization_id=org,
                project_id=project,
                service_account_id=sa.id,
                key_prefix=get_key_prefix(key),
                key_last4=last4(key),
                key_hash=hash_api_key(key),
                scopes=["selection:run", "results:read"],
            )
        )
        db.add(
            ApiKey(
                organization_id=org,
                project_id=project,
                service_account_id=sa.id,
                key_prefix=get_key_prefix(influence_key),
                key_last4=last4(influence_key),
                key_hash=hash_api_key(influence_key),
                scopes=["near_miss:influence"],
            )
        )
        for i in range(1200):
            service = (
                "transaction_service-001" if i < 900 else "notification_service-001"
            )
            row = FunctionalTestLibrary(
                project_id=PROJECT,
                test_id=f"synthetic-only-{i:04}",
                name=f"SYNTHETIC definition {i}",
                service=service,
                suite=f"synthetic-{i % 12}",
                framework="pytest",
                test_level="integration",
                tags=["synthetic", "local-rehearsal"],
                business_criticality="HIGH" if i % 3 == 0 else "MEDIUM",
                avg_duration_ms=400 + i,
                timeout_ms=3000,
                parallelizable=True,
                code_mapping={"file_globs": [service.split("-001")[0] + "/*.py"]},
            )
            db.add(row)
            db.flush()
            db.add(
                FunctionalTestResult(
                    run_id=uuid4(),
                    project_id=PROJECT,
                    test_id=row.id,
                    service=service,
                    status="failed" if i % 9 == 0 else "passed",
                    duration_ms=400 + i,
                    started_at=datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(hours=2),
                    is_flaky=False,
                    extra_data={"synthetic_fixture": True},
                )
            )
        profile = BUILTIN_PROMETHEUS_DEFAULT_PROFILE.model_copy(
            update={"id": "project-prometheus"}
        )
        create_profile(
            db,
            organization_id=str(org),
            project_id=PROJECT,
            profile_payload=profile,
            metadata={
                "prometheus_url": prom_url,
                "profile_ready": True,
                "selected_job": "local-rehearsal",
                "effective_job": "local-rehearsal",
                "profile_source": "default",
                "service_label": "service",
                "lookback": "5m",
            },
        )
        db.commit()
        set_organization_plan_for_testing(db, org, "enterprise_l")
    return engine, str(org), key, influence_key


def inspect_run(engine, folder, expected):
    """Compare real HTTP exports with persisted identities, never classify causality."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    exported = bundle_for_inspection(folder / "bundle")
    summary, manifest = exported["summary"], exported["manifest"]
    context, explanation = (
        summary["selection_context"],
        summary["near_miss_explanation"],
    )
    assert summary["status"] == "completed"
    assert context["status"] == "complete" and context["mapping_status"] == "complete"
    assert context["controls"]["selection_influence_enabled"] is expected
    assert context["controls"]["detection_enabled"] is True
    assert context["controls"]["automatic_observation_enabled"] is False
    assert context["library_count"] == 1200 and context["unmatched_file_count"] > 0
    assert context["provenance"]["provider"] == "prometheus"
    assert context["provenance"]["dataset"] == "synthetic"
    assert context["provenance"]["evaluation_id"]
    assert explanation["influence_enabled"] is expected
    if expected:
        assert explanation["comparison_status"] == "complete"
        assert explanation["counts"]["eligible_tests"] > 0
        assert all(
            explanation["counts"][key] is not None
            for key in (
                "baseline_selected",
                "actual_selected",
                "direct_addition",
                "indirect_addition",
                "removed",
            )
        )
    selected = exported["selected"]
    assert len(selected) > 100  # actual exporter must fetch multiple selected pages
    assert (
        manifest["complete"] is True and manifest["selection_context_complete"] is True
    )
    assert (
        len(selected) == summary["selected_experiments"] == manifest["selected_count"]
    )
    assert len(exported["near_miss"]) == 1200
    with (folder / "bundle/selected-tests.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        csv_rows = list(csv.DictReader(handle))
    assert {int(r["internal_test_id"]) for r in csv_rows} == {
        r["internal_test_id"] for r in selected
    }
    with Session(engine) as db:
        rows = db.execute(
            text(
                "select test_id, selected, reasons from functional_run_selection where run_id = :run"
            ),
            {"run": summary["run_id"]},
        ).all()
        assert len(rows) == 1200
        assert {r.test_id for r in rows if r.selected} == {
            r["internal_test_id"] for r in selected
        }
        assert sum("selection_context" in (r.reasons or {}) for r in rows) == 1
        considered_skipped = {r.test_id for r in rows if not r.selected}
        assert any(
            r.get("internal_test_id") in considered_skipped
            for r in exported["changes"]
            if r.get("matched")
        )
    observations = exported["observations"]
    assert observations.get("evaluations")
    if expected:
        assert observations.get("episodes")
    result = {
        "run_id": summary["run_id"],
        "selected": len(selected),
        "library": len(rows),
        "mode": expected,
        "manifest_complete": True,
        "single_context_anchor": True,
        "skipped_mapping_included": True,
        "mapping_gaps": context["unmatched_file_count"],
        "comparison_status": explanation["comparison_status"],
        "backend_counts": explanation["counts"],
        "fingerprints": {k: v for k, v in context.items() if "fingerprint" in k},
        "saved_controls": context["controls"],
        "saved_provenance": context["provenance"],
    }
    write(folder / "inspection.json", result)
    return result


def bundle_for_inspection(path):
    from demo.report import bundle

    return bundle(path)


def verify_artifacts(output):
    """Offline verification/regeneration of known completed runs; no HTTP calls."""
    from html.parser import HTMLParser
    from demo.report import bundle, model, render

    class OfflineHTML(HTMLParser):
        def handle_starttag(self, tag, attrs):
            assert tag not in {
                "script",
                "iframe",
                "img",
                "link",
            }, "Unexpected external or executable HTML resource"

    results = []
    for mode in ("sync", "async"):
        access = (output / (mode + "-backend.log")).read_text(
            encoding="utf-8", errors="replace"
        )
        assert access.count('"GET /api/v1/functional/select?') == 2
        assert "view=selected&page=2&page_size=100" in access
        assert "view=near_miss&page=12&page_size=100" in access
        if mode == "async":
            assert (
                access.count(
                    '"POST /internal/workers/functional-selection HTTP/1.1" 404'
                )
                == 2
            )
            assert (
                access.count(
                    '"POST /internal/workers/functional-selection HTTP/1.1" 200'
                )
                == 2
            )
        for influence in ("off", "on"):
            folder = output / mode / influence
            inspection = json.loads((folder / "inspection.json").read_text())
            saved = bundle(folder / "bundle")  # verify all file hashes and counts
            recovered = json.loads((folder / "recovery-wait.json").read_text())
            assert recovered["run_id"] == inspection["run_id"]
            assert saved["summary"]["run_id"] == inspection["run_id"]
            if mode == "async" and influence == "on":
                copy = bundle(folder / "recovered")
                assert copy["selected"] == saved["selected"]
                assert copy["summary"] == saved["summary"]
            results.append(
                {"mode": mode, "influence": influence, "inspection": inspection}
            )
        report = render(
            model(
                bundle(output / mode / "off/bundle"),
                bundle(output / mode / "on/bundle"),
                json.loads((output / "changes.json").read_text()),
                json.loads((output / "build/build.json").read_text()),
                "https://example.invalid",
                sample=True,
            ),
            output / mode / "report",
        )
        html = (output / mode / "report/report.html").read_text(encoding="utf-8")
        OfflineHTML().feed(html)
        assert "SYNTHETIC SAMPLE" in html and "GCP simulator telemetry" not in html
        assert "no live provider acceptance" in html
        assert (
            report["runs"]["A"]["mode_verified"]
            and report["runs"]["B"]["mode_verified"]
        )
        assert report["contribution"]["comparison_status"] == "complete"
        integrity = json.loads((output / mode / "report/manifest.json").read_text())
        for name, digest in integrity["files"].items():
            assert (
                hashlib.sha256(
                    (output / mode / "report" / name).read_bytes()
                ).hexdigest()
                == digest
            )
        for artifact in [
            *(output / mode / "report").glob("*"),
            *(output / mode / "off/bundle").glob("*"),
            *(output / mode / "on/bundle").glob("*"),
        ]:
            if artifact.is_file():
                content = artifact.read_text(encoding="utf-8-sig")
                assert "local-fixture-runtime" not in content
                assert "synthetic-local-worker-only" not in content
                assert "qm_live_" not in content and "qm_dev_" not in content
    for field in (
        "library_fingerprint",
        "mapping_fingerprint",
        "source_fingerprint",
        "fixed_configuration_fingerprint",
        "explicit_inputs_fingerprint",
        "normalized_inputs_fingerprint",
    ):
        assert len({item["inspection"]["fingerprints"][field] for item in results}) == 1
    write(
        output / "integration-results.json",
        {
            "fixture_based_integration": True,
            "live_provider_acceptance": False,
            "worker_delivery": "actual authenticated internal HTTP endpoint; local delivery of in_memory queued receipt, not Cloud Tasks",
            "selection_requests": 4,
            "no_submission_during_recovery": True,
            "wrong_organization_worker_requests_rejected": 2,
            "runs": results,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-state",
        type=Path,
        help="Previously created EMPTY labelled disposable DB; otherwise create a new tmpfs DB",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--verify-existing",
        action="store_true",
        help="Only inspect saved local artifacts and regenerate reports; no services or submissions",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if args.verify_existing:
        sys.path.insert(0, str(DEMO))
        verify_artifacts(output)
        return
    output.mkdir(parents=True, exist_ok=False)
    own_database = args.database_state is None
    if own_database:
        name, dbport = "qm-cli-rehearsal-db-" + uuid4().hex[:10], free_port()
        dbid = docker(
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "quantikmind.local-rehearsal=20261031",
            "--tmpfs",
            "/var/lib/postgresql/data:rw",
            "-p",
            f"127.0.0.1:{dbport}:5432",
            "-e",
            "POSTGRES_PASSWORD=local-fixture-only",
            "-e",
            "POSTGRES_DB=qm_rehearsal",
            "postgres@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab",
        )
        state = {"id": dbid, "name": name, "port": str(dbport)}
        write(output / "db-state.json", state)
        for attempt in range(60):
            if (
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        name,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "postgres",
                    ],
                    capture_output=True,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.25)
        docker(
            "exec",
            name,
            "psql",
            "-U",
            "postgres",
            "-d",
            "qm_rehearsal",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE ROLE qm_rehearsal_runtime LOGIN PASSWORD 'local-fixture-runtime' NOSUPERUSER NOBYPASSRLS",
        )
    else:
        state = json.loads(args.database_state.read_text())
    inspection = json.loads(docker("inspect", state["id"]))[0]
    assert (
        inspection["Config"]["Labels"].get("quantikmind.local-rehearsal") == "20261031"
    )
    assert inspection["Name"].startswith("/qm-cli-rehearsal-db-")
    assert inspection["HostConfig"]["Tmpfs"].get("/var/lib/postgresql/data")
    assert (
        inspection["HostConfig"]["PortBindings"]["5432/tcp"][0]["HostIp"] == "127.0.0.1"
    )
    owner = f"postgresql://postgres:local-fixture-only@127.0.0.1:{state['port']}/qm_rehearsal"
    runtime = f"postgresql://qm_rehearsal_runtime:local-fixture-runtime@127.0.0.1:{state['port']}/qm_rehearsal"
    os.environ.update(
        ENVIRONMENT="staging",
        DEBUG="false",
        DATABASE_URL=runtime,
        DB_ENABLED="true",
        JWT_SECRET_KEY="synthetic-local-rehearsal-secret-20261031-only",
        ALLOW_PRIVATE_OBSERVABILITY_URLS="true",
        ASYNC_SELECTION_ENABLED="false",
        SELECTION_QUEUE_PROVIDER="in_memory",
        CLOUD_TASKS_ENABLED="false",
        INTERNAL_WORKER_TOKEN="synthetic-local-worker-only",
        RUNTIME_DATABASE_ROLE="qm_rehearsal_runtime",
        QUANTIKMIND_TELEMETRY_DISABLED="1",
    )
    if own_database:
        migration_env = os.environ.copy()
        migration_env["ALEMBIC_DATABASE_URL"] = owner
        with (output / "migration.log").open("w", encoding="utf-8") as migration_log:
            command(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=BACKEND,
                env=migration_env,
                stdout=migration_log,
                stderr=subprocess.STDOUT,
            )
    sys.path[:0] = [str(BACKEND), str(DEMO)]
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from demo.changes import plan
    from demo.report import bundle, model, render

    prom = exporter = None
    server = child = None
    try:
        prom, prom_url, exporter = prometheus(output)
        engine, org, key, influence_key = seed(owner, prom_url)
        manifest = json.loads((BANKING / "demo/build-services.json").read_text())
        # Actual historical Banking commit range; reviewed build manifest is local,
        # because implementation is intentionally uncommitted. No synthetic commits.
        head = docker_git_head()
        base = "5cc93a214348022953b8324b437bbc249ed9353c"
        change_plan = plan(BANKING, base, head, manifest)
        assert change_plan["services"] and not change_plan["skip_selection"]
        write(output / "changes.json", change_plan)
        write(output / "changed-files.json", change_plan["changed_files"])
        # Exercise the real build script on the corrected local implementation.
        build_plan = change_plan
        write(output / "build-plan.json", build_plan)
        command(
            [
                sys.executable,
                "-m",
                "demo.build",
                "--repo",
                BANKING,
                "--plan",
                output / "build-plan.json",
                "--mode",
                "real",
                "--local-validation",
                "--output",
                output / "build",
            ],
            cwd=DEMO,
        )
        results = []
        for execution_mode in ("sync", "async"):
            # Synthetic initial state differs between pairs so both restoration
            # directions are exercised; no owner writes occur inside A/B.
            with Session(engine) as db:
                from app.models.project_settings import ProjectSettings

                row = (
                    db.query(ProjectSettings).filter_by(project_id=UUID(PROJECT)).one()
                )
                value = json.loads(json.dumps(row.additional_config))
                value["near_miss"]["selectionInfluenceEnabled"] = (
                    execution_mode == "sync"
                )
                row.additional_config = value
                db.commit()
            port = free_port()
            env = os.environ.copy()
            env["ASYNC_SELECTION_ENABLED"] = str(execution_mode == "async").lower()
            log = (output / (execution_mode + "-backend.log")).open(
                "w", encoding="utf-8"
            )
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=BACKEND,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            wait_http(f"http://127.0.0.1:{port}/health", server)
            import httpx
            from concurrent.futures import ThreadPoolExecutor

            controls_url = f"http://127.0.0.1:{port}/api/v1/near-miss/controls"
            influence_url = f"http://127.0.0.1:{port}/api/v1/near-miss/influence"
            scope = {"project_id": PROJECT}
            read_headers = {"X-QM-API-Key": key}
            write_headers = {"X-QM-API-Key": influence_key}
            original = httpx.get(
                controls_url, params=scope, headers=read_headers
            ).json()
            request = {
                "enabled": not original["selection_influence_enabled"],
                "expected_revision": original["revision"],
                "operation_id": str(uuid4()),
            }
            assert (
                httpx.put(
                    influence_url, params=scope, headers=read_headers, json=request
                ).status_code
                == 403
            )
            assert (
                httpx.get(
                    controls_url,
                    params={"project_id": str(uuid4())},
                    headers=write_headers,
                ).status_code
                == 403
            )

            def competing_edit(_):
                value = {**request, "operation_id": str(uuid4())}
                return httpx.put(
                    influence_url, params=scope, headers=write_headers, json=value
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                races = list(pool.map(competing_edit, range(2)))
            assert sorted(response.status_code for response in races) == [200, 409]
            applied = next(
                response.json() for response in races if response.status_code == 200
            )
            recovered_control = httpx.put(
                influence_url,
                params=scope,
                headers=write_headers,
                json={
                    "enabled": original["selection_influence_enabled"],
                    "expected_revision": applied["revision"],
                    "operation_id": str(uuid4()),
                    "restore_of": applied["last_operation_id"],
                },
            )
            assert recovered_control.status_code == 200
            assert (
                recovered_control.json()["selection_influence_enabled"]
                == original["selection_influence_enabled"]
            )
            # An actual CLI no-op barrier invalidates a deliberately late original PUT.
            control_folder = output / execution_mode / "control-recovery"
            control_folder.mkdir(parents=True)
            pending_operation = str(uuid4())
            base_control = recovered_control.json()
            write(
                control_folder / "state.json",
                {
                    "schema_version": 1,
                    "project_id": PROJECT,
                    "original": base_control,
                    "operation_id": pending_operation,
                    "restore_operation_id": str(uuid4()),
                    "status": "prepared",
                },
            )
            control_env = env.copy()
            control_env.update(
                QMIND_API_URL=f"http://127.0.0.1:{port}",
                QMIND_API_KEY=key,
                QMIND_INFLUENCE_API_KEY=influence_key,
                USERPROFILE=str(control_folder / "home"),
            )
            executable = ROOT / "_tools/clean-cli/Scripts/qmind.exe"
            command(
                [
                    executable,
                    "init",
                    "--project-id",
                    PROJECT,
                    "--framework",
                    "pytest",
                    "--non-interactive",
                ],
                cwd=control_folder,
                env=control_env,
                capture_output=True,
                text=True,
            )
            cancellation = command(
                [
                    executable,
                    "near-miss",
                    "influence",
                    "restore",
                    "--state-file",
                    control_folder / "state.json",
                ],
                cwd=control_folder,
                env=control_env,
                capture_output=True,
                text=True,
            )
            write(control_folder / "result.json", json.loads(cancellation.stdout))
            late = httpx.put(
                influence_url,
                params=scope,
                headers=write_headers,
                json={
                    "enabled": not original["selection_influence_enabled"],
                    "expected_revision": base_control["revision"],
                    "operation_id": pending_operation,
                },
            )
            assert late.status_code == 409
            write(
                output / execution_mode / "control-authorization-cas.json",
                {
                    "selection_key_write_denied": True,
                    "cross_project_denied": True,
                    "concurrent_same_revision_statuses": [200, 409],
                    "restored": True,
                    "actual_cli_cancel_barrier_late_write_denied": True,
                },
            )
            for influence in ("off", "on"):
                folder = output / execution_mode / influence
                folder.mkdir(parents=True)
                if influence == "on":
                    from demo.cross_run import validate_reference

                    previous = output / execution_mode / "off/publication"
                    captured = json.loads((previous / "session.json").read_text())
                    metadata = {
                        "repository": {"full_name": "Quantik-Mind/banking-app"},
                        "path": ".github/workflows/quantikmind-pipeline-demo.yml",
                        "head_branch": "demo/pipeline",
                        "conclusion": "success",
                        "event": "push",
                        "run_attempt": 1,
                        "id": "local-fixture",
                        "head_sha": change_plan["head"],
                    }
                    validated = validate_reference(
                        previous,
                        metadata,
                        a_tooling_sha=captured["tooling_sha"],
                        cli_sha=captured["cli_source_sha"],
                        wheel_sha=captured["wheel_sha256"],
                    )
                    assert (validated["head"], validated["base"]) == (
                        change_plan["head"],
                        change_plan["base"],
                    )
                    assert (
                        json.loads(
                            (previous / "source-build/changed-files.json").read_text()
                        )
                        == change_plan["changed_files"]
                    )
                command(
                    [
                        sys.executable,
                        "-m",
                        "demo.build",
                        "--repo",
                        BANKING,
                        "--plan",
                        output / "build-plan.json",
                        "--mode",
                        "real",
                        "--local-validation",
                        "--output",
                        folder / "build",
                    ],
                    cwd=DEMO,
                )
                cli_env = env.copy()
                cli_env.update(
                    QMIND_API_URL=f"http://127.0.0.1:{port}",
                    QMIND_API_KEY=key,
                    QMIND_INFLUENCE_API_KEY=influence_key,
                    QMIND_PROJECT_ID=PROJECT,
                    PYTHONPATH=str(DEMO),
                    USERPROFILE=str(folder / "home"),
                )
                cli_env["PATH"] = (
                    str(ROOT / "_tools/clean-cli/Scripts")
                    + os.pathsep
                    + cli_env["PATH"]
                )
                with (folder / "pipeline.log").open(
                    "w", encoding="utf-8"
                ) as pipeline_log:
                    child = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "demo.pipeline",
                            "--mode",
                            influence,
                            "--files",
                            str(output / "changed-files.json"),
                            "--output",
                            str(folder),
                        ],
                        cwd=folder,
                        env=cli_env,
                        stdout=pipeline_log,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    if execution_mode == "async":
                        receipt = folder / "receipt.json"
                        deadline = time.monotonic() + 45
                        received = None
                        while child.poll() is None and time.monotonic() < deadline:
                            if receipt.exists():
                                received = json.loads(receipt.read_text()).get("run_id")
                                if received:
                                    break
                            time.sleep(0.1)
                        if not received:
                            raise RuntimeError(
                                "Async submission did not create durable receipt"
                            )
                        run_id = received
                        held = subprocess.run(
                            [
                                str(ROOT / "_tools/clean-cli/Scripts/qmind.exe"),
                                "near-miss",
                                "influence",
                                "restore",
                                "--state-file",
                                str(folder / "influence-state.json"),
                            ],
                            cwd=folder,
                            env=cli_env,
                            capture_output=True,
                            text=True,
                        )
                        assert (
                            held.returncode == 7
                        ), "Restoration must remain held while the actual queued run is pending"
                        write(
                            folder / "pending-restoration-check.json",
                            {
                                "exit_code": held.returncode,
                                "held_without_settings_write": True,
                            },
                        )
                        time.sleep(2)  # establish genuine pending read before delivery
                        from app.queues.base import SelectionJob
                        from app.queues.selection_jobs import SelectionJobType
                        from app.core.rls_context import set_rls_org_context
                        from app.models.run import Run
                        from sqlalchemy import create_engine

                        with Session(create_engine(runtime)) as db:
                            set_rls_org_context(db, org)
                            queued = db.query(Run).filter_by(id=UUID(run_id)).one()
                            assert queued.status == "queued"
                            job = SelectionJob(
                                job_type=SelectionJobType.FUNCTIONAL_SELECTION,
                                run_id=run_id,
                                project_id=PROJECT,
                                organization_id=org,
                                idempotency_key=queued.idempotency_key,
                                payload={
                                    "changed_files": change_plan["changed_files"],
                                    "lookback_commits_hours": 24,
                                    "signal_override": "auto",
                                },
                            )
                        import httpx

                        # Real authenticated internal endpoint, not a patched worker.
                        worker_url = f"http://127.0.0.1:{port}/internal/workers/functional-selection"
                        headers = {
                            "X-Internal-Worker-Token": "synthetic-local-worker-only"
                        }
                        wrong_scope = job.model_dump(
                            mode="json", exclude={"created_at"}
                        )
                        wrong_scope["organization_id"] = str(uuid4())
                        rejected = httpx.post(
                            worker_url, json=wrong_scope, headers=headers, timeout=30
                        )
                        assert rejected.status_code == 404
                        delivery = httpx.post(
                            worker_url,
                            json=job.model_dump(mode="json", exclude={"created_at"}),
                            headers=headers,
                            timeout=120,
                        )
                        delivery.raise_for_status()
                        assert delivery.json()["executed"] is True
                        write(folder / "local-worker-delivery.json", delivery.json())
                    if child.wait(timeout=650):
                        raise RuntimeError(
                            f"{execution_mode}/{influence} failed; inspect pipeline.log"
                        )
                run_id = json.loads((folder / "receipt.json").read_text())["run_id"]
                inspection = inspect_run(engine, folder, influence == "on")
                assert (
                    json.loads((folder / "restoration.json").read_text())["status"]
                    == "restored"
                )
                persisted_controls = httpx.get(
                    controls_url, params=scope, headers=read_headers
                ).json()
                assert (
                    persisted_controls["selection_influence_enabled"]
                    == original["selection_influence_enabled"]
                )
                # A is rendered completely before B's separate subprocess starts.
                label = "A" if influence == "off" else "B"
                current = bundle(folder / "bundle")
                render(
                    model(
                        current if label == "A" else None,
                        current if label == "B" else None,
                        change_plan,
                        json.loads((folder / "build/build.json").read_text()),
                        None,
                        sample=True,
                        execution=label,
                    ),
                    folder / "report",
                )
                from demo.session import package
                import shutil

                source = folder / "source-build"
                source.mkdir()
                for name in ("changes.json", "changed-files.json"):
                    shutil.copyfile(output / name, source / name)
                shutil.copyfile(folder / "build/build.json", source / "build.json")
                package(
                    source,
                    folder,
                    folder / "report",
                    folder / "publication",
                    label,
                    tooling_sha="ab" * 20,
                    cli_sha="cd" * 20,
                    wheel_sha=hashlib.sha256(
                        (
                            ROOT
                            / "_tools/cli-wheel-b3/quantikmind_cli-0.1.0b3-py3-none-any.whl"
                        ).read_bytes()
                    ).hexdigest(),
                )
                with Session(engine) as db:
                    before = db.execute(text("select count(*) from runs")).scalar_one()
                recovery_commands = [
                    ["runs", "wait", run_id, "--timeout-seconds", "20", "--json"]
                ]
                if execution_mode == "async" and influence == "on":
                    recovery_commands.append(
                        [
                            "runs",
                            "export",
                            run_id,
                            "--output-dir",
                            str(folder / "recovered"),
                            "--expected-influence",
                            influence,
                        ]
                    )
                for cli_args in recovery_commands:
                    recovered = command(
                        [ROOT / "_tools/clean-cli/Scripts/qmind.exe", *cli_args],
                        cwd=folder,
                        env=cli_env,
                        capture_output=True,
                        text=True,
                    )
                    write(
                        folder / ("recovery-" + cli_args[1] + ".json"),
                        json.loads(recovered.stdout),
                    )
                with Session(engine) as db:
                    after = db.execute(text("select count(*) from runs")).scalar_one()
                assert before == after
                results.append(
                    {
                        "mode": execution_mode,
                        "influence": influence,
                        "run_id": run_id,
                        "runs_before_recovery": before,
                        "runs_after_recovery": after,
                        "inspection": inspection,
                    }
                )
            result = render(
                model(
                    bundle(output / execution_mode / "off/bundle"),
                    bundle(output / execution_mode / "on/bundle"),
                    change_plan,
                    json.loads((output / "build/build.json").read_text()),
                    "https://example.invalid",
                    sample=True,
                ),
                output / execution_mode / "report",
            )
            write(
                output / execution_mode / "report-inspection.json",
                {
                    "sample": result["sample"],
                    "attribution": result["attribution"],
                    "limitations": result["limitations"],
                },
            )
            server.terminate()
            server.wait(timeout=20)
            server = None
            log.close()
        for execution_mode in ("sync", "async"):
            access = (output / (execution_mode + "-backend.log")).read_text(
                encoding="utf-8", errors="replace"
            )
            assert access.count('"GET /api/v1/functional/select?') == 2
            assert "view=selected&page=2&page_size=100" in access
            assert "view=near_miss&page=12&page_size=100" in access
        write(
            output / "integration-results.json",
            {
                "fixture_based_integration": True,
                "live_provider_acceptance": False,
                "worker_delivery": "real canonical worker, locally delivered in_memory receipt",
                "selection_requests": 4,
                "no_submission_during_recovery": True,
                "runs": results,
            },
        )
        verify_artifacts(output)
    finally:
        if child and child.poll() is None:
            # Terminate only the process tree launched by this fixture harness.
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    capture_output=True,
                )
            else:
                child.terminate()
            child.wait(timeout=20)
        if server:
            server.terminate()
            server.wait(timeout=20)
        if prom:
            docker("rm", "-f", prom)
        if exporter:
            exporter.shutdown()
            exporter.server_close()
        if own_database:
            docker("rm", "-f", state["id"])
        for credential in output.glob("*/*/home/.qmind/credentials.yaml"):
            credential.unlink()


def docker_git_head():
    return command(
        ["git", "rev-parse", "HEAD"], cwd=BANKING, capture_output=True, text=True
    ).stdout.strip()


if __name__ == "__main__":
    main()
