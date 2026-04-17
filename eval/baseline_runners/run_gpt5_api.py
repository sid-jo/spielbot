#!/usr/bin/env python3
"""GPT baselines via LiteLLM (OpenAI-compatible): Setting 2 (prompt) and 3 (prompt + PDF)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
from pathlib import Path

from openai import OpenAI

SYSTEM_PROMPT = """\
You are a board game rule assistant who excels at answering questions about board game rules. 

When answering:
1. State the answer directly with brief explanations of the relevant 
   rule(s) when needed.
2. If a rule interaction is contested, acknowledge both interpretations
   and indicate which is most commonly accepted.
3. Be precise and cite specific rulebook sections or game components
   when possible.
4. If anything is unclear, say so rather than guessing.

"""


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("\"'")
            if key not in os.environ:
                os.environ[key] = val


def _canonical_id(q: dict) -> str:
    return f"{q['game']}_{q['id']}"


def _get_litellm_client() -> OpenAI:
    """OpenAI SDK pointed at the LiteLLM gateway (same env as src/generate.py)."""
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            "Set LITELLM_BASE_URL and LITELLM_API_KEY in .env (LiteLLM / OpenAI-compatible gateway)."
        )
    return OpenAI(base_url=base_url.rstrip("/") + "/v1", api_key=api_key)


def _assistant_text(message) -> str:
    """Normalize assistant `content` (str, None, or list of content parts from newer APIs)."""
    raw = getattr(message, "content", None)
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                elif block.get("text"):
                    parts.append(str(block["text"]))
            else:
                t = getattr(block, "text", None)
                if t:
                    parts.append(str(t))
        return "\n".join(parts).strip()
    return str(raw).strip()


def _chat_completion_kwargs(
    *,
    model: str,
    messages: list,
    max_tokens: int,
    reasoning_effort: str | None,
) -> dict:
    """Build kwargs; GPT-5 may need a higher token cap + lower reasoning so output is not all 'thinking'."""
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if reasoning_effort:
        # LiteLLM / OpenAI pass-through for reasoning models (gpt-5, o-series, etc.)
        kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}
    return kwargs


def load_rulebook_pdfs(rulebook_dir: Path) -> dict[str, str]:
    """Load rulebook PDFs as base64 strings, keyed by game name."""
    pdfs: dict[str, str] = {}
    for game in ("catan", "splendor", "root"):
        candidates = list(rulebook_dir.glob(f"{game}*.pdf"))
        if not candidates:
            sub = rulebook_dir / game
            if sub.is_dir():
                candidates = list(sub.glob("*.pdf"))
        if candidates:
            pdf_bytes = candidates[0].read_bytes()
            pdfs[game] = base64.standard_b64encode(pdf_bytes).decode()
            print(f"  Loaded {candidates[0].name} ({len(pdf_bytes) // 1024}KB)")
        else:
            print(f"  WARNING: No PDF found for {game} in {rulebook_dir}")
    return pdfs


def run_setting_2(
    client: OpenAI,
    dataset: dict,
    model: str,
    max_tokens: int,
    reasoning_effort: str | None,
) -> list[dict]:
    answers = []
    for q in dataset["questions"]:
        user_msg = f"Board game: {q['game'].title()}\n\nQuestion: {q['question']}"
        t0 = time.time()
        resp = client.chat.completions.create(
            **_chat_completion_kwargs(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        )
        latency_ms = int((time.time() - t0) * 1000)
        choice = resp.choices[0]
        text = _assistant_text(choice.message)
        row = {
            "question_id": _canonical_id(q),
            "game": q["game"],
            "type": q["type"],
            "question": q["question"],
            "response": text,
            "latency_ms": latency_ms,
        }
        if not text:
            fr = getattr(choice, "finish_reason", None)
            row["error"] = (
                f"empty model content (finish_reason={fr!r}); "
                f"raise --max-tokens or set --reasoning-effort lower if using GPT-5."
            )
        answers.append(row)
        status = "OK" if text else "EMPTY"
        print(f"  {_canonical_id(q)}: {latency_ms}ms {status}")
    return answers


def run_setting_3(
    client: OpenAI,
    dataset: dict,
    rulebook_dir: Path,
    model: str,
    max_tokens: int,
    reasoning_effort: str | None,
) -> list[dict]:
    pdfs = load_rulebook_pdfs(rulebook_dir)
    answers = []

    for q in dataset["questions"]:
        game = q["game"]
        if game not in pdfs:
            answers.append(
                {
                    "question_id": _canonical_id(q),
                    "game": game,
                    "type": q["type"],
                    "question": q["question"],
                    "response": "[SKIPPED — no PDF]",
                    "latency_ms": 0,
                }
            )
            continue

        user_content = [
            {
                "type": "file",
                "file": {
                    "filename": f"{game}_rulebook.pdf",
                    "file_data": f"data:application/pdf;base64,{pdfs[game]}",
                },
            },
            {
                "type": "text",
                "text": (
                    f"Using the attached official rulebook for {game.title()}, "
                    f"answer this question:\n\n{q['question']}"
                ),
            },
        ]

        t0 = time.time()
        resp = client.chat.completions.create(
            **_chat_completion_kwargs(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        )
        latency_ms = int((time.time() - t0) * 1000)
        choice = resp.choices[0]
        text = _assistant_text(choice.message)
        row = {
            "question_id": _canonical_id(q),
            "game": game,
            "type": q["type"],
            "question": q["question"],
            "response": text,
            "latency_ms": latency_ms,
        }
        if not text:
            fr = getattr(choice, "finish_reason", None)
            row["error"] = (
                f"empty model content (finish_reason={fr!r}); "
                f"raise --max-tokens or set --reasoning-effort lower if using GPT-5."
            )
        answers.append(row)
        status = "OK" if text else "EMPTY"
        print(f"  {_canonical_id(q)}: {latency_ms}ms {status}")

    return answers


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--setting", type=int, choices=[2, 3], required=True)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="Completion budget. GPT-5 may use many tokens for reasoning; 1024 often yields empty text.",
    )
    parser.add_argument(
        "--reasoning-effort",
        type=str,
        default="low",
        metavar="LEVEL",
        help='For reasoning models: "minimal", "low", "medium", "high", or "none" to omit.',
    )
    parser.add_argument(
        "--rulebook-dir",
        type=str,
        default=None,
        help="Directory containing {game}*.pdf or {game}/*.pdf (setting 3 only)",
    )
    args = parser.parse_args()
    effort = args.reasoning_effort.strip().lower()
    reasoning_effort = None if effort in ("", "none") else effort

    eval_dir = Path(__file__).parent.parent
    ds_path = eval_dir / "eval_datasets" / "dataset.json"
    if not ds_path.exists():
        ds_path = eval_dir / "dataset.json"
    dataset = json.loads(ds_path.read_text(encoding="utf-8"))
    client = _get_litellm_client()

    if args.setting == 2:
        answers = run_setting_2(
            client,
            dataset,
            args.model,
            max_tokens=args.max_tokens,
            reasoning_effort=reasoning_effort,
        )
        tag = "s2_gpt5_prompt"
        out_dir = eval_dir / "results" / "gpt_sys_prompt"
    else:
        rb_dir = (
            Path(args.rulebook_dir)
            if args.rulebook_dir
            else (eval_dir.parent / "data" / "rulebooks")
        )
        answers = run_setting_3(
            client,
            dataset,
            rb_dir,
            args.model,
            max_tokens=args.max_tokens,
            reasoning_effort=reasoning_effort,
        )
        tag = "s3_gpt5_pdf"
        out_dir = eval_dir / "results" / "gpt_sys_prompt_pdf"

    output = {
        "setting": tag,
        "model": args.model,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "answers": answers,
    }
    out_path = out_dir / f"{tag}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved {len(answers)} answers -> {out_path}")


if __name__ == "__main__":
    main()
