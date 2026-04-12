import json
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rank_bm25 import BM25Okapi

from bgg_config import GAMES

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
RULEBOOK_COLLECTION = "spielbot_rulebook"
FORUM_COLLECTION = "spielbot_forum"

# Default max chars returned per chunk — snapped to sentence boundary.
# At 1000 chars, ~75% of chunks pass through untrimmed; the long tail is clipped.
# Pass max_chars=None to a search method to disable truncation entirely.
MAX_CONTENT_CHARS = 1000

# Minimal stopwords — deliberately excludes rule-critical words like
# "can", "may", "must", "not", "no", "if", "when", "each", "all", "any".
STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "and", "but", "or", "so",
    "at", "by", "for", "in", "of", "on", "to", "with", "from", "as",
    "it", "its", "this", "that", "these", "those",
})


@dataclass
class ChunkResult:
    chunk_id: str
    content: str              # text the generator will see (may be trimmed)
    game_name: str
    source_type: str          # "rulebook", "forum", or "card"
    section_title: str        # "" for forum chunks
    source_tier: str          # "core_rules" / "reference" / "" for forum
    retrieval_priority: int   # 1=rulebook/card, 2=forum
    page_start: int           # -1 if not applicable (forum/card)
    page_end: int             # -1 if not applicable (forum/card)
    score: float = 0.0
    # Forum-specific (empty strings for rulebook chunks)
    thread_id: str = ""
    thread_subject: str = ""
    resolution_status: str = ""
    confidence: str = ""
    # Card-specific (empty for non-card chunks)
    card_deck: str = ""
    card_suit: str = ""
    card_box: str = ""
    card_cost: str = ""
    card_quantity: int = 0


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


def get_embed_text(chunk: dict) -> str:
    if chunk["source_type"] in ("forum", "card"):
        return chunk["embed_text"]
    return chunk["content"]


def _trim_content(text: str, max_chars: int | None) -> str:
    """Trim text to max_chars, snapping to the last sentence boundary."""
    if max_chars is None or len(text) <= max_chars:
        return text
    # Try to end at a sentence boundary (". ") within the limit
    window = text[:max_chars]
    last_period = window.rfind(". ")
    if last_period > max_chars // 2:  # only snap if we keep at least half
        return window[: last_period + 1]
    return window.rstrip() + "…"


class ChunkIndex:
    def __init__(self, project_root: Path):
        # ── Dense index (ChromaDB) ────────────────────────────────────────
        vectorstore_dir = project_root / "data" / "vectorstore"
        self._chroma_client = chromadb.PersistentClient(path=str(vectorstore_dir))

        embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
            normalize_embeddings=True,
        )

        try:
            self._rulebook_collection = self._chroma_client.get_collection(
                name=RULEBOOK_COLLECTION,
                embedding_function=embed_fn,
            )
            self._forum_collection = self._chroma_client.get_collection(
                name=FORUM_COLLECTION,
                embedding_function=embed_fn,
            )
        except (ValueError, chromadb.errors.NotFoundError) as e:
            raise RuntimeError(
                f"Chroma collections '{RULEBOOK_COLLECTION}' / '{FORUM_COLLECTION}' "
                f"not found. Run embed_chunks.py first."
            ) from e

        print(
            f"Dense index: {self._rulebook_collection.count()} rulebook, "
            f"{self._forum_collection.count()} forum chunks"
        )

        # ── Sparse index (BM25) ──────────────────────────────────────────
        chunks_dir = project_root / "data" / "chunks"
        self._bm25_indexes: dict[str, dict[str, BM25Okapi]] = {}
        self._bm25_chunks: dict[str, dict[str, list[dict]]] = {}

        for game_name in GAMES:
            self._bm25_indexes[game_name] = {}
            self._bm25_chunks[game_name] = {}
            for suffix in ("rulebook", "forum"):
                path = chunks_dir / f"{game_name}_{suffix}_chunks.json"
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                source_chunks = list(data["chunks"])
                # Cards live in the rulebook Chroma collection; include them in BM25 rulebook pool.
                if suffix == "rulebook":
                    card_path = chunks_dir / f"{game_name}_card_chunks.json"
                    if card_path.exists():
                        card_data = json.loads(
                            card_path.read_text(encoding="utf-8")
                        )
                        source_chunks.extend(card_data["chunks"])
                if not source_chunks:
                    continue
                tokenized = [tokenize(get_embed_text(c)) for c in source_chunks]
                self._bm25_indexes[game_name][suffix] = BM25Okapi(tokenized)
                self._bm25_chunks[game_name][suffix] = source_chunks
            rb = len(self._bm25_chunks[game_name].get("rulebook", []))
            fm = len(self._bm25_chunks[game_name].get("forum", []))
            print(f"BM25 index: {game_name} — {rb} rulebook, {fm} forum chunks")

    # ── Dense search ─────────────────────────────────────────────────────

    def dense_search(
        self,
        query: str,
        game_name: str,
        source_type: str = "rulebook",
        top_k: int = 10,
        max_chars: int | None = MAX_CONTENT_CHARS,
        source_types: list[str] | None = None,
    ) -> list[ChunkResult]:
        if source_types is not None:
            if not source_types:
                return []
            st_set = set(source_types)
            rules_set = {"rulebook", "card"}
            if st_set <= rules_set:
                collection = self._rulebook_collection
                where_filter = {
                    "$and": [
                        {"game_name": game_name},
                        {"source_type": {"$in": list(st_set)}},
                    ],
                }
            elif st_set == {"forum"}:
                collection = self._forum_collection
                where_filter = {
                    "$and": [
                        {"game_name": game_name},
                        {"source_type": {"$in": ["forum"]}},
                    ],
                }
            else:
                raise ValueError(
                    "dense_search source_types must be a subset of "
                    "{'rulebook', 'card'} or exactly {'forum'}; "
                    f"got {source_types!r}"
                )
        else:
            collection = (
                self._rulebook_collection
                if source_type == "rulebook"
                else self._forum_collection
            )
            where_filter = {"game_name": game_name}

        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
            include=["metadatas", "distances"],
        )

        chunk_results = []
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            chunk_results.append(ChunkResult(
                chunk_id=meta["chunk_id"],
                content=_trim_content(meta["content"], max_chars),
                game_name=meta["game_name"],
                source_type=meta["source_type"],
                section_title=meta.get("section_title", ""),
                source_tier=meta.get("source_tier", ""),
                retrieval_priority=meta["retrieval_priority"],
                page_start=meta.get("page_start", -1),
                page_end=meta.get("page_end", -1),
                score=1.0 - dist,
                thread_id=meta.get("thread_id", ""),
                thread_subject=meta.get("thread_subject", ""),
                resolution_status=meta.get("resolution_status", ""),
                confidence=meta.get("confidence", ""),
                card_deck=meta.get("card_deck", ""),
                card_suit=meta.get("card_suit", ""),
                card_box=meta.get("card_box", ""),
                card_cost=meta.get("card_cost", ""),
                card_quantity=int(meta.get("card_quantity", 0) or 0),
            ))
        return chunk_results

    # ── BM25 search ──────────────────────────────────────────────────────

    def bm25_search(
        self,
        query: str,
        game_name: str,
        source_type: str = "rulebook",
        top_k: int = 10,
        max_chars: int | None = MAX_CONTENT_CHARS,
        source_types: list[str] | None = None,
    ) -> list[ChunkResult]:
        if source_types is not None:
            if not source_types:
                return []
            st_set = set(source_types)
            rules_set = {"rulebook", "card"}
            if st_set <= rules_set:
                suffix = "rulebook"
            elif st_set == {"forum"}:
                suffix = "forum"
            else:
                raise ValueError(
                    "bm25_search source_types must be a subset of "
                    "{'rulebook', 'card'} or exactly {'forum'}; "
                    f"got {source_types!r}"
                )
            idx_map = self._bm25_indexes.get(game_name, {})
            if suffix not in idx_map:
                return []
            chunks = self._bm25_chunks[game_name][suffix]
            bm25 = idx_map[suffix]
            if st_set <= rules_set:
                valid_indices = [
                    i
                    for i in range(len(chunks))
                    if chunks[i]["source_type"] in st_set
                ]
            else:
                valid_indices = list(range(len(chunks)))
        else:
            idx_map = self._bm25_indexes.get(game_name, {})
            if source_type not in idx_map:
                return []
            chunks = self._bm25_chunks[game_name][source_type]
            bm25 = idx_map[source_type]
            valid_indices = list(range(len(chunks)))

        query_tokens = tokenize(query)
        scores = bm25.get_scores(query_tokens)
        top_indices = sorted(
            valid_indices, key=lambda i: scores[i], reverse=True
        )[:top_k]

        chunk_results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            chunk = chunks[idx]
            cd = chunk.get("card_deck", "")
            card_deck_str = ", ".join(cd) if isinstance(cd, list) else str(cd)
            chunk_results.append(ChunkResult(
                chunk_id=chunk["chunk_id"],
                content=_trim_content(chunk["content"], max_chars),
                game_name=chunk["game_name"],
                source_type=chunk["source_type"],
                section_title=chunk.get("section_title", ""),
                source_tier=chunk.get("source_tier", ""),
                retrieval_priority=chunk["retrieval_priority"],
                page_start=chunk.get("page_start", -1),
                page_end=chunk.get("page_end", -1),
                score=float(scores[idx]),
                thread_id=chunk.get("thread_id", ""),
                thread_subject=chunk.get("thread_subject", ""),
                resolution_status=chunk.get("resolution_status", ""),
                confidence=chunk.get("confidence", ""),
                card_deck=card_deck_str,
                card_suit=chunk.get("card_suit", ""),
                card_box=chunk.get("card_box", ""),
                card_cost=chunk.get("card_cost", ""),
                card_quantity=int(chunk.get("card_quantity", 0) or 0),
            ))
        return chunk_results


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    idx = ChunkIndex(project_root)

    for q in ["roll a 7", "longest road", "Distance Rule"]:
        print(f"\nQuery: {q}")
        for st in ("rulebook", "forum"):
            dense = idx.dense_search(q, "catan", source_type=st, top_k=3)
            sparse = idx.bm25_search(q, "catan", source_type=st, top_k=3)
            print(f"  [{st}] Dense:  {[r.chunk_id for r in dense]}")
            print(f"  [{st}] BM25:   {[r.chunk_id for r in sparse]}")
