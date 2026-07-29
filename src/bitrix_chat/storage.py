from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Deque, Protocol

import redis


class DedupStore(Protocol):
    def seen(self, key: str) -> bool: ...
    def add(self, key: str) -> None: ...


@dataclass
class InMemoryDedupStore:
    max_items: int = 10_000
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _items: set[str] = field(default_factory=set, init=False, repr=False)
    _order: Deque[str] = field(default_factory=deque, init=False, repr=False)

    def seen(self, key: str) -> bool:
        with self._lock:
            return key in self._items

    def add(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                return
            self._items.add(key)
            self._order.append(key)
            while len(self._order) > self.max_items:
                old_key = self._order.popleft()
                self._items.discard(old_key)


class RedisDedupStore:
    def __init__(self, redis_url: str, ttl: int = 86400) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._redis.ping()
        self._prefix = "bitrix:dedup:"
        self._ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def seen(self, key: str) -> bool:
        return self._redis.exists(self._key(key)) > 0

    def add(self, key: str) -> None:
        self._redis.setex(self._key(key), self._ttl, "1")
