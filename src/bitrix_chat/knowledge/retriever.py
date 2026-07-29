"""Hybrid retriever: FAISS vector search + BM25 keyword search.

Loads pre-built indexes from INDEX_DIR and provides a retrieve() function
that merges results from both methods using Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np
import tiktoken

from ..agent.config import (
    EMBEDDING_MODEL,
    INDEX_DIR,
    KNOWLEDGE_DIR,
    OPENROUTER_API_KEY,
    TOP_K,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """One retrieved segment with score."""

    text: str
    source: str
    score: float
    rank: int


class HybridRetriever:
    """FAISS + BM25 hybrid retriever with RRF fusion."""

    def __init__(self) -> None:
        self._loaded = False
        self._faiss_index: faiss.Index | None = None
        self._segments: list = []
        self._bm25 = None
        self._enc: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")
        self._dim: int = 0

    def _load(self) -> None:
        if self._loaded:
            return

        faiss_path = INDEX_DIR / "faiss.index"
        meta_path = INDEX_DIR / "segments.pkl"
        bm25_path = INDEX_DIR / "bm25.pkl"

        if not faiss_path.exists():
            logger.warning(
                "FAISS index not found at %s — retrieval disabled", faiss_path
            )
            return

        self._faiss_index = faiss.read_index(str(faiss_path))
        self._dim = self._faiss_index.d

        with open(meta_path, "rb") as f:
            self._segments = pickle.load(f)

        with open(bm25_path, "rb") as f:
            self._bm25 = pickle.load(f)

        self._loaded = True
        logger.info(
            "Retriever loaded: %d vectors (dim=%d), %d segments",
            self._faiss_index.ntotal,
            self._dim,
            len(self._segments),
        )

    def is_available(self) -> bool:
        self._load()
        return self._faiss_index is not None and len(self._segments) > 0

    def _embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string via OpenRouter."""
        import httpx

        from ..agent.config import OPENROUTER_API_KEY

        resp = httpx.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": EMBEDDING_MODEL, "input": query},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return np.array(data["data"][0]["embedding"], dtype=np.float32)

    def _rrf_score(self, rank: int, k: int = 60) -> float:
        """Reciprocal Rank Fusion score."""
        return 1.0 / (k + rank)

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Retrieve top-k segments using hybrid FAISS + BM25 with RRF."""
        self._load()

        if not self._loaded:
            return []

        k = top_k or TOP_K

        # --- FAISS search ---
        faiss_scores: dict[int, float] = {}
        try:
            query_vec = self._embed_query(query).reshape(1, -1)
            distances, indices = self._faiss_index.search(
                query_vec, min(k * 2, len(self._segments))
            )
            for rank, (idx, dist) in enumerate(zip(indices[0], distances[0])):
                if idx < 0:
                    continue
                faiss_scores[int(idx)] = self._rrf_score(rank)
        except Exception:
            logger.exception("FAISS search failed")

        # --- BM25 search ---
        bm25_scores: dict[int, float] = {}
        if self._bm25 is not None:
            tokenized_query = [self._enc.decode([t]) for t in self._enc.encode(query)]
            scores = self._bm25.get_scores(tokenized_query)
            top_indices = np.argsort(scores)[::-1][: k * 2]
            for rank, idx in enumerate(top_indices):
                bm25_scores[int(idx)] = self._rrf_score(rank)

        # --- Merge with RRF ---
        all_indices = set(faiss_scores.keys()) | set(bm25_scores.keys())
        merged: list[tuple[int, float]] = []
        for idx in all_indices:
            combined = faiss_scores.get(idx, 0.0) + bm25_scores.get(idx, 0.0)
            merged.append((idx, combined))

        merged.sort(key=lambda x: x[1], reverse=True)
        top = merged[:k]

        results: list[RetrievalResult] = []
        for rank, (idx, score) in enumerate(top):
            seg = self._segments[idx]
            results.append(
                RetrievalResult(
                    text=seg.text,
                    source=seg.source,
                    score=score,
                    rank=rank + 1,
                )
            )

        return results


# Module-level singleton
_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
