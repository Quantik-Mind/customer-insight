"""Offline report formatting only. No network calls and no causal classifier."""

import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID

OUTCOMES = {
    "influence_disabled": "Near-miss selection influence was disabled.",
    "no_qualifying_evidence": "Influence was enabled; no qualifying near-miss evidence was available.",
    "eligible_without_promotion": "Eligible evidence was present; no candidate promotion was applied.",
    "promotion_without_additional_selection": "Candidate promotion occurred without additional final selections.",
    "selection_changes": "The saved frozen comparison shows final membership changes under influence.",
    "comparison_unavailable": "A complete frozen comparison is unavailable; final membership contribution cannot be established.",
    "evidence_unavailable": "Saved influence evidence is unavailable or incomplete.",
}
COUNT_LABELS = {
    "eligible_tests": "Eligible tests",
    "promoted_candidates": "Applied candidate promotions",
    "retained_promotions": "Retained promotions",
    "baseline_selected": "Frozen baseline selected",
    "actual_selected": "Actually selected",
    "direct_addition": "Direct additions",
    "indirect_addition": "Indirect additions",
    "added": "All additions",
    "removed": "Removals",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scrub(value):
    if isinstance(value, dict):
        return {
            k: scrub(v)
            for k, v in value.items()
            if not re.search(
                r"token|password|secret|credential|authorization|api_key|raw_response",
                k,
                re.I,
            )
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"qm_(?:live|dev)_[A-Za-z0-9_-]+", "[REDACTED]", value)
    return value


def valid_base(url):
    parsed = urlsplit(url)
    if (
        any(ord(character) <= 32 or ord(character) == 127 for character in url)
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or not re.fullmatch(
            r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?",
            parsed.hostname or "",
        )
    ):
        raise ValueError(
            "Frontend URL must be an HTTPS origin without credentials/query/path."
        )
    parsed.port  # Reject malformed/out-of-range port declarations.
    return url.rstrip("/")


def display(value):
    if value is None:
        return "Unavailable"
    return str(value)


def md(value):
    # Prevent markdown injection and active HTML in GitHub summaries.
    return (
        escape(display(value))
        .replace("|", "&#124;")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("`", "&#96;")
    )


def bundle(directory):
    directory = Path(directory)
    if not (directory / "manifest.json").exists():
        return {
            "manifest": {"schema_version": 1, "complete": False},
            "summary": {"status": "unavailable_or_failed"},
            "selected": [],
            "near_miss": [],
            "changes": [],
            "observations": {},
            "focused_evidence": [],
        }
    manifest = load(directory / "manifest.json")
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported CLI bundle version.")
    for name, digest in manifest.get("files", {}).items():
        if Path(name).name != name or not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
            raise ValueError("Unsafe evidence artifact name.")
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Evidence artifact integrity mismatch.")
    required = {
        "summary.json",
        "selected-tests.json",
        "selected-tests.csv",
        "near-miss.json",
        "changes.json",
        "focused-evidence.json",
        "observations.json",
    }
    if manifest.get("complete") is True and not required <= set(
        manifest.get("files", {})
    ):
        raise ValueError("Complete bundle is missing required integrity entries.")
    summary = (
        load(directory / "summary.json")
        if (directory / "summary.json").exists()
        else {}
    )
    selected = (
        load(directory / "selected-tests.json")
        if (directory / "selected-tests.json").exists()
        else []
    )
    if manifest.get("complete") is True and len(selected) != summary.get(
        "selected_experiments"
    ):
        raise ValueError("Complete list disagrees with summary.")
    own_build = directory.parent / "build/build.json"
    if not own_build.exists():
        own_build = directory.parent.parent / "source-build/build.json"
    return {
        "manifest": manifest,
        "summary": summary,
        "selected": selected,
        "build_provenance": load(own_build) if own_build.exists() else None,
        "near_miss": (
            load(directory / "near-miss.json")
            if (directory / "near-miss.json").exists()
            else []
        ),
        "changes": (
            load(directory / "changes.json")
            if (directory / "changes.json").exists()
            else []
        ),
        "observations": (
            load(directory / "observations.json")
            if (directory / "observations.json").exists()
            else {}
        ),
        "focused_evidence": (
            load(directory / "focused-evidence.json")
            if (directory / "focused-evidence.json").exists()
            else []
        ),
        "restoration": (
            load(directory.parent / "restoration.json")
            if (directory.parent / "restoration.json").exists()
            else {"status": "unverified_legacy"}
        ),
    }


def model(a, b, changes, build, frontend=None, *, sample=False, execution=None):
    frontend = valid_base(frontend) if frontend else None
    result = {
        "schema_version": 1,
        "sample": sample,
        "project_name": "Continuous Resiliance",
        "project_id": "90e48503-115d-4b34-be95-9f2f1b62767d",
        "changes": changes,
        "build": build,
        "boundary": "Tests were recommended, not executed. No deployment occurred. Banking library/workload are synthetic validation data. Image assembly does not establish startup or functional correctness. Test-count reduction is not measured time/cost savings or incident prevention.",
        "attribution": "A/B are separate executions with changing observation times. Only B's backend-validated frozen influence-off comparison supplies causal attribution.",
        "runs": {},
        "limitations": [],
    }
    entries = [("A", a, False), ("B", b, True)]
    if execution:
        entries = [entry for entry in entries if entry[0] == execution]
        result["attribution"] = (
            "Execution A is complete independently; B has not been submitted or scheduled."
            if execution == "A"
            else "Attribution uses this B run's saved frozen comparison only."
        )
    for label, value, expected in entries:
        summary = value["summary"]
        if summary.get("project_id") not in {None, result["project_id"]}:
            raise ValueError("Demo report project mismatch.")
        run_id = summary.get("run_id")
        link = (
            frontend + "/results?runId=" + str(UUID(run_id))
            if run_id and frontend
            else None
        )
        explanation = summary.get("near_miss_explanation") or {}
        context = summary.get("selection_context") or {}
        total, selected = summary.get("total_experiments"), summary.get(
            "selected_experiments"
        )
        reduction = (
            round((total - selected) / total * 100, 2)
            if type(total) is int
            and total > 0
            and type(selected) is int
            and 0 <= selected <= total
            else None
        )
        result["runs"][label] = {
            **value,
            "link": link,
            "count_reduction_pct": reduction,
            "mode_verified": explanation.get("influence_enabled") is expected,
            "provider": (context.get("provenance") or {}).get("provider"),
        }
        if explanation.get("influence_enabled") is not expected:
            result["limitations"].append(
                f"{label}: saved effective influence missing/mismatched."
            )
        if value["manifest"].get("complete") is not True:
            result["limitations"].append(f"{label}: selected export incomplete.")
        if (value.get("restoration") or {}).get("status") == "RESTORATION_REQUIRED":
            result["limitations"].append(
                f"{label}: RESTORATION REQUIRED. Preserve influence-state.json; wait/reconcile the saved run, then use conditional CLI restore. Concurrent editor changes must not be overwritten."
            )
        if context.get("status") != "complete":
            result["limitations"].append(
                f"{label}: saved mapping/configuration manifest unavailable."
            )
        result["limitations"].extend(
            f"{label}: {text}" for text in explanation.get("limitations", [])
        )
    ca = a["summary"].get("selection_context") or {} if a else {}
    cb = b["summary"].get("selection_context") or {} if b else {}
    for key in (
        "library_fingerprint",
        "mapping_fingerprint",
        "source_fingerprint",
        "fixed_configuration_fingerprint",
        "explicit_inputs_fingerprint",
        "normalized_inputs_fingerprint",
    ):
        if ca.get(key) and cb.get(key) and ca[key] != cb[key]:
            result["limitations"].append(
                f"Between-run {key} changed; do not claim controlled input parity."
            )
    result["contribution"] = (b or a)["summary"].get("near_miss_explanation") or {
        "comparison_status": "unavailable",
        "counts": {},
        "outcome": "evidence_unavailable",
    }
    provenance = (cb or ca).get("provenance") or {}
    result["data_scope"] = (
        (
            "Explicitly synthetic fixtures; no live provider acceptance. "
            if sample
            else ""
        )
        + f"Saved source: {display(provenance.get('source'))}; dataset: {display(provenance.get('dataset'))}."
    )
    return scrub(result)


def render(result, output):
    result = scrub(result)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    runs = result["runs"]
    head = str(result["changes"].get("head", ""))
    commit_link = (
        "https://github.com/Quantik-Mind/banking-app/commit/" + head
        if re.fullmatch(r"[a-f0-9]{40}", head)
        else None
    )
    lines = [
        "# Quantik Mind pipeline demo"
        + (" — SYNTHETIC SAMPLE" if result["sample"] else ""),
        "",
        result["boundary"],
        "",
        f"Commit: `{md(result['changes'].get('head'))}` · Build: **{md(result['build'].get('mode'))}** / {md(result['build'].get('status'))}",
        f"Changed services: {md(', '.join(result['changes'].get('services', [])))} · Files: {len(result['changes'].get('changed_files', []))}",
        f"Project: {md(result['project_name'])} · `{result['project_id']}`",
        f"Data: {md(result['data_scope'])}",
        "",
        "| | " + " | ".join("Execution " + label for label in runs) + " |",
        "|---|" + "---|" * len(runs),
    ]
    getters = [
        ("Status", lambda r: r["summary"].get("status")),
        (
            "Influence",
            lambda r: {True: "ON", False: "OFF"}.get(
                (r["summary"].get("near_miss_explanation") or {}).get(
                    "influence_enabled"
                ),
                "Unavailable",
            ),
        ),
        ("Saved mode verified", lambda r: r["mode_verified"]),
        ("Provider", lambda r: r["provider"]),
        (
            "Selected / total",
            lambda r: f"{display(r['summary'].get('selected_experiments'))} / {display(r['summary'].get('total_experiments'))}",
        ),
        ("Test-count reduction (%)", lambda r: r["count_reduction_pct"]),
        ("Complete selected export", lambda r: r["manifest"].get("complete")),
        (
            "Original influence restoration",
            lambda r: (r.get("restoration") or {}).get("status", "unverified_legacy"),
        ),
    ]
    for title, getter in getters:
        lines.append(
            "| "
            + title
            + " | "
            + " | ".join(md(getter(value)) for value in runs.values())
            + " |"
        )
    if commit_link:
        lines.extend(["", f"[Open Banking source commit]({commit_link})"])
    for label, value in runs.items():
        if value["link"]:
            lines.extend(
                [
                    "",
                    f"[Open saved {label}]({value['link']}) (authentication and project/history access required)",
                ]
            )
    contribution = result["contribution"]
    lines.extend(
        [
            "",
            "## Saved influence evidence within "
            + ("B" if "B" in runs else "A (influence OFF)"),
            "",
            f"Backend outcome: **{md(contribution.get('outcome'))}** · Comparison: **{md(contribution.get('comparison_status'))}**",
            "",
            "| Backend field | Value |",
            "|---|---|",
        ]
    )
    counts = contribution.get("counts") or {}
    for key in (
        "eligible_tests",
        "promoted_candidates",
        "retained_promotions",
        "baseline_selected",
        "actual_selected",
        "direct_addition",
        "indirect_addition",
        "added",
        "removed",
    ):
        lines.append(f"| {COUNT_LABELS[key]} | {md(counts.get(key))} |")
    lines.extend(
        [
            "",
            OUTCOMES.get(
                contribution.get("outcome"), "Saved influence outcome is unavailable."
            ),
            "",
            result["attribution"],
            "",
            "Zero direct additions is a valid result. Applied promotion and retention do not by themselves establish additional selection.",
            "",
            "## Evidence limitations",
            "",
        ]
    )
    lines.extend(
        ["- " + md(item) for item in result["limitations"]]
        or [
            "No additional limitations established by this export; this is not certification or customer validation."
        ]
    )
    lines.extend(
        [
            "",
            "## Technical drill-down",
            "",
            "Offline HTML contains complete lists, mapping details, safe captured configuration and observation evidence. JSON preserves backend classifications and nulls. CSV/JSON downloads are included in each run's CLI bundle.",
        ]
    )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "report.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )

    def table(headers, rows):
        return (
            "<table><thead><tr>"
            + "".join("<th>" + escape(h) + "</th>" for h in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                + "".join("<td>" + escape(display(c)) + "</td>" for c in row)
                + "</tr>"
                for row in rows
            )
            + "</tbody></table>"
        )

    comparison = table(
        [
            "",
            *(
                label + " · influence " + ("OFF" if label == "A" else "ON")
                for label in runs
            ),
        ],
        [
            [title, *(getter(value) for value in runs.values())]
            for title, getter in getters
        ],
    )
    sections = []
    for label, value in runs.items():
        summary = value["summary"]
        items = [
            ("This execution's image build provenance", value.get("build_provenance")),
            (
                "Captured configuration and fingerprints",
                summary.get("selection_context"),
            ),
            ("Mapping matches and gaps · complete paginated export", value["changes"]),
            (
                "Backend-validated promotion / retention / baseline classifications",
                value["near_miss"],
            ),
            (
                "Rules, units, freshness, traffic, coverage and episode/evaluation history",
                value["observations"],
            ),
            ("Focused sanitized selected evidence", value["focused_evidence"]),
            ("CLI export integrity and completeness", value["manifest"]),
            ("Conditional original influence restoration", value.get("restoration")),
        ]
        sections.append(f"<h2>Execution {label}</h2>")
        if value["link"]:
            sections.append(
                f'<p><a rel="noopener noreferrer" href="{escape(value["link"], quote=True)}">Open authenticated saved result {label}</a></p>'
            )
        for title, data in items:
            sections.append(
                "<details><summary>"
                + escape(title)
                + "</summary><pre>"
                + escape(json.dumps(data, indent=2))
                + "</pre></details>"
            )
        fields = ["internal_test_id", "id", "service", "experiment_type", "origin"]
        sections.append(
            "<details><summary>Complete selected list · "
            + str(len(value["selected"]))
            + " records</summary>"
            + table(fields, [[row.get(k) for k in fields] for row in value["selected"]])
            + "</details>"
        )
    html = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Quantik Mind pipeline demo</title><style>body{font:16px system-ui;background:#f5f7fb;color:#172238;margin:0}main{max-width:1180px;margin:auto;padding:32px}h1,h2{color:#193a65}.card,details{background:white;border:1px solid #d7e1ed;border-radius:10px;padding:18px;margin:14px 0}table{border-collapse:collapse;width:100%;background:white}td,th{padding:10px;border-bottom:1px solid #d7e1ed;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer;font-weight:600}.notice{border-left:5px solid #c47b00;padding:16px;background:#fff5dc}a{color:#1455a2}</style><main>'
    html += (
        "<h1>Quantik Mind · Pipeline demo"
        + (" · SYNTHETIC SAMPLE" if result["sample"] else "")
        + "</h1>"
    )
    html += '<p class="notice">' + escape(result["boundary"]) + "</p>"
    if commit_link:
        html += (
            '<p><a rel="noopener noreferrer" href="'
            + escape(commit_link, quote=True)
            + '">Open Banking source commit</a></p>'
        )
    html += (
        "<p>Project: <strong>"
        + escape(result["project_name"])
        + "</strong> · "
        + result["project_id"]
        + "</p>"
    )
    html += (
        "<div class=card><strong>Commit:</strong> "
        + escape(display(result["changes"].get("head")))
        + "<br><strong>Build:</strong> "
        + escape(display(result["build"].get("mode")))
        + " · "
        + escape(display(result["build"].get("status")))
        + "<br><strong>Changed services:</strong> "
        + escape(", ".join(result["changes"].get("services", [])))
        + "<br><strong>Changed files:</strong> "
        + escape(", ".join(result["changes"].get("changed_files", [])))
        + "</div>"
        + comparison
    )
    html += (
        "<h2>Saved near-miss influence evidence within "
        + ("B" if "B" in runs else "A (influence OFF)")
        + "</h2><p>"
        + escape(display(contribution.get("outcome")))
        + " · Comparison: "
        + escape(display(contribution.get("comparison_status")))
        + "</p>"
    )
    html += "<p>Data: " + escape(result["data_scope"]) + "</p>"
    html += (
        "<p>"
        + escape(
            OUTCOMES.get(
                contribution.get("outcome"), "Saved influence outcome is unavailable."
            )
        )
        + "</p>"
    )
    html += table(
        ["Backend field", "Value"],
        [
            [COUNT_LABELS[key], counts.get(key)]
            for key in (
                "eligible_tests",
                "promoted_candidates",
                "retained_promotions",
                "baseline_selected",
                "actual_selected",
                "direct_addition",
                "indirect_addition",
                "removed",
            )
        ],
    )
    html += (
        "<p>"
        + escape(result["attribution"])
        + "</p><p>Zero direct additions is valid. A retained promotion may already belong to the frozen baseline.</p>"
    )
    html += (
        "<h2>Limitations</h2><ul>"
        + "".join("<li>" + escape(item) + "</li>" for item in result["limitations"])
        + "</ul>"
    )
    html += (
        "<details><summary>Source/build provenance and measured build duration</summary><pre>"
        + escape(
            json.dumps(
                {"changes": result["changes"], "build": result["build"]}, indent=2
            )
        )
        + "</pre></details>"
        + "".join(sections)
        + "</main></html>"
    )
    (output / "report.html").write_text(html, encoding="utf-8")
    integrity = {
        "schema_version": 1,
        "sample": result["sample"],
        "files": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in ("report.md", "report.json", "report.html")
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(integrity, indent=2), encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ("changes", "build", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--a", type=Path)
    parser.add_argument("--b", type=Path)
    parser.add_argument("--execution", choices=["A", "B"])
    parser.add_argument("--frontend")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    render(
        model(
            bundle(args.a) if args.a else None,
            bundle(args.b) if args.b else None,
            load(args.changes),
            load(args.build),
            args.frontend,
            sample=args.sample,
            execution=args.execution,
        ),
        args.output,
    )


if __name__ == "__main__":
    main()
