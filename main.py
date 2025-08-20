#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié
5 commandes seulement: !create, !join, !leave, !lobbies, !leaderboard
Base de données PostgreSQL pour Koyeb
"""

import discord
from discord.ext import commands
from discord import app_commands
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import logging
import random

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Maps Brawl Stars
MAPS = [
    "Mine Hard Rock",
    "Fort de Gemmes", 
    "Tunnel de Mine",
    "Triple Dribble",
    "Milieu de Scène", 
    "Ligue Junior",
    "Étoile Filante",
    "Mille-Feuille",
    "Cachette Secrète",
    "C'est Chaud Patate",
    "Zone Sécurisée",
    "Pont au Loin",
    "C'est Ouvert !",
    "Cercle de Feu",
    "Rocher de la Belle",
    "Ravin du Bras d'Or"
]

def create_random_teams(player_ids):
    """Crée 2 équipes aléatoires équilibrées"""
    # Mélanger les joueurs
    shuffled = player_ids.copy()
    random.shuffle(shuffled)
    
    # Diviser en 2 équipes
    team1 = shuffled[:3]
    team2 = shuffled[3:6]
    
    return team1, team2

def select_random_maps(count=3):
    """Sélectionne des maps aléatoires"""
    return random.sample(MAPS, min(count, len(MAPS)))

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Bot instance
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ================================
# DATABASE POSTGRESQL
# ================================

def get_connection():
    """Obtient une connexion à la base PostgreSQL"""
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Erreur connexion DB: {e}")
        return None

def init_db():
    """Initialise la base de données PostgreSQL"""
    conn = get_connection()
    if not conn:
        logger.error("Impossible de se connecter à la base de données")
        return
    
    try:
        with conn.cursor() as c:
            # Table joueurs
            c.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    discord_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    elo INTEGER DEFAULT 1000,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table lobbies
            c.execute('''
                CREATE TABLE IF NOT EXISTS lobbies (
                    id SERIAL PRIMARY KEY,
                    room_code TEXT NOT NULL,
                    players TEXT DEFAULT '',
                    max_players INTEGER DEFAULT 6,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logger.info("Base de données initialisée avec succès")
    except Exception as e:
        logger.error(f"Erreur initialisation DB: {e}")
    finally:
        conn.close()

def get_player(discord_id):
    """Récupère un joueur"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT * FROM players WHERE discord_id = %s', (str(discord_id),))
            result = c.fetchone()
            return dict(result) if result else None
    except Exception as e:
        logger.error(f"Erreur get_player: {e}")
        return None
    finally:
        conn.close()

def create_player(discord_id, name):
    """Crée un nouveau joueur"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            c.execute('''
                INSERT INTO players (discord_id, name) 
                VALUES (%s, %s) 
                ON CONFLICT (discord_id) DO NOTHING
            ''', (str(discord_id), name))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur create_player: {e}")
        return False
    finally:
        conn.close()

def update_player_elo(discord_id, new_elo, won):
    """Met à jour l'ELO d'un joueur"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            if won:
                c.execute('''
                    UPDATE players 
                    SET elo = %s, wins = wins + 1 
                    WHERE discord_id = %s
                ''', (new_elo, str(discord_id)))
            else:
                c.execute('''
                    UPDATE players 
                    SET elo = %s, losses = losses + 1 
                    WHERE discord_id = %s
                ''', (new_elo, str(discord_id)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur update_player_elo: {e}")
        return False
    finally:
        conn.close()

def get_leaderboard():
    """Récupère le classement"""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT * FROM players ORDER BY elo DESC LIMIT 20')
            results = c.fetchall()
            return [dict(row) for row in results] if results else []
    except Exception as e:
        logger.error(f"Erreur get_leaderboard: {e}")
        return []
    finally:
        conn.close()

def create_lobby(room_code):
    """Crée un lobby"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as c:
            c.execute('INSERT INTO lobbies (room_code) VALUES (%s) RETURNING id', (room_code,))
            lobby_id = c.fetchone()['id']
            conn.commit()
            return lobby_id
    except Exception as e:
        logger.error(f"Erreur create_lobby: {e}")
        return None
    finally:
        conn.close()

def get_lobby(lobby_id):
    """Récupère un lobby"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT * FROM lobbies WHERE id = %s', (lobby_id,))
            result = c.fetchone()
            return dict(result) if result else None
    except Exception as e:
        logger.error(f"Erreur get_lobby: {e}")
        return None
    finally:
        conn.close()

def add_player_to_lobby(lobby_id, discord_id):
    """Ajoute un joueur au lobby"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Récupérer le lobby
            c.execute('SELECT players FROM lobbies WHERE id = %s', (lobby_id,))
            result = c.fetchone()
            if not result:
                return False, "Lobby inexistant"
            
            players = result['players'].split(',') if result['players'] else []
            
            # Vérifier si le joueur est déjà dans le lobby
            if str(discord_id) in players:
                return False, "Déjà dans ce lobby"
            
            # Vérifier si le lobby est plein
            if len(players) >= 6:
                return False, "Lobby complet"
            
            # Ajouter le joueur
            players.append(str(discord_id))
            players_str = ','.join(filter(None, players))
            
            c.execute('UPDATE lobbies SET players = %s WHERE id = %s', (players_str, lobby_id))
            conn.commit()
            
            return True, f"Rejoint! ({len(players)}/6 joueurs)"
    except Exception as e:
        logger.error(f"Erreur add_player_to_lobby: {e}")
        return False, "Erreur interne"
    finally:
        conn.close()

def remove_player_from_lobby(discord_id):
    """Retire un joueur de tous les lobbies"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Trouver le lobby du joueur
            c.execute('SELECT id, players FROM lobbies')
            lobbies = c.fetchall()
            
            for lobby in lobbies:
                lobby_id = lobby['id']
                players_str = lobby['players']
                players = players_str.split(',') if players_str else []
                
                if str(discord_id) in players:
                    players.remove(str(discord_id))
                    new_players_str = ','.join(filter(None, players))
                    
                    if new_players_str:
                        # Lobby pas vide, juste mettre à jour
                        c.execute('UPDATE lobbies SET players = %s WHERE id = %s', 
                                 (new_players_str, lobby_id))
                    else:
                        # Lobby vide, supprimer
                        c.execute('DELETE FROM lobbies WHERE id = %s', (lobby_id,))
                    
                    conn.commit()
                    return True, f"Quitté lobby {lobby_id}"
            
            return False, "Vous n'êtes dans aucun lobby"
    except Exception as e:
        logger.error(f"Erreur remove_player_from_lobby: {e}")
        return False, "Erreur interne"
    finally:
        conn.close()

def get_all_lobbies():
    """Récupère tous les lobbies"""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT * FROM lobbies ORDER BY created_at DESC')
            results = c.fetchall()
            return [dict(row) for row in results] if results else []
    except Exception as e:
        logger.error(f"Erreur get_all_lobbies: {e}")
        return []
    finally:
        conn.close()

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
    print(f'🐘 Connexion PostgreSQL: {"✅" if get_connection() else "❌"}')
    init_db()
    
    # Synchroniser les commandes slash
    try:
        synced = await bot.tree.sync()
        print(f'📡 {len(synced)} commande(s) slash synchronisée(s)')
    except Exception as e:
        print(f'❌ Erreur synchronisation: {e}')

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
        if not create_player(ctx.author.id, ctx.author.display_name):
            await ctx.send("❌ **Erreur:** Impossible de créer votre profil")
            return
    
    # Créer le lobby
    lobby_id = create_lobby(room_code.upper())
    if not lobby_id:
        await ctx.send("❌ **Erreur:** Impossible de créer le lobby")
        return
    
    # Ajouter le créateur au lobby
    success, msg = add_player_to_lobby(lobby_id, ctx.author.id)
    
    if success:
        await ctx.send(f"🎮 **Lobby créé!**\n"
                      f"**Lobby #{lobby_id}**\n"
                      f"Code: `{room_code.upper()}`\n"
                      f"Créateur: {ctx.author.display_name}\n"
                      f"Joueurs: 1/6\n"
                      f"Rejoindre: `!join {lobby_id}`")
    else:
        await ctx.send(f"❌ **Erreur:** {msg}")

@bot.command(name='join')
async def join_lobby_cmd(ctx, lobby_id: int = None):
    """!join <id> - Rejoindre un lobby"""
    if lobby_id is None:
        await ctx.send("❌ **Usage:** `!join <id_lobby>`")
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        if not create_player(ctx.author.id, ctx.author.display_name):
            await ctx.send("❌ **Erreur:** Impossible de créer votre profil")
            return
    
    # Rejoindre le lobby
    success, msg = add_player_to_lobby(lobby_id, ctx.author.id)
    
    if success:
        # Récupérer info lobby
        lobby = get_lobby(lobby_id)
        if lobby:
            players_list = lobby['players'].split(',') if lobby['players'] else []
            players_count = len(players_list)
            
            if players_count >= 6:
                # Créer les équipes aléatoires
                team1_ids, team2_ids = create_random_teams(players_list)
                
                # Récupérer les noms des joueurs
                team1_names = []
                team2_names = []
                
                for player_id in team1_ids:
                    player = get_player(player_id)
                    if player:
                        team1_names.append(player['name'])
                
                for player_id in team2_ids:
                    player = get_player(player_id)
                    if player:
                        team2_names.append(player['name'])
                
                # Sélectionner 3 maps aléatoires
                selected_maps = select_random_maps(3)
                
                team1_text = '\n'.join([f"• {name}" for name in team1_names])
                team2_text = '\n'.join([f"• {name}" for name in team2_names])
                maps_text = '\n'.join([f"• {map_name}" for map_name in selected_maps])
                
                await ctx.send(f"🚀 **MATCH LANCÉ!**\n"
                              f"Lobby #{lobby_id} complet! Équipes créées!\n\n"
                              f"🔵 **Équipe 1:**\n{team1_text}\n\n"
                              f"🔴 **Équipe 2:**\n{team2_text}\n\n"
                              f"🗺️ **Maps:**\n{maps_text}\n\n"
                              f"🎮 **Code:** `{lobby['room_code']}`")
                
                # Supprimer le lobby maintenant qu'il est lancé
                conn = get_connection()
                if conn:
                    try:
                        with conn.cursor() as c:
                            c.execute('DELETE FROM lobbies WHERE id = %s', (lobby_id,))
                            conn.commit()
                    finally:
                        conn.close()
            else:
                await ctx.send(f"✅ **Lobby rejoint!**\n"
                              f"{msg}\n"
                              f"Lobby: #{lobby_id}\n"
                              f"Code: `{lobby['room_code']}`\n"
                              f"Joueurs: {players_count}/6")
        else:
            await ctx.send(f"✅ **Rejoint:** {msg}")
    else:
        await ctx.send(f"❌ **Erreur:** {msg}")

@bot.command(name='leave')
async def leave_lobby_cmd(ctx):
    """!leave - Quitter votre lobby"""
    success, msg = remove_player_from_lobby(ctx.author.id)
    
    if success:
        await ctx.send(f"👋 **Quitté:** {msg}")
    else:
        await ctx.send(f"❌ **Erreur:** {msg}")

@bot.command(name='lobbies')
async def list_lobbies_cmd(ctx):
    """!lobbies - Liste des lobbies actifs"""
    lobbies = get_all_lobbies()
    
    if not lobbies:
        await ctx.send("📋 **Aucun lobby**\nCréez le premier avec `!create <code>`")
        return
    
    message = "🎮 **Lobbies actifs:**\n\n"
    
    for lobby in lobbies:
        lobby_id = lobby['id']
        room_code = lobby['room_code']
        players_str = lobby['players']
        players_count = len(players_str.split(',')) if players_str else 0
        
        status = "🟢" if players_count < 6 else "🔴"
        message += f"{status} **Lobby #{lobby_id}**\n"
        message += f"Code: `{room_code}`\n"
        message += f"Joueurs: {players_count}/6\n\n"
    
    message += f"{len(lobbies)} lobby(s) actif(s)"
    await ctx.send(message)

@bot.command(name='elo')
async def show_elo_cmd(ctx):
    """!elo - Voir son ELO et rang"""
    player = get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ **Non inscrit**\n"
                      "Utilisez `!create <code>` ou `!join <id>` pour vous inscrire automatiquement")
        return
    
    name = player['name']
    elo = player['elo']
    wins = player['wins']
    losses = player['losses']
    
    total_games = wins + losses
    winrate = round(wins / total_games * 100, 1) if total_games > 0 else 0
    
    # Calculer le rang
    players = get_leaderboard()
    rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(ctx.author.id)), len(players))
    
    await ctx.send(f"📊 **{name}**\n"
                  f"**ELO:** {elo} points\n"
                  f"**Rang:** #{rank}/{len(players)}\n"
                  f"**Victoires:** {wins}\n"
                  f"**Défaites:** {losses}\n"
                  f"**Winrate:** {winrate}%")

@bot.command(name='leaderboard', aliases=['top'])
async def leaderboard_cmd(ctx):
    """!leaderboard - Classement des joueurs"""
    players = get_leaderboard()
    
    if not players:
        await ctx.send("📊 **Classement vide**\nAucun joueur inscrit")
        return
    
    message = "🏆 **Classement ELO**\n\n"
    
    for i, player in enumerate(players[:10], 1):
        name = player['name']
        elo = player['elo']
        wins = player['wins']
        losses = player['losses']
        
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
        
        message += f"{emoji} **{name}** - {elo} ELO ({winrate}%)\n"
    
    message += f"\n{len(players)} joueur(s) total"
    
    # Position du joueur actuel
    current_player = get_player(ctx.author.id)
    if current_player:
        current_pos = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(ctx.author.id)), None)
        if current_pos:
            message += f"\n\n**Votre position:** #{current_pos} - {current_player['elo']} ELO"
    
    await ctx.send(message)

# ================================
# COMMANDES ADMIN SIMPLES
# ================================

@app_commands.command(name="results", description="Enregistrer un résultat de match")
@app_commands.describe(
    gagnant1="Premier joueur gagnant",
    gagnant2="Deuxième joueur gagnant", 
    gagnant3="Troisième joueur gagnant",
    perdant1="Premier joueur perdant",
    perdant2="Deuxième joueur perdant",
    perdant3="Troisième joueur perdant"
)
@app_commands.default_permissions(administrator=True)
async def record_match_result(
    interaction: discord.Interaction,
    gagnant1: discord.Member,
    gagnant2: discord.Member,
    gagnant3: discord.Member,
    perdant1: discord.Member,
    perdant2: discord.Member,
    perdant3: discord.Member
):
    """Enregistrer le résultat d'un match"""
    winners = [gagnant1, gagnant2, gagnant3]
    losers = [perdant1, perdant2, perdant3]
    
    # Vérifier qu'il n'y a pas de doublons
    all_members = winners + losers
    unique_ids = set(member.id for member in all_members)
    
    if len(unique_ids) != 6:
        await interaction.response.send_message("❌ **Erreur:** Chaque joueur ne peut apparaître qu'une seule fois", 
                                               ephemeral=True)
        return
    
    # Vérifier que tous sont inscrits
    for member in all_members:
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
    
    # Calculer nouveaux ELO
    winner_elos = []
    loser_elos = []
    
    for member in winners:
        player = get_player(member.id)
        if player:
            winner_elos.append(player['elo'])
        else:
            await interaction.response.send_message("❌ **Erreur:** Impossible de récupérer les données des joueurs", 
                                                   ephemeral=True)
            return
    
    for member in losers:
        player = get_player(member.id)
        if player:
            loser_elos.append(player['elo'])
        else:
            await interaction.response.send_message("❌ **Erreur:** Impossible de récupérer les données des joueurs", 
                                                   ephemeral=True)
            return
    
    winner_avg = sum(winner_elos) / 3
    loser_avg = sum(loser_elos) / 3
    
    # Mettre à jour ELO
    message = "⚔️ **Match enregistré!**\n\n"
    
    message += "🏆 **Gagnants:**\n"
    for i, member in enumerate(winners):
        old_elo = winner_elos[i]
        change = calculate_elo_change(old_elo, loser_avg, True)
        new_elo = max(0, old_elo + change)
        if update_player_elo(member.id, new_elo, True):
            message += f"**{member.display_name}:** {old_elo} → {new_elo} (+{change})\n"
        else:
            message += f"**{member.display_name}:** Erreur mise à jour\n"
    
    message += "\n💀 **Perdants:**\n"
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        change = calculate_elo_change(old_elo, winner_avg, False)
        new_elo = max(0, old_elo + change)
        if update_player_elo(member.id, new_elo, False):
            message += f"**{member.display_name}:** {old_elo} → {new_elo} ({change:+})\n"
        else:
            message += f"**{member.display_name}:** Erreur mise à jour\n"
    
    # Statistiques du match
    elo_diff = abs(winner_avg - loser_avg)
    message += f"\n📊 **Analyse:**\n"
    message += f"**ELO moyen gagnants:** {round(winner_avg)}\n"
    message += f"**ELO moyen perdants:** {round(loser_avg)}\n"
    message += f"**Écart:** {round(elo_diff)} points"
    
    await interaction.response.send_message(message)

# Ajouter la commande au bot
bot.tree.add_command(record_match_result)

@bot.command(name='result')
@commands.has_permissions(administrator=True)
async def old_record_match_result(ctx, winner1: discord.Member, winner2: discord.Member, winner3: discord.Member,
                             loser1: discord.Member, loser2: discord.Member, loser3: discord.Member):
    """!result @w1 @w2 @w3 @l1 @l2 @l3 - Enregistrer un match (ancienne version)"""
    await ctx.send("⚠️ **Commande obsolète**\n"
                  "Utilisez la nouvelle commande `/results` avec les arguments nommés :\n"
                  "• `gagnant1`, `gagnant2`, `gagnant3`\n"
                  "• `perdant1`, `perdant2`, `perdant3`")

# ================================
# LANCEMENT DU BOT
# ================================

if __name__ == '__main__':
    if not TOKEN:
        print("❌ DISCORD_TOKEN manquant!")
        exit(1)
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL manquant!")
        exit(1)
    
    print("🚀 Lancement du bot ELO ultra simplifié...")
    print(f"🐘 Base PostgreSQL: {DATABASE_URL[:50]}...")
    bot.run(TOKEN)