#!/usr/bin/env python3
"""Evaluate SpielBot retrieval quality against ground-truth chunk annotations."""

import json
import math
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from index import ChunkIndex
from retrieve import retrieve_split

K_VALUES = [3, 8]


# ── Adaptive / rank-aware metrics ────────────────────────────────────────

def mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """Reciprocal rank of the first relevant chunk."""
    for i, cid in enumerate(retrieved_ids):
        if cid in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def average_precision(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    Average Precision: mean of precision@rank at each rank where a relevant
    chunk appears. Naturally adapts to |relevant| — a question with 1 relevant
    chunk can score 1.0 if that chunk is ranked first.

    Example: relevant={A, B}, retrieved=[A, X, B, Y, Z]
      precision@1 = 1/1 = 1.0  (A is relevant)
      precision@3 = 2/3 = 0.67 (B is relevant)
      AP = (1.0 + 0.67) / 2 = 0.833
    """
    if not relevant_ids:
        return 0.0
    hits = 0
    sum_precision = 0.0
    for i, cid in enumerate(retrieved_ids):
        if cid in relevant_ids:
            hits += 1
            sum_precision += hits / (i + 1)
    return sum_precision / len(relevant_ids)


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Normalized Discounted Cumulative Gain at k.

    Uses binary relevance (1 if relevant, 0 otherwise). The ideal ranking
    places all relevant chunks first, so a question with |relevant|=1 that
    retrieves 7 irrelevant chunks can still score 1.0 if the 1 relevant
    chunk is at rank 1.
    """
    def dcg(ranked_ids, rel_set, n):
        score = 0.0
        for i, cid in enumerate(ranked_ids[:n]):
            if cid in rel_set:
                score += 1.0 / math.log2(i + 2)  # i+2 because log2(1)=0
        return score

    actual_dcg = dcg(retrieved_ids, relevant_ids, k)

    # Ideal: all relevant chunks ranked first
    ideal_count = min(len(relevant_ids), k)
    ideal_dcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))

    return actual_dcg / ideal_dcg if ideal_dcg > 0 else 0.0


def r_precision(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    Precision at R, where R = |relevant|. Adapts the evaluation window to
    the number of chunks that actually matter for this question.

    If 1 chunk is relevant -> checks if top-1 is relevant (max score = 1.0)
    If 3 chunks are relevant -> checks top-3 (max score = 1.0)
    """
    r = len(relevant_ids)
    if r == 0:
        return 0.0
    top_r = retrieved_ids[:r]
    return len(set(top_r) & relevant_ids) / r


# ── Fixed-k metrics (secondary) ─────────────────────────────────────────

def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    return len(set(top_k) & relevant_ids) / k if k > 0 else 0.0


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    return len(set(top_k) & relevant_ids) / len(relevant_ids) if relevant_ids else 0.0


def hit_rate_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    return 1.0 if set(retrieved_ids[:k]) & relevant_ids else 0.0


# ── Evaluation loop ─────────────────────────────────────────────────────

def evaluate(dataset, idx):
    per_question = []

    for q in dataset["questions"]:
        results = retrieve_split(idx, q["question"], q["game"])
        retrieved_ids = [r.chunk_id for r in results]
        relevant = set(q["relevant_chunk_ids"])

        rulebook_ids = [r.chunk_id for r in results if r.source_type in ("rulebook", "card")]
        forum_ids = [r.chunk_id for r in results if r.source_type == "forum"]

        row = {
            "id": q["id"],
            "game": q["game"],
            "type": q["type"],
            "num_retrieved": len(retrieved_ids),
            "num_relevant": len(relevant),
            "num_rulebook": len(rulebook_ids),
            "num_forum": len(forum_ids),
            "retrieved_ids": retrieved_ids,
            "relevant_ids": list(relevant),
            # ── Primary (adaptive) ──
            "mrr": round(mrr(retrieved_ids, relevant), 4),
            "map": round(average_precision(retrieved_ids, relevant), 4),
            "r_precision": round(r_precision(retrieved_ids, relevant), 4),
        }

        for k in K_VALUES:
            row[f"ndcg_at_{k}"] = round(ndcg_at_k(retrieved_ids, relevant, k), 4)
            row[f"recall_at_{k}"] = round(recall_at_k(retrieved_ids, relevant, k), 4)
            row[f"hit_rate_at_{k}"] = round(hit_rate_at_k(retrieved_ids, relevant, k), 4)
            row[f"precision_at_{k}"] = round(precision_at_k(retrieved_ids, relevant, k), 4)

        per_question.append(row)

    return per_question


def aggregate(per_question):
    """Compute mean metrics overall, per-game, and per-question-type."""
    primary_keys = ["mrr", "map", "r_precision"]
    kv_keys = [
        f"{m}_at_{k}"
        for m in ("ndcg", "recall", "hit_rate", "precision")
        for k in K_VALUES
    ]
    all_metric_keys = primary_keys + kv_keys

    def mean_metrics(rows):
        out = {}
        for m in all_metric_keys:
            vals = [r[m] for r in rows if m in r]
            out[m] = round(sum(vals) / len(vals), 4) if vals else 0.0
        return out

    summary = {"overall": mean_metrics(per_question), "n": len(per_question)}

    games = sorted(set(r["game"] for r in per_question))
    summary["by_game"] = {}
    for g in games:
        subset = [r for r in per_question if r["game"] == g]
        summary["by_game"][g] = {**mean_metrics(subset), "n": len(subset)}

    summary["by_type"] = {}
    for t in ("comprehension", "reasoning"):
        subset = [r for r in per_question if r["type"] == t]
        if subset:
            summary["by_type"][t] = {**mean_metrics(subset), "n": len(subset)}

    # Average |relevant| per question type (context for interpreting precision)
    for t in ("comprehension", "reasoning"):
        subset = [r for r in per_question if r["type"] == t]
        if subset:
            avg_rel = round(sum(r["num_relevant"] for r in subset) / len(subset), 1)
            summary["by_type"][t]["avg_num_relevant"] = avg_rel

    return summary


def main():
    eval_dir = Path(__file__).parent
    project_root = eval_dir.parent
    dataset = json.loads((eval_dir / "dataset.json").read_text(encoding="utf-8"))

    idx = ChunkIndex(project_root)
    per_question = evaluate(dataset, idx)
    summary = aggregate(per_question)

    output = {"per_question": per_question, "summary": summary}
    out_path = eval_dir / "results" / "retrieval_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # ── Print primary metrics table ──
    print(f"\n{'Metric':<18} {'Overall':>8}  ", end="")
    for g in sorted(summary["by_game"]):
        print(f"{g:>10}", end="")
    print()
    print("─" * (28 + 10 * len(summary["by_game"])))

    for m in ["mrr", "map", "r_precision", "ndcg_at_8", "recall_at_8", "hit_rate_at_8"]:
        label = m.upper().replace("_AT_", "@")
        print(f"{label:<18} {summary['overall'][m]:>8.3f}  ", end="")
        for g in sorted(summary["by_game"]):
            print(f"{summary['by_game'][g][m]:>10.3f}", end="")
        print()

    # ── Print comp vs reasoning ──
    print(f"\n{'Metric':<18} {'Comp':>8} {'Reasoning':>10}")
    print("─" * 38)
    for m in ["mrr", "map", "r_precision", "ndcg_at_8", "recall_at_8"]:
        label = m.upper().replace("_AT_", "@")
        c_val = summary["by_type"].get("comprehension", {}).get(m, 0)
        r_val = summary["by_type"].get("reasoning", {}).get(m, 0)
        print(f"{label:<18} {c_val:>8.3f} {r_val:>10.3f}")

    for t in ("comprehension", "reasoning"):
        avg_rel = summary["by_type"].get(t, {}).get("avg_num_relevant", "?")
        print(f"  avg |relevant| ({t}): {avg_rel}")

    print(f"\nSaved detailed results to {out_path}")


if __name__ == "__main__":
    main()
