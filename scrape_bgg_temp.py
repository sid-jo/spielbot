"""
Temporary BGG Rules forum scraper using the public geekdo API.

Scrapes the 20 most recent threads from the Rules forum for Catan,
Splendor, and Root, outputting one JSON file per game into scraped_output/.

Usage:
    python scrape_bgg_temp.py
"""

import json
import re
import time
from datetime import date
from pathlib import Path

import requests

# ── Configuration ─────────────────────────────────────────────────────────

GEEKDO_API = "https://api.geekdo.com/api"
REQUEST_DELAY = 2.0  # seconds between requests (be polite)

# Forum type 66 = "Rules" on BGG; objectid distinguishes the game.
GAMES = {
    "catan":    {"object_id": 13,     "forum_id": 66},
    "splendor": {"object_id": 148228, "forum_id": 66},
    "root":     {"object_id": 237182, "forum_id": 66},
}

THREADS_TO_SCRAPE = 20
THREADS_PER_PAGE = 10  # BGG returns 10 threads per page

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


# ── Helpers ───────────────────────────────────────────────────────────────

def polite_get(url, params=None):
    """GET with a delay and basic retry."""
    time.sleep(REQUEST_DELAY)
    for attempt in range(3):
        resp = requests.get(url, params=params, headers=HEADERS)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503):
            wait = 10 * (2 ** attempt)
            print(f"      HTTP {resp.status_code}, retrying in {wait}s ...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Request failed after retries: {url}")


def clean_body(text):
    """Strip BGG forum markup ([q]...[/q], [article]...) from post body."""
    # Remove quoted blocks: [q="..."]...[/q]
    text = re.sub(r'\[q="[^"]*"\].*?\[/q\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[q\].*?\[/q\]', '', text, flags=re.DOTALL)
    # Remove inline references like [article=12345][/article]
    text = re.sub(r'\[article=\d+\]\[/article\]', '', text)
    # Remove any remaining BBCode-style tags
    text = re.sub(r'\[/?[a-zA-Z]+[^\]]*\]', '', text)
    # Collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def resolve_username(user_id, cache, session=None):
    """Look up a BGG username by user ID, with caching."""
    uid = str(user_id)
    if uid in cache:
        return cache[uid]
    try:
        data = polite_get(f"{GEEKDO_API}/users/{uid}")
        name = data.get("username", f"user_{uid}")
    except Exception:
        name = f"user_{uid}"
    cache[uid] = name
    return name


# ── Core scraping ─────────────────────────────────────────────────────────

def fetch_thread_list(object_id, forum_id, count):
    """Fetch the N most recent thread stubs from a Rules forum."""
    threads = []
    pages_needed = (count + THREADS_PER_PAGE - 1) // THREADS_PER_PAGE

    for page in range(1, pages_needed + 1):
        print(f"    Fetching thread list page {page}/{pages_needed} ...")
        data = polite_get(
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


def fetch_thread_posts(thread_id, user_cache):
    """Fetch all posts for a single thread."""
    posts = []
    page = 1

    while True:
        data = polite_get(
            f"{GEEKDO_API}/articles",
            params={"threadid": thread_id, "page": page},
        )
        articles = data.get("articles", [])
        if not articles:
            break

        for a in articles:
            author_id = a.get("author", "")
            username = resolve_username(author_id, user_cache)
            posts.append({
                "username": username,
                "date": a.get("postdate", ""),
                "body": clean_body(a.get("body", "")),
            })

        # Check if there are more pages
        total = data.get("total", 0)
        per_page = data.get("perPage", 25)
        if page * per_page >= total:
            break
        page += 1

    return posts


# ── Orchestration ─────────────────────────────────────────────────────────

def scrape_game(game_name, config, output_dir):
    """Scrape the 20 most recent Rules forum threads for one game."""
    print(f"\n[{game_name}] Fetching thread list ...")
    threads = fetch_thread_list(
        config["object_id"], config["forum_id"], THREADS_TO_SCRAPE
    )
    print(f"  Found {len(threads)} threads")

    user_cache = {}
    result_threads = {}
    seen_subjects = set()

    for i, t in enumerate(threads, 1):
        tid = t["thread_id"]
        subject = t["subject"]
        print(f"  [{i}/{len(threads)}] {subject[:65]}")

        posts = fetch_thread_posts(tid, user_cache)

        # Disambiguate duplicate titles
        key = subject
        if key in seen_subjects:
            key = f"{subject} [thread:{tid}]"
        seen_subjects.add(key)

        result_threads[key] = posts

    output = {
        "meta": {
            "game_name": game_name,
            "game_id": config["object_id"],
            "forum_type": "Rules",
            "threads_scraped": len(result_threads),
            "scrape_date": str(date.today()),
        },
        "threads": result_threads,
    }

    out_path = output_dir / f"{game_name}_bgg_forums.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {out_path}")


def main():
    project_root = Path(__file__).parent
    output_dir = project_root / "scraped_output"
    output_dir.mkdir(exist_ok=True)

    print(f"BGG Rules Forum Scraper (temp)")
    print(f"Threads per game: {THREADS_TO_SCRAPE}")
    print(f"Output: {output_dir}")

    for game_name, config in GAMES.items():
        try:
            scrape_game(game_name, config, output_dir)
        except Exception as e:
            print(f"  ERROR scraping {game_name}: {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
