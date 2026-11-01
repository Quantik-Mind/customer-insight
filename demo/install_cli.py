"""Hash-checked CLI wheel download/install. No API selection calls."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener


class AssetRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.hostname not in {
            "github.com",
            "api.github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }:
            raise ValueError("Unapproved release-asset redirect.")
        redirected = super().redirect_request(
            request, fp, code, message, headers, newurl
        )
        if redirected:
            redirected.remove_header("Authorization")
        return redirected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    url = urlsplit(args.url)
    # Use GitHub release asset API URL, with explicit octet-stream Accept; supports private assets.
    if (
        url.scheme != "https"
        or url.hostname != "api.github.com"
        or url.username
        or url.password
        or url.query
        or url.fragment
        or not re.fullmatch(
            r"/repos/Quantik-Mind/quantikmind-platform/releases/assets/[0-9]+", url.path
        )
        or not re.fullmatch(r"[a-f0-9]{64}", args.sha256)
    ):
        raise ValueError("Require the approved GitHub release-asset URL and SHA-256.")
    headers = {
        "Accept": "application/octet-stream",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("DEMO_READ_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    with tempfile.TemporaryDirectory(prefix="qmind-install-") as directory:
        wheel = Path(directory) / "quantikmind_cli-0.1.0b2-py3-none-any.whl"
        with build_opener(AssetRedirect()).open(
            Request(args.url, headers=headers), timeout=60
        ) as response:
            data = response.read(20_000_001)
        if len(data) > 20_000_000 or hashlib.sha256(data).hexdigest() != args.sha256:
            raise ValueError("CLI wheel integrity/size check failed.")
        wheel.write_bytes(data)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "-r",
                str(args.lock),
            ],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-deps", str(wheel)],
            check=True,
        )
        subprocess.run(["qmind", "--version"], check=True)


if __name__ == "__main__":
    main()
