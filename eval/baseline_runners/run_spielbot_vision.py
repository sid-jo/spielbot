#!/usr/bin/env python3
"""Run SpielBot vision pipeline on vision_dataset.json. Binary accuracy."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from orchestrator import SpielBotSession


def _normalize_binary(text: str) -> str:
    """Extract yes/no from a model response."""
    low = text.strip().lower()
    first = low.split()[0] if low.split() else ""
    first = first.strip(".,!:;")
    if first in ("yes", "yeah", "correct", "true"):
        return "Yes"
    if first in ("no", "not", "incorrect", "false", "nope"):
        return "No"
    if "yes" in low[:50]:
        return "Yes"
    if "no" in low[:50]:
        return "No"
    return "Unknown"


def main() -> None:
    eval_dir = Path(__file__).parent.parent
    ds_path = eval_dir / "eval_datasets" / "vision_dataset.json"
    dataset = json.loads(ds_path.read_text(encoding="utf-8"))
    img_dir = eval_dir / "eval_datasets" / "imgs"

    session = SpielBotSession(eager_load=True)
    current_game = None
    results = []
    correct = total = 0

    for q in dataset["questions"]:
        if q["game"] != current_game:
            session.select_game(q["game"])
            current_game = q["game"]
            print(f"\n  Switched to {current_game}")

        img_path = img_dir / f"{q['img_id']}.jpg"
        if not img_path.exists():
            img_path = img_dir / f"{q['img_id']}.png"
        if not img_path.exists():
            print(f"  Q{q['id']}: SKIP — no image {q['img_id']}")
            continue

        t0 = time.time()
        result = session.ask(q["question"], image=str(img_path))
        latency_ms = int((time.time() - t0) * 1000)

        predicted = _normalize_binary(result.answer)
        gold = q["gold_answer"]
        is_correct = predicted == gold
        if is_correct:
            correct += 1
        total += 1

        status = "✓" if is_correct else "✗"
        print(
            f"  Q{q['id']} ({q['game']}): {status} "
            f"pred={predicted} gold={gold} ({latency_ms}ms)"
        )

        results.append(
            {
                "eval_id": q.get("eval_id", f"{q['game']}_{q['id']}"),
                "game": q["game"],
                "question": q["question"],
                "img_id": q["img_id"],
                "gold_answer": gold,
                "predicted": predicted,
                "correct": is_correct,
                "full_response": result.answer,
                "retrieved_chunk_ids": [s.chunk_id for s in result.sources],
                "latency_ms": latency_ms,
            }
        )

        session.reset_chat()
        time.sleep(1.0)

    accuracy = correct / total if total > 0 else 0
    print(f"\n  Accuracy: {correct}/{total} = {accuracy:.1%}")

    output = {
        "setting": "s4_spielbot_vision",
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "total": total,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": results,
    }
    out_path = eval_dir / "results" / "spielbot" / "s4_spielbot_vision.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"  Saved -> {out_path}")


if __name__ == "__main__":
    main()
