"""
LLM generation for SpielBot: OpenAI-compatible client (LiteLLM proxy), message
building, and a small CLI for isolated testing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

from openai import OpenAI

def _load_env() -> None:
    """Load .env file from project root if it exists."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("\"'")
            if key not in os.environ:
                os.environ[key] = val


_load_env()

# --- LiteLLM / Model Config ---

LITELLM_BASE_URL_ENV = "LITELLM_BASE_URL"
LITELLM_API_KEY_ENV = "LITELLM_API_KEY"

GEN_MODEL_ENV = "SPIELBOT_GEN_MODEL"
DEFAULT_MODEL = os.environ.get(GEN_MODEL_ENV, "gemini-2.5-flash")
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 4096

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        base_url = os.environ.get(LITELLM_BASE_URL_ENV)
        api_key = os.environ.get(LITELLM_API_KEY_ENV, "")
        if not base_url:
            raise RuntimeError(
                f"Set {LITELLM_BASE_URL_ENV} in your .env or environment. "
                f"This should be the URL of your LiteLLM proxy."
            )
        if not api_key:
            raise RuntimeError(
                f"Set {LITELLM_API_KEY_ENV} in your .env or environment."
            )
        _client = OpenAI(
            base_url=base_url.rstrip("/") + "/v1",
            api_key=api_key,
        )
    return _client


@dataclass
class GeneratorResponse:
    answer: str
    game_name: str
    model: str
    query: str
    num_sources: int
    source_ids: list[str] = field(default_factory=list)
    error: str | None = None


def build_user_content(
    query: str,
    game_name: str,
    context: str,
    source_ids: list[str],
    reasoning_answer: str | None = None,
) -> str:
    _ = game_name, source_ids
    parts: list[str] = []
    parts.append(f"--- Retrieved Sources ---\n\n{context}")
    if reasoning_answer:
        parts.append(
            f"--- Reasoning Model Answer ---\n\n{reasoning_answer}"
        )
    parts.append(f"--- Player Question ---\n\n{query}")
    return "\n\n".join(parts)


def generate(
    query: str,
    game_name: str,
    context: str,
    source_ids: list[str],
    system_prompt: str,
    history: list[dict] | None = None,
    reasoning_answer: str | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> GeneratorResponse:
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if history:
        messages.extend(history)

    user_content = build_user_content(
        query=query,
        game_name=game_name,
        context=context,
        source_ids=source_ids,
        reasoning_answer=reasoning_answer,
    )
    messages.append({"role": "user", "content": user_content})

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw = response.choices[0].message.content
        answer = (raw or "").strip()
        return GeneratorResponse(
            answer=answer,
            game_name=game_name,
            model=model,
            query=query,
            num_sources=len(source_ids),
            source_ids=source_ids,
        )
    except Exception as e:
        return GeneratorResponse(
            answer="",
            game_name=game_name,
            model=model,
            query=query,
            num_sources=len(source_ids),
            source_ids=source_ids,
            error=str(e),
        )


def generate_stream(
    query: str,
    game_name: str,
    context: str,
    source_ids: list[str],
    system_prompt: str,
    history: list[dict] | None = None,
    reasoning_answer: str | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Generator[str, None, GeneratorResponse]:
    """
    Stream LLM response tokens. Yields individual text chunks as they arrive.
    Returns a GeneratorResponse with the complete answer when done.

    Usage:
        streamer = generate_stream(...)
        full_answer = ""
        try:
            while True:
                token = next(streamer)
                print(token, end="", flush=True)
                full_answer += token
        except StopIteration as e:
            response = e.value   # GeneratorResponse with complete answer
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    user_content = build_user_content(
        query=query,
        game_name=game_name,
        context=context,
        source_ids=source_ids,
        reasoning_answer=reasoning_answer,
    )
    messages.append({"role": "user", "content": user_content})

    full_answer = ""
    try:
        client = _get_client()
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_answer += delta.content
                yield delta.content

        return GeneratorResponse(
            answer=full_answer.strip(),
            game_name=game_name,
            model=model,
            query=query,
            num_sources=len(source_ids),
            source_ids=source_ids,
        )
    except Exception as e:
        return GeneratorResponse(
            answer=full_answer.strip(),
            game_name=game_name,
            model=model,
            query=query,
            num_sources=len(source_ids),
            source_ids=source_ids,
            error=str(e),
        )


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Test SpielBot generation (optionally with retrieval).",
    )
    parser.add_argument("--game", type=str, required=True, help="Game key, e.g. catan")
    parser.add_argument("--query", type=str, required=True, help="Player question")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max completion tokens (default: {DEFAULT_MAX_TOKENS}).",
    )
    parser.add_argument(
        "--context-file",
        type=str,
        default=None,
        help="Path to pre-formatted context; if omitted, runs retrieve_split.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full messages list sent to the API.",
    )
    args = parser.parse_args()

    from bgg_config import GAMES
    from prompts import get_system_prompt

    if args.game not in GAMES:
        print(
            f"Unknown game '{args.game}'. Valid: {', '.join(GAMES.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)

    system_prompt = get_system_prompt(args.game)

    if args.context_file:
        context_path = Path(args.context_file)
        context = context_path.read_text(encoding="utf-8")
        source_ids: list[str] = []
    else:
        from index import ChunkIndex
        from retrieve import format_context, retrieve_split

        project_root = Path(__file__).parent.parent
        idx = ChunkIndex(project_root)
        results = retrieve_split(idx, args.query, args.game)
        if not results:
            print("No retrieval results; cannot generate.", file=sys.stderr)
            sys.exit(2)
        context = format_context(results)
        source_ids = [r.chunk_id for r in results]

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    user_content = (
        f"--- Retrieved Sources ---\n\n"
        f"{context}\n\n"
        f"--- Player Question ---\n\n"
        f"{args.query}"
    )
    messages.append({"role": "user", "content": user_content})

    if args.verbose:
        print(json.dumps(messages, indent=2, ensure_ascii=False))

    out = generate(
        query=args.query,
        game_name=args.game,
        context=context,
        source_ids=source_ids,
        system_prompt=system_prompt,
        history=None,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    if out.error:
        print(f"Error: {out.error}", file=sys.stderr)
        sys.exit(3)

    print(out.answer)


if __name__ == "__main__":
    _cli()
