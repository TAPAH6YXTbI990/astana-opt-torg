"""Shared data structures for knowledge base indexing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Segment:
    """One chunk of text ready for indexing."""

    id: int
    text: str
    source: str  # filename or "catalog"
    start_token: int
    end_token: int
