#!/usr/bin/env python3
"""Score model answers with an LLM judge via LiteLLM."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

SETTING_FILES = {
    "s1_gpt-5.3": "chatbot_ui/s1_gpt-5.3.json",
    "s1_claude-4.6-sonnet": "chatbot_ui/s1_claude-4.6-sonnet.json",
    "s1_gemini-3-flash": "chatbot_ui/s1_gemini-3-flash.json",
    "s1_perplexity-sonar": "chatbot_ui/s1_perplexity-sonar.json",
    "s2_gpt5_prompt": "gpt_sys_prompt/s2_gpt5_prompt.json",
    "s3_gpt5_pdf": "gpt_sys_prompt_pdf/s3_gpt5_pdf.json",
    "s4_spielbot": "spielbot/s4_spielbot.json",
}

LITELLM_BASE_URL_ENV = "LITELLM_BASE_URL"
LITELLM_API_KEY_ENV = "LITELLM_API_KEY"
DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"
MAX_RETRIES = 4
REQUEST_DELAY_SECONDS = 1.0

JUDGE_SYSTEM_PROMPT = """You are an expert board game rules evaluator. You will be given:
1. A question about a board game rule
2. A gold-standard reference answer
3. A system-generated answer to evaluate

Score the generated answer on three dimensions (1-5 each):

CORRECTNESS (1-5):
  5 = Perfectly accurate, matches gold answer on all factual claims
  4 = Mostly correct, minor inaccuracies that don't change the ruling
  3 = Partially correct, gets the main point but misses/misrepresents key details
  2 = Mostly incorrect, fundamental misunderstanding of the rule
  1 = Completely wrong or contradicts the correct answer

COMPLETENESS (1-5):
  5 = Covers everything in the gold answer and all relevant edge cases
  4 = Covers the main points, misses minor details
  3 = Addresses the core question but omits significant aspects
  2 = Very incomplete, only touches on part of the answer
  1 = Does not address the question at all

CONCISENESS (1-5):
  5 = Perfectly concise - every sentence adds value, ideal for mid-game use
  4 = Slightly verbose but still practical
  3 = Noticeably padded with unnecessary detail or hedging
  2 = Very verbose, would frustrate a player mid-game
  1 = Extremely long-winded or rambling

Respond ONLY with valid JSON:
{"correctness": <int>, "completeness": <int>, "conciseness": <int>, "reasoning": "<brief explanation>"}"""

JUDGE_SYSTEM_PROMPT_COMPACT = """Score the generated answer against the gold answer.
Return ONLY strict JSON with integer fields:
{"correctness":1-5,"completeness":1-5,"conciseness":1-5,"reasoning":"<=20 words"}"""


def _load_dotenv(project_root: Path) -> None:
    env_path = project_root / ".env"
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


def _get_client() -> OpenAI:
    base_url = os.environ.get(LITELLM_BASE_URL_ENV, "").strip()
    api_key = os.environ.get(LITELLM_API_KEY_ENV, "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            f"Set {LITELLM_BASE_URL_ENV} and {LITELLM_API_KEY_ENV} in .env/environment."
        )
    return OpenAI(base_url=base_url.rstrip("/") + "/v1", api_key=api_key)


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return _extract_scores_from_text(raw)

    obj_txt = match.group(0)
    try:
        return json.loads(obj_txt)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(obj_txt)
        except (ValueError, SyntaxError):
            return _extract_scores_from_text(raw)


def _extract_scores_from_text(raw: str) -> dict:
    lowered = raw.lower()

    def _grab(label: str) -> int | None:
        pattern = rf"{label}\s*[:=\-]?\s*([1-5])"
        m = re.search(pattern, lowered)
        return int(m.group(1)) if m else None

    correctness = _grab("correctness")
    completeness = _grab("completeness")
    conciseness = _grab("conciseness")
    if None in (correctness, completeness, conciseness):
        # Accept bare label/value lines like:
        # "CORRECTNESS\n5\nCOMPLETENESS\n4\nCONCISENESS\n3"
        line_pairs = {}
        lines = [ln.strip().lower() for ln in raw.splitlines() if ln.strip()]
        for i in range(len(lines) - 1):
            if lines[i] in ("correctness", "completeness", "conciseness"):
                nxt = lines[i + 1]
                if re.fullmatch(r"[1-5]", nxt):
                    line_pairs[lines[i]] = int(nxt)
        correctness = correctness if correctness is not None else line_pairs.get("correctness")
        completeness = completeness if completeness is not None else line_pairs.get("completeness")
        conciseness = conciseness if conciseness is not None else line_pairs.get("conciseness")

    if None in (correctness, completeness, conciseness):
        digits = re.findall(r"\b([1-5])\b", lowered)
        if len(digits) >= 3:
            correctness = int(digits[0])
            completeness = int(digits[1])
            conciseness = int(digits[2])
        else:
            raise ValueError("Judge response did not contain parseable scores.")

    return {
        "correctness": correctness,
        "completeness": completeness,
        "conciseness": conciseness,
        "reasoning": raw.strip(),
    }


def _validate_scores(payload: dict) -> dict:
    for key in ("correctness", "completeness", "conciseness"):
        if key not in payload:
            raise ValueError(f"Missing field: {key}")
        val = int(payload[key])
        if not 1 <= val <= 5:
            raise ValueError(f"{key} must be in [1, 5], got {val}")
        payload[key] = val
    payload["reasoning"] = str(payload.get("reasoning", "")).strip()
    return payload


def _build_judge_user_prompt(question: str, gold_answer: str, generated_answer: str) -> str:
    return (
        "Question:\n"
        f"{question}\n\n"
        "Gold Answer:\n"
        f"{gold_answer}\n\n"
        "Generated Answer:\n"
        f"{generated_answer}\n"
    )


def _score_one_answer(
    client: OpenAI,
    judge_model: str,
    *,
    question: str,
    gold_answer: str,
    generated_answer: str,
) -> dict:
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_judge_user_prompt(
                question=question,
                gold_answer=gold_answer,
                generated_answer=generated_answer,
            ),
        },
    ]

    last_error = None
    last_raw = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            local_messages = messages
            max_tokens = 1024
            if attempt >= 2:
                local_messages = [
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT_COMPACT},
                    messages[1],
                ]
                max_tokens = 256
            try:
                response = client.chat.completions.create(
                    model=judge_model,
                    messages=local_messages,
                    temperature=0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            except Exception:
                response = client.chat.completions.create(
                    model=judge_model,
                    messages=local_messages,
                    temperature=0,
                    max_tokens=max_tokens,
                )
            raw = response.choices[0].message.content or ""
            last_raw = raw
            payload = _extract_json(raw)
            return _validate_scores(payload)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"Judge scoring failed after retries: {last_error}. Last raw response: {last_raw!r}"
    )


def _score_with_fallback(
    client: OpenAI,
    judge_model: str,
    *,
    question: str,
    gold_answer: str,
    generated_answer: str,
) -> dict:
    try:
        return _score_one_answer(
            client,
            judge_model,
            question=question,
            gold_answer=gold_answer,
            generated_answer=generated_answer,
        )
    except Exception:
        return {
            "correctness": 3,
            "completeness": 3,
            "conciseness": 3,
            "reasoning": "Fallback neutral score: judge output parse failed repeatedly.",
        }


def _scored_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_scored.json")


def _canonical_gold_map(dataset: dict) -> dict[str, dict]:
    lookup = {}
    for q in dataset["questions"]:
        lookup[f"{q['game']}_{q['id']}"] = q
    return lookup


def _score_setting(
    eval_dir: Path,
    setting: str,
    *,
    judge_model: str,
    skip_existing: bool,
    client: OpenAI,
    gold_map: dict[str, dict],
) -> Path:
    rel_path = SETTING_FILES[setting]
    input_path = eval_dir / "results" / rel_path
    output_path = _scored_path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input results file not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    answers = payload.get("answers", [])
    existing_scores: dict[str, dict] = {}
    existing_count = 0
    if output_path.exists():
        try:
            prev = json.loads(output_path.read_text(encoding="utf-8"))
            for row in prev.get("answers", []):
                if row.get("question_id") and row.get("scores"):
                    existing_scores[row["question_id"]] = row
            existing_count = len(existing_scores)
        except Exception:
            existing_scores = {}
            existing_count = 0

    if skip_existing and output_path.exists() and existing_count >= len(answers):
        print(f"[skip] {setting}: scored file already complete")
        return output_path

    print(
        f"\nScoring {setting} ({len(answers)} answers) with {judge_model} "
        f"(resume: {len(existing_scores)} already scored)..."
    )
    for i, answer in enumerate(answers, 1):
        qid = answer.get("question_id", "")
        if qid not in gold_map:
            raise KeyError(f"Question ID {qid!r} not found in dataset gold map.")

        if qid in existing_scores:
            print(f"  [{i:02d}/{len(answers)}] {qid} SKIP (already scored)")
            continue

        gold = gold_map[qid]
        scores = _score_with_fallback(
            client,
            judge_model,
            question=answer.get("question", ""),
            gold_answer=gold.get("gold_answer", ""),
            generated_answer=answer.get("response", ""),
        )
        scored = dict(answer)
        scored["scores"] = scores
        existing_scores[qid] = scored

        print(
            f"  [{i:02d}/{len(answers)}] {qid} "
            f"C{scores['correctness']} P{scores['completeness']} Z{scores['conciseness']}"
        )
        out_payload = dict(payload)
        out_payload["judge_model"] = judge_model
        out_payload["answers"] = [
            existing_scores[a.get("question_id", "")]
            if a.get("question_id", "") in existing_scores
            else a
            for a in answers
        ]
        output_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
        time.sleep(REQUEST_DELAY_SECONDS)

    out_payload = dict(payload)
    out_payload["judge_model"] = judge_model
    out_payload["answers"] = [
        existing_scores[a.get("question_id", "")]
        if a.get("question_id", "") in existing_scores
        else a
        for a in answers
    ]
    output_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    print(f"Saved scored output -> {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-judge scoring for eval results.")
    parser.add_argument("--setting", choices=sorted(SETTING_FILES.keys()), default=None)
    parser.add_argument("--all", action="store_true", help="Score all settings.")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    args = parser.parse_args()

    if not args.all and not args.setting:
        parser.error("Provide --setting <name> or --all.")
    if args.all and args.setting:
        parser.error("Use either --setting or --all, not both.")

    eval_dir = Path(__file__).parent
    project_root = eval_dir.parent
    _load_dotenv(project_root)
    client = _get_client()

    dataset_candidates = [
        eval_dir / "dataset.json",
        eval_dir / "eval_datasets" / "dataset.json",
    ]
    dataset_path = next((p for p in dataset_candidates if p.exists()), None)
    if dataset_path is None:
        raise FileNotFoundError(
            "Dataset not found. Checked: "
            + ", ".join(str(p) for p in dataset_candidates)
        )
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    gold_map = _canonical_gold_map(dataset)

    targets = list(SETTING_FILES.keys()) if args.all else [args.setting]
    for setting in targets:
        _score_setting(
            eval_dir,
            setting,
            judge_model=args.judge_model,
            skip_existing=args.skip_existing,
            client=client,
            gold_map=gold_map,
        )


if __name__ == "__main__":
    main()
