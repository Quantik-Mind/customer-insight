"""Generate clearly labelled synthetic sample artifacts, without a live API."""

import argparse
import hashlib
import json
from pathlib import Path

from .report import bundle, model, render

PROJECT = "90e48503-115d-4b34-be95-9f2f1b62767d"


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    for label, influence in (("a", False), ("b", True)):
        directory = output / label
        directory.mkdir(exist_ok=True)
        run_id = (
            "11111111-1111-4111-8111-111111111111"
            if label == "a"
            else "22222222-2222-4222-8222-222222222222"
        )
        counts = (
            {
                "eligible_tests": 2,
                "promoted_candidates": 1,
                "retained_promotions": 1,
                "baseline_selected": 1,
                "actual_selected": 2,
                "direct_addition": 0,
                "indirect_addition": 1,
                "added": 1,
                "removed": 0,
            }
            if influence
            else {"direct_addition": None}
        )
        selected = [
            {
                "internal_test_id": 1,
                "id": "SYNTHETIC-T1",
                "service": "transaction_service-001",
                "experiment_type": "Illustrative stored test definition",
                "origin": "superposition",
            }
        ]
        if influence:
            selected.append(
                {
                    "internal_test_id": 2,
                    "id": "SYNTHETIC-T2",
                    "service": "transaction_service-002",
                    "experiment_type": "Illustrative indirect addition",
                    "origin": "uncertainty",
                }
            )
        context = {
            "status": "complete",
            "input_mode": "explicit",
            "library_fingerprint": "synthetic-library",
            "mapping_fingerprint": "synthetic-mapping",
            "source_fingerprint": "synthetic-source",
            "controls": {
                "selection_influence_enabled": influence,
                "detection_enabled": True,
                "automatic_observation_enabled": True,
            },
            "provenance": {
                "provider": "prometheus",
                "source": "SYNTHETIC SAMPLE",
                "dataset": "synthetic",
                "decision_cutoff": 1793448000,
            },
        }
        summary = {
            "run_id": run_id,
            "project_id": PROJECT,
            "status": "completed",
            "total_experiments": 4,
            "selected_experiments": len(selected),
            "selection_context": context,
            "near_miss_explanation": {
                "influence_enabled": influence,
                "comparison_status": "complete" if influence else "unavailable",
                "outcome": "selection_changes" if influence else "influence_disabled",
                "counts": counts,
                "limitations": [
                    "Synthetic fixture only; not a live execution or acceptance result."
                ],
            },
        }
        payloads = {
            "summary.json": summary,
            "selected-tests.json": selected,
            "near-miss.json": (
                [
                    {
                        "test_id": 1,
                        "classification": "promoted_already_selected",
                        "promoted": True,
                        "retained": True,
                        "baseline_selected": True,
                    }
                ]
                if influence
                else []
            ),
            "changes.json": [
                {
                    "path": "transaction_service/main.py",
                    "matched": True,
                    "service": "transaction_service-001",
                    "test_identifier": "SYNTHETIC-T1",
                }
            ],
            "focused-evidence.json": [],
            "observations.json": {
                "limitations": ["Synthetic sample; no provider request was made."]
            },
        }
        for name, value in payloads.items():
            (directory / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
        (directory / "selected-tests.csv").write_text(
            "internal_test_id,id,service\n"
            + "".join(
                f"{r['internal_test_id']},{r['id']},{r['service']}\n" for r in selected
            ),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "complete": True,
            "sample": True,
            "selected_count": len(selected),
            "files": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in directory.iterdir()
                if p.name != "manifest.json"
            },
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    changes = {
        "head": "SYNTHETIC — not an actual code commit",
        "services": ["transaction_service"],
        "changed_files": ["transaction_service/main.py"],
    }
    build = {
        "mode": "SIMULATED SAMPLE",
        "status": "illustrative",
        "services": [],
        "tests_executed": False,
        "deployed": False,
    }
    for label, name in (("A", "a"), ("B", "b")):
        value = bundle(output / name)
        render(
            model(
                value if label == "A" else None,
                value if label == "B" else None,
                changes,
                build,
                sample=True,
                execution=label,
            ),
            output / ("execution-" + name + "-report"),
        )
    return render(
        model(
            bundle(output / "a"),
            bundle(output / "b"),
            changes,
            build,
            "https://example.invalid",
            sample=True,
        ),
        output,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)
