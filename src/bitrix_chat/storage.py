from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Deque


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

