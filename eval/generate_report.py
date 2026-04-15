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
    "s2_gpt5_prompt",
    "s3_gpt5_pdf",
    "s4_spielbot",
]
SETTING_LABELS = {
    "s1_gpt-5.3": "S1-GPT",
    "s1_claude-4.6-sonnet": "S1-Claude",
    "s1_gemini-3-flash": "S1-Gemini",
    "s1_perplexity-sonar": "S1-Perplexity",
    "s2_gpt5_prompt": "S2-GPT+Prompt",
    "s3_gpt5_pdf": "S3-GPT+PDF",
    "s4_spielbot": "S4-SpielBot",
}


def _setting_color(setting: str, idx: int) -> str:
    if setting == "s4_spielbot":
        return SPIELBOT_COLOR
    return BASELINE_COLORS[idx % len(BASELINE_COLORS)]


def _sorted_present_settings(by_setting: dict) -> list[str]:
    return [s for s in SETTING_ORDER if s in by_setting]


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


def chart_by_game_heatmap(answer_quality: dict, out_dir: Path) -> None:
    by_setting_game = answer_quality["by_setting_and_game"]
    settings = [s for s in SETTING_ORDER if s in by_setting_game]
    games = ["catan", "splendor", "root"]
    data = np.full((len(games), len(settings)), np.nan)

    for i, game in enumerate(games):
        for j, setting in enumerate(settings):
            row = by_setting_game.get(setting, {}).get(game)
            if row:
                data[i, j] = row["composite_mean"]

    fig, ax = plt.subplots(figsize=(12, 4.5))
    im = ax.imshow(data, cmap="YlGnBu", vmin=1, vmax=5, aspect="auto")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Composite Score")

    ax.set_xticks(np.arange(len(settings)))
    ax.set_xticklabels([SETTING_LABELS.get(s, s) for s in settings], rotation=20, ha="right")
    ax.set_yticks(np.arange(len(games)))
    ax.set_yticklabels([g.title() for g in games])
    ax.set_title("Composite Score by Game and Setting")

    for i in range(len(games)):
        for j in range(len(settings)):
            if not np.isnan(data[i, j]):
                ax.text(j, i, f"{data[i, j]:.2f}", ha="center", va="center", color="black")

    fig.tight_layout()
    fig.savefig(out_dir / "by_game_heatmap.png", dpi=300)
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
    chart_by_game_heatmap(answer_quality, out_dir)
    chart_retrieval_metrics(aggregate, out_dir)
    chart_comp_vs_reasoning(answer_quality, out_dir)

    print(f"Saved report figures to {out_dir}")


if __name__ == "__main__":
    main()
