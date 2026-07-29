from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from docling.datamodel.document import DoclingDocument

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.output_dir / "manifest.json"
        self._manifest: dict[str, Any] = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "entries" in data:
                    return data
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("could not read manifest: %s", exc)
        return {"entries": []}

    def load_visited(self) -> set[str]:
        return {entry["url"] for entry in self._manifest.get("entries", [])}

    @staticmethod
    def _slug(url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_")
        path = re.sub(r"[^A-Za-z0-9_.-]", "_", path) or "home"
        if parsed.query:
            query = re.sub(r"[^A-Za-z0-9]", "_", parsed.query)[:40]
            path = f"{path}__{query}"
        return path[:120]

    def save(
        self,
        url: str,
        doc: DoclingDocument,
        *,
        title: Optional[str] = None,
        is_catalog: bool = False,
    ) -> None:
        slug = self._slug(url)
        md_path = self.output_dir / f"{slug}.md"
        json_path = self.output_dir / f"{slug}.json"

        markdown = doc.export_to_markdown()
        md_path.write_text(markdown, encoding="utf-8")

        data = doc.export_to_dict()
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        resolved_title = title
        if not resolved_title and isinstance(data, dict):
            resolved_title = data.get("name")

        entry = {
            "url": url,
            "title": resolved_title,
            "file_md": md_path.name,
            "file_json": json_path.name,
            "is_catalog": is_catalog,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        }
        self._manifest.setdefault("entries", []).append(entry)
        self.manifest_path.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("saved %s -> %s", url, md_path.name)
