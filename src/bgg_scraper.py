"""
Scrape BGG Rules forum threads for board games.

Uses the XMLAPI2 if a BGG_API_TOKEN is available, otherwise falls back
to the public Geekdo API (no auth required).

Output: one JSON per thread in bgg_threads/<game>/<thread_slug>.json

Usage:
    python src/bgg_scraper.py              # 10 most recent threads per game
    python src/bgg_scraper.py --limit 25   # 25 threads per game
    python src/bgg_scraper.py --limit 0    # all threads (full scrape)
"""

import argparse
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import requests

from bgg_config import (
    BGG_API_BASE,
    BGG_API_TOKEN_ENV,
    DEFAULT_THREAD_LIMIT,
    GAMES,
    GAMES_GEEKDO,
    GEEKDO_API,
    GEEKDO_REQUEST_DELAY,
    GEEKDO_THREADS_PER_PAGE,
    MAX_RETRIES,
    REQUEST_DELAY,
    RETRY_BACKOFF,
    USER_AGENT,
)


# ===========================================================================
# Shared helpers
# ===========================================================================

def load_api_token(project_root):
    """Load BGG API token from env var or .env file."""
    token = os.environ.get(BGG_API_TOKEN_ENV)
    if token:
        return token.strip()

    env_path = project_root / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{BGG_API_TOKEN_ENV}="):
                    return line.split("=", 1)[1].strip().strip("\"'")

    return None


# ===========================================================================
# XMLAPI2 method (requires API token)
# ===========================================================================

def _xml_request(url, params, session):
    """Rate-limited GET with retry on 429, 5xx, and 202 (processing)."""
    for attempt in range(MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY)
        resp = session.get(url, params=params)

        if resp.status_code == 200:
            return ET.fromstring(resp.content)

        if resp.status_code == 202:
            wait = RETRY_BACKOFF
            print(f"    BGG returned 202 (processing), retrying in {wait:.0f}s ...")
            time.sleep(wait)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            wait = RETRY_BACKOFF * (2 ** attempt)
            print(f"    HTTP {resp.status_code}, retrying in {wait:.0f}s ...")
            time.sleep(wait)
            continue

        resp.raise_for_status()

    raise RuntimeError(
        f"BGG request failed after {MAX_RETRIES} retries: {url} {params}"
    )


def _strip_html(text):
    """Convert BGG post HTML to plain text, removing citation/quote blocks."""
    # Remove quote blocks: <q>...</q> and preceding "Username wrote:" attribution
    text = re.sub(
        r'\S+ wrote:\s*(?:<br\s*/?>[\s]*)*<q\b[^>]*>.*?</q>',
        '', text, flags=re.DOTALL | re.IGNORECASE,
    )
    # Catch any remaining standalone <q>...</q> blocks
    text = re.sub(r'<q\b[^>]*>.*?</q>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Convert <br> to newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|li|tr)>", "\n", text, flags=re.IGNORECASE)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Checkpoint I/O ────────────────────────────────────────────────────────

def _load_checkpoint(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_checkpoint(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


# ── XMLAPI2 scraping functions ────────────────────────────────────────────

def _xml_get_rules_forum_id(game_id, session):
    root = _xml_request(
        f"{BGG_API_BASE}/forumlist",
        {"id": game_id, "type": "thing"},
        session,
    )
    for forum in root.iter("forum"):
        title = forum.get("title", "")
        if title.lower().strip() == "rules":
            return int(forum.get("id"))
    raise ValueError(f"No 'Rules' forum found for game {game_id}")


def _xml_get_thread_ids(forum_id, session, limit, checkpoint):
    threads = list(checkpoint.get("threads_discovered", []))
    start_page = checkpoint.get("last_page_scraped", 0) + 1

    if limit and len(threads) >= limit:
        return threads[:limit]

    page = start_page
    while True:
        print(f"    Fetching thread list page {page} ...")
        root = _xml_request(
            f"{BGG_API_BASE}/forum",
            {"id": forum_id, "page": page},
            session,
        )

        page_threads = root.findall(".//thread")
        if not page_threads:
            break

        for t in page_threads:
            threads.append({
                "id": int(t.get("id")),
                "subject": t.get("subject", ""),
                "num_articles": int(t.get("numarticles", 0)),
            })

        checkpoint["threads_discovered"] = threads
        checkpoint["last_page_scraped"] = page

        if limit and len(threads) >= limit:
            break

        page += 1

    if limit:
        threads = threads[:limit]
    return threads


def _xml_get_thread_content(thread_id, session):
    root = _xml_request(
        f"{BGG_API_BASE}/thread",
        {"id": thread_id},
        session,
    )

    posts = []
    for article in root.iter("article"):
        body_el = article.find("body")
        body_text = _strip_html(body_el.text) if body_el is not None and body_el.text else ""
        posts.append({
            "username": article.get("username", ""),
            "date": article.get("postdate", ""),
            "body": body_text,
        })
    return posts


def _xml_scrape_game(game_name, game_id, output_dir, checkpoint_dir, limit, session):
    """Full XMLAPI2 pipeline for one game."""
    cp_path = checkpoint_dir / f"{game_name}_checkpoint.json"
    checkpoint = _load_checkpoint(cp_path)

    forum_id = checkpoint.get("forum_id")
    if not forum_id:
        print(f"  Discovering Rules forum ID for {game_name} ...")
        forum_id = _xml_get_rules_forum_id(game_id, session)
        checkpoint["forum_id"] = forum_id
        _save_checkpoint(checkpoint, cp_path)
    print(f"  Rules forum ID: {forum_id}")

    threads = _xml_get_thread_ids(forum_id, session, limit, checkpoint)
    _save_checkpoint(checkpoint, cp_path)
    print(f"  Threads to scrape: {len(threads)}")

    completed = set(checkpoint.get("threads_completed", []))
    thread_data = checkpoint.get("thread_data", {})

    for i, t in enumerate(threads, 1):
        tid = t["id"]
        if tid in completed:
            continue

        print(f"    [{i}/{len(threads)}] Scraping thread {tid}: {t['subject'][:60]}")
        posts = _xml_get_thread_content(tid, session)

        thread_data[str(tid)] = {
            "subject": t["subject"],
            "posts": posts,
        }
        completed.add(tid)

        checkpoint["thread_data"] = thread_data
        checkpoint["threads_completed"] = list(completed)
        _save_checkpoint(checkpoint, cp_path)

    # Save each thread as a separate JSON
    game_dir = output_dir / game_name
    for tid, entry in thread_data.items():
        _save_thread_json(
            game_dir, tid, entry["subject"], game_name, game_id, entry["posts"]
        )

    print(f"  Saved {len(thread_data)} thread files to {game_dir}")

    if cp_path.exists():
        cp_path.unlink()


# ===========================================================================
# Geekdo webscraping method (no auth required)
# ===========================================================================

def _web_get(url, params=None):
    """GET with a delay and basic retry."""
    time.sleep(GEEKDO_REQUEST_DELAY)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    for attempt in range(3):
        resp = requests.get(url, params=params, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503):
            wait = 10 * (2 ** attempt)
            print(f"      HTTP {resp.status_code}, retrying in {wait}s ...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Request failed after retries: {url}")


def _web_clean_body(text):
    """Strip BGG forum markup ([q]...[/q], [article]...) from post body."""
    text = re.sub(r'\[q="[^"]*"\].*?\[/q\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[q\].*?\[/q\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[article=\d+\]\[/article\]', '', text)
    text = re.sub(r'\[/?[a-zA-Z]+[^\]]*\]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _web_resolve_username(user_id, cache):
    """Look up a BGG username by user ID, with caching."""
    uid = str(user_id)
    if uid in cache:
        return cache[uid]
    try:
        data = _web_get(f"{GEEKDO_API}/users/{uid}")
        name = data.get("username", f"user_{uid}")
    except Exception:
        name = f"user_{uid}"
    cache[uid] = name
    return name


def _web_fetch_thread_list(object_id, forum_id, count):
    """Fetch the N most recent thread stubs from a Rules forum."""
    threads = []
    pages_needed = (count + GEEKDO_THREADS_PER_PAGE - 1) // GEEKDO_THREADS_PER_PAGE

    for page in range(1, pages_needed + 1):
        print(f"    Fetching thread list page {page}/{pages_needed} ...")
        data = _web_get(
            f"{GEEKDO_API}/forums/threads",
            params={
                "forumid": forum_id,
                "objectid": object_id,
                "objecttype": "thing",
                "pageid": page,
                "sort": "recent",
            },
        )
        for t in data.get("threads", []):
            threads.append({
                "thread_id": t["threadid"],
                "subject": t["subject"],
                "author": t.get("user", {}).get("username", "unknown"),
                "post_date": t.get("postdate", ""),
                "num_posts": int(t.get("numposts", 0)),
            })
        if len(threads) >= count:
            break

    return threads[:count]


def _web_fetch_thread_posts(thread_id, user_cache):
    """Fetch all posts for a single thread."""
    posts = []
    page = 1

    while True:
        data = _web_get(
            f"{GEEKDO_API}/articles",
            params={"threadid": thread_id, "page": page},
        )
        articles = data.get("articles", [])
        if not articles:
            break

        for a in articles:
            author_id = a.get("author", "")
            username = _web_resolve_username(author_id, user_cache)
            posts.append({
                "username": username,
                "date": a.get("postdate", ""),
                "body": _web_clean_body(a.get("body", "")),
            })

        total = data.get("total", 0)
        per_page = data.get("perPage", 25)
        if page * per_page >= total:
            break
        page += 1

    return posts


def _web_scrape_game(game_name, game_config, output_dir, limit):
    """Full Geekdo webscraping pipeline for one game."""
    count = limit if limit else 20

    print(f"  Fetching thread list ...")
    threads = _web_fetch_thread_list(
        game_config["object_id"], game_config["forum_id"], count
    )
    print(f"  Found {len(threads)} threads")

    user_cache = {}
    game_dir = output_dir / game_name

    for i, t in enumerate(threads, 1):
        tid = t["thread_id"]
        subject = t["subject"]
        print(f"    [{i}/{len(threads)}] {subject[:65]}")

        posts = _web_fetch_thread_posts(tid, user_cache)

        _save_thread_json(
            game_dir, str(tid), subject, game_name, game_config["object_id"], posts
        )

    print(f"  Saved {len(threads)} thread files to {game_dir}")


# ===========================================================================
# Shared output
# ===========================================================================

def _save_thread_json(game_dir, slug, subject, game_name, game_id, posts):
    """Write a single thread JSON to bgg_threads/<game>/<slug>.json."""
    game_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {
            "game_name": game_name,
            "game_id": game_id,
            "forum_type": "Rules",
            "scrape_date": str(date.today()),
        },
        "subject": subject,
        "posts": posts,
    }
    path = game_dir / f"{slug}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


# ===========================================================================
# Orchestration
# ===========================================================================

def scrape_all_games(output_dir, checkpoint_dir, limit, project_root):
    """Scrape Rules forums for all configured games.

    Tries XMLAPI2 first (needs BGG_API_TOKEN). Falls back to the public
    Geekdo API if no token is found.
    """
    token = load_api_token(project_root)

    if token:
        # ── XMLAPI2 path ────────────────────────────────────────────────
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        session.headers["Authorization"] = f"Bearer {token}"

        label = f"(limit: {limit} threads)" if limit else "(all threads)"
        print(f"BGG Rules Forum Scraper — XMLAPI2 mode {label}")
        print(f"Output: {output_dir}\n")

        for game_name, game_id in GAMES.items():
            print(f"[{game_name}] Starting (BGG ID: {game_id}) ...")
            try:
                _xml_scrape_game(
                    game_name, game_id, output_dir, checkpoint_dir, limit, session
                )
            except Exception as e:
                print(f"  ERROR: {e}")
                print(f"  Checkpoint saved — rerun to resume.\n")
                continue
            print()
    else:
        # ── Geekdo webscraping fallback ─────────────────────────────────
        label = f"(limit: {limit} threads)" if limit else "(default: 20 threads)"
        print(f"No BGG API token found — using Geekdo webscraping fallback {label}")
        print(f"(Set {BGG_API_TOKEN_ENV} env var or add to .env for XMLAPI2 mode)")
        print(f"Output: {output_dir}\n")

        for game_name, game_config in GAMES_GEEKDO.items():
            print(f"[{game_name}] Starting (BGG ID: {game_config['object_id']}) ...")
            try:
                _web_scrape_game(game_name, game_config, output_dir, limit)
            except Exception as e:
                print(f"  ERROR scraping {game_name}: {e}")
            print()

    print("Done!")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape BGG Rules forums for board games."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_THREAD_LIMIT,
        help=f"Max threads per game (0 = all). Default: {DEFAULT_THREAD_LIMIT}",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    output_dir = project_root / "data" / "bgg_threads"
    checkpoint_dir = project_root / "data" / "checkpoints"

    scrape_all_games(output_dir, checkpoint_dir, args.limit, project_root)
