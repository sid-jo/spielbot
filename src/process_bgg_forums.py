"""
Process raw BGG forum thread JSONs into structured chunks for RAG retrieval.

Reads individual thread JSONs from data/bgg_threads/<game>/, uses Llama
(via Groq) to extract structured fields (embed_text, content,
resolution_status, etc.), and writes one consolidated JSON per game to
data/processed/<game>_forum_chunks.json.

Usage:
    python src/process_bgg_forums.py                 # process all games
    python src/process_bgg_forums.py --game catan     # process one game
    python src/process_bgg_forums.py --dry-run        # show what would be processed
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from groq import Groq

from bgg_config import GAMES


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GROQ_API_KEY_ENV = "GROQ_API_KEY"
MODEL = "llama-3.3-70b-versatile"
REQUEST_DELAY = 1.0  # seconds between API calls to avoid rate limits

EXTRACTION_PROMPT = """\
You are a structured data extractor for a board game rules assistant.
You will be given a BGG forum thread as a JSON object. Your job is to
extract a clean, structured summary that will be stored in a retrieval
database.

FIELDS:
- embed_text (string): A clean, standalone restatement of the core rules
  question being asked in this thread. Write it as a natural language
  question in 1-3 sentences. This will be used as the embedding target
  for semantic search, so it should capture the question's intent clearly
  and without assuming context. Do not include usernames or thread metadata.

- content (string): A concise summary of the community's resolution to
  the question. If a consensus was reached, state it clearly. If the
  thread is contested, summarize the competing interpretations. If no
  answer was given, say so. 2-5 sentences max.

- resolution_status (string): One of exactly three values:
    "resolved"   - thread reached a clear consensus answer
    "contested"  - multiple conflicting answers, no consensus
    "unanswered" - no substantive answer was given

- has_publisher_post (boolean): true if any post is authored by a
  verified publisher, designer, or official representative of the game.
  false otherwise. When in doubt, return false.

- confidence (string): One of exactly three values:
    "high"   - publisher post present, OR resolved with clear consensus
    "medium" - resolved but with some disagreement or ambiguity
    "low"    - contested or unanswered

RULES:
- embed_text must be self-contained. A reader with no thread context
  should understand the question.
- content must not speculate. Only report what the thread actually says.
- If the thread subject line contains the answer (e.g. "Distance rule
  always applies"), do not treat that as a post - only use post bodies.
- Ignore posts that are purely social (e.g. "Thanks!", "Agreed.") with
  no substantive rules content.
- Never hallucinate publisher status. Only set has_publisher_post: true
  if there is explicit evidence in the thread (e.g. username matches
  game publisher, post says "I am the designer", etc.)

Respond with ONLY a JSON object containing these five fields. No markdown
fencing, no explanation, just the JSON."""


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def strip_citations(text):
    """Remove 'Username wrote: ...' citation blocks from post text.

    These appear in XMLAPI2 data as plain text after HTML stripping.
    Handles nested citations (quote-within-quote).
    """
    # Repeatedly strip from innermost citations outward
    prev = None
    while prev != text:
        prev = text
        # Match "Username wrote:\n\n<quoted block>\n\n" — the quoted block
        # ends at a double-newline that is NOT immediately followed by
        # another "wrote:" line (which would be a deeper nesting level).
        text = re.sub(
            r'\S+ wrote:\n\n.*?\n\n',
            '',
            text,
            count=1,
            flags=re.DOTALL,
        )
    return text.strip()


def clean_posts(posts):
    """Return posts with citation blocks stripped from bodies."""
    cleaned = []
    for post in posts:
        body = strip_citations(post["body"])
        if body:  # drop posts that become empty after stripping
            cleaned.append({
                "username": post["username"],
                "date": post["date"],
                "body": body,
            })
    return cleaned


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def extract_date(iso_str):
    """Extract YYYY-MM-DD from an ISO datetime string."""
    try:
        return datetime.fromisoformat(iso_str).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str[:10] if iso_str and len(iso_str) >= 10 else None


def get_date_range(posts):
    """Return [earliest_date, latest_date] from posts."""
    dates = [extract_date(p["date"]) for p in posts if p.get("date")]
    dates = [d for d in dates if d]
    if not dates:
        return [None, None]
    return [min(dates), max(dates)]


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

def load_api_key(project_root):
    """Load Groq API key from env var or .env file."""
    key = os.environ.get(GROQ_API_KEY_ENV)
    if key:
        return key.strip()

    env_path = project_root / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{GROQ_API_KEY_ENV}="):
                    return line.split("=", 1)[1].strip().strip("\"'")

    return None


def extract_fields(client, thread_data):
    """Call Llama via Groq to extract structured fields from a thread."""
    thread_json = json.dumps(thread_data, indent=2, ensure_ascii=False)

    time.sleep(REQUEST_DELAY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Thread:\n{thread_json}"},
        ],
        temperature=0,
        max_completion_tokens=1024,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown fencing if the model adds it despite instructions
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------

def process_thread(client, thread_path, game_name, game_id):
    """Process a single thread JSON into a forum chunk."""
    with open(thread_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    thread_id = thread_path.stem
    subject = raw["subject"]
    posts = raw["posts"]

    # Clean citation blocks from post bodies
    cleaned_posts = clean_posts(posts)

    # Build a cleaned version of the thread for the LLM
    thread_for_llm = {
        "subject": subject,
        "posts": cleaned_posts,
    }

    # Extract structured fields via LLM
    fields = extract_fields(client, thread_for_llm)

    # Assemble the final chunk
    chunk = {
        "chunk_id": f"{game_name}_{game_id}_forum_{thread_id}",
        "source_type": "forum",
        "game_name": game_name,
        "game_id": game_id,
        "thread_id": thread_id,
        "thread_subject": subject,
        "embed_text": fields["embed_text"],
        "content": fields["content"],
        "raw_thread": cleaned_posts,
        "resolution_status": fields["resolution_status"],
        "has_publisher_post": fields["has_publisher_post"],
        "confidence": fields["confidence"],
        "post_count": len(cleaned_posts),
        "date_range": get_date_range(posts),
        "retrieval_priority": 2,
    }

    return chunk


def process_game(client, game_name, game_id, threads_dir, output_dir):
    """Process all threads for a game into a single output JSON."""
    game_dir = threads_dir / game_name
    if not game_dir.exists():
        print(f"  No threads directory found at {game_dir}, skipping.")
        return

    thread_files = sorted(game_dir.glob("*.json"))
    if not thread_files:
        print(f"  No thread files found in {game_dir}, skipping.")
        return

    print(f"  Processing {len(thread_files)} threads ...")
    chunks = []

    for i, path in enumerate(thread_files, 1):
        print(f"    [{i}/{len(thread_files)}] {path.name}")
        try:
            chunk = process_thread(client, path, game_name, game_id)
            chunks.append(chunk)
        except Exception as e:
            print(f"      ERROR: {e}")
            continue

    # Write consolidated output
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{game_name}_forum_chunks.json"
    output = {
        "game_name": game_name,
        "game_id": game_id,
        "total_chunks": len(chunks),
        "chunks": chunks,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  Saved {len(chunks)} chunks to {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Process BGG forum threads into structured chunks for RAG."
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        help="Process a single game (e.g. 'catan'). Default: all games.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without calling the LLM.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    threads_dir = project_root / "data" / "bgg_threads"
    output_dir = project_root / "data" / "processed"

    games_to_process = {args.game: GAMES[args.game]} if args.game else GAMES

    if args.dry_run:
        for game_name in games_to_process:
            game_dir = threads_dir / game_name
            files = sorted(game_dir.glob("*.json")) if game_dir.exists() else []
            print(f"[{game_name}] {len(files)} threads to process")
            for f in files:
                print(f"    {f.name}")
        return

    # Load API key
    api_key = load_api_key(project_root)
    if not api_key:
        print(f"ERROR: Groq API key not found.")
        print(f"Set the {GROQ_API_KEY_ENV} environment variable or add it to .env")
        return

    client = Groq(api_key=api_key)

    print(f"BGG Forum Data Processor")
    print(f"Input:  {threads_dir}")
    print(f"Output: {output_dir}\n")

    for game_name, game_id in games_to_process.items():
        print(f"[{game_name}] (BGG ID: {game_id})")
        try:
            process_game(client, game_name, game_id, threads_dir, output_dir)
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    print("Done!")


if __name__ == "__main__":
    main()
