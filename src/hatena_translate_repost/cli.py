from __future__ import annotations

from pathlib import Path

import httpx
import typer

from hatena_translate_repost.config import Settings
from hatena_translate_repost.workflow import (
    CategoryMode,
    build_source_index,
    publish_entry,
    queue_count,
    translate_to_queue,
    upload_from_queue,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def publish(
    source: str = typer.Argument(..., help="Source entry ID, Atom member URL, or public article URL."),
    env_file: Path = typer.Option(Path(".env"), help="Path to the .env file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Translate and display the result without posting."),
    allow_repost: bool = typer.Option(False, "--allow-repost", help="Allow reposting the same source entry again."),
    max_search_pages: int = typer.Option(500, min=1, help="Maximum Atom entry pages to scan when a public URL is provided."),
    category_mode: CategoryMode = typer.Option(CategoryMode.COPY, help="Whether to copy source categories to the target entry."),
) -> None:
    settings = _load_settings(env_file)

    try:
        result = publish_entry(
            settings,
            source,
            dry_run=dry_run,
            allow_repost=allow_repost,
            max_search_pages=max_search_pages,
            category_mode=category_mode,
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        _handle_error(exc)

    if result.dry_run:
        _print_preview(result.translated.title, result.translated.body)
        return

    typer.secho("Published translated entry.", fg=typer.colors.GREEN)
    typer.echo(f"Source title: {result.source_entry.title}")
    typer.echo(f"Translated title: {result.translated.title}")
    if result.published_entry and result.published_entry.alternate_url:
        typer.echo(f"Published URL: {result.published_entry.alternate_url}")
    if result.published_entry and result.published_entry.edit_url:
        typer.echo(f"Edit URL: {result.published_entry.edit_url}")


@app.command()
def preview(
    source: str = typer.Argument(..., help="Source entry ID, Atom member URL, or public article URL."),
    env_file: Path = typer.Option(Path(".env"), help="Path to the .env file."),
    max_search_pages: int = typer.Option(500, min=1, help="Maximum Atom entry pages to scan when a public URL is provided."),
    category_mode: CategoryMode = typer.Option(CategoryMode.COPY, help="Whether to copy source categories to the target entry."),
) -> None:
    publish(
        source=source,
        env_file=env_file,
        dry_run=True,
        allow_repost=False,
        max_search_pages=max_search_pages,
        category_mode=category_mode,
    )


@app.command()
def translate(
    source: str = typer.Argument(..., help="Source entry ID, Atom member URL, or public article URL."),
    env_file: Path = typer.Option(Path(".env"), help="Path to the .env file."),
    allow_requeue: bool = typer.Option(False, "--allow-requeue", help="Re-translate even if already queued or published."),
    max_search_pages: int = typer.Option(500, min=1, help="Maximum Atom entry pages to scan when a public URL is provided."),
    category_mode: CategoryMode = typer.Option(CategoryMode.COPY, help="Whether to copy source categories to the target entry."),
) -> None:
    """Translate a source entry and add it to the local queue without posting to Hatena."""
    settings = _load_settings(env_file)

    try:
        result = translate_to_queue(
            settings,
            source,
            allow_requeue=allow_requeue,
            max_search_pages=max_search_pages,
            category_mode=category_mode,
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        _handle_error(exc)

    if result.skipped:
        typer.secho(f"Skipped ({result.skip_reason}): {result.source_entry.title}", fg=typer.colors.YELLOW)
        return

    typer.secho(f"Queued: {result.translated.title}", fg=typer.colors.GREEN)


@app.command()
def upload(
    env_file: Path = typer.Option(Path(".env"), help="Path to the .env file."),
    limit: int = typer.Option(100, min=1, help="Maximum number of entries to upload from the queue."),
) -> None:
    """Upload queued translated entries to Hatena blog."""
    settings = _load_settings(env_file)

    def on_upload(entry, n: int) -> None:
        typer.echo(f"[{n}] Uploading: {entry.translated_title} ...")

    try:
        results = upload_from_queue(settings, limit=limit, on_upload=on_upload)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        _handle_error(exc)

    if not results:
        typer.secho("Queue is empty.", fg=typer.colors.YELLOW)
        return

    typer.echo()
    for result in results:
        typer.secho(f"Published: {result.queued_entry.translated_title}", fg=typer.colors.GREEN)
        if result.published_entry.alternate_url:
            typer.echo(f"  {result.published_entry.alternate_url}")

    remaining = queue_count(settings)
    typer.secho(f"\nUploaded {len(results)} entries. Queue remaining: {remaining}", fg=typer.colors.GREEN)


@app.command()
def index(
    env_file: Path = typer.Option(Path(".env"), help="Path to the .env file."),
) -> None:
    """Scan all source blog entries and build a local URL-to-entry-ID index."""
    settings = _load_settings(env_file)

    def on_page(page: int, total: int) -> None:
        typer.echo(f"\rScanning... page {page} ({total} entries found)", nl=False)

    try:
        count = build_source_index(settings, on_page=on_page)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        typer.echo()
        _handle_error(exc)

    typer.echo()
    typer.secho(f"Indexed {count} entries.", fg=typer.colors.GREEN)


@app.command(name="queue-status")
def queue_status(
    env_file: Path = typer.Option(Path(".env"), help="Path to the .env file."),
) -> None:
    """Show how many translated entries are waiting in the local queue."""
    settings = _load_settings(env_file)
    count = queue_count(settings)
    typer.echo(f"Queue: {count} entries pending upload.")


def _handle_error(exc: Exception) -> None:
    typer.secho(str(exc), fg=typer.colors.RED, err=True)
    if isinstance(exc, httpx.HTTPStatusError):
        typer.secho(f"Response body: {exc.response.text}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1) from exc


def _load_settings(env_file: Path) -> Settings:
    try:
        env_path = env_file if env_file.exists() else None
        return Settings.load(env_path)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


def _print_preview(title: str, body: str) -> None:
    typer.secho("Preview mode: no post was created.", fg=typer.colors.YELLOW)
    typer.echo("\n=== Translated Title ===\n")
    typer.echo(title)
    typer.echo("\n=== Translated Markdown ===\n")
    typer.echo(body)


def main() -> None:
    app()