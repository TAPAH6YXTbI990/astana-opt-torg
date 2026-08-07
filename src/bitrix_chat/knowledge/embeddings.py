"""Build FAISS + BM25 indexes from knowledge base.

Usage:
    python -m bitrix_chat.knowledge.embeddings [--force]

Reads knowledge/raw/*.md, knowledge/*.md, and knowledge/catalog/catalog.json,
chunks them by tokens, generates embeddings via OpenRouter, and saves
FAISS index + BM25 data + metadata to knowledge_index/.
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
from pathlib import Path

import faiss
import numpy as np
import tiktoken
from rank_bm25 import BM25Okapi

from .schema import Segment

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load .env from project root
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(_project_root / ".env")

# ---------------------------------------------------------------------------
# Config defaults (override via .env or environment)
# ---------------------------------------------------------------------------


def _env(key: str, default: str = "") -> str:
    import os

    return os.getenv(key, default)


EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "text-embedding-small")

_knowledge_raw = _env("KNOWLEDGE_DIR", "knowledge")
KNOWLEDGE_DIR = (
    Path(_knowledge_raw)
    if Path(_knowledge_raw).is_absolute()
    else _project_root / _knowledge_raw
)

_index_raw = _env("INDEX_DIR", "knowledge_index")
INDEX_DIR = (
    Path(_index_raw) if Path(_index_raw).is_absolute() else _project_root / _index_raw
)

CHUNK_MAX_TOKENS = int(_env("CHUNK_MAX_TOKENS", "512"))
CHUNK_OVERLAP_TOKENS = int(_env("CHUNK_OVERLAP_TOKENS", "50"))

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------


def _tokenize(text: str, enc: tiktoken.Encoding) -> list[str]:
    """Return token strings (for BM25)."""
    tokens = enc.encode(text)
    return [enc.decode([t]) for t in tokens]


def _chunk_text(
    text: str, source: str, enc: tiktoken.Encoding, max_tokens: int, overlap: int
) -> list[Segment]:
    """Split text into overlapping token-based chunks."""
    token_ids = enc.encode(text)
    if len(token_ids) <= max_tokens:
        return [
            Segment(
                id=0, text=text, source=source, start_token=0, end_token=len(token_ids)
            )
        ]

    chunks: list[Segment] = []
    start = 0
    chunk_idx = 0
    while start < len(token_ids):
        end = min(start + max_tokens, len(token_ids))
        chunk_token_ids = token_ids[start:end]
        chunk_text = enc.decode(chunk_token_ids)
        chunks.append(
            Segment(
                id=chunk_idx,
                text=chunk_text,
                source=source,
                start_token=start,
                end_token=end,
            )
        )
        chunk_idx += 1
        if end >= len(token_ids):
            break
        start = end - overlap
    return chunks


# ---------------------------------------------------------------------------
# Load knowledge base
# ---------------------------------------------------------------------------


def load_segments(knowledge_dir: Path, enc: tiktoken.Encoding) -> list[Segment]:
    """Load all knowledge files and return token-chunked segments."""
    segments: list[Segment] = []
    global_idx = 0

    # 1) Root .md files (about-us.md, contact-us.md, etc.)
    for md_file in sorted(knowledge_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8").strip()
        if not text:
            continue
        chunks = _chunk_text(
            text, md_file.name, enc, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS
        )
        for c in chunks:
            c.id = global_idx
            global_idx += 1
        segments.extend(chunks)
        logger.info("Loaded %s: %d chunks", md_file.name, len(chunks))

    # 2) Raw product .md files
    raw_dir = knowledge_dir / "raw"
    if raw_dir.is_dir():
        for md_file in sorted(raw_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8").strip()
            if not text:
                continue
            chunks = _chunk_text(
                text, md_file.name, enc, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS
            )
            for c in chunks:
                c.id = global_idx
                global_idx += 1
            segments.extend(chunks)
        logger.info("Loaded raw/: %d files", len(list(raw_dir.glob("*.md"))))

    # 3) catalog.json — split by product, each product is a segment
    catalog_json = knowledge_dir / "catalog" / "catalog.json"
    if catalog_json.is_file():
        products = json.loads(catalog_json.read_text(encoding="utf-8"))
        for product in products:
            # Build a readable text representation
            lines = [f"Товар: {product.get('name', 'Без названия')}"]
            if product.get("sku"):
                lines.append(f"Артикул: {product['sku']}")
            if product.get("price") is not None:
                lines.append(f"Цена: {product['price']:.0f} тенге")
            if product.get("pack_qty") and product.get("price_per_unit"):
                lines.append(
                    f"Упаковка: {product['pack_qty']} шт | {product['price_per_unit']:.0f} тенге/шт"
                )
            if product.get("stock") is not None:
                lines.append(f"Остаток: {product['stock']} шт")
            if product.get("category_path"):
                lines.append(f"Категория: {product['category_path']}")
            if product.get("url"):
                lines.append(f"Ссылка: {product['url']}")
            text = "\n".join(lines)
            segments.append(
                Segment(
                    id=global_idx,
                    text=text,
                    source="catalog",
                    start_token=0,
                    end_token=0,
                )
            )
            global_idx += 1
        logger.info("Loaded catalog.json: %d products", len(products))

    return segments


# ---------------------------------------------------------------------------
# Embedding via OpenRouter
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    key = _env("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return key


def embed_texts(texts: list[str], model: str, batch_size: int = 64) -> np.ndarray:
    """Embed texts using OpenRouter embeddings API. Returns (N, dim) array."""
    import httpx

    api_key = _get_api_key()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = httpx.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": batch},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in sorted(data["data"], key=lambda x: x["index"]):
            all_embeddings.append(item["embedding"])
        logger.info(
            "Embedded batch %d/%d",
            i // batch_size + 1,
            (len(texts) + batch_size - 1) // batch_size,
        )

    return np.array(all_embeddings, dtype=np.float32)


# ---------------------------------------------------------------------------
# Build indexes
# ---------------------------------------------------------------------------


def build_indexes(segments: list[Segment], force: bool = False) -> None:
    """Build FAISS + BM25 indexes and save to INDEX_DIR."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    index_file = INDEX_DIR / "faiss.index"
    meta_file = INDEX_DIR / "segments.pkl"
    bm25_file = INDEX_DIR / "bm25.pkl"

    if index_file.exists() and not force:
        logger.info("Index already exists at %s. Use --force to rebuild.", INDEX_DIR)
        return

    if not segments:
        logger.warning("No segments to index.")
        return

    # --- FAISS ---
    logger.info(
        "Embedding %d segments with model=%s ...", len(segments), EMBEDDING_MODEL
    )
    texts = [s.text for s in segments]
    embeddings = embed_texts(texts, EMBEDDING_MODEL)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    faiss.write_index(index, str(index_file))
    logger.info("FAISS index saved: %d vectors, dim=%d", index.ntotal, dim)

    # --- Metadata ---
    with open(meta_file, "wb") as f:
        pickle.dump(segments, f)
    logger.info("Metadata saved: %d segments", len(segments))

    # --- BM25 ---
    enc = tiktoken.get_encoding("cl100k_base")
    tokenized_corpus = [_tokenize(s.text, enc) for s in segments]
    bm25 = BM25Okapi(tokenized_corpus)
    with open(bm25_file, "wb") as f:
        pickle.dump(bm25, f)
    logger.info("BM25 index saved.")

    logger.info("Done. All indexes in %s", INDEX_DIR)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    force = "--force" in sys.argv
    enc = tiktoken.get_encoding("cl100k_base")
    segments = load_segments(KNOWLEDGE_DIR, enc)
    logger.info("Total segments: %d", len(segments))
    build_indexes(segments, force=force)


if __name__ == "__main__":
    main()
