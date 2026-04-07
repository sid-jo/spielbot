import json
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rank_bm25 import BM25Okapi

from bgg_config import GAMES

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION_NAME = "spielbot_chunks"

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
    source_type: str          # "rulebook" or "forum"
    section_title: str        # "" for forum chunks
    source_tier: str          # "core_rules" / "reference" / "" for forum
    retrieval_priority: int   # 1=rulebook, 2=forum
    page_start: int           # -1 if not applicable (forum)
    page_end: int             # -1 if not applicable (forum)
    score: float = 0.0
    # Forum-specific (empty strings for rulebook chunks)
    thread_id: str = ""
    thread_subject: str = ""
    resolution_status: str = ""
    confidence: str = ""


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


def get_embed_text(chunk: dict) -> str:
    if chunk["source_type"] == "forum":
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
            self._collection = self._chroma_client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=embed_fn,
            )
        except (ValueError, chromadb.errors.NotFoundError):
            raise RuntimeError(
                f"Collection '{COLLECTION_NAME}' not found. Run embed_chunks.py first."
            )

        print(f"Dense index: {self._collection.count()} chunks in ChromaDB")

        # ── Sparse index (BM25) ──────────────────────────────────────────
        chunks_dir = project_root / "data" / "chunks"
        self._bm25_indexes: dict[str, BM25Okapi] = {}
        self._bm25_chunks: dict[str, list[dict]] = {}

        for game_name in GAMES:
            chunks: list[dict] = []
            for suffix in ("rulebook", "forum"):
                path = chunks_dir / f"{game_name}_{suffix}_chunks.json"
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    chunks.extend(data["chunks"])

            tokenized_corpus = [tokenize(get_embed_text(c)) for c in chunks]
            self._bm25_indexes[game_name] = BM25Okapi(tokenized_corpus)
            self._bm25_chunks[game_name] = chunks
            print(f"BM25 index: {game_name} — {len(chunks)} chunks")

    # ── Dense search ─────────────────────────────────────────────────────

    def dense_search(
        self,
        query: str,
        game_name: str,
        top_k: int = 10,
        max_chars: int | None = MAX_CONTENT_CHARS,
    ) -> list[ChunkResult]:
        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"game_name": game_name},
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
            ))
        return chunk_results

    # ── BM25 search ──────────────────────────────────────────────────────

    def bm25_search(
        self,
        query: str,
        game_name: str,
        top_k: int = 10,
        max_chars: int | None = MAX_CONTENT_CHARS,
    ) -> list[ChunkResult]:
        if game_name not in self._bm25_indexes:
            return []

        query_tokens = tokenize(query)
        scores = self._bm25_indexes[game_name].get_scores(query_tokens)
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        chunks = self._bm25_chunks[game_name]
        chunk_results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            chunk = chunks[idx]
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
            ))
        return chunk_results


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    idx = ChunkIndex(project_root)

    for q in ["roll a 7", "longest road", "Distance Rule"]:
        dense = idx.dense_search(q, "catan", top_k=3)
        sparse = idx.bm25_search(q, "catan", top_k=3)
        print(f"\nQuery: {q}")
        print(f"  Dense:  {[r.chunk_id for r in dense]}")
        print(f"  BM25:   {[r.chunk_id for r in sparse]}")
