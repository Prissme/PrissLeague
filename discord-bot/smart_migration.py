#!/usr/bin/env python3
"""Smart database migration script for PrissLeague."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from typing import Dict, Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


def log(message: str) -> None:
    print(f"[smart_migration] {message}")


def create_backup(database_url: str) -> None:
    """Create a timestamped SQL backup using pg_dump."""
    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = f"db_backup_{timestamp}.sql"
    log(f"Creating backup at {backup_file} ...")
    try:
        result = subprocess.run(
            ["pg_dump", database_url, "-f", backup_file],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stderr:
            log(f"pg_dump warnings: {result.stderr.strip()}")
        log("Backup completed successfully.")
    except FileNotFoundError:
        log("WARNING: pg_dump not found. Skipping automatic backup.")
    except subprocess.CalledProcessError as exc:
        log("ERROR: pg_dump failed. Aborting migration.")
        log(exc.stderr.strip())
        raise


def get_primary_key_column(cursor, table_name: str) -> Optional[str]:
    cursor.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = %s
        ORDER BY kcu.ordinal_position
        """,
        (table_name,),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    return rows[0]["column_name"]


def table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (table_name,),
    )
    return cursor.fetchone()["exists"]


def column_info(cursor, table_name: str) -> Dict[str, Dict[str, str]]:
    cursor.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    info: Dict[str, Dict[str, str]] = {}
    for row in cursor.fetchall():
        info[row["column_name"]] = {
            "data_type": row["data_type"],
            "is_nullable": row["is_nullable"],
            "column_default": row["column_default"],
        }
    return info


def ensure_players_schema(cursor) -> None:
    if not table_exists(cursor, "players"):
        log("Table 'players' does not exist. Creating with expected schema ...")
        cursor.execute(
            """
            CREATE TABLE players (
                discord_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                division TEXT NOT NULL DEFAULT 'division2',
                solo_elo INTEGER NOT NULL DEFAULT 1000,
                solo_wins INTEGER NOT NULL DEFAULT 0,
                solo_losses INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            )
            """
        )
        return

    log("Ensuring 'players' table schema ...")
    info = column_info(cursor, "players")
    pk_column = get_primary_key_column(cursor, "players")
    log(f"Current primary key column: {pk_column!r}")

    if pk_column != "discord_id":
        log("Adjusting primary key to be 'discord_id' ...")
        if "discord_id" in info:
            log("Column 'discord_id' already exists but is not primary key.")
        else:
            if pk_column is None:
                log("No primary key detected. Attempting to infer identifier column ...")
                candidate = None
                for name in ("discord_id", "user_id", "id"):
                    if name in info:
                        candidate = name
                        break
                if candidate is None and info:
                    candidate = next(iter(info))
                pk_column = candidate
            if pk_column is None:
                raise RuntimeError("Unable to determine identifier column for players table")
            log(f"Using column '{pk_column}' to populate new discord_id column.")
            cursor.execute("ALTER TABLE players ADD COLUMN discord_id TEXT")
            cursor.execute(
                sql.SQL("""
                    UPDATE players
                    SET discord_id = {pk}::text
                """).format(pk=sql.Identifier(pk_column))
            )
        # Ensure discord_id is not null
        cursor.execute(
            "SELECT COUNT(*) FROM players WHERE discord_id IS NULL OR discord_id = ''"
        )
        null_count = cursor.fetchone()["count"]
        if null_count:
            raise RuntimeError(
                "Cannot set discord_id as primary key because some rows are missing values."
            )
        # Drop existing primary key if present
        if pk_column:
            cursor.execute(
                """
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_schema = 'public' AND table_name = 'players' AND constraint_type = 'PRIMARY KEY'
                """
            )
            row = cursor.fetchone()
            if row:
                constraint_name = row["constraint_name"]
                cursor.execute(
                    sql.SQL("ALTER TABLE players DROP CONSTRAINT {}" ).format(
                        sql.Identifier(constraint_name)
                    )
                )
        # Ensure discord_id column type text
        cursor.execute(
            "ALTER TABLE players ALTER COLUMN discord_id TYPE TEXT USING discord_id::text"
        )
        cursor.execute("ALTER TABLE players ALTER COLUMN discord_id SET NOT NULL")
        cursor.execute("ALTER TABLE players ADD PRIMARY KEY (discord_id)")
    else:
        # Ensure column type text
        cursor.execute(
            "ALTER TABLE players ALTER COLUMN discord_id TYPE TEXT USING discord_id::text"
        )
        cursor.execute("ALTER TABLE players ALTER COLUMN discord_id SET NOT NULL")

    # Handle legacy display_name column
    if "display_name" in info:
        if "name" not in info:
            log("Renaming legacy column 'display_name' to 'name'.")
            cursor.execute("ALTER TABLE players RENAME COLUMN display_name TO name")
            info["name"] = info.pop("display_name")
        else:
            log("Migrating values from legacy column 'display_name' into 'name'.")
            cursor.execute(
                """
                UPDATE players
                SET name = display_name
                WHERE (name IS NULL OR name = '') AND display_name IS NOT NULL
                """
            )
            cursor.execute("ALTER TABLE players DROP COLUMN display_name")
            info.pop("display_name", None)

    # Ensure name column exists
    if "name" not in info:
        log("Adding missing column 'name'.")
        cursor.execute("ALTER TABLE players ADD COLUMN name TEXT NOT NULL DEFAULT 'Unknown'")
    else:
        cursor.execute("ALTER TABLE players ALTER COLUMN name SET NOT NULL")

    # Ensure division column
    if "division" not in info:
        log("Adding missing column 'division'.")
        cursor.execute(
            "ALTER TABLE players ADD COLUMN division TEXT NOT NULL DEFAULT 'division2'"
        )
    else:
        cursor.execute(
            "ALTER TABLE players ALTER COLUMN division SET DEFAULT 'division2'"
        )
        cursor.execute("UPDATE players SET division = 'division2' WHERE division IS NULL")
        cursor.execute("ALTER TABLE players ALTER COLUMN division SET NOT NULL")

    # Ensure solo_elo column
    if "solo_elo" not in info:
        log("Adding missing column 'solo_elo'.")
        cursor.execute(
            "ALTER TABLE players ADD COLUMN solo_elo INTEGER NOT NULL DEFAULT 1000"
        )
    else:
        cursor.execute(
            "ALTER TABLE players ALTER COLUMN solo_elo SET DEFAULT 1000"
        )
        cursor.execute("UPDATE players SET solo_elo = 1000 WHERE solo_elo IS NULL")
        cursor.execute("ALTER TABLE players ALTER COLUMN solo_elo SET NOT NULL")

    # Ensure solo_wins column
    if "solo_wins" not in info:
        log("Adding missing column 'solo_wins'.")
        cursor.execute(
            "ALTER TABLE players ADD COLUMN solo_wins INTEGER NOT NULL DEFAULT 0"
        )
    else:
        cursor.execute(
            "ALTER TABLE players ALTER COLUMN solo_wins SET DEFAULT 0"
        )
        cursor.execute("UPDATE players SET solo_wins = 0 WHERE solo_wins IS NULL")
        cursor.execute("ALTER TABLE players ALTER COLUMN solo_wins SET NOT NULL")

    # Ensure solo_losses column
    if "solo_losses" not in info:
        log("Adding missing column 'solo_losses'.")
        cursor.execute(
            "ALTER TABLE players ADD COLUMN solo_losses INTEGER NOT NULL DEFAULT 0"
        )
    else:
        cursor.execute(
            "ALTER TABLE players ALTER COLUMN solo_losses SET DEFAULT 0"
        )
        cursor.execute("UPDATE players SET solo_losses = 0 WHERE solo_losses IS NULL")
        cursor.execute("ALTER TABLE players ALTER COLUMN solo_losses SET NOT NULL")

    # Ensure created_at column
    if "created_at" not in info:
        log("Adding missing column 'created_at'.")
        cursor.execute(
            "ALTER TABLE players ADD COLUMN created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()"
        )

    # Migrate legacy columns if they exist
    legacy_mapping = {
        "elo": "solo_elo",
        "wins": "solo_wins",
        "losses": "solo_losses",
    }
    for old_col, new_col in legacy_mapping.items():
        if old_col in info:
            log(f"Migrating data from '{old_col}' to '{new_col}'.")
            cursor.execute(
                sql.SQL(
                    """
                    UPDATE players
                    SET {new_col} = COALESCE({old_col}, {new_col})
                    """
                ).format(new_col=sql.Identifier(new_col), old_col=sql.Identifier(old_col))
            )


def ensure_solo_matches_table(cursor) -> None:
    if table_exists(cursor, "solo_matches"):
        log("Table 'solo_matches' already exists. Ensuring required columns ...")
        info = column_info(cursor, "solo_matches")
        required_columns = {
            "division": "TEXT NOT NULL",
            "team1_ids": "TEXT NOT NULL",
            "team2_ids": "TEXT NOT NULL",
            "room_code": "TEXT NOT NULL",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "winner": "TEXT",
            "created_at": "TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()",
            "completed_at": "TIMESTAMP WITHOUT TIME ZONE",
        }
        for column, definition in required_columns.items():
            if column not in info:
                log(f"Adding missing column '{column}' to solo_matches.")
                cursor.execute(
                    sql.SQL("ALTER TABLE solo_matches ADD COLUMN {} {}" ).format(
                        sql.Identifier(column), sql.SQL(definition)
                    )
                )
        if "id" not in info:
            log("Adding primary key column 'id' to solo_matches.")
            cursor.execute("ALTER TABLE solo_matches ADD COLUMN id SERIAL PRIMARY KEY")
        else:
            pk_column = get_primary_key_column(cursor, "solo_matches")
            if pk_column != "id":
                log("Ensuring 'id' column is primary key for solo_matches.")
                if pk_column:
                    cursor.execute(
                        """
                        SELECT constraint_name
                        FROM information_schema.table_constraints
                        WHERE table_schema = 'public'
                          AND table_name = 'solo_matches'
                          AND constraint_type = 'PRIMARY KEY'
                        """
                    )
                    row = cursor.fetchone()
                    if row:
                        cursor.execute(
                            sql.SQL("ALTER TABLE solo_matches DROP CONSTRAINT {}" ).format(
                                sql.Identifier(row["constraint_name"])
                            )
                        )
                cursor.execute("ALTER TABLE solo_matches ADD PRIMARY KEY (id)")
        return

    log("Creating 'solo_matches' table ...")
    cursor.execute(
        """
        CREATE TABLE solo_matches (
            id SERIAL PRIMARY KEY,
            division TEXT NOT NULL,
            team1_ids TEXT NOT NULL,
            team2_ids TEXT NOT NULL,
            room_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            winner TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            completed_at TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    try:
        create_backup(database_url)
    except Exception:
        log("Backup failed. Migration aborted.")
        sys.exit(1)

    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    try:
        with conn.cursor() as cursor:
            log("Starting migration inside transaction ...")
            ensure_players_schema(cursor)
            ensure_solo_matches_table(cursor)
        conn.commit()
        log("Migration completed successfully.")
    except Exception as exc:
        conn.rollback()
        log(f"Migration failed and has been rolled back: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
