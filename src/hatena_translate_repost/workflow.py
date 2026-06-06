from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from hatena_translate_repost.config import Settings
from hatena_translate_repost.index import EntryIndex
from hatena_translate_repost.translator import Translator
from hatena_translate_repost.hatena import HatenaBlogClient
from hatena_translate_repost.models import BlogEntry, PublishResult, QueuedEntry, TranslationResult
from hatena_translate_repost.queue import EntryQueue
from hatena_translate_repost.state import PublishState


def _source_index(settings: Settings) -> EntryIndex:
    return EntryIndex(settings.state_path.parent / "source-index.json")


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
    _require_source_credentials(settings)
    state = PublishState(settings.state_path)

    with HatenaBlogClient(
        settings.source_hatena_id,
        settings.source_blog_id,
        settings.source_api_key,
        settings.request_timeout_seconds,
    ) as source_client:
        source_entry = _resolve_source_entry(source_client, source, max_search_pages, _source_index(settings))

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


def _resolve_source_entry(
    client: HatenaBlogClient,
    source: str,
    max_search_pages: int,
    index: EntryIndex | None = None,
) -> BlogEntry:
    if source.startswith("http://") or source.startswith("https://"):
        if "/atom/entry/" in source:
            return client.get_entry(source.rstrip("/").split("/")[-1])
        # ローカルインデックスを最優先（HTTP不要）
        if index is not None:
            entry_id = index.get(source)
            if entry_id:
                return client.get_entry(entry_id)
        # HTMLパース（1リクエスト）
        entry_id = client.fetch_entry_id_from_public_url(source)
        if entry_id:
            return client.get_entry(entry_id)
        # フォールバック: ページスキャン
        matched = client.find_entry_by_url(source, max_pages=max_search_pages)
        if matched is None:
            raise ValueError("Could not find the source entry from the provided URL")
        return client.get_entry(matched.entry_id)

    return client.get_entry(source)


def build_source_index(
    settings: Settings,
    on_page: Callable[[int, int], None] | None = None,
) -> int:
    """Scan all source blog entries and write a local URL→entry_id index."""
    _require_source_credentials(settings)
    all_entries: list[BlogEntry] = []

    with HatenaBlogClient(
        settings.source_hatena_id,
        settings.source_blog_id,
        settings.source_api_key,
        settings.request_timeout_seconds,
    ) as client:
        page_url: str | None = None
        page_num = 0
        done = False
        while not done:
            entries, page_url = client.list_entries(page_url)
            for e in entries:
                if _entry_year(e) < _INDEX_SINCE_YEAR:
                    done = True
                    break
                all_entries.append(e)
            page_num += 1
            if on_page:
                on_page(page_num, len(all_entries))
            if page_url is None:
                break

    _source_index(settings).build(all_entries)
    return len(all_entries)


_INDEX_SINCE_YEAR = 2023


def _entry_year(entry: BlogEntry) -> int:
    if entry.published and len(entry.published) >= 4:
        try:
            return int(entry.published[:4])
        except ValueError:
            pass
    return 9999


def _ensure_markdown(entry: BlogEntry) -> None:
    allowed_types = {"text/x-markdown", "text/markdown"}
    if entry.content_type not in allowed_types:
        raise ValueError(
            f"Only Markdown entries are supported, but the source content type was {entry.content_type}"
        )


@dataclass(slots=True)
class TranslateResult:
    source_entry: BlogEntry
    translated: TranslationResult | None
    skipped: bool
    skip_reason: str  # "published" | "queued" | ""


@dataclass(slots=True)
class UploadResult:
    queued_entry: QueuedEntry
    published_entry: BlogEntry


def translate_to_queue(
    settings: Settings,
    source: str,
    *,
    allow_requeue: bool,
    max_search_pages: int,
    category_mode: CategoryMode,
) -> TranslateResult:
    _require_source_credentials(settings)
    state = PublishState(settings.state_path)
    queue = EntryQueue(settings.state_path.parent / "queue.json")

    with HatenaBlogClient(
        settings.source_hatena_id,
        settings.source_blog_id,
        settings.source_api_key,
        settings.request_timeout_seconds,
    ) as source_client:
        source_entry = _resolve_source_entry(source_client, source, max_search_pages, _source_index(settings))

    _ensure_markdown(source_entry)
    source_key = _source_key(source_entry)

    if not allow_requeue:
        if state.get(source_key):
            return TranslateResult(source_entry=source_entry, translated=None, skipped=True, skip_reason="published")
        if queue.has(source_key):
            return TranslateResult(source_entry=source_entry, translated=None, skipped=True, skip_reason="queued")

    with Translator(
        settings.lm_studio_base_url,
        settings.lm_studio_model,
        settings.request_timeout_seconds,
    ) as translator:
        translated = translator.translate(source_entry.title, source_entry.content)

    categories = source_entry.categories if category_mode == CategoryMode.COPY else []
    queue.add(
        QueuedEntry(
            source_key=source_key,
            source_title=source_entry.title,
            source_alternate_url=source_entry.alternate_url or "",
            translated_title=translated.title,
            translated_body=translated.body,
            categories=categories,
            published=source_entry.published,
        ),
        overwrite=allow_requeue,
    )

    return TranslateResult(source_entry=source_entry, translated=translated, skipped=False, skip_reason="")


def upload_from_queue(
    settings: Settings,
    *,
    limit: int,
) -> list[UploadResult]:
    queue = EntryQueue(settings.state_path.parent / "queue.json")
    state = PublishState(settings.state_path)
    results: list[UploadResult] = []

    with HatenaBlogClient(
        settings.target_hatena_id,
        settings.target_blog_id,
        settings.target_api_key,
        settings.request_timeout_seconds,
    ) as target_client:
        for _ in range(limit):
            peeked = queue.peek(1)
            if not peeked:
                break
            entry = peeked[0]
            published = target_client.create_entry(
                BlogEntry(
                    entry_id="",
                    title=entry.translated_title,
                    content=entry.translated_body,
                    content_type="text/x-markdown",
                    categories=entry.categories,
                    published=entry.published,
                ),
                draft=False,
            )
            state.record(
                entry.source_key,
                {
                    "source_title": entry.source_title,
                    "source_alternate_url": entry.source_alternate_url,
                    "target_title": published.title,
                    "target_alternate_url": published.alternate_url or "",
                    "target_edit_url": published.edit_url or "",
                },
            )
            queue.remove(entry.source_key)
            results.append(UploadResult(queued_entry=entry, published_entry=published))

    return results


def queue_count(settings: Settings) -> int:
    return EntryQueue(settings.state_path.parent / "queue.json").count()


def _require_source_credentials(settings: Settings) -> None:
    if not settings.source_hatena_id or not settings.source_blog_id or not settings.source_api_key:
        raise ValueError(
            "SOURCE_HATENA_ID, SOURCE_BLOG_ID, and SOURCE_API_KEY are required for this operation."
        )


def _source_key(entry: BlogEntry) -> str:
    if entry.edit_url:
        return entry.edit_url
    if entry.alternate_url:
        return entry.alternate_url
    return entry.entry_id