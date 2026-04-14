#!/usr/bin/env python3
"""Thin orchestrator for evaluation pipeline legs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> None:
    print(f"\n> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation pipeline legs.")
    parser.add_argument(
        "--legs",
        required=True,
        help=(
            "One of: retrieval, judge, aggregate, report, all, "
            "or comma-separated list (e.g., judge,report)"
        ),
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    eval_dir = project_root / "eval"

    legs = {
        "retrieval": [sys.executable, str(eval_dir / "retrieval_eval.py")],
        "judge": [sys.executable, str(eval_dir / "llm_judge.py"), "--all"],
        "aggregate": [sys.executable, str(eval_dir / "aggregate_results.py")],
        "report": [sys.executable, str(eval_dir / "generate_report.py")],
    }

    if args.legs.strip().lower() == "all":
        plan = ["retrieval", "judge", "aggregate", "report"]
    else:
        plan = [p.strip().lower() for p in args.legs.split(",") if p.strip()]
        invalid = [p for p in plan if p not in legs]
        if invalid:
            parser.error(
                f"Invalid leg(s): {', '.join(invalid)}. Valid: retrieval, judge, aggregate, report, all."
            )

    for leg in plan:
        print(f"Running leg: {leg}")
        _run(legs[leg])

    print("\nEvaluation pipeline completed.")


if __name__ == "__main__":
    main()
