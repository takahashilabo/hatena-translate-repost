from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


class PublishState:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, source_key: str) -> dict[str, str] | None:
        payload = self._load()
        return payload.get("entries", {}).get(source_key)

    def record(self, source_key: str, data: dict[str, str]) -> None:
        payload = self._load()
        entries = payload.setdefault("entries", {})
        entries[source_key] = {
            **data,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _load(self) -> dict[str, dict[str, dict[str, str]]]:
        if not self.path.exists():
            return {"entries": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))