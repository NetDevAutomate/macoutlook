"""Command-line interface for macoutlook library."""

import json
import logging
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import click

from ..core.client import create_client
from ..exceptions import OutlookDBError

logger = logging.getLogger(__name__)


def format_output(data: Sequence[Any], output_format: str) -> str:
    """Format data for output in specified format."""
    if output_format == "json":
        items = []
        for item in data:
            if hasattr(item, "model_dump"):
                items.append(item.model_dump())
            elif isinstance(item, dict):
                items.append(item)
            else:
                items.append(str(item))
        return json.dumps(items, indent=2, default=str)

    elif output_format == "table":
        if data and hasattr(data[0], "model_dump"):
            result = []
            for i, item in enumerate(data):
                result.append(f"--- Item {i + 1} ---")
                for key, value in item.model_dump().items():
                    result.append(f"{key}: {value}")
            return "\n".join(result)
        return str(data)

    return str(data)


@click.group()
@click.option("--db-path", help="Path to Outlook database file")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx: click.Context, db_path: str | None, verbose: bool) -> None:
    """macoutlook: Access Microsoft Outlook data on macOS."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["verbose"] = verbose

    if verbose:
        logging.basicConfig(level=logging.DEBUG)


@cli.command()
@click.option("--start-date", type=click.DateTime(), help="Start date (YYYY-MM-DD)")
@click.option("--end-date", type=click.DateTime(), help="End date (YYYY-MM-DD)")
@click.option("--limit", default=100, help="Maximum number of emails")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
@click.pass_context
def emails(
    ctx: click.Context,
    start_date: datetime | None,
    end_date: datetime | None,
    limit: int,
    output_format: str,
) -> None:
    """Get emails by date range."""
    try:
        if not start_date:
            start_date = datetime.now() - timedelta(days=7)
        if not end_date:
            end_date = datetime.now()

        client = create_client(db_path=ctx.obj["db_path"])
        emails_list = client.get_emails(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        if not emails_list:
            click.echo("No emails found for the specified criteria.")
            return

        click.echo(format_output(emails_list, output_format))

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="table",
)
@click.pass_context
def calendars(ctx: click.Context, output_format: str) -> None:
    """List all available calendars."""
    try:
        client = create_client(db_path=ctx.obj["db_path"])
        calendars_list = client.get_calendars()

        if not calendars_list:
            click.echo("No calendars found.")
            return

        click.echo(format_output(calendars_list, output_format))

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--calendar-id", help="Calendar ID to filter by")
@click.option("--start-date", type=click.DateTime(), help="Start date (YYYY-MM-DD)")
@click.option("--end-date", type=click.DateTime(), help="End date (YYYY-MM-DD)")
@click.option("--limit", default=100, help="Maximum number of events")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="table",
)
@click.pass_context
def events(
    ctx: click.Context,
    calendar_id: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    limit: int,
    output_format: str,
) -> None:
    """Get calendar events."""
    try:
        if not start_date:
            start_date = datetime.now()
        if not end_date:
            end_date = datetime.now() + timedelta(days=30)

        client = create_client(db_path=ctx.obj["db_path"])
        events_list = client.get_calendar_events(
            calendar_id=calendar_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        if not events_list:
            click.echo("No events found for the specified criteria.")
            return

        click.echo(format_output(events_list, output_format))

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--query", required=True, help="Search query text")
@click.option("--sender", help="Filter by sender")
@click.option("--fuzzy", is_flag=True, help="Enable fuzzy sender matching")
@click.option("--start-date", type=click.DateTime(), help="Start date")
@click.option("--end-date", type=click.DateTime(), help="End date")
@click.option("--limit", default=50, help="Maximum results")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="table",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    sender: str | None,
    fuzzy: bool,
    start_date: datetime | None,
    end_date: datetime | None,
    limit: int,
    output_format: str,
) -> None:
    """Search emails."""
    try:
        client = create_client(db_path=ctx.obj["db_path"])
        results = client.search_emails(
            query=query,
            sender=sender,
            fuzzy=fuzzy,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        if not results:
            click.echo(f"No results found for query: {query}")
            return

        click.echo(format_output(results, output_format))

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Show information about the Outlook database."""
    try:
        client = create_client(db_path=ctx.obj["db_path"])
        db_info = client.get_database_info()

        click.echo("Outlook Database Information:")
        click.echo(f"  Path: {db_info['db_path']}")
        click.echo(f"  Tables: {', '.join(db_info.get('tables', []))}")  # type: ignore[arg-type]

        if "mail_count" in db_info:
            click.echo(f"  Total emails: {db_info['mail_count']:,}")
        if "calendarevents_count" in db_info:
            click.echo(f"  Total events: {db_info['calendarevents_count']:,}")

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("build-index")
@click.option("--force", is_flag=True, help="Force full rebuild, ignoring cache")
@click.pass_context
def build_index(ctx: click.Context, force: bool) -> None:
    """Build the .olk15MsgSource file index for full email content.

    This scans all message source files and extracts Message-IDs.
    The index is cached to disk so subsequent operations are instant.
    First build may take ~10 minutes for large mailboxes due to macOS
    file access latency.
    """
    from ..core.message_source import MessageSourceReader

    reader = MessageSourceReader()
    click.echo(f"Sources: {reader.sources_dir}")

    if not reader.sources_dir.exists():
        click.echo("Error: Message Sources directory not found.", err=True)
        sys.exit(1)

    def progress(current: int, total: int) -> None:
        pct = current / total * 100 if total else 0
        click.echo(f"  Indexed {current:,}/{total:,} files ({pct:.0f}%)", nl=True)

    import time

    start = time.time()
    count = reader.build_index(force=force, progress_callback=progress)
    elapsed = time.time() - start

    if elapsed < 1:
        click.echo(f"Loaded {count:,} entries from cache.")
    else:
        click.echo(f"Indexed {count:,} message sources in {elapsed:.0f}s.")


if __name__ == "__main__":
    cli()
