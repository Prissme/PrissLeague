#!/usr/bin/env python3
"""Utility helpers to address in-game progression issues.

This script focuses on two support requests reported by the community:

* Kenji is disproportionately rare in the matchmaking ("mm") reward tables
  compared to other difficult brawlers like Surge.
* Advanced players sometimes open an egg, receive the pet in their inventory,
  but the grade quest associated with the egg fails to progress.

The implementation intentionally avoids assumptions about the exact database
schema.  Instead, it inspects the public schema dynamically and performs the
updates only when the expected tables and columns are present.  This makes the
tool resilient to the small variations that exist between different Supabase
deployments of the project.

Usage
-----

The script can be executed directly once the ``DATABASE_URL`` environment
variable is defined::

    $ export DATABASE_URL=postgres://...
    $ python3 game_support_tools.py

The script is idempotent – running it multiple times will simply ensure the
target data stays in the desired shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


KENJI_TARGET_RATE = 0.35
"""Desired minimum drop rate for Kenji in matchmaking loot tables."""


PLAYER_ID_CANDIDATES: Sequence[str] = (
    "player_id",
    "user_id",
    "profile_id",
    "account_id",
    "discord_id",
)

NAME_COLUMN_CANDIDATES: Sequence[str] = (
    "name",
    "brawler_name",
    "reward_name",
    "item_name",
    "slug",
    "code",
)

RATE_COLUMN_CANDIDATES: Sequence[str] = (
    "drop_rate",
    "probability",
    "weight",
    "chance",
    "odds",
)

PROGRESS_COLUMN_CANDIDATES: Sequence[str] = (
    "progress",
    "current_progress",
    "value",
    "count",
)

TARGET_COLUMN_CANDIDATES: Sequence[str] = (
    "target",
    "goal",
    "required",
    "needed",
    "objective",
)

TYPE_COLUMN_CANDIDATES: Sequence[str] = (
    "quest_type",
    "type",
    "category",
    "code",
    "slug",
    "identifier",
)


@dataclass
class TableInfo:
    """Description of a table detected during the inspection phase."""

    name: str
    columns: Dict[str, Dict[str, str]]

    def find_column(self, candidates: Iterable[str]) -> Optional[str]:
        """Return the first column that matches one of the candidates."""

        for candidate in candidates:
            if candidate in self.columns:
                return candidate
        return None


def get_connection() -> psycopg2.extensions.connection:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def fetch_table_names(cursor) -> List[str]:
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
    )
    return [row["table_name"] for row in cursor.fetchall()]


def fetch_table_info(cursor, table_name: str) -> TableInfo:
    cursor.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )

    columns: Dict[str, Dict[str, str]] = {}
    for row in cursor.fetchall():
        columns[row["column_name"]] = {
            "data_type": row["data_type"],
            "is_nullable": row["is_nullable"],
            "column_default": row["column_default"],
        }
    return TableInfo(name=table_name, columns=columns)


def rebalance_kenji_drop_rate(conn) -> List[Tuple[str, Optional[float]]]:
    """Bring Kenji's drop rate in line with expectations.

    Returns a list of tuples describing the affected tables and the previous
    rate (if it could be determined).
    """

    updates: List[Tuple[str, Optional[float]]] = []
    with conn.cursor() as cursor:
        table_names = fetch_table_names(cursor)
        table_infos = {name: fetch_table_info(cursor, name) for name in table_names}

        for table_name, info in table_infos.items():
            name_column = info.find_column(NAME_COLUMN_CANDIDATES)
            rate_column = info.find_column(RATE_COLUMN_CANDIDATES)

            if not name_column or not rate_column:
                continue

            # Check whether Kenji exists in the table.
            cursor.execute(
                sql.SQL(
                    "SELECT {rate} FROM {table} "
                    "WHERE LOWER({name}) = 'kenji'"
                ).format(
                    rate=sql.Identifier(rate_column),
                    table=sql.Identifier(table_name),
                    name=sql.Identifier(name_column),
                )
            )
            rows = cursor.fetchall()
            if not rows:
                continue

            current_rates = [row[rate_column] for row in rows if row[rate_column] is not None]
            current_rate = (
                sum(current_rates) / len(current_rates)
                if current_rates
                else None
            )

            cursor.execute(
                sql.SQL(
                    "UPDATE {table} "
                    "SET {rate} = GREATEST(%s, {rate}) "
                    "WHERE LOWER({name}) = 'kenji'"
                ).format(
                    table=sql.Identifier(table_name),
                    rate=sql.Identifier(rate_column),
                    name=sql.Identifier(name_column),
                ),
                (KENJI_TARGET_RATE,),
            )

            if cursor.rowcount:
                updates.append((table_name, current_rate))

    if updates:
        conn.commit()

    return updates


def build_grade_condition(type_column: Optional[str], table_has_grade_in_name: bool) -> Optional[sql.SQL]:
    """Return the SQL condition that isolates grade-related quests."""

    if type_column:
        return sql.SQL(
            "("  # noqa: D400 - multi-line SQL expression
            "COALESCE({type_col}, '') ILIKE 'grade%%' OR "
            "COALESCE({type_col}, '') ILIKE 'pet%%' OR "
            "COALESCE({type_col}, '') ILIKE 'egg%%'"
            ")"
        ).format(type_col=sql.Identifier(type_column))

    if table_has_grade_in_name:
        return sql.SQL("TRUE")

    return None


def fix_grade_quest_progress(conn) -> List[Tuple[str, str, int]]:
    """Repair grade quest progression using pet inventory information."""

    updates: List[Tuple[str, str, int]] = []
    with conn.cursor() as cursor:
        table_names = fetch_table_names(cursor)
        table_infos = {name: fetch_table_info(cursor, name) for name in table_names}

        quest_tables: List[TableInfo] = []
        pet_tables: List[TableInfo] = []

        for name, info in table_infos.items():
            lowered = name.lower()

            if "quest" in lowered:
                quest_tables.append(info)
            if "pet" in lowered or "egg" in lowered:
                pet_tables.append(info)

        for quest_info in quest_tables:
            player_column = quest_info.find_column(PLAYER_ID_CANDIDATES)
            progress_column = quest_info.find_column(PROGRESS_COLUMN_CANDIDATES)
            target_column = quest_info.find_column(TARGET_COLUMN_CANDIDATES)
            type_column = quest_info.find_column(TYPE_COLUMN_CANDIDATES)
            grade_condition = build_grade_condition(
                type_column, "grade" in quest_info.name.lower()
            )

            if not (player_column and progress_column and target_column and grade_condition):
                continue

            for pet_info in pet_tables:
                pet_player_column = pet_info.find_column(
                    (player_column,) + tuple(PLAYER_ID_CANDIDATES)
                )

                if not pet_player_column:
                    continue

                update_sql = sql.SQL(
                    """
                    WITH pet_counts AS (
                        SELECT {pet_player} AS player_id, COUNT(*) AS pet_count
                        FROM {pet_table}
                        GROUP BY {pet_player}
                    )
                    UPDATE {quest_table} AS q
                    SET {progress} = GREATEST(
                        COALESCE({progress}, 0),
                        LEAST({target}, pet_counts.pet_count)
                    )
                    FROM pet_counts
                    WHERE q.{quest_player} = pet_counts.player_id
                      AND {grade_condition}
                    """
                ).format(
                    pet_player=sql.Identifier(pet_player_column),
                    pet_table=sql.Identifier(pet_info.name),
                    quest_table=sql.Identifier(quest_info.name),
                    progress=sql.Identifier(progress_column),
                    target=sql.Identifier(target_column),
                    quest_player=sql.Identifier(player_column),
                    grade_condition=grade_condition,
                )

                cursor.execute(update_sql)
                if cursor.rowcount:
                    updates.append((quest_info.name, pet_info.name, cursor.rowcount))
                    break  # Use the first matching pet table for each quest table.

    if updates:
        conn.commit()

    return updates


def main() -> None:
    conn = get_connection()
    try:
        kenji_updates = rebalance_kenji_drop_rate(conn)
        quest_updates = fix_grade_quest_progress(conn)

        if kenji_updates:
            print("🐱 Kenji drop rate adjustments:")
            for table_name, previous_rate in kenji_updates:
                if previous_rate is None:
                    print(f"  • {table_name}: now at ≥ {KENJI_TARGET_RATE:.2f} (previous unknown)")
                else:
                    print(
                        f"  • {table_name}: {previous_rate:.2f} → "
                        f"{KENJI_TARGET_RATE:.2f} (minimum enforced)"
                    )
        else:
            print("ℹ️ Aucun tableau loot avec Kenji n'a été trouvé.")

        if quest_updates:
            print("🐣 Grade quest progression repaired:")
            for quest_table, pet_table, affected in quest_updates:
                print(
                    f"  • {quest_table} synchronisé avec {pet_table} – "
                    f"{affected} quêtes mises à jour"
                )
        else:
            print(
                "ℹ️ Aucune combinaison quête/pet compatible trouvée pour corriger les "
                "quêtes de grade."
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
