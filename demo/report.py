"""Offline report formatting only. No network calls and no causal classifier."""

import argparse
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import statistics
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

# Display the normalized backend rule contract, not raw provider-unit inference.
NORMALIZED_METRIC_UNITS = {
    "latency": "seconds (p95)",
    "error_rate": "ratio (0–1)",
    "cpu": "ratio (0–1)",
    "request_rate": "requests/second",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def probability_summary(rows):
    values = sorted(
        float(row["informative_probability"])
        for row in rows
        if isinstance(row.get("informative_probability"), (int, float))
    )
    if not values:
        return {"count": 0, "minimum": None, "median": None, "maximum": None, "bins": []}
    bounds = ((0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4),
              (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8),
              (0.8, 0.9), (0.9, 1.0000000001))
    return {
        "count": len(values),
        "minimum": values[0],
        "median": statistics.median(values),
        "maximum": values[-1],
        "bins": [
            {"from": low, "to": min(high, 1.0), "count": sum(low <= v < high for v in values)}
            for low, high in bounds
        ],
    }


def changed_probability(row):
    off, on = row.get("probability_off"), row.get("probability_on")
    return isinstance(off, (int, float)) and isinstance(on, (int, float)) and off != on


def percentage(value):
    return "Unavailable" if not isinstance(value, (int, float)) else f"{value * 100:.2f}%"


def comparison_reason(row):
    reason = row.get("selection_change_reason")
    if reason == "removed_adaptive_threshold_increased":
        return "Removed because the adaptive threshold increased; the saved individual probability did not change and no coverage guardrail retained the test."
    if reason in {"added_probability_increased", "added_above_threshold"}:
        return "Added because its saved estimated informativeness increased enough to meet the adaptive threshold."
    if reason in {"added_coverage_guardrail", "removed_coverage_policy"}:
        return "Selection changed through the saved mapped-risk coverage policy."
    if reason:
        return str(reason).replace("_", " ").capitalize() + "."
    if row.get("baseline_selected") is False and row.get("selected") is True:
        return "Added with near-miss influence; saved evidence does not isolate a more specific cause."
    if row.get("baseline_selected") is True and row.get("selected") is False:
        return "Removed with near-miss influence; saved evidence does not isolate a more specific cause."
    return "Selection did not change."


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
    local = os.environ.get("QMIND_LOCAL_DEMO") == "1" and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    if (
        any(ord(character) <= 32 or ord(character) == 127 for character in url)
        or (parsed.scheme != "https" and not local)
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
            "excluded": [],
            "assessed": [],
            "coverage_gaps": [],
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
    modeled = [row for row in selected if row.get("assessment_status") == "estimated"]
    if modeled:
        if len(modeled) != len(selected) or any(
            not isinstance(row.get("informative_probability"), (int, float))
            for row in selected
        ):
            raise ValueError("Model-mode export contains missing probability assessments.")
        expected = sorted(
            selected,
            key=lambda row: (-float(row["informative_probability"]), int(row["internal_test_id"])),
        )
        if [row.get("internal_test_id") for row in selected] != [row.get("internal_test_id") for row in expected]:
            raise ValueError("Model-mode export is not in canonical probability order.")
    own_build = directory.parent / "build/build.json"
    if not own_build.exists():
        own_build = directory.parent.parent / "source-build/build.json"
    return {
        "manifest": manifest,
        "summary": summary,
        "selected": selected,
        "excluded": (
            load(directory / "excluded-tests.json")
            if (directory / "excluded-tests.json").exists()
            else []
        ),
        "assessed": (
            load(directory / "assessed-tests.json")
            if (directory / "assessed-tests.json").exists()
            else []
        ),
        "coverage_gaps": (
            load(directory / "coverage-gaps.json")
            if (directory / "coverage-gaps.json").exists()
            else []
        ),
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
    supplied = [value for value in (a, b) if value]
    project_ids = {
        value.get("summary", {}).get("project_id")
        for value in supplied
        if value.get("summary", {}).get("project_id")
    }
    if len(project_ids) > 1:
        raise ValueError("Demo report project mismatch.")
    project_id = next(iter(project_ids), "90e48503-115d-4b34-be95-9f2f1b62767d")
    result = {
        "schema_version": 1,
        "sample": sample,
        "project_name": (
            "Continuous Resiliance"
            if project_id == "90e48503-115d-4b34-be95-9f2f1b62767d"
            else "Local banking selection demo"
        ),
        "project_id": project_id,
        "changes": changes,
        "build": build,
        "boundary": "Tests were selected, not executed. The demo intentionally ends at selection and reporting. Banking library/workload are synthetic validation data. Image assembly does not establish startup or functional correctness. Test-count reduction is measured; duration savings, when shown, are estimates from saved historical durations and are not measured pipeline wall-clock savings.",
        "attribution": "A/B are separate executions with changing observation times. Only B's backend-validated frozen comparison without near-miss influence supplies causal attribution.",
        "runs": {},
        "limitations": [],
        "normalized_metric_units": NORMALIZED_METRIC_UNITS,
    }
    entries = [("A", a, False), ("B", b, True)]
    if execution:
        entries = [entry for entry in entries if entry[0] == execution]
        result["attribution"] = (
            "This A execution does not submit or schedule B; its report is complete independently."
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
            "model": {
                "versions": sorted({row.get("model_version") for row in value["selected"] if row.get("model_version")}),
                "all_selected_probabilities_available": bool(value["selected"]) and all(row.get("informative_probability") is not None for row in value["selected"]),
                "first_rank": value["selected"][0].get("priority_rank") if value["selected"] else None,
                "last_rank": value["selected"][-1].get("priority_rank") if value["selected"] else None,
                "artifact_sha256": next(
                    (row.get("artifact_sha256") for row in value["assessed"] if row.get("artifact_sha256")),
                    ((summary.get("business_metrics") or {}).get("model_details") or {}).get("artifact_sha256"),
                ),
                "feature_contract": next(
                    (row.get("feature_schema_version") for row in value["assessed"] if row.get("feature_schema_version")),
                    ((summary.get("business_metrics") or {}).get("model_details") or {}).get("feature_schema_version"),
                ),
                "training_data_kind": next(
                    (row.get("training_data_kind") for row in value["assessed"] if row.get("training_data_kind")),
                    ((summary.get("business_metrics") or {}).get("model_details") or {}).get("training_data_kind"),
                ),
                "calibration_status": next(
                    (row.get("calibration_status") for row in value["assessed"] if row.get("calibration_status")),
                    None,
                ),
            },
            "probability_distribution": {
                "complete_population": probability_summary(value["assessed"]),
                "selected": probability_summary(value["selected"]),
            },
            "membership": {
                "standard_threshold": sum(
                    row.get("mandatory_critical_coverage") is not True
                    for row in value["selected"]
                ),
                "coverage_guardrail": sum(
                    row.get("mandatory_critical_coverage") is True
                    for row in value["selected"]
                ),
            },
            "selection_metrics": {
                "semantics_version": (summary.get("business_metrics") or {}).get("metric_semantics_version"),
                "mapped_risk_coverage": (summary.get("business_metrics") or {}).get("mapped_risk_coverage"),
                "critical_risk_coverage": (
                    ((summary.get("business_metrics") or {}).get("mapped_risk_coverage") or {}).get("critical")
                    or (summary.get("business_metrics") or {}).get("critical_risk_area_coverage")
                ),
                "overall_risk_coverage": (
                    ((summary.get("business_metrics") or {}).get("mapped_risk_coverage") or {}).get("overall")
                    or (summary.get("business_metrics") or {}).get("declared_behavior_coverage")
                ),
                "coverage_gaps": (summary.get("business_metrics") or {}).get("coverage_gaps"),
                "membership_reconciliation": (summary.get("business_metrics") or {}).get("membership_reconciliation"),
                "legacy_score_diagnostics": (summary.get("business_metrics") or {}).get("legacy_score_diagnostics"),
                "selection_configuration": summary.get("selection_configuration")
                or (summary.get("business_metrics") or {}).get("selection_configuration"),
            },
        }
        if explanation.get("influence_enabled") is not expected:
            result["limitations"].append(
                f"{label}: saved effective influence missing/mismatched."
            )
        if value["manifest"].get("complete") is not True:
            result["limitations"].append(f"{label}: selected export incomplete.")
        if (value.get("restoration") or {}).get("status") in {
            "RESTORATION_REQUIRED",
            "PRIOR_OPERATION_REQUIRES_RECOVERY",
        }:
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
    comparison_rows = (b or a).get("near_miss", [])
    result["near_miss_comparison"] = {
        "tests": [dict(row, readable_reason=comparison_reason(row)) for row in comparison_rows],
        "probability_changed": sum(changed_probability(row) for row in comparison_rows),
        "probability_only": sum(
            changed_probability(row)
            and row.get("baseline_selected") == row.get("selected")
            for row in comparison_rows
        ),
        "added": sum(
            row.get("baseline_selected") is False and row.get("selected") is True
            for row in comparison_rows
        ),
        "removed": sum(
            row.get("baseline_selected") is True and row.get("selected") is False
            for row in comparison_rows
        ),
    }
    counts = result["contribution"].get("counts") or {}
    if result["contribution"].get("comparison_status") == "complete":
        baseline, added, removed, actual = (
            counts.get("baseline_selected"), counts.get("added"),
            counts.get("removed"), counts.get("actual_selected"),
        )
        if all(type(value) is int for value in (baseline, added, removed, actual)):
            if baseline + added - removed != actual:
                raise ValueError("Saved near-miss membership counts do not reconcile.")
            result["near_miss_comparison"]["reconciliation"] = {
                "without_influence": baseline,
                "added": added,
                "removed": removed,
                "with_influence": actual,
                "valid": True,
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
        ("Run ID", lambda r: r["summary"].get("run_id")),
        ("Decision time", lambda r: r["summary"].get("created_at") or r["summary"].get("completed_at")),
        (
            "Influence",
            lambda r: {True: "With near-miss influence", False: "Without near-miss influence"}.get(
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
        ("Selected by standard threshold", lambda r: r["membership"]["standard_threshold"]),
        ("Additional mapped-risk guardrail inclusions", lambda r: r["membership"]["coverage_guardrail"]),
        (
            "Critical risk coverage",
            lambda r: "{}/{}".format(
                (r["selection_metrics"].get("critical_risk_coverage") or {}).get("covered_count", "Unavailable"),
                (r["selection_metrics"].get("critical_risk_coverage") or {}).get("total_count", "Unavailable"),
            ),
        ),
        (
            "Overall risk coverage",
            lambda r: "{}/{}".format(
                (r["selection_metrics"].get("overall_risk_coverage") or {}).get("covered_count", "Unavailable"),
                (r["selection_metrics"].get("overall_risk_coverage") or {}).get("total_count", "Unavailable"),
            ),
        ),
        (
            "Risks without selected tests",
            lambda r: len(r["selection_metrics"].get("coverage_gaps") or []),
        ),
        (
            "Selection breadth (tau)",
            lambda r: (r["selection_metrics"].get("selection_configuration") or {}).get("effective_tau", "Unavailable"),
        ),
        (
            "Minimum informativeness for standard selection",
            lambda r: (r["selection_metrics"].get("membership_reconciliation") or {}).get("effective_threshold", "Unavailable"),
        ),
        ("Complete selected export", lambda r: r["manifest"].get("complete")),
        ("Model version", lambda r: ", ".join(r["model"]["versions"]) or "Unavailable"),
        ("Feature contract", lambda r: r["model"].get("feature_contract") or "Unavailable"),
        ("Model SHA-256", lambda r: r["model"].get("artifact_sha256") or "Unavailable"),
        ("Training provenance", lambda r: r["model"].get("training_data_kind") or "Unavailable"),
        ("All selected probabilities available", lambda r: r["model"]["all_selected_probabilities_available"]),
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
    for label, value in runs.items():
        distribution = value["probability_distribution"]
        coverage = value["selection_metrics"].get("mapped_risk_coverage") or {}
        lines.extend(
            [
                "",
                f"## Execution {label}: probability and mapped-risk summary",
                "",
                "Estimated informativeness is the model-estimated chance that a test provides new, relevant risk evidence. It is not failure probability.",
                "",
                "| Population | Count | Minimum | Median | Maximum |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for population in ("complete_population", "selected"):
            values = distribution[population]
            lines.append(
                "| " + ("Complete assessed population" if population == "complete_population" else "Selected tests")
                + f" | {values['count']} | {percentage(values['minimum'])} | {percentage(values['median'])} | {percentage(values['maximum'])} |"
            )
        lines.extend(
            [
                "",
                "Coverage shows defined risks with at least one associated test selected. Tests have not necessarily run. This does not establish complete behavioral coverage or elimination of risk.",
                "",
                "| Severity | Covered | Defined | Gaps |",
                "|---|---:|---:|---:|",
            ]
        )
        for severity in ("critical", "high", "medium", "low", "unknown", "overall"):
            metric = coverage.get(severity) or {}
            defined = metric.get("total_count")
            covered = metric.get("covered_count")
            gaps = defined - covered if type(defined) is int and type(covered) is int else "Unavailable"
            lines.append(f"| {severity.title()} | {display(covered)} | {display(defined)} | {display(gaps)} |")
    lines.extend(
        [
            "",
            "## Saved influence evidence within "
            + ("B" if "B" in runs else "A (near-miss influence disabled)"),
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
    lines.append(
        f"| Individual probabilities changed | {result['near_miss_comparison']['probability_changed']} |"
    )
    lines.append(
        f"| Probability changed, selection unchanged | {result['near_miss_comparison']['probability_only']} |"
    )
    lines.extend(
        [
            "",
            OUTCOMES.get(
                contribution.get("outcome"), "Saved influence outcome is unavailable."
            ),
            "",
            result["attribution"],
            "",
            "Both frozen assessments use the same saved inputs. Only near-miss influence changes.",
            "",
            "Zero direct additions is a valid result. Applied promotion and retention do not by themselves establish additional selection.",
            "",
            "## Evidence limitations",
            "",
        ]
    )
    changed_rows = result["near_miss_comparison"]["tests"]
    membership_rows = [
        row for row in changed_rows
        if row.get("baseline_selected") != row.get("selected")
    ]
    if membership_rows:
        lines.extend(
            [
                "",
                "### Added and removed tests",
                "",
                "| Test | Service | Without near-miss influence | With near-miss influence | Probability change | Thresholds | Explanation |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in membership_rows:
            off_selected = "Selected" if row.get("baseline_selected") else "Not selected"
            on_selected = "Selected" if row.get("selected") else "Not selected"
            off, on = row.get("probability_off"), row.get("probability_on")
            delta = percentage(on - off) if isinstance(off, (int, float)) and isinstance(on, (int, float)) else "Unavailable"
            lines.append(
                "| " + md(row.get("test_identifier") or row.get("test_id"))
                + " | " + md(row.get("service") or row.get("saved_service"))
                + f" | {off_selected} ({percentage(off)}) | {on_selected} ({percentage(on)})"
                + f" | {delta} points | {percentage(row.get('threshold_off'))} → {percentage(row.get('threshold_on'))}"
                + " | " + md(row.get("readable_reason")) + " |"
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
                label + " · " + ("without near-miss influence" if label == "A" else "with near-miss influence")
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
            (
                "Normalized backend rule units (when evidence is available)",
                result["normalized_metric_units"],
            ),
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
            ("Complete assessed population", value["assessed"]),
            ("Complete unselected population", value["excluded"]),
            ("Mapped risks without selected tests", value["coverage_gaps"]),
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
        fields = ["priority_rank", "internal_test_id", "id", "service", "informative_probability", "risk_areas", "business_criticality", "selection_utility", "inclusion_rule", "mandatory_critical_coverage", "model_version"]
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
    for label, value in runs.items():
        distribution = value["probability_distribution"]
        coverage = value["selection_metrics"].get("mapped_risk_coverage") or {}
        html += f"<h2>Execution {escape(label)}: probability and mapped-risk summary</h2>"
        html += "<p>Estimated informativeness concerns new, relevant risk evidence; it is not failure probability.</p>"
        html += table(
            ["Population", "Count", "Minimum", "Median", "Maximum"],
            [
                [
                    "Complete assessed population" if key == "complete_population" else "Selected tests",
                    distribution[key]["count"], percentage(distribution[key]["minimum"]),
                    percentage(distribution[key]["median"]), percentage(distribution[key]["maximum"]),
                ]
                for key in ("complete_population", "selected")
            ],
        )
        html += "<p>Coverage shows defined risks with at least one associated test selected. Tests have not necessarily run. This does not establish complete behavioral coverage or elimination of risk.</p>"
        html += table(
            ["Severity", "Covered", "Defined", "Gaps"],
            [
                [
                    severity.title(), (coverage.get(severity) or {}).get("covered_count"),
                    (coverage.get(severity) or {}).get("total_count"),
                    (
                        (coverage.get(severity) or {}).get("total_count")
                        - (coverage.get(severity) or {}).get("covered_count")
                        if isinstance((coverage.get(severity) or {}).get("total_count"), int)
                        and isinstance((coverage.get(severity) or {}).get("covered_count"), int)
                        else "Unavailable"
                    ),
                ]
                for severity in ("critical", "high", "medium", "low", "unknown", "overall")
            ],
        )
    html += (
        "<h2>Saved near-miss influence evidence within "
        + ("B" if "B" in runs else "A (near-miss influence disabled)")
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
                "added",
                "removed",
            )
        ]
        + [
            ["Individual probabilities changed", result["near_miss_comparison"]["probability_changed"]],
            ["Probability changed, selection unchanged", result["near_miss_comparison"]["probability_only"]],
        ],
    )
    if membership_rows:
        html += "<h3>Added and removed tests</h3>"
        html += table(
            ["Test", "Service", "Without near-miss influence", "With near-miss influence", "Probability delta", "Thresholds", "Explanation"],
            [
                [
                    row.get("test_identifier") or row.get("test_id"),
                    row.get("service") or row.get("saved_service"),
                    ("Selected" if row.get("baseline_selected") else "Not selected") + " · " + percentage(row.get("probability_off")),
                    ("Selected" if row.get("selected") else "Not selected") + " · " + percentage(row.get("probability_on")),
                    percentage(row.get("probability_on") - row.get("probability_off"))
                    if isinstance(row.get("probability_on"), (int, float)) and isinstance(row.get("probability_off"), (int, float))
                    else "Unavailable",
                    percentage(row.get("threshold_off")) + " → " + percentage(row.get("threshold_on")),
                    row.get("readable_reason"),
                ]
                for row in membership_rows
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
