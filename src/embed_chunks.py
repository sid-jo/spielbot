import argparse
import json
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from bgg_config import GAMES

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5" # 384 dim
COLLECTION_PREFIX = "spielbot"
RULEBOOK_COLLECTION = f"{COLLECTION_PREFIX}_rulebook"
FORUM_COLLECTION = f"{COLLECTION_PREFIX}_forum"
BATCH_SIZE = 64 # chunks per embedding batch


def load_chunks(chunks_dir: Path, game_name: str | None = None) -> list[dict]:
    """Load all chunk dicts from JSON files in chunks_dir."""
    if game_name:
        patterns = [
            f"{game_name}_rulebook_chunks.json",
            f"{game_name}_forum_chunks.json",
            f"{game_name}_card_chunks.json",
        ]
        files = [chunks_dir / p for p in patterns if (chunks_dir / p).exists()]
    else:
        files = sorted(chunks_dir.glob("*_chunks.json"))

    all_chunks = []
    rulebook_count = 0
    forum_count = 0
    card_count = 0

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        chunks = data["chunks"]
        for c in chunks:
            st = c["source_type"]
            if st == "rulebook":
                rulebook_count += 1
            elif st == "forum":
                forum_count += 1
            elif st == "card":
                card_count += 1
        all_chunks.extend(chunks)

    game_label = game_name if game_name else "all games"
    print(
        f"Loaded {len(all_chunks)} chunks ({rulebook_count} rulebook, "
        f"{forum_count} forum, {card_count} card) for {game_label}"
    )
    return all_chunks


def get_embed_text(chunk: dict) -> str:
    """Return the text that should be embedded for a given chunk."""
    if chunk["source_type"] in ("forum", "card"):
        return chunk["embed_text"]
    # Prepend section title to content for embedding
    title = chunk.get("section_title", "")
    content = chunk["content"]
    if title:
        return f"{title}\n\n{content}"
    return content


def build_metadata(chunk: dict) -> dict:
    """Extract metadata fields to store alongside the embedding in ChromaDB."""
    meta = {
        "chunk_id": chunk["chunk_id"],
        "source_type": chunk["source_type"],
        "game_name": chunk["game_name"],
        "section_title": chunk.get("section_title", ""),
        "source_tier": chunk.get("source_tier", ""),
        "retrieval_priority": chunk["retrieval_priority"],
        "page_start": chunk.get("page_start", -1),
        "page_end": chunk.get("page_end", -1),
    }

    if chunk["source_type"] == "forum":
        meta["thread_id"] = chunk.get("thread_id", "")
        meta["thread_subject"] = chunk.get("thread_subject", "")
        meta["resolution_status"] = chunk.get("resolution_status", "")
        meta["confidence"] = chunk.get("confidence", "")

    if chunk["source_type"] == "card":
        cd = chunk.get("card_deck", "")
        meta["card_deck"] = ", ".join(cd) if isinstance(cd, list) else str(cd)
        meta["card_suit"] = chunk.get("card_suit", "")
        meta["card_box"] = chunk.get("card_box", "")
        meta["card_cost"] = chunk.get("card_cost", "")
        meta["card_quantity"] = int(chunk.get("card_quantity", 0))
        if "game_id" in chunk:
            meta["game_id"] = int(chunk["game_id"])

    return meta


def embed_and_store(chunks: list[dict], collection) -> int:
    """Embed chunks and upsert them into a ChromaDB collection."""
    ids = [c["chunk_id"] for c in chunks]
    documents = [get_embed_text(c) for c in chunks]
    metadatas = []
    for c in chunks:
        meta = build_metadata(c)
        meta["content"] = c["content"]
        metadatas.append(meta)

    for i in range(0, len(ids), BATCH_SIZE):
        batch_end = min(i + BATCH_SIZE, len(ids))
        collection.upsert(
            ids=ids[i:batch_end],
            documents=documents[i:batch_end],
            metadatas=metadatas[i:batch_end],
        )

    return len(ids)


def main():
    parser = argparse.ArgumentParser(
        description="Embed chunk JSONs into a ChromaDB vector store."
    )
    parser.add_argument('--game', type=str, default=None,
                        help=f"Game to embed. Options: {', '.join(GAMES.keys())}")
    parser.add_argument('--dry-run', action='store_true',
                        help="Print chunk counts without embedding")
    parser.add_argument('--reset', action='store_true',
                        help="Delete existing collection before embedding")
    args = parser.parse_args()

    if args.game and args.game not in GAMES:
        parser.error(
            f"Unknown game '{args.game}'. Valid options: {', '.join(GAMES.keys())}"
        )

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    chunks_dir = project_root / "data" / "chunks"
    vectorstore_dir = project_root / "data" / "vectorstore"

    chunks = load_chunks(chunks_dir, args.game)

    if args.dry_run:
        counts: dict[str, dict[str, int]] = {}
        for c in chunks:
            game = c["game_name"]
            stype = c["source_type"]
            counts.setdefault(game, {"rulebook": 0, "forum": 0, "card": 0})
            if stype in counts[game]:
                counts[game][stype] += 1
        for game, type_counts in sorted(counts.items()):
            print(
                f"  {game}: {type_counts['rulebook']} rulebook, "
                f"{type_counts['forum']} forum, {type_counts['card']} card"
            )
        return

    client = chromadb.PersistentClient(path=str(vectorstore_dir))

    embed_fn = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        normalize_embeddings=True,
    )

    # Cards share the rulebook Chroma collection (official rules text).
    rulebook_chunks = [
        c for c in chunks if c["source_type"] in ("rulebook", "card")
    ]
    forum_chunks = [c for c in chunks if c["source_type"] == "forum"]

    for col_name, col_chunks in [
        (RULEBOOK_COLLECTION, rulebook_chunks),
        (FORUM_COLLECTION, forum_chunks),
    ]:
        if args.reset:
            try:
                client.delete_collection(col_name)
                print(f"Deleted existing collection '{col_name}'")
            except (ValueError, chromadb.errors.NotFoundError):
                pass

        collection = client.get_or_create_collection(
            name=col_name,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        count = embed_and_store(col_chunks, collection)
        print(f"Embedded {count} chunks into '{col_name}'")

    print(f"Vector store path: {vectorstore_dir}")


if __name__ == "__main__":
    main()
