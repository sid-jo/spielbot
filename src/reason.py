"""
Reasoning module: query expansion + optional image-based reasoning.

Calls a beefy model to generate sub-questions for multi-query retrieval.
For image queries, also produces a scene_description that the generator
uses as additional context when answering.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


REASON_MODEL_ENV = "SPIELBOT_REASON_MODEL"
DEFAULT_REASON_MODEL = "claude-sonnet-4-20250514-v1:0"


def _get_reason_model() -> str:
    return os.environ.get(REASON_MODEL_ENV, DEFAULT_REASON_MODEL)


# ── Result ───────────────────────────────────────────────────────────────

@dataclass
class ReasoningResult:
    sub_questions: list[str]
    scene_description: str | None = None  # Rich VLM scene description (image queries only)
    raw_response: str = ""
    error: str | None = None


# ── Game-specific guidance (inserted into prompts) ───────────────────────

GAME_GUIDANCE: dict[str, str] = {
    "root": (
        "ROOT-SPECIFIC:\n"
        "- If the user mentions a card by name (Tunnels, Ambush, Sappers, "
        "Royal Claim, Favor of the Foxes, Armorers, Brutal Tactics, etc.), "
        "ALWAYS include a query: 'What does the [Card] card do in Root?'\n"
        "- If the user mentions a Vagabond action (Strike, Aid, Explore, "
        "Craft, Repair, Steal, Day Labor, Scorched Earth, etc.), "
        "include: 'Vagabond [Action] action rules Root'\n"
        "- Root has asymmetric factions — include faction-specific queries\n"
        "- Include queries targeting both The Law of Root and faction rules"
    ),
    "catan": (
        "CATAN-SPECIFIC:\n"
        "- Distinguish player trades, maritime trades (4:1), and harbor "
        "trades (3:1, 2:1) when relevant\n"
        "- Development card rules are a common confusion source\n"
        "- Include queries about the specific game phase if relevant "
        "(setup, regular turn, special builds)"
    ),
    "splendor": (
        "SPLENDOR-SPECIFIC:\n"
        "- Token-taking rules have edge cases (fewer than 4, can't take "
        "2 of same color, etc.)\n"
        "- Noble visits are automatic with specific timing\n"
        "- Reserved cards and gold tokens have linked mechanics"
    ),
}


# ── Prompt builders ──────────────────────────────────────────────────────

def _build_text_prompt(query: str, game_name: str) -> str:
    guidance = GAME_GUIDANCE.get(game_name, "")
    return (
        f"You are a board game rules expert for {game_name.title()}.\n\n"
        f'A player asked: "{query}"\n\n'
        f"Think about which rules, mechanics, and edge cases are relevant "
        f"to this question. Then generate 5 to 7 short search queries "
        f"(5-15 words each) that would retrieve the most relevant rulebook "
        f"passages and community forum posts to answer it.\n\n"
        f"Each query should:\n"
        f"- Use the specific terminology that {game_name.title()}'s "
        f"rulebook uses\n"
        f"- Target a different rule, section, or mechanic\n"
        f"- NOT just rephrase the original question\n\n"
        f"{guidance}\n\n"
        f"Respond with ONLY valid JSON, no markdown fences:\n"
        f'{{"sub_questions": ["query1", "query2", ...]}}'
    )


def _build_image_prompt(query: str, game_name: str) -> str:
    guidance = GAME_GUIDANCE.get(game_name, "")
    return (
        f"You are a board game rules expert for {game_name.title()}.\n\n"
        f'A player uploaded a photo of their current game and asked: '
        f'"{query}"\n\n'
        f"Do two things:\n\n"
        f"1. DESCRIBE THE SCENE: Look at the image carefully and write a "
        f"rich, detailed description of the visible game state. Include:\n"
        f"   - Which pieces, tokens, cards, and components are visible\n"
        f"   - Player positions, colors, and approximate piece counts\n"
        f"   - Board layout details relevant to the player's question\n"
        f"   - Any notable game state (whose turn it might be, game phase,\n"
        f"     special conditions like the robber position in Catan)\n"
        f"   Be specific about what you CAN see vs what is unclear.\n\n"
        f"2. GENERATE SEARCH QUERIES: Create 5 to 7 short search queries "
        f"(5-15 words) that would find the rulebook passages and forum "
        f"posts most relevant to the player's question, informed by what "
        f"you see in the image.\n\n"
        f"{guidance}\n\n"
        f"Respond with ONLY valid JSON, no markdown fences:\n"
        f'{{"scene_description": "<your detailed scene description>", '
        f'"sub_questions": ["q1", "q2", ...]}}'
    )


# ── Image encoding ───────────────────────────────────────────────────────

def _encode_image(image_input: bytes | str | Path) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    if isinstance(image_input, bytes):
        raw = image_input
    else:
        raw = Path(image_input).read_bytes()

    if raw[:4] == b"\x89PNG":
        mt = "image/png"
    elif raw[:4] == b"RIFF":
        mt = "image/webp"
    else:
        mt = "image/jpeg"
    return base64.b64encode(raw).decode(), mt


# ── JSON extraction ───────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Parse JSON from model output, handling fences and noise."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : i + 1])

    raise ValueError("Incomplete JSON in model response.")


def _message_text(message) -> str:
    """Normalize assistant content (str or multimodal list) from LiteLLM/OpenAI."""
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


# ── Model calls ──────────────────────────────────────────────────────────

def _reasoning_model_extras(model: str) -> dict:
    """
    LiteLLM / OpenAI pass-through for reasoning models (e.g. GPT-5).

    High internal reasoning can consume the completion budget and yield empty
    visible content at low max_tokens; pairing a higher cap with low
    reasoning_effort matches eval/baseline_runners/run_gpt5_api.py.
    """
    m = (model or "").lower()
    if m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3"):
        return {"extra_body": {"reasoning_effort": "low"}}
    return {}


def _call_text(prompt: str, model: str) -> str:
    """Text-only reasoning call."""
    from generate import _get_client

    client = _get_client()
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    kwargs.update(_reasoning_model_extras(model))
    try:
        resp = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        # Fallback: some models don't support response_format
        resp = client.chat.completions.create(**kwargs)
    return _message_text(resp.choices[0].message)


def _call_vision(
    prompt: str,
    img_b64: str,
    media_type: str,
    model: str,
) -> str:
    """Image+text reasoning call."""
    from generate import _get_client

    client = _get_client()
    content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{img_b64}"},
        },
        {"type": "text", "text": prompt},
    ]
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    kwargs.update(_reasoning_model_extras(model))
    try:
        resp = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = client.chat.completions.create(**kwargs)
    return _message_text(resp.choices[0].message)


# ── Main entry point ─────────────────────────────────────────────────────

def reason(
    query: str,
    game_name: str,
    image: bytes | str | Path | None = None,
    model: str | None = None,
) -> ReasoningResult:
    """
    Expand the query into sub-questions for multi-query retrieval.
    If an image is provided, also produce a scene_description.

    On error, sub_questions is [] and callers fall back to single-query.
    """
    reason_model = model or _get_reason_model()
    has_image = image is not None

    try:
        if has_image:
            prompt = _build_image_prompt(query, game_name)
            assert image is not None
            img_b64, media_type = _encode_image(image)
            raw = _call_vision(prompt, img_b64, media_type, reason_model)
        else:
            prompt = _build_text_prompt(query, game_name)
            raw = _call_text(prompt, reason_model)
    except Exception as e:
        return ReasoningResult(sub_questions=[], error=str(e))

    try:
        parsed = _extract_json(raw)
    except Exception as e:
        return ReasoningResult(
            sub_questions=[],
            raw_response=raw,
            error=str(e),
        )

    questions = parsed.get("sub_questions", [])
    if not isinstance(questions, list):
        questions = []
    questions = [str(q).strip() for q in questions if str(q).strip()]

    scene_description = None
    if has_image:
        sd = parsed.get("scene_description", "")
        if isinstance(sd, str) and sd.strip():
            scene_description = sd.strip()

    return ReasoningResult(
        sub_questions=questions,
        scene_description=scene_description,
        raw_response=raw,
    )


# ── CLI ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test reasoning module.")
    parser.add_argument("--game", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--image", default=None, help="Path to image file")
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--raw", action="store_true", help="Print raw output")
    args = parser.parse_args()

    result = reason(
        args.query,
        args.game,
        image=args.image,
        model=args.model,
    )
    if result.error:
        print(f"ERROR: {result.error}")
    print(f"\nSub-questions ({len(result.sub_questions)}):")
    for i, q in enumerate(result.sub_questions, 1):
        print(f"  {i}. {q}")
    if result.scene_description:
        print(f"\nScene description:\n{result.scene_description}")
    if args.raw:
        print(f"\nRaw:\n{result.raw_response}")
