from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

import redis

from .config import REDIS_URL, PROFILE_TTL

logger = logging.getLogger(__name__)

PROFILE_KEY_PREFIX = "bitrix:client_profile:"


@dataclass
class ClientProfile:
    session_id: str
    name: str | None = None
    company: str | None = None
    contact_info: str | None = None
    city: str | None = None
    country: str | None = None
    interests: list[str] = field(default_factory=list)
    volume: str | None = None
    client_type: str | None = None  # физлицо / юрлицо / ИП
    request_summary: str | None = None
    interest_level: str | None = None  # низкий / средний / высокий
    handoff_needed: bool = False
    handoff_reason: str | None = None
    extra: str | None = None
    bitrix_lead_id: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["interests"] = json.dumps(d["interests"], ensure_ascii=False)
        d["handoff_needed"] = str(d["handoff_needed"])
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> ClientProfile:
        interests_raw = data.get("interests", "[]")
        if isinstance(interests_raw, str):
            try:
                interests = json.loads(interests_raw)
            except (json.JSONDecodeError, TypeError):
                interests = []
        else:
            interests = interests_raw or []
        return cls(
            session_id=data.get("session_id", ""),
            name=data.get("name"),
            company=data.get("company"),
            contact_info=data.get("contact_info"),
            city=data.get("city"),
            country=data.get("country"),
            interests=interests,
            volume=data.get("volume"),
            client_type=data.get("client_type"),
            request_summary=data.get("request_summary"),
            interest_level=data.get("interest_level"),
            handoff_needed=data.get("handoff_needed") == "True"
            or data.get("handoff_needed") is True,
            handoff_reason=data.get("handoff_reason"),
            extra=data.get("extra"),
            bitrix_lead_id=int(data["bitrix_lead_id"])
            if data.get("bitrix_lead_id")
            else None,
        )

    def format_for_prompt(self) -> str:
        parts: list[str] = []
        if self.name:
            parts.append(f"Имя: {self.name}")
        if self.company:
            parts.append(f"Компания: {self.company}")
        if self.city or self.country:
            location = ", ".join(filter(None, [self.city, self.country]))
            parts.append(f"Местоположение: {location}")
        if self.client_type:
            parts.append(f"Тип клиента: {self.client_type}")
        if self.interests:
            parts.append(f"Интересы: {', '.join(self.interests)}")
        if self.volume:
            parts.append(f"Объём закупки: {self.volume}")
        if self.interest_level:
            parts.append(f"Целевой интерес: {self.interest_level}")
        if self.contact_info:
            parts.append(f"Контакт: {self.contact_info}")
        if self.request_summary:
            parts.append(f"Суть запроса: {self.request_summary}")
        if self.extra:
            parts.append(f"Доп. информация: {self.extra}")
        if not parts:
            return ""
        return "\n".join(parts)


class ProfileStore:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    def _key(self, session_id: str) -> str:
        return f"{PROFILE_KEY_PREFIX}{session_id}"

    def get(self, session_id: str) -> ClientProfile:
        try:
            data = self._get_redis().hgetall(self._key(session_id))
            if not data:
                return ClientProfile(session_id=session_id)
            data["session_id"] = session_id
            return ClientProfile.from_dict(data)
        except Exception:
            logger.exception("Failed to load client profile")
            return ClientProfile(session_id=session_id)

    def update(self, session_id: str, **fields) -> ClientProfile:
        try:
            r = self._get_redis()
            key = self._key(session_id)
            existing = r.hgetall(key)
            profile = ClientProfile.from_dict({**existing, "session_id": session_id})

            for k, v in fields.items():
                if v is not None and hasattr(profile, k):
                    if k == "interests" and isinstance(v, list):
                        current = profile.interests or []
                        profile.interests = list(set(current + v))
                    else:
                        setattr(profile, k, v)

            r.hset(key, mapping=profile.to_dict())
            r.expire(key, PROFILE_TTL)
            logger.info(
                "client profile updated",
                extra={"session_id": session_id, "fields": list(fields.keys())},
            )
            return profile
        except Exception:
            logger.exception("Failed to update client profile")
            return ClientProfile(session_id=session_id)

    def clear(self, session_id: str) -> None:
        try:
            self._get_redis().delete(self._key(session_id))
        except Exception:
            logger.exception("Failed to clear client profile")
