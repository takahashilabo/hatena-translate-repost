from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hatena_translate_repost.models import BlogEntry


class EntryIndex:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, url: str) -> str | None:
        entries = self._load().get("entries", {})
        normalized = _normalize(url)
        if normalized in entries:
            return entries[normalized]
        return entries.get(_toggle_scheme(normalized))

    def build(self, all_entries: list[BlogEntry]) -> None:
        entry_map: dict[str, str] = {
            _normalize(e.alternate_url): e.entry_id
            for e in all_entries
            if e.alternate_url and e.entry_id
        }
        data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "count": len(entry_map),
            "entries": entry_map,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def count(self) -> int:
        return self._load().get("count", 0)

    def last_updated(self) -> str | None:
        return self._load().get("last_updated")

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))


def _normalize(url: str) -> str:
    return url.rstrip("/")


def _toggle_scheme(url: str) -> str:
    if url.startswith("https://"):
        return "http://" + url[8:]
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url
