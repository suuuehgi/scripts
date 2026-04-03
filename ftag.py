#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["click"]
# ///

"""ftag – Tag files using extended filesystem attributes.

Tags are stored in user.xdg.tags  (visible in Dolphin).
Dates are stored in user.dublincore.date (ISO 8601: YYYY-MM-DD).
"""

import errno
import os
import re
from datetime import date as Date

import click

TAGS_ATTR = "user.xdg.tags"
DATE_ATTR = "user.dublincore.date"
DATE_RE   = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── xattr helpers ────────────────────────────────────────────────────────────

def _get_xattr(filepath: str, attr: str) -> str | None:
    try:
        return os.getxattr(filepath, attr).decode()
    except OSError as e:
        if e.errno in (errno.ENODATA, errno.ENOTSUP):
            return None
        raise


def _set_xattr(filepath: str, attr: str, value: str) -> None:
    os.setxattr(filepath, attr, value.encode())


def _remove_xattr(filepath: str, attr: str) -> None:
    try:
        os.removexattr(filepath, attr)
    except OSError as e:
        if e.errno != errno.ENODATA:
            raise


def get_tags(filepath: str) -> list[str]:
    raw = _get_xattr(filepath, TAGS_ATTR)
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def set_tags(filepath: str, tags: list[str]) -> None:
    if tags:
        _set_xattr(filepath, TAGS_ATTR, ",".join(tags))
    else:
        _remove_xattr(filepath, TAGS_ATTR)


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """ftag – tag files via extended filesystem attributes."""


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.argument("tags", nargs=-1, required=True)
def add(file, tags):
    """Add one or more TAGS to FILE (idempotent)."""
    current = get_tags(file)
    added = [t for t in tags if t not in current]
    set_tags(file, current + added)
    if added:
        click.echo(f"Added: {', '.join(added)}")
    else:
        click.echo("Nothing to add (all tags already present).")


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.argument("tags", nargs=-1, required=True)
def rm(file, tags):
    """Remove one or more TAGS from FILE."""
    current = get_tags(file)
    removed = [t for t in tags if t in current]
    set_tags(file, [t for t in current if t not in tags])
    if removed:
        click.echo(f"Removed: {', '.join(removed)}")
    else:
        click.echo("Nothing removed (none of those tags were present).")


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt.")
def clear(file, force):
    """Remove ALL tags from FILE."""
    current = get_tags(file)
    if not current:
        click.echo("No tags to clear.")
        return
    if not force:
        click.confirm(
            f"Remove all {len(current)} tag(s) from '{file}'?"
            f"  ({', '.join(current)})",
            abort=True,
        )
    set_tags(file, [])
    click.echo("All tags cleared.")


@cli.command()
@click.argument("file", type=click.Path(exists=True))
def show(file):
    """Show tags and date of FILE."""
    tags     = get_tags(file)
    date_val = _get_xattr(file, DATE_ATTR)
    click.echo(f"Tags : {', '.join(tags) if tags else '(none)'}")
    click.echo(f"Date : {date_val or '(none)'}")


@cli.command("date")
@click.argument("file", type=click.Path(exists=True))
@click.argument("value", required=False)
@click.option("--delete", "-d", is_flag=True, help="Remove the date attribute.")
def date_cmd(file, value, delete):
    """Set or remove the date of FILE.

    VALUE must be YYYY-MM-DD.  Use --delete / -d to remove the date.
    """
    if delete and value:
        raise click.UsageError("Cannot combine --delete with a date value.")
    if not delete and not value:
        raise click.UsageError("Provide a date value, or use --delete / -d.")

    if delete:
        _remove_xattr(file, DATE_ATTR)
        click.echo("Date removed.")
    else:
        if not DATE_RE.match(value):
            raise click.BadParameter(
                f"'{value}' is not valid. Expected format: YYYY-MM-DD",
                param_hint="VALUE",
            )
        try:
            Date.fromisoformat(value)   # rejects e.g. 2024-13-01
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="VALUE")
        _set_xattr(file, DATE_ATTR, value)
        click.echo(f"Date set to {value}.")


if __name__ == "__main__":
    cli()
