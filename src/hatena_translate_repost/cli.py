from __future__ import annotations

from pathlib import Path

import httpx
import typer

from hatena_translate_repost.config import Settings
from hatena_translate_repost.workflow import CategoryMode, publish_entry

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def publish(
    source: str = typer.Argument(..., help="Source entry ID, Atom member URL, or public article URL."),
    env_file: Path = typer.Option(Path(".env"), help="Path to the .env file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Translate and display the result without posting."),
    allow_repost: bool = typer.Option(False, "--allow-repost", help="Allow reposting the same source entry again."),
    max_search_pages: int = typer.Option(20, min=1, help="Maximum Atom entry pages to scan when a public URL is provided."),
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
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

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
    max_search_pages: int = typer.Option(20, min=1, help="Maximum Atom entry pages to scan when a public URL is provided."),
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