from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, create_engine, func, inspect, select, text

from accounts.store import Base as AccountsBase
from accounts.store import UserStore

from .store import Base as InteractionsBase
from .store import InteractionStore

SQLITE_PREFIX = "sqlite:///"


class CopyError(RuntimeError):
    pass


def copy_database(source_url: str, target_url: str) -> dict[str, int]:
    """Copies every table (chats, HR requests, model calls, accounts, sign-in sessions) from
    one database to another, empty one, and checks every row arrived. The source is opened
    read-only, so it's never changed. Returns the rows copied per table."""
    if source_url == target_url:
        raise CopyError("The source and target are the same database.")
    source = create_engine(_read_only(source_url))
    # The stores create the tables, with every column the code has now.
    InteractionStore(target_url)
    UserStore(target_url)
    target = create_engine(target_url)

    tables = [*AccountsBase.metadata.sorted_tables, *InteractionsBase.metadata.sorted_tables]
    with target.connect() as connection:
        filled = [table.name for table in tables if connection.scalar(select(func.count()).select_from(table))]
    if filled:
        raise CopyError(f"The target already has rows in {', '.join(filled)}; nothing was copied.")

    schema = inspect(source)
    source_columns = {name: {column["name"] for column in schema.get_columns(name)} for name in schema.get_table_names()}
    copied: dict[str, int] = {}
    with source.connect() as read, target.begin() as write:
        for table in tables:
            if table.name not in source_columns:
                copied[table.name] = 0
                continue
            # Columns added since the source was created are left empty, as the app would.
            columns = [column for column in table.columns if column.name in source_columns[table.name]]
            rows = [{key: _utc(value) for key, value in row._mapping.items()} for row in read.execute(select(*columns))]
            if rows:
                write.execute(table.insert(), rows)
            copied[table.name] = len(rows)
        if write.dialect.name == "postgresql":
            _reset_sequences(write, tables)

    _check_copy(source, target, [table for table in tables if table.name in source_columns])
    return copied


def back_up_sqlite(database_url: str, backup_dir: Path) -> Path:
    """A consistent copy of a SQLite database file, made with SQLite's own backup."""
    path = Path(database_url.removeprefix(SQLITE_PREFIX))
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{path.stem}-{stamp}-before-postgres{path.suffix}"
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as source, sqlite3.connect(backup) as copy:
        source.backup(copy)
    return backup


def _read_only(database_url: str) -> str:
    if not database_url.startswith(SQLITE_PREFIX):
        return database_url
    path = Path(database_url.removeprefix(SQLITE_PREFIX))
    if not path.exists():
        raise CopyError(f"No database at {path}.")
    return f"sqlite:///file:{path}?mode=ro&uri=true"


def _utc(value: Any) -> Any:
    # SQLite hands datetimes back without a timezone; they were all stored in UTC.
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _reset_sequences(connection: Any, tables: list[Any]) -> None:
    # Rows were copied with their ids, so the next id has to start after the highest one.
    for table in tables:
        for column in table.primary_key.columns:
            if isinstance(column.type, Integer) and column.autoincrement in (True, "auto"):
                connection.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{column.name}'), "
                        f"COALESCE((SELECT MAX({column.name}) FROM {table.name}), 0) + 1, false)"
                    )
                )


def _check_copy(source: Any, target: Any, tables: list[Any]) -> None:
    for table in tables:
        keys = list(table.primary_key.columns)
        with source.connect() as read, target.connect() as written:
            expected = set(read.execute(select(*keys)))
            found = set(written.execute(select(*keys)))
        if expected != found:
            raise CopyError(f"{table.name}: {len(found)} rows in the target, {len(expected)} in the source.")

