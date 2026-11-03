"""Authenticated, bounded read-only recovery of an immutable successful A artifact."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
from uuid import UUID
import zipfile

from .report import bundle

REPOSITORY = "Quantik-Mind/banking-app"
PROJECT = os.environ.get("QMIND_PROJECT_ID", "").strip() or "90e48503-115d-4b34-be95-9f2f1b62767d"


def validate_reference(root, run, *, tooling_sha, cli_sha, wheel_sha):
    root = Path(root)
    session = json.loads((root / "session.json").read_text())
    assert run["repository"]["full_name"] == REPOSITORY
    assert run["path"] == ".github/workflows/quantikmind-pipeline-demo.yml"
    assert run["head_branch"] == "demo/pipeline" and run["conclusion"] == "success"
    assert run["event"] in {"push", "workflow_dispatch"} and run["run_attempt"] == 1
    assert session["workflow_run_id"] == str(run["id"])
    assert session["execution"] == "A" and session["project_id"] == PROJECT
    assert session["repository"] == REPOSITORY and session["head"] == run["head_sha"]
    assert (
        session["tooling_sha"] == tooling_sha and session["cli_source_sha"] == cli_sha
    )
    assert session["wheel_sha256"] == wheel_sha
    invalid_files = []
    for name, digest in session["files"].items():
        path = PurePosixPath(name)
        assert (
            re.fullmatch(r"[A-Za-z0-9_./-]+", name)
            and not path.is_absolute()
            and ".." not in path.parts
        )
        target = root / name
        if not target.is_file():
            invalid_files.append(f"missing:{name}")
        elif hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            invalid_files.append(f"checksum:{name}")
    assert not invalid_files, "Recovered artifact integrity failures: " + ", ".join(
        invalid_files
    )
    assert {
        "source-build/changes.json",
        "source-build/changed-files.json",
        "source-build/build.json",
        "execution/receipt.json",
        "execution/bundle/manifest.json",
        "execution/restoration.json",
    } <= set(session["files"])
    plan = json.loads((root / "source-build/changes.json").read_text())
    files = json.loads((root / "source-build/changed-files.json").read_text())
    assert plan["head"] == session["head"] and plan["base"] == session["base"]
    assert plan["changed_files"] == files and not plan["skip_selection"]
    assert json.loads((root / "source-build/build.json").read_text())["mode"] == "real"
    assert (
        json.loads((root / "execution/restoration.json").read_text())["status"]
        == "restored"
    )
    saved = bundle(root / "execution/bundle")
    assert saved["manifest"]["complete"] is True
    assert saved["summary"]["run_id"] == session["selection_run_id"]
    assert saved["summary"]["near_miss_explanation"]["influence_enabled"] is False
    UUID(session["session_id"])
    return session


class ArtifactRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        url = urlsplit(newurl)
        host = url.hostname or ""
        if (
            url.scheme != "https"
            or url.username
            or not (
                host == "api.github.com"
                or host.endswith(".blob.core.windows.net")
                or host.endswith(".githubusercontent.com")
                or host == "github.com"
            )
        ):
            raise ValueError("Untrusted artifact redirect")
        redirected = super().redirect_request(
            request, fp, code, message, headers, newurl
        )
        if host != "api.github.com":
            redirected.remove_header("Authorization")
        return redirected


def get(path):
    assert path.startswith("https://api.github.com/repos/" + REPOSITORY + "/actions/")
    request = Request(
        path,
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "Accept": "application/vnd.github+json",
            "User-Agent": "quantikmind-pipeline-demo",
        },
    )
    with build_opener(ArtifactRedirect()).open(request, timeout=45) as response:
        value = response.read(50_000_001)
    assert len(value) <= 50_000_000, "Artifact response exceeds bound"
    return value


def recover(run_id, output, *, tooling_sha, cli_sha, wheel_sha):
    assert re.fullmatch(r"[1-9][0-9]{0,19}", str(run_id))
    prefix = "https://api.github.com/repos/" + REPOSITORY + "/actions/"
    run = json.loads(get(prefix + "runs/" + str(run_id)))
    artifacts = []
    for page in range(1, 11):
        values = json.loads(
            get(prefix + f"runs/{run_id}/artifacts?per_page=100&page={page}")
        )["artifacts"]
        artifacts.extend(v for v in values if v["name"] == "qmind-execution-A")
        if len(values) < 100:
            break
    assert len(artifacts) == 1 and not artifacts[0]["expired"]
    artifact = artifacts[0]
    content = get(prefix + "artifacts/" + str(artifact["id"]) + "/zip")
    assert (
        artifact.get("digest") == "sha256:" + hashlib.sha256(content).hexdigest()
    ), "Artifact digest unavailable/mismatched"
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert (
            len(archive.infolist()) <= 150
            and sum(item.file_size for item in archive.infolist()) <= 100_000_000
        )
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            assert (
                re.fullmatch(r"[A-Za-z0-9_./-]+", item.filename)
                and not name.is_absolute()
                and ".." not in name.parts
            )
            assert (
                item.external_attr >> 16
            ) & 0o170000 != 0o120000, "Artifact symlink refused"
            if item.is_dir():
                continue
            assert name.suffix in {
                ".json",
                ".csv",
                ".html",
                ".md",
            }, "Executable/unexpected artifact refused"
            target = output / str(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
    session = validate_reference(
        output, run, tooling_sha=tooling_sha, cli_sha=cli_sha, wheel_sha=wheel_sha
    )
    return session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--a-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tooling-sha", required=True)
    parser.add_argument("--cli-sha", required=True)
    parser.add_argument("--wheel-sha", required=True)
    args = parser.parse_args()
    session = recover(
        args.a_run_id,
        args.output,
        tooling_sha=args.tooling_sha,
        cli_sha=args.cli_sha,
        wheel_sha=args.wheel_sha,
    )
    with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
        handle.write("head=" + session["head"] + "\nbase=" + session["base"] + "\n")


if __name__ == "__main__":
    main()
