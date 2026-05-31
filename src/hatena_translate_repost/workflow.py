from __future__ import annotations

from enum import StrEnum

from hatena_translate_repost.config import Settings
from hatena_translate_repost.translator import Translator
from hatena_translate_repost.hatena import HatenaBlogClient
from hatena_translate_repost.models import BlogEntry, PublishResult
from hatena_translate_repost.state import PublishState


class CategoryMode(StrEnum):
    COPY = "copy"
    SKIP = "skip"


def publish_entry(
    settings: Settings,
    source: str,
    *,
    dry_run: bool,
    allow_repost: bool,
    max_search_pages: int,
    category_mode: CategoryMode,
) -> PublishResult:
    state = PublishState(settings.state_path)

    with HatenaBlogClient(
        settings.source_hatena_id,
        settings.source_blog_id,
        settings.source_api_key,
        settings.request_timeout_seconds,
    ) as source_client:
        source_entry = _resolve_source_entry(source_client, source, max_search_pages)

    _ensure_markdown(source_entry)
    source_key = _source_key(source_entry)

    existing = state.get(source_key)
    if existing and not allow_repost:
        raise ValueError(
            "This source entry has already been reposted. "
            "Use --allow-repost if you intentionally want to post it again."
        )

    with Translator(
        settings.lm_studio_base_url,
        settings.lm_studio_model,
        settings.request_timeout_seconds,
    ) as translator:
        translated = translator.translate(source_entry.title, source_entry.content)

    categories = source_entry.categories if category_mode == CategoryMode.COPY else []
    target_entry = BlogEntry(
        entry_id="",
        title=translated.title,
        content=translated.body,
        content_type="text/x-markdown",
        categories=categories,
        published=source_entry.published,
    )

    if dry_run:
        return PublishResult(
            source_entry=source_entry,
            translated=translated,
            published_entry=None,
            dry_run=True,
        )

    with HatenaBlogClient(
        settings.target_hatena_id,
        settings.target_blog_id,
        settings.target_api_key,
        settings.request_timeout_seconds,
    ) as target_client:
        published_entry = target_client.create_entry(target_entry, draft=False)

    state.record(
        source_key,
        {
            "source_title": source_entry.title,
            "source_alternate_url": source_entry.alternate_url or "",
            "target_title": published_entry.title,
            "target_alternate_url": published_entry.alternate_url or "",
            "target_edit_url": published_entry.edit_url or "",
        },
    )

    return PublishResult(
        source_entry=source_entry,
        translated=translated,
        published_entry=published_entry,
        dry_run=False,
    )


def _resolve_source_entry(client: HatenaBlogClient, source: str, max_search_pages: int) -> BlogEntry:
    if source.startswith("http://") or source.startswith("https://"):
        if "/atom/entry/" in source:
            return client.get_entry(source.rstrip("/").split("/")[-1])
        # HTMLからエントリーIDを直接取得（全ページスキャン不要）
        entry_id = client.fetch_entry_id_from_public_url(source)
        if entry_id:
            return client.get_entry(entry_id)
        # フォールバック: ページスキャン
        matched = client.find_entry_by_url(source, max_pages=max_search_pages)
        if matched is None:
            raise ValueError("Could not find the source entry from the provided URL")
        return client.get_entry(matched.entry_id)

    return client.get_entry(source)


def _ensure_markdown(entry: BlogEntry) -> None:
    allowed_types = {"text/x-markdown", "text/markdown"}
    if entry.content_type not in allowed_types:
        raise ValueError(
            f"Only Markdown entries are supported, but the source content type was {entry.content_type}"
        )


def _source_key(entry: BlogEntry) -> str:
    if entry.edit_url:
        return entry.edit_url
    if entry.alternate_url:
        return entry.alternate_url
    return entry.entry_id