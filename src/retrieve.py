"""
Hybrid retrieval: per-source dense + BM25 via RRF; rulebook and forum pools merged for context.

Rulebook and forum each use separate Chroma collections and BM25 indexes (plans/split_vectordb_plan.md).
"""

import argparse
from collections import defaultdict
from pathlib import Path

from bgg_config import GAMES
from index import ChunkIndex, ChunkResult

# RRF (per source pool)
RRF_K = 60
DENSE_TOP_K = 15
SPARSE_TOP_K = 15
POOL_K = 3  # max chunks per source type; up to 2 * POOL_K total

RULES_TOP_K = 3  # max chunks from rulebook + card sources
FORUM_TOP_K = 3  # max chunks from forum sources
# Total chunks merged for RAG context; eval fixed-k metrics use @3 and @this (see eval/retrieval_eval.py).
TOTAL_RETRIEVED_K = RULES_TOP_K + FORUM_TOP_K

TIER_BOOST = 0.005  # within-pool tiebreaker for core_rules vs reference
CARD_NAME_BOOST = TIER_BOOST * 5  # 0.025 — card name appears in query


def reciprocal_rank_fusion(
    dense_results: list[ChunkResult],
    sparse_results: list[ChunkResult],
) -> list[ChunkResult]:
    all_chunks: dict[str, ChunkResult] = {}
    for r in dense_results + sparse_results:
        if r.chunk_id not in all_chunks:
            all_chunks[r.chunk_id] = r

    rrf_scores: defaultdict[str, float] = defaultdict(float)

    for rank, r in enumerate(dense_results):
        rrf_scores[r.chunk_id] += 1.0 / (RRF_K + rank + 1)

    for rank, r in enumerate(sparse_results):
        rrf_scores[r.chunk_id] += 1.0 / (RRF_K + rank + 1)

    for chunk_id, chunk in all_chunks.items():
        chunk.score = rrf_scores[chunk_id]

    merged = sorted(all_chunks.values(), key=lambda r: r.score, reverse=True)
    return merged


def apply_boosts(results: list[ChunkResult], query: str = "") -> list[ChunkResult]:
    query_lower = query.lower() if query else ""
    for r in results:
        if r.source_tier == "core_rules":
            r.score += TIER_BOOST
        # Boost card chunks when their name literally appears in the query
        if (
            r.source_type == "card"
            and query_lower
            and r.section_title
            and r.section_title.lower() in query_lower
        ):
            r.score += CARD_NAME_BOOST
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def retrieve(
    index: ChunkIndex,
    query: str,
    game_name: str,
    pool_k: int = POOL_K,
) -> list[ChunkResult]:
    if not query.strip():
        return []

    results: list[ChunkResult] = []

    for source_type in ("rulebook", "forum"):
        dense = index.dense_search(
            query, game_name, source_type=source_type, top_k=DENSE_TOP_K
        )
        sparse = index.bm25_search(
            query, game_name, source_type=source_type, top_k=SPARSE_TOP_K
        )
        merged = reciprocal_rank_fusion(dense, sparse)
        boosted = apply_boosts(merged, query=query)
        results.extend(boosted[:pool_k])

    return results


def retrieve_split(
    index: ChunkIndex,
    query: str,
    game_name: str,
    rules_top_k: int = RULES_TOP_K,
    forum_top_k: int = FORUM_TOP_K,
) -> list[ChunkResult]:
    """
    Two-pass hybrid retrieval with separate budgets for rules vs. forum.

    Pass 1: Retrieve from rulebook + card chunks (max rules_top_k)
    Pass 2: Retrieve from forum chunks (max forum_top_k)

    Each pass does its own dense + BM25 + RRF fusion internally.
    Results are concatenated with rules first, then forum.
    """
    if not query.strip():
        return []

    rules_types = ["rulebook", "card"]
    forum_types = ["forum"]

    dense_rules = index.dense_search(
        query, game_name, top_k=DENSE_TOP_K, source_types=rules_types
    )
    sparse_rules = index.bm25_search(
        query, game_name, top_k=SPARSE_TOP_K, source_types=rules_types
    )
    merged_rules = reciprocal_rank_fusion(dense_rules, sparse_rules)
    boosted_rules = apply_boosts(merged_rules, query=query)
    top_rules = boosted_rules[:rules_top_k]

    dense_forum = index.dense_search(
        query, game_name, top_k=DENSE_TOP_K, source_types=forum_types
    )
    sparse_forum = index.bm25_search(
        query, game_name, top_k=SPARSE_TOP_K, source_types=forum_types
    )
    merged_forum = reciprocal_rank_fusion(dense_forum, sparse_forum)
    boosted_forum = apply_boosts(merged_forum, query=query)
    top_forum = boosted_forum[:forum_top_k]

    return top_rules + top_forum


def multi_query_retrieve(
    index: ChunkIndex,
    queries: list[str],
    game_name: str,
    per_query_rules_k: int = 1,
    per_query_forum_k: int = 1,
) -> list[ChunkResult]:
    """
    Run retrieve_split() per sub-question, union-dedup by chunk_id.

    Keeps the best score for each chunk across all queries.
    Returns results sorted by best score descending.
    """
    best: dict[str, ChunkResult] = {}

    for q in queries:
        if not q.strip():
            continue
        for r in retrieve_split(
            index,
            q,
            game_name,
            rules_top_k=per_query_rules_k,
            forum_top_k=per_query_forum_k,
        ):
            existing = best.get(r.chunk_id)
            if existing is None or r.score > existing.score:
                best[r.chunk_id] = r

    return sorted(best.values(), key=lambda r: r.score, reverse=True)


def _format_source_block(i: int, r: ChunkResult) -> str:
    header_parts = [f"[Source {i}]"]
    header_parts.append(f"Game: {r.game_name}")
    header_parts.append(f"Type: {r.source_type}")

    if r.source_type == "rulebook":
        if r.section_title:
            header_parts.append(f"Section: {r.section_title}")
        if r.page_start > 0:
            if r.page_start == r.page_end:
                header_parts.append(f"Page: {r.page_start}")
            else:
                header_parts.append(f"Pages: {r.page_start}-{r.page_end}")
    elif r.source_type == "card":
        if r.section_title:
            header_parts.append(f"Card: {r.section_title}")
        if r.card_deck:
            header_parts.append(f"Deck: {r.card_deck}")
        if r.card_suit:
            header_parts.append(f"Suit: {r.card_suit}")
        if r.card_cost:
            header_parts.append(f"Cost: {r.card_cost}")
    elif r.source_type == "forum":
        if r.thread_subject:
            header_parts.append(f"Thread: {r.thread_subject}")
        if r.resolution_status:
            header_parts.append(f"Status: {r.resolution_status}")
        if r.confidence:
            header_parts.append(f"Confidence: {r.confidence}")

    header = " | ".join(header_parts)
    return f"{header}\n{r.content}"


def format_context(results: list[ChunkResult]) -> str:
    official = [r for r in results if r.source_type in ("rulebook", "card")]
    forum = [r for r in results if r.source_type == "forum"]

    blocks = []
    if official:
        blocks.append("=== OFFICIAL RULES ===")
        for i, r in enumerate(official, 1):
            blocks.append(_format_source_block(i, r))
    if forum:
        blocks.append("=== COMMUNITY DISCUSSION ===")
        for i, r in enumerate(forum, len(official) + 1):
            blocks.append(_format_source_block(i, r))

    return "\n\n---\n\n".join(blocks)


def sources_for_api(results: list[ChunkResult]) -> list[dict]:
    """
    Citation order matches format_context(): rulebook+card first [1..k],
    then forum [k+1..]. Safe for UI [n] brackets in the model answer.
    """
    official = [r for r in results if r.source_type in ("rulebook", "card")]
    forum = [r for r in results if r.source_type == "forum"]
    out: list[dict] = []
    for i, r in enumerate(official, 1):
        out.append(
            {
                "citationIndex": i,
                "sourceType": r.source_type,
                "content": r.content,
                "reference": _format_result_header(i, r),
                "chunkId": r.chunk_id,
            }
        )
    for i, r in enumerate(forum, len(official) + 1):
        out.append(
            {
                "citationIndex": i,
                "sourceType": r.source_type,
                "content": r.content,
                "reference": _format_result_header(i, r),
                "chunkId": r.chunk_id,
            }
        )
    return out


def _format_result_header(rank: int, r: ChunkResult) -> str:
    st = r.source_type
    if st == "rulebook":
        title = r.section_title or ""
        if r.page_start > 0:
            if r.page_start == r.page_end:
                page_ref = f"p.{r.page_start}"
            else:
                page_ref = f"pp.{r.page_start}-{r.page_end}"
            return f'[{rank}] ({st}) {r.chunk_id} — "{title}" {page_ref}'
        return f'[{rank}] ({st}) {r.chunk_id} — "{title}"'
    if st == "card":
        title = r.section_title or ""
        extra = f" [{r.card_suit}]" if r.card_suit else ""
        return f'[{rank}] ({st}) {r.chunk_id} — "{title}"{extra}'
    subj = r.thread_subject or ""
    meta_parts = [p for p in (r.resolution_status, r.confidence) if p]
    meta = f'  [{"/".join(meta_parts)}]' if meta_parts else ""
    return f'[{rank}] ({st}) {r.chunk_id} — "{subj}"{meta}'


def _print_results(results: list[ChunkResult], show_scores: bool) -> None:
    for i, r in enumerate(results, 1):
        print(_format_result_header(i, r))
        preview = r.content
        if len(preview) > 150:
            preview = preview[:150] + "..."
        print(f"    {preview}")
        if show_scores:
            print(f"    [score: {r.score:.4f}]")
        print()


def _run_query(
    index: ChunkIndex,
    query: str,
    game_name: str,
    pool_k: int,
    dense_only: bool,
    bm25_only: bool,
    show_scores: bool,
) -> None:
    q = query.strip()
    if not q:
        print("Empty query — nothing to retrieve.")
        return

    results: list[ChunkResult] = []

    if dense_only:
        for source_type in ("rulebook", "forum"):
            raw = index.dense_search(
                q, game_name, source_type=source_type, top_k=DENSE_TOP_K
            )
            boosted = apply_boosts(raw, query=q)
            results.extend(boosted[:pool_k])
    elif bm25_only:
        for source_type in ("rulebook", "forum"):
            raw = index.bm25_search(
                q, game_name, source_type=source_type, top_k=SPARSE_TOP_K
            )
            boosted = apply_boosts(raw, query=q)
            results.extend(boosted[:pool_k])
    else:
        results = retrieve(index, q, game_name, pool_k=pool_k)

    _print_results(results, show_scores)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test hybrid retrieval over SpielBot chunk indexes.",
    )
    parser.add_argument(
        "--game",
        type=str,
        required=True,
        help="Game to search (e.g. 'catan').",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Single query to run.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enter interactive query loop.",
    )
    parser.add_argument(
        "--pool-k",
        type=int,
        default=POOL_K,
        help=f"Max results per source pool, rulebook + forum (default: {POOL_K}).",
    )
    parser.add_argument(
        "--dense-only",
        action="store_true",
        help="Use only dense retrieval (no BM25), per pool.",
    )
    parser.add_argument(
        "--bm25-only",
        action="store_true",
        help="Use only BM25 retrieval (no dense), per pool.",
    )
    parser.add_argument(
        "--show-scores",
        action="store_true",
        help="Print RRF scores alongside results.",
    )
    args = parser.parse_args()

    if args.game not in GAMES:
        parser.error(
            f"Unknown game '{args.game}'. Valid options: {', '.join(GAMES.keys())}"
        )

    if args.dense_only and args.bm25_only:
        parser.error("Use only one of --dense-only and --bm25-only.")

    if not args.interactive and args.query is None:
        parser.error("Provide --query and/or --interactive.")

    project_root = Path(__file__).parent.parent
    idx = ChunkIndex(project_root)

    if args.interactive:
        print("Interactive mode — type 'quit' or 'exit' to stop.\n")
        while True:
            try:
                line = input("Query> ")
            except EOFError:
                break
            raw = line.strip()
            if raw.lower() in ("quit", "exit"):
                break
            if not raw:
                continue
            _run_query(
                idx,
                raw,
                args.game,
                args.pool_k,
                args.dense_only,
                args.bm25_only,
                args.show_scores,
            )
        return

    _run_query(
        idx,
        args.query or "",
        args.game,
        args.pool_k,
        args.dense_only,
        args.bm25_only,
        args.show_scores,
    )


if __name__ == "__main__":
    main()
