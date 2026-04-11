"""
Build Root crafting card chunks from CSV for RAG (plans/card_plans.md).

Reads data/root_card_data.csv, groups and cross-deck deduplicates rows, writes
data/chunks/root_card_chunks.json. No LLM calls.
"""

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from bgg_config import GAMES

ROOT_GAME = "root"
ROOT_GAME_ID = GAMES[ROOT_GAME]
CSV_NAME = "root_card_data.csv"
OUTPUT_NAME = "root_card_chunks.json"

# Variant ordering for bullet lists
_SUIT_ORDER = {"Bird": 0, "Fox": 1, "Rabbit": 2, "Mouse": 3}


def _cost_str(cost: str, cost_suit: str) -> str:
    c = str(cost).strip()
    cs = str(cost_suit).strip() if cost_suit else ""
    if cs.lower() == "none":
        cs = ""
    if not cs:
        return c
    return f"{c} {cs}"


def _box_line(box: str) -> str:
    b = box.strip()
    if b.lower() == "paper":
        return "Paper (one-time use)"
    if b.lower() == "stone":
        return "Stone (persistent effect)"
    return f"{b} (one-time use / persistent effect)"


def _format_decks(decks: list[str]) -> str:
    if len(decks) == 1:
        return decks[0]
    if len(decks) == 2:
        return f"{decks[0]} and {decks[1]}"
    return ", ".join(decks[:-1]) + f", and {decks[-1]}"


def _row_key(row: dict) -> tuple:
    return (
        row["Name"],
        row["Box"],
        row["Suit"],
        str(row["Cost"]).strip(),
        str(row["Cost Suit"]).strip(),
        row["Effect"].strip(),
    )


def _merge_identical_rows(rows: list[dict]) -> list[dict]:
    """Merge rows identical except Deck; sum Quantity; Deck becomes sorted list."""
    buckets: dict[tuple, dict] = {}
    for r in rows:
        k = _row_key(r)
        if k not in buckets:
            buckets[k] = {
                "Name": r["Name"],
                "Box": r["Box"],
                "Suit": r["Suit"],
                "Cost": str(r["Cost"]).strip(),
                "Cost Suit": str(r["Cost Suit"]).strip(),
                "Effect": r["Effect"].strip(),
                "Quantity": 0,
                "decks": set(),
            }
        buckets[k]["Quantity"] += int(r["Quantity"])
        buckets[k]["decks"].add(r["Deck"])
    out = []
    for b in buckets.values():
        decks = sorted(b["decks"], key=lambda d: (d != "Standard Deck", d))
        out.append({
            "Name": b["Name"],
            "Box": b["Box"],
            "Suit": b["Suit"],
            "Cost": b["Cost"],
            "Cost Suit": b["Cost Suit"],
            "Effect": b["Effect"],
            "Quantity": b["Quantity"],
            "Deck": decks,
        })
    return out


def _sort_variant_rows(variants: list[dict]) -> list[dict]:
    return sorted(
        variants,
        key=lambda r: (_SUIT_ORDER.get(r["Suit"], 99), r["Suit"]),
    )


def _build_content(name: str, variants: list[dict]) -> str:
    decks = variants[0]["Deck"]
    if isinstance(decks, str):
        decks = [decks]
    deck_str = _format_decks(decks)
    lines = [f"**{name}** ({deck_str})"]

    if len(decks) > 1:
        lines.append(
            "This card appears in multiple decks: "
            + _format_decks(decks)
            + "."
        )

    box = variants[0]["Box"]
    box_desc = _box_line(box)

    if len(variants) == 1:
        v = variants[0]
        cs = _cost_str(v["Cost"], v["Cost Suit"])
        lines.append(
            f"Type: {box_desc} | Suit: {v['Suit']} | Cost: {cs} | "
            f"Copies in deck: {v['Quantity']}"
        )
        lines.append(f"Effect: {v['Effect']}")
        return "\n".join(lines)

    lines.append("This card has multiple variants by suit:")
    for v in _sort_variant_rows(variants):
        cs = _cost_str(v["Cost"], v["Cost Suit"])
        lines.append(
            f"- {v['Suit']} {name} (×{v['Quantity']}): {v['Effect']}"
        )
    shared_cost = all(
        _cost_str(v["Cost"], v["Cost Suit"])
        == _cost_str(variants[0]["Cost"], variants[0]["Cost Suit"])
        for v in variants
    )
    cost_part = (
        _cost_str(variants[0]["Cost"], variants[0]["Cost Suit"])
        if shared_cost
        else "(cost varies by suit — see variants above)"
    )
    total_q = sum(v["Quantity"] for v in variants)
    lines.append(
        f"All variants: {box_desc} | Cost: {cost_part} | Total copies: {total_q}"
    )
    return "\n".join(lines)


def _embed_summary(name: str, variants: list[dict]) -> str:
    """One short sentence for asymmetric embed_text."""
    if len(variants) == 1:
        eff = variants[0]["Effect"]
    else:
        eff = _sort_variant_rows(variants)[0]["Effect"]
    eff = re.sub(r"\s+", " ", eff).strip()
    if len(eff) > 160:
        eff = eff[:157].rsplit(" ", 1)[0] + "…"
    return eff


def _chunk_metadata_fields(variants: list[dict]) -> dict:
    decks = variants[0]["Deck"]
    if isinstance(decks, str):
        decks = [decks]
    suits = sorted({v["Suit"] for v in variants}, key=lambda s: _SUIT_ORDER.get(s, 99))
    total_q = sum(v["Quantity"] for v in variants)
    costs = {_cost_str(v["Cost"], v["Cost Suit"]) for v in variants}
    card_cost = next(iter(costs)) if len(costs) == 1 else " / ".join(sorted(costs))
    return {
        "card_deck": decks,
        "card_suit": ", ".join(suits),
        "card_box": variants[0]["Box"],
        "card_cost": card_cost,
        "card_quantity": total_q,
    }


def load_csv_rows(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("Name", "").strip():
                continue
            rows.append({k: (v or "").strip() if isinstance(v, str) else v for k, v in row.items()})
    return rows


def build_chunks_from_rows(rows: list[dict]) -> list[dict]:
    merged = _merge_identical_rows(rows)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in merged:
        dk = frozenset(r["Deck"] if isinstance(r["Deck"], list) else [r["Deck"]])
        groups[(r["Name"], dk)].append(r)

    chunk_list = []
    for (name, _dk), variants in sorted(groups.items(), key=lambda x: (x[0][0], str(sorted(x[0][1])))):
        variants = list(variants)
        meta = _chunk_metadata_fields(variants)
        content = _build_content(name, variants)
        summary = _embed_summary(name, variants)
        embed_text = (
            f"What does the card {name} do in Root? {name} card effect, cost, suit.\n"
            f"{summary}"
        )
        chunk_list.append({
            "section_title": name,
            "content": content,
            "embed_text": embed_text,
            **meta,
        })

    total = len(chunk_list)
    out_chunks = []
    for i, ch in enumerate(chunk_list):
        decks = ch["card_deck"]
        out_chunks.append({
            "chunk_id": f"root_card_{i:03d}",
            "source_type": "card",
            "game_name": ROOT_GAME,
            "game_id": ROOT_GAME_ID,
            "section_title": ch["section_title"],
            "source_tier": "reference",
            "retrieval_priority": 1,
            "page_start": -1,
            "page_end": -1,
            "card_deck": decks,
            "card_suit": ch["card_suit"],
            "card_box": ch["card_box"],
            "card_cost": ch["card_cost"],
            "card_quantity": ch["card_quantity"],
            "content": ch["content"],
            "embed_text": ch["embed_text"],
            "chunk_index": i,
            "total_chunks": total,
        })
    return out_chunks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process Root card CSV into chunk JSON for RAG.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print group count without writing output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each chunk content.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    csv_path = project_root / "data" / CSV_NAME
    out_dir = project_root / "data" / "chunks"
    out_path = out_dir / OUTPUT_NAME

    if not csv_path.exists():
        raise SystemExit(f"Missing CSV: {csv_path}")

    rows = load_csv_rows(csv_path)
    chunks = build_chunks_from_rows(rows)

    print(f"Loaded {len(rows)} CSV rows -> {len(chunks)} card chunks")

    if args.dry_run:
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "game_name": ROOT_GAME,
        "game_id": ROOT_GAME_ID,
        "source_file": CSV_NAME,
        "total_chunks": len(chunks),
        "chunks": chunks,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    if args.verbose:
        for c in chunks:
            print(f"\n--- {c['chunk_id']} {c['section_title']} ---\n{c['content']}\n")


if __name__ == "__main__":
    main()
