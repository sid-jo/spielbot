"""
VLM prompts for Gemma 4 game-state analysis.

Preselected-game flow: user already selected game in UI/CLI.
No game-identification prompt is used.
"""

SCENE_PROMPTS: dict[str, str] = {}

SCENE_PROMPTS["catan"] = """\
Analyze this photo of a Catan game. Describe the visible game state as JSON.

IMPORTANT RULES:
- Output ONLY valid JSON, no markdown fences, no commentary before/after
- Use null for anything you cannot clearly see — do NOT guess
- Estimate counts where exact numbers are unclear
- Focus on what is VISIBLE, not what you assume

Output this exact JSON structure:
{
  "game": "catan",
  "confidence": "high | medium | low",
  "game_phase": "setup | early | mid | late",
  "num_players": <int or null>,
  "board": {
    "robber_location": "<description of hex or null>",
    "harbors_visible": ["<harbor descriptions>"],
    "notable_hexes": "<observations about resource layout>"
  },
  "players": [
    {
      "color": "<color>",
      "settlements": <int>,
      "cities": <int>,
      "roads_approximate": <int>,
      "visible_resources": "<description or null>",
      "special_cards": ["<Longest Road, Largest Army, etc.>"]
    }
  ],
  "visible_development_cards": "<description or null>",
  "observations": "<anything else notable>"
}
"""

SCENE_PROMPTS["root"] = """\
Analyze this photo of a Root game. Describe the visible game state as JSON.

IMPORTANT RULES:
- Output ONLY valid JSON, no markdown fences, no commentary before/after
- Use null for anything you cannot clearly see — do NOT guess
- Root is asymmetric: each faction has unique pieces. Identify factions by color:
  Orange=Marquise, Blue=Eyrie, Green=Alliance, Grey/Brown=Vagabond, etc.
- Focus on what is VISIBLE, not what you assume

Output this exact JSON structure:
{
  "game": "root",
  "confidence": "high | medium | low",
  "game_phase": "early | mid | late",
  "num_players": <int or null>,
  "factions": [
    {
      "name": "<faction name>",
      "color": "<piece color>",
      "approximate_pieces_on_board": <int>,
      "buildings_visible": ["<building types>"],
      "vp_if_visible": <int or null>
    }
  ],
  "map": {
    "clearings_detail": [
      {
        "suit": "<fox|mouse|rabbit or null>",
        "controlling_faction": "<name or contested>",
        "pieces_description": "<what is in this clearing>"
      }
    ],
    "forests_or_paths_notable": "<observations>",
    "ruins_status": "<items remaining if visible>"
  },
  "visible_cards": "<any cards face-up on table or in decree>",
  "vagabond_items": "<item track status if Vagabond in play, else null>",
  "observations": "<anything else notable>"
}
"""

SCENE_PROMPTS["splendor"] = """\
Analyze this photo of a Splendor game. Describe the visible game state as JSON.

IMPORTANT RULES:
- Output ONLY valid JSON, no markdown fences, no commentary before/after
- Use null for anything you cannot clearly see — do NOT guess
- Splendor cards are small and often hard to read in photos; only describe
  what you can actually make out
- Focus on what is VISIBLE, not what you assume

Output this exact JSON structure:
{
  "game": "splendor",
  "confidence": "high | medium | low",
  "game_phase": "early | mid | late",
  "num_players": <int or null>,
  "market": {
    "tier_1_cards": "<descriptions of visible Level 1 cards if readable>",
    "tier_2_cards": "<descriptions of visible Level 2 cards if readable>",
    "tier_3_cards": "<descriptions of visible Level 3 cards if readable>",
    "nobles_visible": "<noble tile requirements if readable>"
  },
  "gem_supply": {
    "white": <int or null>, "blue": <int or null>,
    "green": <int or null>, "red": <int or null>,
    "black": <int or null>, "gold": <int or null>,
    "notes": "<rough estimates if exact counts unclear>"
  },
  "players": [
    {
      "position": "<left|center|right or player color>",
      "purchased_cards_approximate": <int>,
      "card_colors_visible": ["<colors of purchased cards>"],
      "gems_held": "<description>",
      "reserved_cards": <int or null>,
      "nobles_earned": <int>,
      "estimated_points": <int or null>
    }
  ],
  "observations": "<anything else notable>"
}
"""

GENERIC_SCENE_PROMPT = """\
Analyze this board game photo. Describe the visible game state as JSON.

Output ONLY valid JSON:
{
  "game": "unknown",
  "confidence": "low",
  "description": "<detailed description of what you see>",
  "components_visible": ["<list of game components visible>"],
  "observations": "<anything notable about the game state>"
}
"""
