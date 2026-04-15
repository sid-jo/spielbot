"""Vision scene analysis for SpielBot image-based queries."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from generate import _get_client
from vision_prompts import (
    GENERIC_SCENE_PROMPT,
    SCENE_PROMPTS,
)

VLM_MODEL_ENV = "SPIELBOT_VLM_MODEL"
DEFAULT_VLM_MODEL = "gemini-2.5-flash"


def _get_vlm_model() -> str:
    return os.environ.get(VLM_MODEL_ENV, DEFAULT_VLM_MODEL)


@dataclass
class SceneAnalysis:
    game_detected: str
    confidence: str
    game_state: dict[str, Any]
    scene_description: str
    retrieval_terms: list[str]
    raw_vlm_response: str
    error: str | None = None


def encode_image(image_input: str | Path | bytes) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    if isinstance(image_input, bytes):
        if image_input[:4] == b"\x89PNG":
            media_type = "image/png"
        elif image_input[:4] == b"RIFF" and image_input[8:12] == b"WEBP":
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"
        return base64.b64encode(image_input).decode(), media_type

    path = Path(image_input)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    suffix = path.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    return base64.b64encode(path.read_bytes()).decode(), media_type


def _call_vlm(
    image_b64: str,
    media_type: str,
    prompt: str,
    model: str | None = None,
    *,
    prefer_json: bool = True,
    max_tokens: int = 1024,
) -> str:
    client = _get_client()
    vlm_model = model or _get_vlm_model()
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]
    if prefer_json:
        try:
            response = client.chat.completions.create(
                model=vlm_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        except Exception:
            response = client.chat.completions.create(
                model=vlm_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
            )
    else:
        response = client.chat.completions.create(
            model=vlm_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
    return _assistant_text(response.choices[0].message)


def _assistant_text(message) -> str:
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


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    if start == -1:
        raise ValueError("VLM response did not contain JSON object.")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : i + 1])

    raise ValueError("VLM response contained incomplete JSON object.")


def _extract_retrieval_terms(game_state: dict[str, Any], game_name: str) -> list[str]:
    terms: list[str] = []

    if game_name == "root":
        for faction in game_state.get("factions", []):
            name = str(faction.get("name", "")).strip()
            if name:
                terms.append(name)
            for b in faction.get("buildings_visible", []):
                bname = str(b).strip()
                if bname:
                    terms.append(bname)
        v_items = str(game_state.get("vagabond_items", "")).strip().lower()
        if v_items and v_items != "null":
            terms.append("vagabond items")

    elif game_name == "catan":
        board = game_state.get("board", {})
        if board.get("robber_location"):
            terms.append("robber")
        for p in game_state.get("players", []):
            for card in p.get("special_cards", []):
                cname = str(card).strip()
                if cname:
                    terms.append(cname)
            if int(p.get("cities", 0) or 0) > 0:
                terms.append("city")
        if game_state.get("visible_development_cards"):
            terms.append("development card")

    elif game_name == "splendor":
        gems = game_state.get("gem_supply", {})
        if gems.get("gold") == 0:
            terms.append("gold token")
        for p in game_state.get("players", []):
            if int(p.get("reserved_cards", 0) or 0) > 0:
                terms.append("reserve")
            if int(p.get("nobles_earned", 0) or 0) > 0:
                terms.append("noble")

    deduped: list[str] = []
    seen = set()
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(t)
    return deduped


def build_retrieval_query(user_question: str, retrieval_terms: list[str]) -> str:
    if not retrieval_terms:
        return user_question
    return f"{user_question} {' '.join(retrieval_terms)}"


def _format_scene_for_generator(game_state: dict[str, Any], game_name: str) -> str:
    lines = [f"Game: {game_name.title()}"]
    phase = game_state.get("game_phase")
    if phase:
        lines.append(f"Phase: {phase}")
    n_players = game_state.get("num_players")
    if n_players:
        lines.append(f"Players: {n_players}")

    if game_name == "root":
        factions = game_state.get("factions", [])
        if factions:
            faction_strs = []
            for f in factions:
                name = f.get("name", "Unknown")
                pieces = f.get("approximate_pieces_on_board", "?")
                buildings = f.get("buildings_visible", [])
                b_str = f" with {', '.join(buildings)}" if buildings else ""
                vp = f.get("vp_if_visible")
                vp_str = f" ({vp}VP)" if vp is not None else ""
                faction_strs.append(f"{name}: ~{pieces} pieces{b_str}{vp_str}")
            lines.append("Factions: " + "; ".join(faction_strs))

    elif game_name == "catan":
        board = game_state.get("board", {})
        if board.get("robber_location"):
            lines.append(f"Robber: {board['robber_location']}")
        for p in game_state.get("players", []):
            color = p.get("color", "?")
            s = p.get("settlements", "?")
            c = p.get("cities", "?")
            r = p.get("roads_approximate", "?")
            specials = p.get("special_cards", [])
            sp_str = f" [{', '.join(specials)}]" if specials else ""
            lines.append(f"  {color}: {s}S/{c}C/{r}R{sp_str}")

    elif game_name == "splendor":
        gems = game_state.get("gem_supply", {})
        gem_parts = []
        for color in ["white", "blue", "green", "red", "black", "gold"]:
            val = gems.get(color)
            if val is not None:
                gem_parts.append(f"{color}:{val}")
        if gem_parts:
            lines.append(f"Gem supply: {', '.join(gem_parts)}")
        for p in game_state.get("players", []):
            pos = p.get("position", "?")
            cards = p.get("purchased_cards_approximate", "?")
            pts = p.get("estimated_points")
            pts_str = f" (~{pts}pts)" if pts is not None else ""
            lines.append(f"  {pos}: {cards} cards{pts_str}")

    obs = game_state.get("observations")
    if obs:
        lines.append(f"Notes: {obs}")
    return "\n".join(lines)


def _normalize_game_name(game_name: str) -> str:
    low = game_name.strip().lower()
    if "catan" in low:
        return "catan"
    if "splendor" in low:
        return "splendor"
    if "root" in low:
        return "root"
    return low


def analyze_game_image(
    image_path: str | Path | bytes,
    game_name: str | None = None,
    user_question: str = "",
    model: str | None = None,
) -> SceneAnalysis:
    """
    Send an image to a VLM and get a structured game-state description.

    game_name is required (preselected game flow).
    Returns SceneAnalysis with structured description and retrieval terms.
    """
    try:
        image_b64, media_type = encode_image(image_path)
    except Exception as exc:
        return SceneAnalysis(
            game_detected=game_name or "unknown",
            confidence="low",
            game_state={},
            scene_description="",
            retrieval_terms=[],
            raw_vlm_response="",
            error=str(exc),
        )

    if not game_name:
        return SceneAnalysis(
            game_detected="unknown",
            confidence="low",
            game_state={},
            scene_description="",
            retrieval_terms=[],
            raw_vlm_response="",
            error="No game selected for vision analysis.",
        )

    detected_game = game_name
    prompt_key = _normalize_game_name(detected_game) if detected_game else "unknown"
    prompt = SCENE_PROMPTS.get(prompt_key, GENERIC_SCENE_PROMPT)
    if user_question:
        prompt += (
            f"\n\nThe player is asking: \"{user_question}\"\n"
            f"Pay special attention to board elements relevant to this question."
        )

    try:
        scene_raw = _call_vlm(
            image_b64=image_b64,
            media_type=media_type,
            prompt=prompt,
            model=model,
            prefer_json=True,
        )
        try:
            game_state = _extract_json(scene_raw)
            confidence = str(game_state.get("confidence", "medium")).strip().lower()
            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"
            scene_description = _format_scene_for_generator(game_state, prompt_key)
            retrieval_terms = _extract_retrieval_terms(game_state, prompt_key)
        except Exception:
            plain_prompt = (
                "Describe only clearly visible board state relevant to the user's question. "
                "Write plain text in 6-10 concise bullet points. "
                "If uncertain, say unclear."
            )
            scene_raw = _call_vlm(
                image_b64=image_b64,
                media_type=media_type,
                prompt=plain_prompt,
                model=model,
                prefer_json=False,
                max_tokens=512,
            )
            confidence = "medium"
            scene_description = scene_raw.strip()
            game_state = {}
            retrieval_terms = []
            if not scene_description:
                raise ValueError("VLM returned empty scene analysis.")
        return SceneAnalysis(
            game_detected=prompt_key if prompt_key else "unknown",
            confidence=confidence,
            game_state=game_state,
            scene_description=scene_description,
            retrieval_terms=retrieval_terms,
            raw_vlm_response=scene_raw,
        )
    except Exception as exc:
        return SceneAnalysis(
            game_detected=prompt_key if prompt_key else "unknown",
            confidence="low",
            game_state={},
            scene_description="",
            retrieval_terms=[],
            raw_vlm_response="",
            error=str(exc),
        )


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Analyze game-state image with VLM.")
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--game", type=str, default=None)
    parser.add_argument("--question", type=str, default="")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--raw", action="store_true", help="Print raw VLM output.")
    args = parser.parse_args()

    out = analyze_game_image(
        image_path=args.image,
        game_name=args.game,
        user_question=args.question,
        model=args.model,
    )
    print(json.dumps(out.__dict__, indent=2))
    if args.raw:
        print("\n--- Raw VLM Response ---")
        print(out.raw_vlm_response)


if __name__ == "__main__":
    _cli()
