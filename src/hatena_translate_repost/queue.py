from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from hatena_translate_repost.models import QueuedEntry

_INTERNAL_KEYS = {"queued_at"}


class EntryQueue:
    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, entry: QueuedEntry, *, overwrite: bool = False) -> bool:
        """Add entry to queue. Returns False (no-op) if already queued and overwrite=False."""
        entries = self._load()
        idx = next((i for i, e in enumerate(entries) if e["source_key"] == entry.source_key), None)
        record = {**asdict(entry), "queued_at": datetime.now(timezone.utc).isoformat()}
        if idx is not None:
            if not overwrite:
                return False
            entries[idx] = record
        else:
            entries.append(record)
        self._save(entries)
        return True

    def has(self, source_key: str) -> bool:
        return any(e["source_key"] == source_key for e in self._load())

    def peek(self, n: int) -> list[QueuedEntry]:
        """Return up to n entries from the front without removing them."""
        return [_to_entry(e) for e in self._load()[:n]]

    def remove(self, source_key: str) -> bool:
        entries = self._load()
        new_entries = [e for e in entries if e["source_key"] != source_key]
        if len(new_entries) == len(entries):
            return False
        self._save(new_entries)
        return True

    def count(self) -> int:
        return len(self._load())

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, entries: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _to_entry(record: dict) -> QueuedEntry:
    return QueuedEntry(**{k: v for k, v in record.items() if k not in _INTERNAL_KEYS})
