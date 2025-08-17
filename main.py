#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié
5 commandes seulement: !create, !join, !leave, !lobbies, !leaderboard
"""

import discord
from discord.ext import commands
import sqlite3
import os
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DB_PATH = 'simple_elo.db'

# Bot instance
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ================================
# DATABASE SIMPLE
# ================================

def init_db():
    """Initialise la base de données SQLite simple"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Table joueurs
    c.execute('''
        CREATE TABLE IF NOT EXISTS players (
            discord_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            elo INTEGER DEFAULT 1000,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0
        )
    ''')
    
    # Table lobbies
    c.execute('''
        CREATE TABLE IF NOT EXISTS lobbies (
            id INTEGER PRIMARY KEY,
            room_code TEXT NOT NULL,
            players TEXT DEFAULT '',
            max_players INTEGER DEFAULT 6,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def get_player(discord_id):
    """Récupère un joueur"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM players WHERE discord_id = ?', (str(discord_id),))
    result = c.fetchone()
    conn.close()
    return result

def create_player(discord_id, name):
    """Crée un nouveau joueur"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO players (discord_id, name) VALUES (?, ?)', 
              (str(discord_id), name))
    conn.commit()
    conn.close()

def update_player_elo(discord_id, new_elo, won):
    """Met à jour l'ELO d'un joueur"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if won:
        c.execute('UPDATE players SET elo = ?, wins = wins + 1 WHERE discord_id = ?', 
                 (new_elo, str(discord_id)))
    else:
        c.execute('UPDATE players SET elo = ?, losses = losses + 1 WHERE discord_id = ?', 
                 (new_elo, str(discord_id)))
    conn.commit()
    conn.close()

def get_leaderboard():
    """Récupère le classement"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM players ORDER BY elo DESC LIMIT 20')
    results = c.fetchall()
    conn.close()
    return results

def create_lobby(room_code):
    """Crée un lobby"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO lobbies (room_code) VALUES (?)', (room_code,))
    lobby_id = c.lastrowid
    conn.commit()
    conn.close()
    return lobby_id

def get_lobby(lobby_id):
    """Récupère un lobby"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM lobbies WHERE id = ?', (lobby_id,))
    result = c.fetchone()
    conn.close()
    return result

def add_player_to_lobby(lobby_id, discord_id):
    """Ajoute un joueur au lobby"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Récupérer le lobby
    c.execute('SELECT players FROM lobbies WHERE id = ?', (lobby_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return False, "Lobby inexistant"
    
    players = result[0].split(',') if result[0] else []
    
    # Vérifier si le joueur est déjà dans le lobby
    if str(discord_id) in players:
        conn.close()
        return False, "Déjà dans ce lobby"
    
    # Vérifier si le lobby est plein
    if len(players) >= 6:
        conn.close()
        return False, "Lobby complet"
    
    # Ajouter le joueur
    players.append(str(discord_id))
    players_str = ','.join(filter(None, players))
    
    c.execute('UPDATE lobbies SET players = ? WHERE id = ?', (players_str, lobby_id))
    conn.commit()
    conn.close()
    
    return True, f"Rejoint! ({len(players)}/6 joueurs)"

def remove_player_from_lobby(discord_id):
    """Retire un joueur de tous les lobbies"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Trouver le lobby du joueur
    c.execute('SELECT id, players FROM lobbies')
    lobbies = c.fetchall()
    
    for lobby_id, players_str in lobbies:
        players = players_str.split(',') if players_str else []
        if str(discord_id) in players:
            players.remove(str(discord_id))
            new_players_str = ','.join(filter(None, players))
            
            if new_players_str:
                # Lobby pas vide, juste mettre à jour
                c.execute('UPDATE lobbies SET players = ? WHERE id = ?', 
                         (new_players_str, lobby_id))
            else:
                # Lobby vide, supprimer
                c.execute('DELETE FROM lobbies WHERE id = ?', (lobby_id,))
            
            conn.commit()
            conn.close()
            return True, f"Quitté lobby {lobby_id}"
    
    conn.close()
    return False, "Vous n'êtes dans aucun lobby"

def get_all_lobbies():
    """Récupère tous les lobbies"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM lobbies')
    results = c.fetchall()
    conn.close()
    return results

def calculate_elo_change(player_elo, opponent_avg_elo, won):
    """Calcul ELO simplifié"""
    K = 30
    expected = 1 / (1 + 10 ** ((opponent_avg_elo - player_elo) / 400))
    actual = 1.0 if won else 0.0
    change = K * (actual - expected)
    return round(change)

# ================================
# BOT EVENTS
# ================================

@bot.event
async def on_ready():
    print(f'🤖 Bot connecté: {bot.user}')
    init_db()

# ================================
# COMMANDES ULTRA SIMPLES
# ================================

@bot.command(name='create')
async def create_lobby_cmd(ctx, room_code: str = None):
    """!create <code_room> - Créer un lobby"""
    if not room_code:
        await ctx.send("❌ **Usage:** `!create <code_room>`")
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
    
    # Créer le lobby
    lobby_id = create_lobby(room_code.upper())
    
    # Ajouter le créateur au lobby
    success, msg = add_player_to_lobby(lobby_id, ctx.author.id)
    
    if success:
        embed = discord.Embed(
            title="🎮 Lobby créé!",
            description=f"**Lobby #{lobby_id}**\nCode: `{room_code.upper()}`",
            color=0x00FF00
        )
        embed.add_field(name="Créateur", value=ctx.author.display_name, inline=True)
        embed.add_field(name="Joueurs", value="1/6", inline=True)
        embed.add_field(name="Rejoindre", value=f"`!join {lobby_id}`", inline=True)
    else:
        embed = discord.Embed(title="❌ Erreur", description=msg, color=0xFF0000)
    
    await ctx.send(embed=embed)

@bot.command(name='join')
async def join_lobby_cmd(ctx, lobby_id: int = None):
    """!join <id> - Rejoindre un lobby"""
    if lobby_id is None:
        await ctx.send("❌ **Usage:** `!join <id_lobby>`")
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
    
    # Rejoindre le lobby
    success, msg = add_player_to_lobby(lobby_id, ctx.author.id)
    
    if success:
        # Récupérer info lobby
        lobby = get_lobby(lobby_id)
        if lobby:
            players_count = len(lobby[2].split(',')) if lobby[2] else 0
            
            embed = discord.Embed(
                title="✅ Lobby rejoint!",
                description=msg,
                color=0x00FF00
            )
            embed.add_field(name="Lobby", value=f"#{lobby_id}", inline=True)
            embed.add_field(name="Code", value=f"`{lobby[1]}`", inline=True)
            embed.add_field(name="Joueurs", value=f"{players_count}/6", inline=True)
            
            # Si lobby plein, lancer le match
            if players_count >= 6:
                embed.add_field(name="🚀 MATCH!", value="Lobby complet! Match lancé!", inline=False)
                embed.color = 0xFFD700
        else:
            embed = discord.Embed(title="✅ Rejoint", description=msg, color=0x00FF00)
    else:
        embed = discord.Embed(title="❌ Erreur", description=msg, color=0xFF0000)
    
    await ctx.send(embed=embed)

@bot.command(name='leave')
async def leave_lobby_cmd(ctx):
    """!leave - Quitter votre lobby"""
    success, msg = remove_player_from_lobby(ctx.author.id)
    
    if success:
        embed = discord.Embed(title="👋 Quitté", description=msg, color=0xFFFF00)
    else:
        embed = discord.Embed(title="❌ Erreur", description=msg, color=0xFF0000)
    
    await ctx.send(embed=embed)

@bot.command(name='lobbies')
async def list_lobbies_cmd(ctx):
    """!lobbies - Liste des lobbies actifs"""
    lobbies = get_all_lobbies()
    
    if not lobbies:
        embed = discord.Embed(
            title="📋 Aucun lobby",
            description="Créez le premier avec `!create <code>`",
            color=0x808080
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(title="🎮 Lobbies actifs", color=0x5865F2)
    
    for lobby in lobbies:
        lobby_id, room_code, players_str, max_players, created_at = lobby
        players_count = len(players_str.split(',')) if players_str else 0
        
        status = "🟢" if players_count < 6 else "🔴"
        embed.add_field(
            name=f"{status} Lobby #{lobby_id}",
            value=f"Code: `{room_code}`\nJoueurs: {players_count}/6",
            inline=True
        )
    
    embed.set_footer(text=f"{len(lobbies)} lobby(s) actif(s)")
    await ctx.send(embed=embed)

@bot.command(name='leaderboard', aliases=['top'])
async def leaderboard_cmd(ctx):
    """!leaderboard - Classement des joueurs"""
    players = get_leaderboard()
    
    if not players:
        embed = discord.Embed(
            title="📊 Classement vide",
            description="Aucun joueur inscrit",
            color=0x808080
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(title="🏆 Classement ELO", color=0xFFD700)
    
    leaderboard_text = ""
    for i, player in enumerate(players[:10], 1):
        discord_id, name, elo, wins, losses = player
        total_games = wins + losses
        winrate = round(wins / total_games * 100, 1) if total_games > 0 else 0
        
        if i == 1:
            emoji = "🥇"
        elif i == 2:
            emoji = "🥈"
        elif i == 3:
            emoji = "🥉"
        else:
            emoji = f"{i}."
        
        leaderboard_text += f"{emoji} **{name}** - {elo} ELO ({winrate}%)\n"
    
    embed.description = leaderboard_text
    embed.set_footer(text=f"{len(players)} joueur(s) total")
    
    # Position du joueur actuel
    current_player = get_player(ctx.author.id)
    if current_player:
        current_pos = next((i for i, p in enumerate(players, 1) if p[0] == str(ctx.author.id)), None)
        if current_pos:
            embed.add_field(
                name="Votre position",
                value=f"#{current_pos} - {current_player[2]} ELO",
                inline=True
            )
    
    await ctx.send(embed=embed)

# ================================
# COMMANDES ADMIN SIMPLES
# ================================

@bot.command(name='result')
@commands.has_permissions(administrator=True)
async def record_match_result(ctx, winner1: discord.Member, winner2: discord.Member, winner3: discord.Member,
                             loser1: discord.Member, loser2: discord.Member, loser3: discord.Member):
    """!result @w1 @w2 @w3 @l1 @l2 @l3 - Enregistrer un match"""
    winners = [winner1, winner2, winner3]
    losers = [loser1, loser2, loser3]
    
    # Vérifier que tous sont inscrits
    all_players = winners + losers
    for member in all_players:
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
    
    # Calculer nouveaux ELO
    winner_elos = []
    loser_elos = []
    
    for member in winners:
        player = get_player(member.id)
        winner_elos.append(player[2])  # ELO
    
    for member in losers:
        player = get_player(member.id)
        loser_elos.append(player[2])  # ELO
    
    winner_avg = sum(winner_elos) / 3
    loser_avg = sum(loser_elos) / 3
    
    # Mettre à jour ELO
    embed = discord.Embed(title="⚔️ Match enregistré!", color=0x00FF00)
    
    winners_text = ""
    for i, member in enumerate(winners):
        old_elo = winner_elos[i]
        change = calculate_elo_change(old_elo, loser_avg, True)
        new_elo = max(0, old_elo + change)
        update_player_elo(member.id, new_elo, True)
        winners_text += f"**{member.display_name}:** {old_elo} → {new_elo} (+{change})\n"
    
    losers_text = ""
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        change = calculate_elo_change(old_elo, winner_avg, False)
        new_elo = max(0, old_elo + change)
        update_player_elo(member.id, new_elo, False)
        losers_text += f"**{member.display_name}:** {old_elo} → {new_elo} ({change:+})\n"
    
    embed.add_field(name="🏆 Gagnants", value=winners_text, inline=True)
    embed.add_field(name="💀 Perdants", value=losers_text, inline=True)
    
    await ctx.send(embed=embed)

# ================================
# LANCEMENT DU BOT
# ================================

if __name__ == '__main__':
    if not TOKEN:
        print("❌ DISCORD_TOKEN manquant!")
        exit(1)
    
    print("🚀 Lancement du bot ELO ultra simplifié...")
    bot.run(TOKEN)
