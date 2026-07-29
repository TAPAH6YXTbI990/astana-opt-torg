from __future__ import annotations

import json
import logging

import redis

from .config import REDIS_URL, HISTORY_TTL, HISTORY_LIMIT

logger = logging.getLogger(__name__)


class DialogHistory:
    def __init__(self, redis_url: str = REDIS_URL) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._prefix = "bitrix:dialog:"

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def save_message(self, session_id: str, role: str, content: str) -> None:
        key = self._key(session_id)
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        self._redis.rpush(key, message)
        self._redis.expire(key, HISTORY_TTL)

    def get_history(self, session_id: str, limit: int = HISTORY_LIMIT) -> list[dict]:
        key = self._key(session_id)
        messages = self._redis.lrange(key, -limit, -1)
        return [json.loads(m) for m in messages]

    def clear_history(self, session_id: str) -> None:
        key = self._key(session_id)
        self._redis.delete(key)
