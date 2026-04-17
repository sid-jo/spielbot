#!/usr/bin/env python3
"""Run all eval questions through the full SpielBot pipeline (Setting 4)."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from orchestrator import SpielBotSession


def _canonical_id(q: dict) -> str:
    return f"{q['game']}_{q['id']}"


def main() -> None:
    eval_dir = Path(__file__).parent.parent
    ds_path = eval_dir / "eval_datasets" / "dataset.json"
    if not ds_path.exists():
        ds_path = eval_dir / "dataset.json"
    dataset = json.loads(ds_path.read_text(encoding="utf-8"))

    session = SpielBotSession()
    current_game = None
    answers = []
    last_model = "unknown"

    for q in dataset["questions"]:
        if q["game"] != current_game:
            session.select_game(q["game"])
            current_game = q["game"]
            print(f"\n  Switched to {current_game}")

        t0 = time.time()
        result = session.ask(q["question"])
        latency_ms = int((time.time() - t0) * 1000)
        last_model = result.generator_response.model or last_model

        answers.append(
            {
                "question_id": _canonical_id(q),
                "game": q["game"],
                "type": q["type"],
                "question": q["question"],
                "response": result.answer,
                "retrieved_chunk_ids": [s.chunk_id for s in result.sources],
                "latency_ms": latency_ms,
                "error": result.error,
            }
        )
        err = "ERROR" if result.error else "OK"
        print(f"  {_canonical_id(q)}: {latency_ms}ms {err}")

        session.reset_chat()
        time.sleep(1.0)

    output = {
        "setting": "s4_spielbot",
        "model": last_model if answers else "unknown",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "answers": answers,
    }
    out_path = eval_dir / "results" / "spielbot" / "s4_spielbot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nSaved {len(answers)} answers -> {out_path}")


if __name__ == "__main__":
    main()
