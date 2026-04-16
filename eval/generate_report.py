#!/usr/bin/env python3
"""Generate matplotlib figures from aggregate evaluation output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

plt.style.use("seaborn-v0_8-whitegrid")
matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["font.size"] = 11

SPIELBOT_COLOR = "#2E86AB"
BASELINE_COLORS = ["#A23B72", "#F18F01", "#C73E1D", "#3B1F2B", "#44AF69", "#EDB88B"]

SETTING_ORDER = [
    "s1_gpt-5.3",
    "s1_claude-4.6-sonnet",
    "s1_gemini-3-flash",
    "s1_perplexity-sonar",
    "s1_bg_wizard",
    "s1_rulesbot",
    "s2_gpt5_prompt",
    "s3_gpt5_pdf",
    "s4_spielbot",
]
SETTING_LABELS = {
    "s1_gpt-5.3": "S1-GPT",
    "s1_claude-4.6-sonnet": "S1-Claude",
    "s1_gemini-3-flash": "S1-Gemini",
    "s1_perplexity-sonar": "S1-Perplexity",
    "s1_bg_wizard": "S1-BG Wizard",
    "s1_rulesbot": "S1-Rulesbot",
    "s2_gpt5_prompt": "S2-GPT+Prompt",
    "s3_gpt5_pdf": "S3-GPT+PDF",
    "s4_spielbot": "S4-SpielBot",
}

# Board Game Wizard vs Rulesbot vs SpielBot (subset charts / metrics)
ASSISTANT_TRIO_ORDER = ("s1_bg_wizard", "s1_rulesbot", "s4_spielbot")
ASSISTANT_TRIO_LABELS = {
    "s1_bg_wizard": "Board Game Wizard",
    "s1_rulesbot": "Rulesbot",
    "s4_spielbot": "SpielBot",
}


def _setting_color(setting: str, idx: int) -> str:
    if setting == "s4_spielbot":
        return SPIELBOT_COLOR
    return BASELINE_COLORS[idx % len(BASELINE_COLORS)]


def _sorted_present_settings(by_setting: dict) -> list[str]:
    return [s for s in SETTING_ORDER if s in by_setting]


def _assistant_trio_answer_quality(answer_quality: dict) -> dict | None:
    """Slice used for assistant-trio-only figures (prefers aggregate ``assistant_trio``)."""
    trio = answer_quality.get("assistant_trio")
    if trio and trio.get("by_setting"):
        return trio
    by_setting = answer_quality.get("by_setting", {})
    present = [s for s in ASSISTANT_TRIO_ORDER if s in by_setting]
    if not present:
        return None
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


def chart_assistant_trio_overall(trio_aq: dict, out_dir: Path) -> None:
    order = trio_aq.get("settings_order") or [
        s for s in ASSISTANT_TRIO_ORDER if s in trio_aq.get("by_setting", {})
    ]
    by_setting = trio_aq["by_setting"]
    if len(order) < 1:
        return

    labels = [ASSISTANT_TRIO_LABELS.get(s, s) for s in order]
    c_vals = [by_setting[s]["correctness_mean"] for s in order]
    p_vals = [by_setting[s]["completeness_mean"] for s in order]
    z_vals = [by_setting[s]["conciseness_mean"] for s in order]

    x = np.arange(len(order))
    width = 0.24
    fig_w = max(7.0, 2.2 * len(order) + 2.0)
    fig, ax = plt.subplots(figsize=(fig_w, 5))

    bars_c = ax.bar(x - width, c_vals, width, label="Correctness", color="#4C78A8")
    bars_p = ax.bar(x, p_vals, width, label="Completeness", color="#F58518")
    bars_z = ax.bar(x + width, z_vals, width, label="Conciseness", color="#54A24B")

    for i, s in enumerate(order):
        if s == "s4_spielbot":
            for bars in (bars_c, bars_p, bars_z):
                bars[i].set_edgecolor("black")
                bars[i].set_linewidth(1.8)

    ax.set_ylim(1, 5)
    ax.set_ylabel("Score (1-5)")
    ax.set_title("Assistant trio: overall answer quality (Wizard vs Rulesbot vs SpielBot)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "assistant_trio_overall.png", dpi=300)
    plt.close(fig)


def chart_assistant_trio_comp_vs_reasoning(trio_aq: dict, out_dir: Path) -> None:
    by_type = trio_aq.get("by_setting_and_type", {})
    order = trio_aq.get("settings_order") or [
        s for s in ASSISTANT_TRIO_ORDER if s in by_type
    ]
    if len(order) < 1:
        return

    labels = [ASSISTANT_TRIO_LABELS.get(s, s) for s in order]
    comp_vals = [by_type[s].get("comprehension", {}).get("composite_mean", 0.0) for s in order]
    reas_vals = [by_type[s].get("reasoning", {}).get("composite_mean", 0.0) for s in order]

    x = np.arange(len(order))
    width = 0.35
    fig_w = max(7.0, 2.2 * len(order) + 2.0)
    fig, ax = plt.subplots(figsize=(fig_w, 5))
    ax.bar(x - width / 2, comp_vals, width, label="Comprehension", color="#4C78A8")
    ax.bar(x + width / 2, reas_vals, width, label="Reasoning", color="#E45756")
    ax.set_ylim(1, 5)
    ax.set_ylabel("Composite Score")
    ax.set_title("Assistant trio: comprehension vs reasoning")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "assistant_trio_comp_vs_reasoning.png", dpi=300)
    plt.close(fig)


def chart_overall_comparison(answer_quality: dict, out_dir: Path) -> None:
    by_setting = answer_quality["by_setting"]
    settings = _sorted_present_settings(by_setting)
    labels = [SETTING_LABELS.get(s, s) for s in settings]

    c_vals = [by_setting[s]["correctness_mean"] for s in settings]
    p_vals = [by_setting[s]["completeness_mean"] for s in settings]
    z_vals = [by_setting[s]["conciseness_mean"] for s in settings]

    x = np.arange(len(settings))
    width = 0.24
    fig, ax = plt.subplots(figsize=(12, 5))

    bars_c = ax.bar(x - width, c_vals, width, label="Correctness", color="#4C78A8")
    bars_p = ax.bar(x, p_vals, width, label="Completeness", color="#F58518")
    bars_z = ax.bar(x + width, z_vals, width, label="Conciseness", color="#54A24B")

    for i, s in enumerate(settings):
        if s == "s4_spielbot":
            for bars in (bars_c, bars_p, bars_z):
                bars[i].set_edgecolor("black")
                bars[i].set_linewidth(1.8)

    ax.set_ylim(1, 5)
    ax.set_ylabel("Score (1-5)")
    ax.set_title("Overall Answer Quality by Setting")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "overall_comparison.png", dpi=300)
    plt.close(fig)


def chart_retrieval_metrics(aggregate: dict, out_dir: Path) -> None:
    retrieval_quality = aggregate.get("retrieval_quality", {})
    by_game = retrieval_quality.get("by_game", {})
    retrieval_config = aggregate.get("retrieval_config", {})
    k_values = retrieval_config.get("metric_k_values") or [3, 6]
    k_small = k_values[0]
    k_full = k_values[-1]

    metric_keys = [
        "mrr",
        "map",
        f"recall_at_{k_small}",
        f"recall_at_{k_full}",
        f"hit_rate_at_{k_full}",
        f"ndcg_at_{k_full}",
    ]
    metric_labels = [
        "MRR",
        "MAP",
        f"Recall@{k_small}",
        f"Recall@{k_full}",
        f"HitRate@{k_full}",
        f"NDCG@{k_full}",
    ]
    games = ["catan", "splendor", "root"]
    x = np.arange(len(metric_keys))
    width = 0.24
    fig, ax = plt.subplots(figsize=(11.5, 5))

    for i, game in enumerate(games):
        row = by_game.get(game, {})
        vals = [row.get(m, 0.0) for m in metric_keys]
        ax.bar(
            x + (i - 1) * width,
            vals,
            width,
            label=game.title(),
            color=BASELINE_COLORS[i % len(BASELINE_COLORS)],
        )

    ax.set_ylim(0, 1)
    ax.set_ylabel("Score")
    ax.set_title("SpielBot Retrieval Metrics by Game")
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "retrieval_metrics.png", dpi=300)
    plt.close(fig)


def chart_comp_vs_reasoning(answer_quality: dict, out_dir: Path) -> None:
    by_type = answer_quality["by_setting_and_type"]
    settings = [s for s in SETTING_ORDER if s in by_type]
    labels = [SETTING_LABELS.get(s, s) for s in settings]

    comp_vals = [by_type[s].get("comprehension", {}).get("composite_mean", 0.0) for s in settings]
    reas_vals = [by_type[s].get("reasoning", {}).get("composite_mean", 0.0) for s in settings]

    x = np.arange(len(settings))
    width = 0.35
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - width / 2, comp_vals, width, label="Comprehension", color="#4C78A8")
    ax.bar(x + width / 2, reas_vals, width, label="Reasoning", color="#E45756")
    ax.set_ylim(1, 5)
    ax.set_ylabel("Composite Score")
    ax.set_title("Comprehension vs Reasoning Performance by Setting")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "comp_vs_reasoning.png", dpi=300)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate eval report figures.")
    parser.add_argument("--output-dir", default="eval/results/figures")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    aggregate_path = project_root / "eval" / "results" / "aggregate.json"
    if not aggregate_path.exists():
        raise FileNotFoundError(
            f"Missing aggregate file: {aggregate_path}. Run eval/aggregate_results.py first."
        )

    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    answer_quality = aggregate.get("answer_quality", {})
    if not answer_quality.get("by_setting"):
        raise RuntimeError("aggregate.json has no answer_quality.by_setting data.")

    out_dir = project_root / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    chart_overall_comparison(answer_quality, out_dir)
    chart_retrieval_metrics(aggregate, out_dir)
    chart_comp_vs_reasoning(answer_quality, out_dir)

    trio_aq = _assistant_trio_answer_quality(answer_quality)
    if trio_aq:
        chart_assistant_trio_overall(trio_aq, out_dir)
        chart_assistant_trio_comp_vs_reasoning(trio_aq, out_dir)
        print(
            "Saved assistant trio figures: assistant_trio_overall.png, "
            "assistant_trio_comp_vs_reasoning.png"
        )
    else:
        print(
            "Skipped assistant trio figures (no scored data for any of "
            "s1_bg_wizard, s1_rulesbot, s4_spielbot)."
        )

    print(f"Saved report figures to {out_dir}")


if __name__ == "__main__":
    main()
