from __future__ import annotations

import os
from pathlib import Path


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "openai/gpt-4o-mini")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
HISTORY_TTL = int(os.getenv("HISTORY_TTL", "86400"))
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "10"))
PROFILE_TTL = int(os.getenv("PROFILE_TTL", "604800"))  # 7 days

# RAG settings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
TOP_K = int(os.getenv("TOP_K", "10"))
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "knowledge"))
INDEX_DIR = Path(os.getenv("INDEX_DIR", "knowledge_index"))
CHUNK_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "512"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "50"))
