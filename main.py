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
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import discord
import psycopg2
from discord.ext import commands
from psycopg2.extras import RealDictCursor

from smart_migration import ensure_players_schema

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

MAP_ROTATION = [
    {
        "mode": "Razzia de gemmes",
        "emoji": "<:GemGrab:1436473738765008976>",
        "maps": ["Mine hard-rock", "Tunnel de mine", "Bruissements"],
    },
    {
        "mode": "Brawlball",
        "emoji": "<:Brawlball:1436473735573143562>",
        "maps": ["Tir au buts", "Super plage", "Triple Dribble"],
    },
    {
        "mode": "Hors-jeu",
        "emoji": "<:KnockOut:1436473703083937914>",
        "maps": ["Rocher de la belle", "Ravin du bras d'or", "À découvert"],
    },
    {
        "mode": "Braquage",
        "emoji": "<:Heist:1436473730812481546>",
        "maps": ["C'est chaud patate", "Arrêt au stand", "Zone sécurisée"],
    },
    {
        "mode": "Zone réservée",
        "emoji": "<:HotZone:1436473698491175137>",
        "maps": ["Duel de scarabées", "Cercle de feu", "Stratégies parallèles"],
    },
    {
        "mode": "Prime",
        "emoji": "<:Bounty:1436473727519948962>",
        "maps": ["Cachette secrète", "Étoile filante", "Mille-feuille"],
    },
]

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
vote_lock = asyncio.Lock()
solo_queues: Dict[str, List[int]] = {"division1": [], "division2": []}
match_votes: Dict[int, Dict[int, str]] = {}

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
            ensure_players_schema(cursor)

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


def finalize_match_result(
    match_id: int, winner_label: str, guild: Optional[discord.Guild]
) -> Optional[str]:
    match = load_match(match_id)
    if not match or match["status"] != "pending":
        return None

    team1_ids = [int(pid) for pid in json.loads(match["team1_ids"])]
    team2_ids = [int(pid) for pid in json.loads(match["team2_ids"])]

    if winner_label == "bleue":
        winning_ids = team1_ids
        losing_ids = team2_ids
    elif winner_label == "rouge":
        winning_ids = team2_ids
        losing_ids = team1_ids
    else:
        raise ValueError(f"Winner label '{winner_label}' invalide")

    players = fetch_players(winning_ids + losing_ids)
    player_map = {player.discord_id: player for player in players}

    missing_ids = [pid for pid in winning_ids + losing_ids if pid not in player_map]
    for pid in missing_ids:
        member = guild.get_member(pid) if guild else None
        name = member.display_name if member else f"Joueur {pid}"
        division = (
            determine_division(member)
            if member and isinstance(member, discord.Member)
            else match["division"]
        )
        player_map[pid] = ensure_player(pid, name, division)

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

    return "\n".join(summary_lines)


class MatchVoteView(discord.ui.View):
    def __init__(
        self,
        match_id: int,
        team1_ids: Sequence[int],
        team2_ids: Sequence[int],
    ) -> None:
        super().__init__(timeout=None)
        self.match_id = match_id
        self.team1_ids = {int(pid) for pid in team1_ids}
        self.team2_ids = {int(pid) for pid in team2_ids}
        self.participants = self.team1_ids | self.team2_ids
        self.majority = len(self.participants) // 2 + 1
        match_votes.setdefault(match_id, {})

    async def _register_vote(self, interaction: discord.Interaction, winner: str) -> None:
        if interaction.user.id not in self.participants:
            await interaction.response.send_message(
                "❌ Seuls les joueurs du match peuvent voter.", ephemeral=True
            )
            return

        async with vote_lock:
            votes = match_votes.setdefault(self.match_id, {})
            votes[interaction.user.id] = winner
            counts = Counter(votes.values())
            majority_reached = counts.get(winner, 0) >= self.majority

        await interaction.response.send_message(
            "🗳️ Votre vote a été enregistré.", ephemeral=True
        )

        if not majority_reached:
            return

        summary = finalize_match_result(self.match_id, winner, interaction.guild)
        if not summary:
            return

        match_votes.pop(self.match_id, None)
        self.disable_all_items()
        try:
            await interaction.message.edit(view=self)
        except (discord.HTTPException, AttributeError):
            pass

        channel = interaction.channel
        if channel:
            await channel.send(summary)

        if interaction.guild:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(summary)

    @discord.ui.button(label="Victoire Bleue", style=discord.ButtonStyle.primary, emoji="🔵")
    async def vote_blue(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._register_vote(interaction, "bleue")

    @discord.ui.button(label="Victoire Rouge", style=discord.ButtonStyle.danger, emoji="🔴")
    async def vote_red(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._register_vote(interaction, "rouge")


async def send_match_message(
    guild: discord.Guild, content: str, view: Optional[discord.ui.View] = None
) -> None:
    channel = guild.get_channel(MATCH_CHANNEL_ID) if guild else None
    if channel is None and guild and guild.system_channel:
        channel = guild.system_channel
    if channel is None:
        logger.warning("No channel available to send match message")
        return
    await channel.send(content, view=view)


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
        "Créez la room via `/room` en complétant le code ci-dessus.",
        "Votez pour l'équipe gagnante avec les boutons ci-dessous.",
        "",
    ]
    message_lines.extend(describe_team("🔵 Équipe Bleue", team1_players))
    message_lines.append("")
    message_lines.extend(describe_team("🔴 Équipe Rouge", team2_players))
    message_lines.append("")
    message_lines.append(f"🔗 https://link.nulls.gg/nb/invite/gameroom/fr?tag={room_code}")

    view = MatchVoteView(match_id, team1_ids, team2_ids)
    selected_modes = random.sample(MAP_ROTATION, k=min(3, len(MAP_ROTATION)))
    picked_maps = [
        (
            mode_info["mode"],
            random.choice(mode_info["maps"]),
            mode_info["emoji"],
        )
        for mode_info in selected_modes
    ]

    if picked_maps:
        message_lines.append("")
        message_lines.append("🗺️ **Maps à jouer**")
        for mode_name, map_name, emoji in picked_maps:
            message_lines.append(f"• {emoji} {mode_name} : {map_name}")

    await send_match_message(guild, "\n".join(message_lines), view=view)

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


@bot.command(name="join")
async def join(ctx: commands.Context):
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


@bot.command(name="leave")
async def leave(ctx: commands.Context):
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


@bot.command(name="queue")
async def queue(ctx: commands.Context):
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


@bot.command(name="maps")
async def maps_command(ctx: commands.Context):
    lines = ["🗺️ **Rotation des maps disponibles**", ""]
    for mode_info in MAP_ROTATION:
        emoji = mode_info["emoji"]
        mode = mode_info["mode"]
        maps = ", ".join(mode_info["maps"])
        lines.append(f"{emoji} **{mode}** : {maps}")

    await ctx.send("\n".join(lines))


@bot.command(name="elo")
async def elo_command(ctx: commands.Context, member: Optional[discord.Member] = None):
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


@bot.command(name="resetstats")
@commands.has_permissions(administrator=True)
async def reset_stats(ctx: commands.Context):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE players
                SET solo_elo = 1000,
                    solo_wins = 0,
                    solo_losses = 0
                """
            )
        conn.commit()
    finally:
        conn.close()

    async with queue_lock:
        for queue in solo_queues.values():
            queue.clear()

    await ctx.send("♻️ Toutes les statistiques des joueurs ont été réinitialisées.")


@reset_stats.error
async def reset_stats_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Vous n'avez pas la permission de réinitialiser les statistiques.")
    else:
        raise error


@bot.command(name="help")
async def help_command(ctx: commands.Context):
    lines = [
        "🤖 **Commandes Matchmaking Solo**",
        "• `!join` – Rejoindre la file 3v3 de votre division",
        "• `!leave` – Quitter la file",
        "• `!queue` – Voir les files actuelles",
        "• `!elo [@joueur]` – Voir l'ELO solo",
        "• Votez pour le vainqueur grâce aux boutons du match",
        "• `!resetstats` – Réinitialiser toutes les stats (administrateurs)",
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
