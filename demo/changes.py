"""Safe Git range parsing and explicit affected-service expansion."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode

SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(repo, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=check, capture_output=True
    )
    return result.stdout


def resolve(repo, base, head, baseline="origin/main"):
    if not SHA.fullmatch(head) or head == "0" * 40:
        raise ValueError(
            "Deleted branch or invalid head: no build or selection is permitted."
        )
    git(repo, "cat-file", "-e", head + "^{commit}")
    if base == "0" * 40:
        try:
            base = git(repo, "merge-base", baseline, head).decode().strip()
        except subprocess.CalledProcessError:
            # Only a true root commit may compare against the empty tree.
            parents = (
                git(repo, "rev-list", "--parents", "-n", "1", head).decode().split()
            )
            if len(parents) != 1:
                raise ValueError(
                    "Missing branch baseline/history. Fetch history; do not guess."
                )
            base = (
                subprocess.run(
                    ["git", "-C", str(repo), "hash-object", "-t", "tree", "--stdin"],
                    input=b"",
                    capture_output=True,
                    check=True,
                )
                .stdout.decode()
                .strip()
            )
            return base, head, True
    if not SHA.fullmatch(base):
        raise ValueError("Base must be an explicit 40-character commit SHA.")
    git(repo, "cat-file", "-e", base + "^{commit}")
    git(repo, "merge-base", "--is-ancestor", base, head)
    return base, head, False


def parse_status(raw):
    tokens = raw.decode("utf-8", errors="strict").split("\0")
    if tokens[-1] != "":
        raise ValueError("Truncated NUL-delimited Git output.")
    tokens.pop()
    changes = []
    while tokens:
        status = tokens.pop(0)
        if not re.fullmatch(r"[AMDTRCU][0-9]*", status):
            raise ValueError("Unsupported Git file status.")
        count = 2 if status[0] in {"R", "C"} else 1
        if len(tokens) < count:
            raise ValueError("Truncated Git rename record.")
        paths, tokens = tokens[:count], tokens[count:]
        for path in paths:
            if (
                path != path.strip()
                or not path
                or path.startswith(("/", "\\"))
                or "\\" in path
                or any(ord(c) < 32 for c in path)
                or ".." in Path(path).parts
                or len(path) > 1000
            ):
                raise ValueError(
                    "Path cannot be safely transported through the CLI contract."
                )
        changes.append({"status": status, "paths": paths})
    return changes


def plan(repo, base, head, manifest, baseline="origin/main"):
    if (
        manifest.get("schema_version") != 1
        or not isinstance(manifest.get("services"), list)
        or not manifest["services"]
        or len(manifest["services"]) > 50
        or len(set(manifest["services"])) != len(manifest["services"])
        or any(
            not isinstance(service, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", service)
            for service in manifest["services"]
        )
        or not isinstance(manifest.get("shared_inputs"), list)
    ):
        raise ValueError("Invalid reviewed build allowlist.")
    base, head, root = resolve(repo, base, head, baseline)
    raw = git(repo, "diff", "--name-status", "-z", "--find-renames", base, head)
    records = parse_status(raw)
    files = sorted({path for item in records for path in item["paths"]})
    if len(files) > 300 or len(urlencode({"changed_files": files}, doseq=True)) > 12000:
        raise ValueError("Changed-file query bound exceeded; no selection submitted.")
    services = manifest["services"]
    shared = any(path in manifest["shared_inputs"] for path in files)
    affected = (
        services
        if shared
        else [
            service
            for service in services
            if any(path.startswith(service + "/") for path in files)
        ]
    )
    extant, deleted = [], []
    for service in affected:
        exists = (
            git(repo, "ls-tree", "--name-only", head, service + "/main.py")
            .decode()
            .strip()
        )
        (extant if exists else deleted).append(service)
    return {
        "schema_version": 1,
        "base": base,
        "head": head,
        "root_commit": root,
        "changes": records,
        "changed_files": files,
        "services": extant,
        "deleted_services": deleted,
        "shared_build_input": shared,
        "unmapped_build_inputs": [
            p
            for p in files
            if not any(p.startswith(s + "/") for s in services)
            and p not in manifest["shared_inputs"]
        ],
        "files_sha256": hashlib.sha256(
            json.dumps(files, separators=(",", ":")).encode()
        ).hexdigest(),
        "skip_selection": not files or not affected,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        manifest = json.loads(
            git(args.repo, "show", args.head + ":demo/build-services.json")
        )
        result = plan(args.repo, args.base, args.head, manifest)
    except Exception as exc:
        (args.output / "failure.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "change_plan",
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "selection_submitted": False,
                }
            ),
            encoding="utf-8",
        )
        raise
    (args.output / "changes.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (args.output / "changed-files.json").write_text(
        json.dumps(result["changed_files"], indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
