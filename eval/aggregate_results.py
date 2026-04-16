#!/usr/bin/env python3
"""Aggregate scored answer quality and retrieval metrics."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


def _mean(vals: list[float]) -> float:
    return round(statistics.mean(vals), 2) if vals else 0.0


def _composite(correctness: float, completeness: float, conciseness: float) -> float:
    return (correctness + completeness + conciseness) / 3.0


def _setting_key_from_file(path: Path) -> str:
    """Derive the eval setting id from the results filename (not JSON metadata).

    Using the path avoids mis-tagged copies where ``setting`` inside the JSON
    does not match the file (e.g. two exports share the same header).
    """
    stem = path.stem
    if stem.endswith("_scored"):
        return stem[: -len("_scored")]
    return stem


ASSISTANT_TRIO_SETTINGS = ("s1_bg_wizard", "s1_rulesbot", "s4_spielbot")


def _answer_quality_trio_subset(answer_quality: dict) -> dict:
    """Metrics for Board Game Wizard, Rulesbot, and SpielBot only (when present)."""
    by_setting = answer_quality.get("by_setting", {})
    present = [s for s in ASSISTANT_TRIO_SETTINGS if s in by_setting]
    return {
        "settings_order": present,
        "by_setting": {s: by_setting[s] for s in present},
        "by_setting_and_game": {
            s: answer_quality.get("by_setting_and_game", {}).get(s, {}) for s in present
        },
        "by_setting_and_type": {
            s: answer_quality.get("by_setting_and_type", {}).get(s, {}) for s in present
        },
    }


def _aggregate_one_answers(answers: list[dict]) -> dict:
    c_vals = [a["scores"]["correctness"] for a in answers]
    p_vals = [a["scores"]["completeness"] for a in answers]
    z_vals = [a["scores"]["conciseness"] for a in answers]
    c_mean = _mean(c_vals)
    p_mean = _mean(p_vals)
    z_mean = _mean(z_vals)
    comp = _mean([_composite(c, p, z) for c, p, z in zip(c_vals, p_vals, z_vals)])
    return {
        "correctness_mean": c_mean,
        "completeness_mean": p_mean,
        "conciseness_mean": z_mean,
        "composite_mean": comp,
        "n": len(answers),
    }


def _print_summary(answer_quality: dict) -> None:
    print("\nAnswer quality by setting")
    print(f"{'Setting':<24} {'Corr':>6} {'Comp':>6} {'Conc':>6} {'Composite':>10} {'n':>4}")
    print("-" * 62)
    for setting in sorted(answer_quality["by_setting"].keys()):
        row = answer_quality["by_setting"][setting]
        print(
            f"{setting:<24} "
            f"{row['correctness_mean']:>6.2f} "
            f"{row['completeness_mean']:>6.2f} "
            f"{row['conciseness_mean']:>6.2f} "
            f"{row['composite_mean']:>10.2f} "
            f"{row['n']:>4d}"
        )


def main() -> None:
    eval_dir = Path(__file__).parent
    results_dir = eval_dir / "results"

    scored_files = sorted(results_dir.glob("**/*_scored.json"))
    if not scored_files:
        raise RuntimeError("No scored files found under eval/results/**/*_scored.json")

    answer_quality = {
        "by_setting": {},
        "by_setting_and_game": {},
        "by_setting_and_type": {},
    }

    for file_path in scored_files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        answers = payload.get("answers", [])
        if not answers:
            continue

        setting = _setting_key_from_file(file_path)
        model = payload.get("model", "unknown")

        setting_agg = _aggregate_one_answers(answers)
        setting_agg["model"] = model
        answer_quality["by_setting"][setting] = setting_agg

        game_groups: defaultdict[str, list[dict]] = defaultdict(list)
        type_groups: defaultdict[str, list[dict]] = defaultdict(list)
        for a in answers:
            game_groups[a.get("game", "unknown")].append(a)
            type_groups[a.get("type", "unknown")].append(a)

        answer_quality["by_setting_and_game"][setting] = {}
        for game, rows in sorted(game_groups.items()):
            answer_quality["by_setting_and_game"][setting][game] = _aggregate_one_answers(rows)

        answer_quality["by_setting_and_type"][setting] = {}
        for qtype, rows in sorted(type_groups.items()):
            answer_quality["by_setting_and_type"][setting][qtype] = _aggregate_one_answers(rows)

    answer_quality["assistant_trio"] = _answer_quality_trio_subset(answer_quality)

    retrieval_path = results_dir / "retrieval_metrics.json"
    if not retrieval_path.exists():
        raise FileNotFoundError(f"Missing retrieval metrics file: {retrieval_path}")
    retrieval_payload = json.loads(retrieval_path.read_text(encoding="utf-8"))

    aggregate = {
        "answer_quality": answer_quality,
        "retrieval_quality": retrieval_payload.get("summary", {}),
        "retrieval_config": retrieval_payload.get("retrieval_config", {}),
    }
    out_path = results_dir / "aggregate.json"
    out_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")

    _print_summary(answer_quality)
    print(f"\nSaved aggregate file -> {out_path}")


if __name__ == "__main__":
    main()
