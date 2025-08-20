#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié - FICHIER PRINCIPAL
Configuration, base de données et lancement du bot
"""

import discord
from discord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor
import os
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

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Bot instance
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ================================
# FONCTIONS UTILITAIRES
# ================================

def create_random_teams(player_ids):
    """Crée 2 équipes aléatoires équilibrées"""
    shuffled = player_ids.copy()
    random.shuffle(shuffled)
    team1 = shuffled[:3]
    team2 = shuffled[3:6]
    return team1, team2

def select_random_maps(count=3):
    """Sélectionne des maps aléatoires"""
    return random.sample(MAPS, min(count, len(MAPS)))

def calculate_elo_change(player_elo, opponent_avg_elo, won):
    """Calcul ELO simplifié"""
    K = 30
    expected = 1 / (1 + 10 ** ((opponent_avg_elo - player_elo) / 400))
    actual = 1.0 if won else 0.0
    change = K * (actual - expected)
    return round(change)

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

# ================================
# BOT EVENTS (sera remplacé dans __main__)
# ================================

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
    
    # Charger les commandes après le démarrage du bot
    @bot.event
    async def on_ready():
        print(f'🤖 Bot connecté: {bot.user}')
        print(f'🐘 Connexion PostgreSQL: {"✅" if get_connection() else "❌"}')
        init_db()
        
        # Charger les commandes
        from commands import setup_commands as setup_bot_commands
        await setup_bot_commands(bot)
        
        # Synchroniser les commandes slash
        try:
            synced = await bot.tree.sync()
            print(f'📡 {len(synced)} commande(s) slash synchronisée(s)')
        except Exception as e:
            print(f'❌ Erreur synchronisation: {e}')
    
    # Lancer le bot
    bot.run(TOKEN)
