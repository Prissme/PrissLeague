#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Solo matchmaking bot with division support."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import string
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import discord
import psycopg2
from discord.ext import commands
from psycopg2.extras import RealDictCursor

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
QUEUE_TARGET_SIZE = 6  # 3v3

MATCH_CHANNEL_ID = 1434509931360419890
LOG_CHANNEL_ID = 1237166689188053023

DIVISION_ONE_ROLE_IDS = {
    1382754272415846552,
    1427036443599179837,
    1382755128955637790,
    1429940014036553899,
    1382755717781524590,
}
DIVISION_LABELS = {
    "division1": "Division 1",
    "division2": "Division 2",
}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
queue_lock = asyncio.Lock()
solo_queues: Dict[str, List[int]] = {"division1": [], "division2": []}

# ----------------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------------


def get_connection():
    """Create a PostgreSQL connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db() -> None:
    """Ensure the required tables exist and have the correct columns."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
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

            # Ensure expected columns exist for legacy databases
            cursor.execute(
                "ALTER TABLE players ADD COLUMN IF NOT EXISTS division TEXT NOT NULL DEFAULT 'division2'"
            )
            cursor.execute(
                "ALTER TABLE players ADD COLUMN IF NOT EXISTS solo_elo INTEGER NOT NULL DEFAULT 1000"
            )
            cursor.execute(
                "ALTER TABLE players ADD COLUMN IF NOT EXISTS solo_wins INTEGER NOT NULL DEFAULT 0"
            )
            cursor.execute(
                "ALTER TABLE players ADD COLUMN IF NOT EXISTS solo_losses INTEGER NOT NULL DEFAULT 0"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS solo_matches (
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

        conn.commit()
    finally:
        conn.close()


@dataclass
class Player:
    discord_id: int
    name: str
    solo_elo: int
    solo_wins: int
    solo_losses: int
    division: str

    @classmethod
    def from_row(cls, row: Dict) -> "Player":
        return cls(
            discord_id=int(row["discord_id"]),
            name=row.get("name", "Unknown"),
            solo_elo=int(row.get("solo_elo", 1000)),
            solo_wins=int(row.get("solo_wins", 0)),
            solo_losses=int(row.get("solo_losses", 0)),
            division=row.get("division", "division2"),
        )


# ----------------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------------


def calculate_elo_change(player_elo: float, opponent_avg_elo: float, won: bool) -> int:
    """Return the integer ELO change for a player."""
    k_factor = 30
    expected = 1 / (1 + 10 ** ((opponent_avg_elo - player_elo) / 400))
    actual = 1.0 if won else 0.0
    change = k_factor * (actual - expected)
    return round(change)


def generate_room_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=length))


def determine_division(member: discord.Member) -> str:
    member_role_ids = {role.id for role in getattr(member, "roles", [])}
    if member_role_ids & DIVISION_ONE_ROLE_IDS:
        return "division1"
    return "division2"


def ensure_player(discord_id: int, name: str, division: str) -> Player:
    """Create or update the player with the correct division."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO players (discord_id, name, division)
                VALUES (%s, %s, %s)
                ON CONFLICT (discord_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        division = EXCLUDED.division
                RETURNING discord_id, name, division, solo_elo, solo_wins, solo_losses
                """,
                (str(discord_id), name, division),
            )
            row = cursor.fetchone()
        conn.commit()
        return Player.from_row(row)
    finally:
        conn.close()


def fetch_players(discord_ids: Sequence[int]) -> List[Player]:
    if not discord_ids:
        return []

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT discord_id, name, division, solo_elo, solo_wins, solo_losses
                FROM players
                WHERE discord_id = ANY(%s)
                """,
                ([str(i) for i in discord_ids],),
            )
            rows = cursor.fetchall()
        return [Player.from_row(row) for row in rows]
    finally:
        conn.close()


def fetch_player(discord_id: int) -> Optional[Player]:
    players = fetch_players([discord_id])
    return players[0] if players else None


def record_match(
    team1_ids: Sequence[int],
    team2_ids: Sequence[int],
    room_code: str,
    division: str,
) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO solo_matches (division, team1_ids, team2_ids, room_code)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    division,
                    json.dumps(list(map(int, team1_ids))),
                    json.dumps(list(map(int, team2_ids))),
                    room_code,
                ),
            )
            match_id = cursor.fetchone()["id"]
        conn.commit()
        return int(match_id)
    finally:
        conn.close()


def load_match(match_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM solo_matches
                WHERE id = %s
                """,
                (match_id,),
            )
            row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def complete_match(match_id: int, winner: str) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE solo_matches
                SET status = 'completed', winner = %s, completed_at = NOW()
                WHERE id = %s
                """,
                (winner, match_id),
            )
        conn.commit()
    finally:
        conn.close()


def apply_player_updates(updates: Iterable[Tuple[int, int, bool]]) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for discord_id, new_elo, won in updates:
                if won:
                    cursor.execute(
                        """
                        UPDATE players
                        SET solo_elo = %s, solo_wins = solo_wins + 1
                        WHERE discord_id = %s
                        """,
                        (new_elo, str(discord_id)),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE players
                        SET solo_elo = %s, solo_losses = solo_losses + 1
                        WHERE discord_id = %s
                        """,
                        (new_elo, str(discord_id)),
                    )
        conn.commit()
    finally:
        conn.close()


def format_queue_position(division: str) -> str:
    return f"{len(solo_queues[division])}/{QUEUE_TARGET_SIZE} joueurs dans la file {DIVISION_LABELS[division]}"


def describe_team(title: str, team_players: List[Player]) -> List[str]:
    average_elo = round(sum(p.solo_elo for p in team_players) / len(team_players))
    lines = [f"{title} (moyenne {average_elo} ELO)"]
    for p in team_players:
        lines.append(f"- <@{p.discord_id}> ({p.solo_elo} ELO)")
    return lines


async def send_match_message(guild: discord.Guild, content: str) -> None:
    channel = guild.get_channel(MATCH_CHANNEL_ID) if guild else None
    if channel is None and guild and guild.system_channel:
        channel = guild.system_channel
    if channel is None:
        logger.warning("No channel available to send match message")
        return
    await channel.send(content)


async def create_match_if_possible(ctx: commands.Context, division: str) -> None:
    guild = ctx.guild
    if guild is None:
        return

    async with queue_lock:
        queue_snapshot = list(solo_queues[division])
        if len(queue_snapshot) < QUEUE_TARGET_SIZE:
            return
        selected_ids = queue_snapshot[:QUEUE_TARGET_SIZE]
        solo_queues[division] = queue_snapshot[QUEUE_TARGET_SIZE:]

    players = fetch_players(selected_ids)
    player_map: Dict[int, Player] = {player.discord_id: player for player in players}

    # Ensure we have data for everyone in the queue snapshot
    missing = [pid for pid in selected_ids if pid not in player_map]
    for pid in missing:
        logger.warning("Missing player %s in database, creating default entry", pid)
        member = guild.get_member(pid)
        name = member.display_name if member else f"Joueur {pid}"
        division_override = determine_division(member) if member else "division2"
        player = ensure_player(pid, name, division_override)
        player_map[pid] = player

    sorted_ids = sorted(selected_ids, key=lambda pid: player_map[pid].solo_elo)
    team1_ids = sorted_ids[::2]
    team2_ids = sorted_ids[1::2]
    team1_players = [player_map[pid] for pid in team1_ids]
    team2_players = [player_map[pid] for pid in team2_ids]

    room_code = generate_room_code()
    match_id = record_match(team1_ids, team2_ids, room_code, division)

    message_lines = [
        f"🎮 **Match Solo #{match_id} - {DIVISION_LABELS[division]}**",
        f"Code Null's Brawl : `{room_code}`",
        "Signalez le vainqueur avec `!reportsolo {match_id} blue` ou `!reportsolo {match_id} red`.",
        "",
    ]
    message_lines.extend(describe_team("🔵 Équipe Bleue", team1_players))
    message_lines.append("")
    message_lines.extend(describe_team("🔴 Équipe Rouge", team2_players))
    message_lines.append("")
    message_lines.append(f"🔗 https://link.nulls.gg/nb/invite/gameroom/fr?tag={room_code}")

    await send_match_message(guild, "\n".join(message_lines))

    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(
            f"📝 Nouveau match Solo #{match_id} généré pour {DIVISION_LABELS[division]}."
        )


# ----------------------------------------------------------------------------
# Bot events & commands
# ----------------------------------------------------------------------------


@bot.event
async def on_ready():
    logger.info("Logged in as %s", bot.user)


@bot.command(name="joinsolo")
async def join_solo(ctx: commands.Context):
    member = ctx.author
    if not isinstance(member, discord.Member):
        await ctx.send("❌ Cette commande doit être utilisée dans un serveur.")
        return

    division = determine_division(member)
    player = ensure_player(member.id, member.display_name, division)

    async with queue_lock:
        existing_division: Optional[str] = None
        for div, queue in solo_queues.items():
            if member.id in queue:
                existing_division = div
                break

        if existing_division:
            await ctx.send(
                f"{member.mention} est déjà dans la file solo {DIVISION_LABELS[existing_division]}. "
                f"({format_queue_position(existing_division)})"
            )
            return

        solo_queues[division].append(member.id)
        position = len(solo_queues[division])

    await ctx.send(
        f"✅ {member.mention} rejoint la file solo {DIVISION_LABELS[division]} (ELO {player.solo_elo}). "
        f"Position : {position}/{QUEUE_TARGET_SIZE}."
    )
    await create_match_if_possible(ctx, division)


@bot.command(name="leavesolo")
async def leave_solo(ctx: commands.Context):
    member = ctx.author
    removed = False

    async with queue_lock:
        for queue in solo_queues.values():
            if member.id in queue:
                queue.remove(member.id)
                removed = True
                break

    if removed:
        await ctx.send(f"👋 {member.mention} quitte la file solo.")
    else:
        await ctx.send(f"{member.mention} n'est pas dans une file solo.")


@bot.command(name="queuesolo")
async def queue_solo(ctx: commands.Context):
    lines: List[str] = []
    async with queue_lock:
        for division, queue in solo_queues.items():
            if not queue:
                lines.append(f"📋 **{DIVISION_LABELS[division]}** : file vide")
                continue

            players = fetch_players(queue)
            player_map = {player.discord_id: player for player in players}

            lines.append(f"📋 **File {DIVISION_LABELS[division]}**")
            for index, discord_id in enumerate(queue, start=1):
                player = player_map.get(discord_id)
                elo = player.solo_elo if player else 1000
                lines.append(f"{index}. <@{discord_id}> ({elo} ELO)")
            lines.append("")

    await ctx.send("\n".join(lines) if lines else "Aucune file en cours.")


@bot.command(name="elosolo", aliases=["elo"])
async def elo_solo(ctx: commands.Context, member: Optional[discord.Member] = None):
    target = member or ctx.author
    player = fetch_player(target.id)
    if not player:
        division = determine_division(target) if isinstance(target, discord.Member) else "division2"
        player = ensure_player(target.id, target.display_name, division)

    total_games = player.solo_wins + player.solo_losses
    win_rate = (player.solo_wins / total_games * 100) if total_games else 0.0

    await ctx.send(
        f"📊 ELO Solo de {target.mention} ({DIVISION_LABELS[player.division]}) : {player.solo_elo} "
        f"({player.solo_wins} victoires / {player.solo_losses} défaites, {win_rate:.1f}% WR)"
    )


@bot.command(name="reportsolo")
async def report_solo(ctx: commands.Context, match_id: int, winner: str):
    match = load_match(match_id)
    if not match:
        await ctx.send("❌ Match introuvable.")
        return
    if match["status"] != "pending":
        await ctx.send("❌ Ce match a déjà été confirmé.")
        return

    team1_ids = json.loads(match["team1_ids"])
    team2_ids = json.loads(match["team2_ids"])
    all_player_ids = {int(pid) for pid in team1_ids + team2_ids}

    if ctx.author.id not in all_player_ids:
        await ctx.send("❌ Seuls les joueurs du match peuvent reporter le résultat.")
        return

    normalized = winner.lower()
    if normalized in {"blue", "bleu", "bleue", "team1", "t1"}:
        winning_ids = [int(pid) for pid in team1_ids]
        losing_ids = [int(pid) for pid in team2_ids]
        winner_label = "bleue"
    elif normalized in {"red", "rouge", "team2", "t2"}:
        winning_ids = [int(pid) for pid in team2_ids]
        losing_ids = [int(pid) for pid in team1_ids]
        winner_label = "rouge"
    else:
        await ctx.send("❌ Vainqueur invalide. Utilisez `blue` ou `red`.")
        return

    players = fetch_players(winning_ids + losing_ids)
    player_map = {player.discord_id: player for player in players}

    missing_players = [pid for pid in winning_ids + losing_ids if pid not in player_map]
    if missing_players:
        await ctx.send("❌ Impossible de récupérer certains joueurs en base de données.")
        return

    winner_avg = sum(player_map[pid].solo_elo for pid in winning_ids) / 3
    loser_avg = sum(player_map[pid].solo_elo for pid in losing_ids) / 3

    updates: List[Tuple[int, int, bool]] = []
    summary_lines = [
        f"✅ Match solo #{match_id} confirmé ({DIVISION_LABELS[match['division']]}) : "
        f"victoire équipe {winner_label}!"
    ]
    summary_lines.append("🔵 Équipe Bleue :")
    for pid in team1_ids:
        player = player_map[int(pid)]
        summary_lines.append(f"- <@{player.discord_id}> ({player.solo_elo} ELO)")
    summary_lines.append("🔴 Équipe Rouge :")
    for pid in team2_ids:
        player = player_map[int(pid)]
        summary_lines.append(f"- <@{player.discord_id}> ({player.solo_elo} ELO)")
    summary_lines.append("")

    for pid in winning_ids:
        player = player_map[pid]
        change = calculate_elo_change(player.solo_elo, loser_avg, True)
        new_elo = max(0, player.solo_elo + change)
        updates.append((pid, new_elo, True))
        summary_lines.append(
            f"🏆 <@{pid}> : {player.solo_elo} → {new_elo} ( +{change} )"
        )

    for pid in losing_ids:
        player = player_map[pid]
        change = calculate_elo_change(player.solo_elo, winner_avg, False)
        new_elo = max(0, player.solo_elo + change)
        updates.append((pid, new_elo, False))
        summary_lines.append(
            f"⚔️ <@{pid}> : {player.solo_elo} → {new_elo} ( {change:+} )"
        )

    apply_player_updates(updates)
    complete_match(match_id, winner_label)

    await ctx.send("\n".join(summary_lines))

    log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID) if ctx.guild else None
    if log_channel:
        await log_channel.send("\n".join(summary_lines))


@bot.command(name="help")
async def help_command(ctx: commands.Context):
    lines = [
        "🤖 **Commandes Matchmaking Solo**",
        "• `!joinsolo` – Rejoindre la file 3v3 de votre division",
        "• `!leavesolo` – Quitter la file",
        "• `!queuesolo` – Voir les files actuelles",
        "• `!elosolo [@joueur]` – Voir l'ELO solo",
        "• `!reportsolo <id> <blue|red>` – Valider un match",
    ]
    await ctx.send("\n".join(lines))


# ----------------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------------


async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    init_db()
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
