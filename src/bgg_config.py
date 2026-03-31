# BGG game IDs for the XMLAPI2 scraper (requires API token)
GAMES = {
    "catan": 13,
    "splendor": 148228,
    "root": 237182,
}

# Geekdo API game config for the webscraping fallback (no auth needed)
# Forum type 66 = "Rules" on BGG; object_id distinguishes the game.
GAMES_GEEKDO = {
    "catan":    {"object_id": 13,     "forum_id": 66},
    "splendor": {"object_id": 148228, "forum_id": 66},
    "root":     {"object_id": 237182, "forum_id": 66},
}

# ── XMLAPI2 settings ────────────────────────────────────────────────────
BGG_API_BASE = "https://boardgamegeek.com/xmlapi2"
REQUEST_DELAY = 6.0          # seconds between API calls
MAX_RETRIES = 3
RETRY_BACKOFF = 10.0         # seconds base backoff on 429/5xx
USER_AGENT = "SpielBot/1.0 (board game rules assistant)"
DEFAULT_THREAD_LIMIT = 10    # threads per game (0 = no limit)

# BGG API token — set via BGG_API_TOKEN env var or .env file in project root.
# Register at https://boardgamegeek.com/using_the_xml_api to get a token.
BGG_API_TOKEN_ENV = "BGG_API_TOKEN"

# ── Geekdo webscraping settings ─────────────────────────────────────────
GEEKDO_API = "https://api.geekdo.com/api"
GEEKDO_REQUEST_DELAY = 2.0   # seconds between requests
GEEKDO_THREADS_PER_PAGE = 10 # BGG returns 10 threads per page
