from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BlogEntry:
    entry_id: str
    title: str
    content: str
    content_type: str
    categories: list[str] = field(default_factory=list)
    edit_url: str | None = None
    alternate_url: str | None = None
    draft: bool = False
    published: str | None = None  # ISO 8601 (e.g. "2023-10-13T11:33:16+09:00")


@dataclass(slots=True)
class TranslationResult:
    title: str
    body: str


@dataclass(slots=True)
class PublishResult:
    source_entry: BlogEntry
    translated: TranslationResult
    published_entry: BlogEntry | None
    dry_run: bool