"""Command-line interface for pyoutlook-db library.

This module provides CLI commands for accessing Outlook data directly from
the command line with various output formats.
"""

import json
import sys
from datetime import datetime, timedelta

import click
import structlog

from ..core.client import OutlookClient
from ..core.exceptions import OutlookDBError
from ..models.email import EmailSearchFilter

# Configure logging for CLI
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


def format_output(data, output_format: str) -> str:
    """Format data for output in specified format."""
    if output_format == "json":
        if hasattr(data, "dict"):
            # Pydantic model
            return json.dumps([item.dict() for item in data], indent=2, default=str)
        elif isinstance(data, list):
            # List of dictionaries or objects
            return json.dumps([item.dict() if hasattr(item, "dict") else item for item in data], indent=2, default=str)
        else:
            return json.dumps(data, indent=2, default=str)

    elif output_format == "csv":
        # Simple CSV output - would need pandas for complex CSV
        if isinstance(data, list) and data:
            if hasattr(data[0], "dict"):
                # Pydantic models
                import csv
                import io

                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=data[0].dict().keys())
                writer.writeheader()
                for item in data:
                    writer.writerow(item.dict())
                return output.getvalue()
        return str(data)

    elif output_format == "table":
        # Simple table format
        if isinstance(data, list) and data:
            if hasattr(data[0], "get_summary"):
                return "\n\n".join(item.get_summary() for item in data)
            elif hasattr(data[0], "dict"):
                # Simple key-value display
                result = []
                for i, item in enumerate(data):
                    result.append(f"--- Item {i + 1} ---")
                    for key, value in item.dict().items():
                        result.append(f"{key}: {value}")
                return "\n".join(result)
        return str(data)

    else:
        return str(data)


@click.group()
@click.option("--db-path", help="Path to Outlook database file")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, db_path: str | None, verbose: bool):
    """pyoutlook-db: Access Microsoft Outlook SQLite database on macOS."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["verbose"] = verbose

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)


@cli.command()
@click.option("--start-date", type=click.DateTime(), help="Start date (YYYY-MM-DD)")
@click.option("--end-date", type=click.DateTime(), help="End date (YYYY-MM-DD)")
@click.option("--folder", multiple=True, help="Folder names to search in")
@click.option("--limit", default=100, help="Maximum number of emails to return")
@click.option("--format", "output_format", type=click.Choice(["json", "csv", "table"]), default="table", help="Output format")
@click.option("--no-content", is_flag=True, help="Exclude email content from output")
@click.pass_context
def emails(ctx, start_date: datetime | None, end_date: datetime | None,
          folder: tuple, limit: int, output_format: str, no_content: bool):
    """Get emails by date range."""
    try:
        # Default to last 7 days if no dates provided
        if not start_date:
            start_date = datetime.now() - timedelta(days=7)
        if not end_date:
            end_date = datetime.now()

        client = OutlookClient(db_path=ctx.obj["db_path"])

        folders_list = list(folder) if folder else None
        include_content = not no_content

        emails_list = client.get_emails_by_date_range(
            start_date=start_date,
            end_date=end_date,
            folders=folders_list,
            include_content=include_content,
            limit=limit
        )

        if not emails_list:
            click.echo("No emails found for the specified criteria.")
            return

        output = format_output(emails_list, output_format)
        click.echo(output)

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--format", "output_format", type=click.Choice(["json", "csv", "table"]), default="table", help="Output format")
@click.pass_context
def calendars(ctx, output_format: str):
    """List all available calendars."""
    try:
        client = OutlookClient(db_path=ctx.obj["db_path"])
        calendars_list = client.get_calendars()

        if not calendars_list:
            click.echo("No calendars found.")
            return

        output = format_output(calendars_list, output_format)
        click.echo(output)

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--calendar-id", help="Calendar ID to get events from")
@click.option("--start-date", type=click.DateTime(), help="Start date (YYYY-MM-DD)")
@click.option("--end-date", type=click.DateTime(), help="End date (YYYY-MM-DD)")
@click.option("--limit", default=100, help="Maximum number of events to return")
@click.option("--format", "output_format", type=click.Choice(["json", "csv", "table"]), default="table", help="Output format")
@click.pass_context
def events(ctx, calendar_id: str | None, start_date: datetime | None,
          end_date: datetime | None, limit: int, output_format: str):
    """Get calendar events."""
    try:
        # Default to next 30 days if no dates provided
        if not start_date:
            start_date = datetime.now()
        if not end_date:
            end_date = datetime.now() + timedelta(days=30)

        client = OutlookClient(db_path=ctx.obj["db_path"])

        events_list = client.get_calendar_events(
            calendar_id=calendar_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        if not events_list:
            click.echo("No events found for the specified criteria.")
            return

        output = format_output(events_list, output_format)
        click.echo(output)

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--query", required=True, help="Search query text")
@click.option("--type", "search_type", type=click.Choice(["email", "calendar"]), default="email", help="Type of data to search")
@click.option("--sender", help="Filter by sender email")
@click.option("--folder", multiple=True, help="Folder names to search in")
@click.option("--start-date", type=click.DateTime(), help="Start date (YYYY-MM-DD)")
@click.option("--end-date", type=click.DateTime(), help="End date (YYYY-MM-DD)")
@click.option("--limit", default=50, help="Maximum number of results to return")
@click.option("--format", "output_format", type=click.Choice(["json", "csv", "table"]), default="table", help="Output format")
@click.pass_context
def search(ctx, query: str, search_type: str, sender: str | None, folder: tuple,
          start_date: datetime | None, end_date: datetime | None,
          limit: int, output_format: str):
    """Search emails or calendar events."""
    try:
        client = OutlookClient(db_path=ctx.obj["db_path"])

        if search_type == "email":
            search_filter = EmailSearchFilter(
                query=query,
                sender=sender,
                folders=list(folder) if folder else None,
                start_date=start_date,
                end_date=end_date,
                limit=limit
            )

            results = client.search_emails(search_filter)

        else:  # calendar
            # For calendar search, we'll use a simple approach
            events = client.get_calendar_events(
                start_date=start_date,
                end_date=end_date,
                limit=limit
            )

            # Filter events by query
            results = [
                event for event in events
                if query.lower() in event.title.lower() or query.lower() in event.description.lower()
            ]

        if not results:
            click.echo(f"No {search_type} results found for query: {query}")
            return

        output = format_output(results, output_format)
        click.echo(output)

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def info(ctx):
    """Show information about the Outlook database."""
    try:
        client = OutlookClient(db_path=ctx.obj["db_path"])

        # Get basic database info
        tables = client.db.get_table_names()

        info_data = {
            "database_path": client.db.db_path,
            "connected": client.db.is_connected,
            "tables": tables,
        }

        # Get counts for main tables
        if "Mail" in tables:
            info_data["email_count"] = client.db.get_row_count("Mail")

        if "CalendarEvents" in tables:
            info_data["event_count"] = client.db.get_row_count("CalendarEvents")

        if "CalendarEvents" in tables:
            info_data["calendar_count"] = client.db.get_row_count("CalendarEvents")

        click.echo("Outlook Database Information:")
        click.echo(f"Path: {info_data['database_path']}")
        click.echo(f"Connected: {info_data['connected']}")
        click.echo(f"Tables: {', '.join(info_data['tables'])}")

        if "email_count" in info_data:
            click.echo(f"Total emails: {info_data['email_count']:,}")

        if "event_count" in info_data:
            click.echo(f"Total events: {info_data['event_count']:,}")

        if "calendar_count" in info_data:
            click.echo(f"Total calendars: {info_data['calendar_count']:,}")

    except OutlookDBError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
