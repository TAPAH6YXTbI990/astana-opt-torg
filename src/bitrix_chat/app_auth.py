from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(slots=True)
class AppAuth:
    access_token: str
    refresh_token: str
    client_endpoint: str
    server_endpoint: str
    domain: str
    member_id: str
    application_token: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppAuth":
        return cls(
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            client_endpoint=str(data.get("client_endpoint", "")),
            server_endpoint=str(data.get("server_endpoint", "")),
            domain=str(data.get("domain", "")),
            member_id=str(data.get("member_id", "")),
            application_token=str(data.get("application_token", "")),
        )


class AppAuthStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = Lock()

    def load(self) -> AppAuth | None:
        with self._lock:
            if not self._path.exists():
                return None
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return AppAuth.from_mapping(data)

    def save(self, auth: AppAuth) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(asdict(auth), ensure_ascii=False, indent=2), encoding="utf-8")

