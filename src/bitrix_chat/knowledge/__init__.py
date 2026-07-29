"""Bitrix chat knowledge base — catalog extraction, re-crawl, indexing, and RAG retrieval."""

from .retriever import HybridRetriever, get_retriever

__all__ = ["HybridRetriever", "get_retriever"]
