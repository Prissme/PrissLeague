#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple 3v3 ELO matchmaking bot for Null's Brawl."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import string
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

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

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
queue_lock = asyncio.Lock()
trio_queue: List[int] = []

# ----------------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------------


def get_connection():
    """Create a PostgreSQL connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db() -> None:
    """Ensure the required tables exist."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    discord_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trio_elo INTEGER NOT NULL DEFAULT 1000,
                    trio_wins INTEGER NOT NULL DEFAULT 0,
                    trio_losses INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trio_matches (
                    id SERIAL PRIMARY KEY,
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
    trio_elo: int
    trio_wins: int
    trio_losses: int

    @classmethod
    def from_row(cls, row: Dict) -> "Player":
        return cls(
            discord_id=int(row["discord_id"]),
            name=row.get("name", "Unknown"),
            trio_elo=int(row.get("trio_elo", 1000)),
            trio_wins=int(row.get("trio_wins", 0)),
            trio_losses=int(row.get("trio_losses", 0)),
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


def ensure_player(discord_id: int, name: str) -> Player:
    """Create the player if needed and return the player row."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO players (discord_id, name)
                VALUES (%s, %s)
                ON CONFLICT (discord_id) DO UPDATE SET name = EXCLUDED.name
                RETURNING discord_id, name, trio_elo, trio_wins, trio_losses
                """,
                (str(discord_id), name),
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
                SELECT discord_id, name, trio_elo, trio_wins, trio_losses
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


def record_match(team1_ids: Sequence[int], team2_ids: Sequence[int], room_code: str) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO trio_matches (team1_ids, team2_ids, room_code)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (json.dumps(list(map(int, team1_ids))), json.dumps(list(map(int, team2_ids))), room_code),
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
                FROM trio_matches
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
                UPDATE trio_matches
                SET status = 'completed', winner = %s, completed_at = NOW()
                WHERE id = %s
                """,
                (winner, match_id),
            )
        conn.commit()
    finally:
        conn.close()


def apply_player_updates(updates: Iterable[tuple[int, int, bool]]) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for discord_id, new_elo, won in updates:
                if won:
                    cursor.execute(
                        """
                        UPDATE players
                        SET trio_elo = %s, trio_wins = trio_wins + 1
                        WHERE discord_id = %s
                        """,
                        (new_elo, str(discord_id)),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE players
                        SET trio_elo = %s, trio_losses = trio_losses + 1
                        WHERE discord_id = %s
                        """,
                        (new_elo, str(discord_id)),
                    )
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Matchmaking logic
# ----------------------------------------------------------------------------


def format_queue_position() -> str:
    return f"{len(trio_queue)}/{QUEUE_TARGET_SIZE} joueurs dans la file trio"


async def create_match_if_possible(channel: discord.abc.Messageable) -> None:
    async with queue_lock:
        if len(trio_queue) < QUEUE_TARGET_SIZE:
            return
        queue_snapshot = list(trio_queue)

    players = fetch_players(queue_snapshot)
    player_map: Dict[int, Player] = {player.discord_id: player for player in players}

    # Ensure we have data for everyone in the queue snapshot
    missing = [pid for pid in queue_snapshot if pid not in player_map]
    if missing:
        for pid in missing:
            logger.warning("Missing player %s in database, creating default entry", pid)
            member = channel.guild.get_member(pid) if isinstance(channel, discord.abc.GuildChannel) else None
            name = member.display_name if member else f"Joueur {pid}"
            player = ensure_player(pid, name)
            player_map[pid] = player

    sorted_ids = sorted(queue_snapshot, key=lambda pid: player_map[pid].trio_elo)
    selected_ids = sorted_ids[:QUEUE_TARGET_SIZE]
    selected_set = set(selected_ids)

    async with queue_lock:
        trio_queue[:] = [pid for pid in trio_queue if pid not in selected_set]

    team1_ids = selected_ids[::2]
    team2_ids = selected_ids[1::2]
    team1_players = [player_map[pid] for pid in team1_ids]
    team2_players = [player_map[pid] for pid in team2_ids]

    room_code = generate_room_code()
    match_id = record_match(team1_ids, team2_ids, room_code)

    def describe_team(title: str, team_players: List[Player]) -> List[str]:
        average_elo = round(sum(p.trio_elo for p in team_players) / len(team_players))
        lines = [f"{title} (moyenne {average_elo} ELO)"]
        for p in team_players:
            lines.append(f"- <@{p.discord_id}> ({p.trio_elo} ELO)")
        return lines

    message_lines = [
        f"🎮 **Match Trio #{match_id} prêt !**",
        f"Code Null's Brawl : `{room_code}`",
        "Signalez le vainqueur avec `!reporttrio {match_id} blue` ou `!reporttrio {match_id} red`.",
        "",
    ]
    message_lines.extend(describe_team("🔵 Équipe Bleue", team1_players))
    message_lines.append("")
    message_lines.extend(describe_team("🔴 Équipe Rouge", team2_players))
    message_lines.append("")
    message_lines.append(f"🔗 https://link.nulls.gg/nb/invite/gameroom/fr?tag={room_code}")

    await channel.send("\n".join(message_lines))


# ----------------------------------------------------------------------------
# Bot events & commands
# ----------------------------------------------------------------------------


@bot.event
async def on_ready():
    logger.info("Logged in as %s", bot.user)


@bot.command(name="jointrio")
async def join_trio(ctx: commands.Context):
    member = ctx.author
    player = ensure_player(member.id, member.display_name)

    async with queue_lock:
        if member.id in trio_queue:
            await ctx.send(f"{member.mention} est déjà dans la file trio. ({format_queue_position()})")
            return
        trio_queue.append(member.id)
        position = len(trio_queue)

    await ctx.send(
        f"✅ {member.mention} rejoint la file trio (ELO {player.trio_elo}). "
        f"Position : {position}/{QUEUE_TARGET_SIZE}."
    )
    await create_match_if_possible(ctx.channel)


@bot.command(name="leavetrio")
async def leave_trio(ctx: commands.Context):
    member = ctx.author
    async with queue_lock:
        if member.id not in trio_queue:
            await ctx.send(f"{member.mention} n'est pas dans la file trio.")
            return
        trio_queue.remove(member.id)

    await ctx.send(f"👋 {member.mention} quitte la file trio. ({format_queue_position()})")


@bot.command(name="queuetrio")
async def queue_trio(ctx: commands.Context):
    async with queue_lock:
        queue_snapshot = list(trio_queue)

    if not queue_snapshot:
        await ctx.send("La file trio est vide.")
        return

    players = fetch_players(queue_snapshot)
    player_map = {player.discord_id: player for player in players}

    lines = ["📋 **File Trio en cours**"]
    for index, discord_id in enumerate(queue_snapshot, start=1):
        player = player_map.get(discord_id)
        elo = player.trio_elo if player else 1000
        lines.append(f"{index}. <@{discord_id}> ({elo} ELO)")

    await ctx.send("\n".join(lines))


@bot.command(name="elotrio")
async def elo_trio(ctx: commands.Context, member: Optional[discord.Member] = None):
    target = member or ctx.author
    player = fetch_player(target.id)
    if not player:
        player = ensure_player(target.id, target.display_name)

    await ctx.send(
        f"📊 ELO Trio de {target.mention} : {player.trio_elo} ("
        f"{player.trio_wins} victoires / {player.trio_losses} défaites)"
    )


@bot.command(name="reporttrio")
async def report_trio(ctx: commands.Context, match_id: int, winner: str):
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

    winner_avg = sum(player_map[pid].trio_elo for pid in winning_ids) / 3
    loser_avg = sum(player_map[pid].trio_elo for pid in losing_ids) / 3

    updates: List[tuple[int, int, bool]] = []
    summary_lines = [f"✅ Match #{match_id} confirmé : victoire équipe {winner_label}!"]
    summary_lines.append("🔵 Équipe Bleue :")
    for pid in team1_ids:
        player = player_map[int(pid)]
        summary_lines.append(f"- <@{player.discord_id}> ({player.trio_elo} ELO)")
    summary_lines.append("🔴 Équipe Rouge :")
    for pid in team2_ids:
        player = player_map[int(pid)]
        summary_lines.append(f"- <@{player.discord_id}> ({player.trio_elo} ELO)")
    summary_lines.append("")

    for pid in winning_ids:
        player = player_map[pid]
        change = calculate_elo_change(player.trio_elo, loser_avg, True)
        new_elo = max(0, player.trio_elo + change)
        updates.append((pid, new_elo, True))
        summary_lines.append(
            f"🏆 <@{pid}> : {player.trio_elo} → {new_elo} ( +{change} )"
        )

    for pid in losing_ids:
        player = player_map[pid]
        change = calculate_elo_change(player.trio_elo, winner_avg, False)
        new_elo = max(0, player.trio_elo + change)
        updates.append((pid, new_elo, False))
        summary_lines.append(
            f"⚔️ <@{pid}> : {player.trio_elo} → {new_elo} ( {change:+} )"
        )

    apply_player_updates(updates)
    complete_match(match_id, winner_label)

    await ctx.send("\n".join(summary_lines))


@bot.command(name="help")
async def help_command(ctx: commands.Context):
    lines = [
        "🤖 **Commandes Matchmaking Trio**",
        "• `!jointrio` – Rejoindre la file 3v3",
        "• `!leavetrio` – Quitter la file",
        "• `!queuetrio` – Voir la file actuelle",
        "• `!elotrio [@joueur]` – Voir l'ELO trio",
        "• `!reporttrio <id> <blue|red>` – Valider un match",
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
