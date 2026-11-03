"""Build local images only from sanitized exact-commit service contexts."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import sys
import re
from datetime import datetime, timezone

from .changes import git, SHA


def stage(repo, head, service, target, *, local=False):
    if not SHA.fullmatch(head) or not re.fullmatch(r"[A-Za-z0-9_-]+", service):
        raise ValueError("Invalid source commit or service identity.")
    if local and (repo / service).is_symlink():
        raise ValueError("Service directory cannot be a symlink.")
    prefix = service + "/"
    if local:
        # Explicit local-validation mode; never used by the hosted workflow.
        names = [
            str(p.relative_to(repo)).replace("\\", "/")
            for p in (repo / service).iterdir()
            if p.is_file()
        ]
    else:
        names = [
            name
            for name in git(repo, "ls-tree", "-r", "--name-only", "-z", head, prefix)
            .decode()
            .split("\0")
            if name
        ]
    selected = [
        name
        for name in names
        if name.startswith(prefix)
        and "/" not in name[len(prefix) :]
        and (name.endswith(".py") or name == prefix + "requirements-demo.lock")
        and not re.search(
            r"secret|credential|private_key|password", Path(name).name, re.I
        )
    ]
    if (
        prefix + "main.py" not in selected
        or prefix + "requirements-demo.lock" not in selected
    ):
        raise ValueError("Service source or hash lock missing.")
    digests = {}
    for name in selected:
        path = repo / name
        if local:
            if path.is_symlink():
                raise ValueError("Symlink in service context.")
            data = path.read_bytes()
        else:
            mode = git(repo, "ls-tree", head, name).decode().split()[0]
            if mode not in {"100644", "100755"}:
                raise ValueError("Only regular source files may enter build context.")
            data = git(repo, "show", head + ":" + name)
        if name.endswith(".py"):
            try:
                ast.parse(data, filename=name)
            except ValueError as exc:
                # Python versions disagree on whether a NUL byte is a
                # SyntaxError or ValueError.  Expose one stable validation
                # contract to the hosted and local demo paths.
                raise SyntaxError(str(exc)) from exc
        (target / Path(name).name).write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    dockerfile = (
        (repo / "demo/Dockerfile.service").read_bytes()
        if local
        else git(repo, "show", head + ":demo/Dockerfile.service")
    )
    if b"@sha256:" not in dockerfile or b"--require-hashes" not in dockerfile:
        raise ValueError("Build requires pinned base and hash-checked dependencies.")
    (target / "Dockerfile").write_bytes(dockerfile)
    (target / ".dockerignore").write_text(
        "**\n!*.py\n!requirements-demo.lock\n!Dockerfile\n!wheelhouse/\n!wheelhouse/*.whl\n",
        encoding="utf-8",
    )
    digests["Dockerfile"] = hashlib.sha256(dockerfile).hexdigest()
    return hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()


def build(repo, plan, mode, output, *, local=False):
    output.mkdir(parents=True, exist_ok=True)
    manifest = (
        json.loads((repo / "demo/build-services.json").read_text())
        if local
        else json.loads(git(repo, "show", plan["head"] + ":demo/build-services.json"))
    )
    if not set(plan["services"]) <= set(manifest["services"]):
        raise ValueError("Requested build service is not in the reviewed allowlist.")
    result = {
        "schema_version": 1,
        "mode": mode,
        "commit": plan["head"],
        "local_uncommitted_validation": local,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "platform": "linux/amd64",
        "tests_executed": False,
        "deployed": False,
        "services": [],
        "status": "running",
    }
    try:
        if mode not in {"real", "simulated"}:
            raise ValueError("Build mode must be explicitly real or simulated.")
        for service in plan["services"]:
            entry = {
                "service": service,
                "mode": mode,
                "image_id": None,
                "status": "running",
            }
            result["services"].append(entry)
            started = time.monotonic()
            try:
                with tempfile.TemporaryDirectory(prefix="qmind-context-") as directory:
                    context = Path(directory)
                    entry["context_sha256"] = stage(
                        repo, plan["head"], service, context, local=local
                    )
                    entry["base_image"] = next(
                        line.split(None, 1)[1]
                        for line in (context / "Dockerfile").read_text().splitlines()
                        if line.startswith("FROM ")
                    )
                    if mode == "real":
                        # TLS stays on the host's trusted certificate path; image installation is offline.
                        # Binary wheels only, fixed CPython 3.11 Linux target, hashes checked on both sides.
                        subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "pip",
                                "download",
                                "--quiet",
                                "--require-hashes",
                                "--only-binary=:all:",
                                "--platform",
                                "manylinux2014_x86_64",
                                "--implementation",
                                "cp",
                                "--python-version",
                                "311",
                                "--abi",
                                "cp311",
                                "--dest",
                                str(context / "wheelhouse"),
                                "-r",
                                str(context / "requirements-demo.lock"),
                            ],
                            check=True,
                            timeout=240,
                        )
                        log = output / (service + "-build.log")
                        with log.open("w", encoding="utf-8") as handle:
                            subprocess.run(
                                [
                                    "docker",
                                    "build",
                                    "--platform",
                                    "linux/amd64",
                                    "--iidfile",
                                    str(context / "image.id"),
                                    str(context),
                                ],
                                check=True,
                                stdout=handle,
                                stderr=subprocess.STDOUT,
                                timeout=600,
                            )
                        entry["image_id"] = (context / "image.id").read_text().strip()
                    entry["status"] = (
                        "built" if mode == "real" else "SIMULATED — no image created"
                    )
            finally:
                entry["duration_seconds"] = round(time.monotonic() - started, 3)
        result["status"] = "completed"
    except Exception:
        result["status"] = "failed"
        if result["services"]:
            result["services"][-1]["status"] = "failed"
        raise
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output / "build.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--mode", choices=["real", "simulated"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-validation", action="store_true")
    args = parser.parse_args()
    build(
        args.repo,
        json.loads(args.plan.read_text()),
        args.mode,
        args.output,
        local=args.local_validation,
    )


if __name__ == "__main__":
    main()
