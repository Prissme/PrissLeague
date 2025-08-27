#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié - FICHIER PRINCIPAL
Configuration, base de données et lancement du bot avec système de dodge corrigé
"""

import discord
from discord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import logging
import random
from datetime import datetime, timedelta

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

# Paramètres des lobbies
MAX_CONCURRENT_LOBBIES = 3
LOBBY_COOLDOWN_MINUTES = 10
PING_ROLE_ID = 1396673817769803827

# Paramètres système anti-dodge
DODGE_PENALTY_BASE = 15  # Pénalité de base pour un dodge
DODGE_PENALTY_MULTIPLIER = 5  # Multiplicateur par dodge supplémentaire

# Bot instance
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Nécessaire pour get_member
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

def calculate_dodge_penalty(dodge_count):
    """Calcule la pénalité ELO selon le nombre de dodges"""
    if dodge_count <= 1:
        return DODGE_PENALTY_BASE
    else:
        # Pénalité progressive : 15, 20, 25, 30...
        return DODGE_PENALTY_BASE + ((dodge_count - 1) * DODGE_PENALTY_MULTIPLIER)

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
            
            # Table lobbies avec limitation
            c.execute('''
                CREATE TABLE IF NOT EXISTS lobbies (
                    id SERIAL PRIMARY KEY,
                    room_code TEXT NOT NULL,
                    players TEXT DEFAULT '',
                    max_players INTEGER DEFAULT 6,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table pour gérer le cooldown global
            c.execute('''
                CREATE TABLE IF NOT EXISTS lobby_cooldown (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    last_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table pour les dodges
            c.execute('''
                CREATE TABLE IF NOT EXISTS dodges (
                    id SERIAL PRIMARY KEY,
                    discord_id TEXT NOT NULL,
                    dodge_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (discord_id) REFERENCES players(discord_id)
                )
            ''')
            
            # Table pour l'historique des matchs (pour l'undo)
            c.execute('''
                CREATE TABLE IF NOT EXISTS match_history (
                    id SERIAL PRIMARY KEY,
                    match_data TEXT NOT NULL,
                    match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insérer une ligne pour le cooldown si elle n'existe pas
            c.execute('''
                INSERT INTO lobby_cooldown (id, last_creation) 
                VALUES (1, CURRENT_TIMESTAMP) 
                ON CONFLICT (id) DO NOTHING
            ''')
            
            conn.commit()
            logger.info("Base de données initialisée avec succès")
    except Exception as e:
        logger.error(f"Erreur initialisation DB: {e}")
    finally:
        conn.close()

def update_player_name(discord_id, new_name):
    """Met à jour le nom d'un joueur en base de données"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            c.execute('''
                UPDATE players 
                SET name = %s 
                WHERE discord_id = %s
            ''', (new_name, str(discord_id)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur update_player_name: {e}")
        return False
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
                ON CONFLICT (discord_id) DO UPDATE SET name = EXCLUDED.name
            ''', (str(discord_id), name))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur create_player: {e}")
        return False
    finally:
        conn.close()

def update_player_elo_only(discord_id, new_elo):
    """Met à jour SEULEMENT l'ELO d'un joueur (pas les win/loss)"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            c.execute('''
                UPDATE players 
                SET elo = %s 
                WHERE discord_id = %s
            ''', (new_elo, str(discord_id)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur update_player_elo_only: {e}")
        return False
    finally:
        conn.close()

def update_player_elo(discord_id, new_elo, won):
    """Met à jour l'ELO d'un joueur (ANCIENNE VERSION - gardée pour compatibilité)"""
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

def record_dodge(discord_id):
    """Enregistre UN SEUL dodge pour un joueur"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            c.execute('''
                INSERT INTO dodges (discord_id) 
                VALUES (%s)
            ''', (str(discord_id),))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur record_dodge: {e}")
        return False
    finally:
        conn.close()

def get_player_dodge_count(discord_id):
    """Récupère le nombre total de dodges d'un joueur"""
    conn = get_connection()
    if not conn:
        return 0
    
    try:
        with conn.cursor() as c:
            c.execute('''
                SELECT COUNT(*) as count 
                FROM dodges 
                WHERE discord_id = %s
            ''', (str(discord_id),))
            result = c.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        logger.error(f"Erreur get_player_dodge_count: {e}")
        return 0
    finally:
        conn.close()

def save_match_history(winners, losers, winner_elo_changes, loser_elo_changes, dodge_player_id=None):
    """Sauvegarde l'historique d'un match pour permettre l'annulation"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            # Convertir les listes en JSON string
            import json
            
            match_data = {
                'winners': [str(w.id) for w in winners],
                'losers': [str(l.id) for l in losers],
                'winner_elo_changes': winner_elo_changes,
                'loser_elo_changes': loser_elo_changes,
                'dodge_player_id': str(dodge_player_id) if dodge_player_id else None,
                'winner_team_leader': str(winners[0].id),  # Pour les win/loss d'équipe
                'loser_team_leader': str(losers[0].id)
            }
            
            c.execute('''
                INSERT INTO match_history (match_data) 
                VALUES (%s)
            ''', (json.dumps(match_data),))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur save_match_history: {e}")
        return False
    finally:
        conn.close()

def undo_last_match():
    """Annule le dernier match enregistré"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Récupérer le dernier match
            c.execute('''
                SELECT * FROM match_history 
                ORDER BY match_date DESC 
                LIMIT 1
            ''')
            last_match = c.fetchone()
            
            if not last_match:
                return False, "Aucun match à annuler"
            
            import json
            match_data = json.loads(last_match['match_data'])
            
            # Annuler les changements d'ELO pour les gagnants (sans retirer de victoires individuelles)
            winners = match_data['winners']
            winner_changes = match_data['winner_elo_changes']
            
            for i, player_id in enumerate(winners):
                old_change = winner_changes[i]
                # Inverser le changement d'ELO seulement
                c.execute('''
                    UPDATE players 
                    SET elo = elo - %s
                    WHERE discord_id = %s
                ''', (old_change, player_id))
            
            # Annuler les changements d'ELO pour les perdants (sans retirer de défaites individuelles)
            losers = match_data['losers']
            loser_changes = match_data['loser_elo_changes']
            
            for i, player_id in enumerate(losers):
                old_change = loser_changes[i]
                # Inverser le changement d'ELO seulement
                c.execute('''
                    UPDATE players 
                    SET elo = elo - %s
                    WHERE discord_id = %s
                ''', (old_change, player_id))
            
            # Retirer 1 victoire à l'équipe gagnante (leader seulement)
            winner_leader = match_data.get('winner_team_leader', winners[0])
            c.execute('''
                UPDATE players 
                SET wins = GREATEST(wins - 1, 0)
                WHERE discord_id = %s
            ''', (winner_leader,))
            
            # Retirer 1 défaite à l'équipe perdante (leader seulement)
            loser_leader = match_data.get('loser_team_leader', losers[0])
            c.execute('''
                UPDATE players 
                SET losses = GREATEST(losses - 1, 0)
                WHERE discord_id = %s
            ''', (loser_leader,))
            
            # Si il y avait un dodge, retirer UN SEUL dodge du compteur
            dodge_player_id = match_data.get('dodge_player_id')
            if dodge_player_id:
                c.execute('''
                    DELETE FROM dodges 
                    WHERE id = (
                        SELECT id FROM dodges 
                        WHERE discord_id = %s 
                        ORDER BY dodge_date DESC 
                        LIMIT 1
                    )
                ''', (dodge_player_id,))
            
            # Supprimer le match de l'historique
            c.execute('DELETE FROM match_history WHERE id = %s', (last_match['id'],))
            
            conn.commit()
            
            # Construire le message de retour
            winner_names = []
            loser_names = []
            
            for player_id in winners:
                player = get_player(player_id)
                if player:
                    winner_names.append(player['name'])
            
            for player_id in losers:
                player = get_player(player_id)
                if player:
                    loser_names.append(player['name'])
            
            return True, {
                'winners': winner_names,
                'losers': loser_names,
                'winner_changes': winner_changes,
                'loser_changes': loser_changes,
                'had_dodge': dodge_player_id is not None
            }
            
    except Exception as e:
        logger.error(f"Erreur undo_last_match: {e}")
        return False, f"Erreur interne: {str(e)}"
    finally:
        conn.close()

def check_lobby_limits():
    """Vérifie les limites de création de lobby"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Vérifier le nombre de lobbies actifs
            c.execute('SELECT COUNT(*) as count FROM lobbies')
            lobby_count = c.fetchone()['count']
            
            if lobby_count >= MAX_CONCURRENT_LOBBIES:
                return False, f"Limite atteinte: {MAX_CONCURRENT_LOBBIES} lobbies maximum en simultané"
            
            # Vérifier le cooldown global
            c.execute('SELECT last_creation FROM lobby_cooldown WHERE id = 1')
            result = c.fetchone()
            
            if result:
                last_creation = result['last_creation']
                cooldown_end = last_creation + timedelta(minutes=LOBBY_COOLDOWN_MINUTES)
                now = datetime.now()
                
                if now < cooldown_end:
                    remaining = cooldown_end - now
                    minutes = int(remaining.total_seconds() // 60)
                    seconds = int(remaining.total_seconds() % 60)
                    return False, f"Cooldown actif: attendez {minutes}m {seconds}s"
            
            return True, "OK"
    except Exception as e:
        logger.error(f"Erreur check_lobby_limits: {e}")
        return False, "Erreur interne"
    finally:
        conn.close()

def create_lobby(room_code):
    """Crée un lobby avec vérification des limites"""
    # Vérifier les limites
    can_create, message = check_lobby_limits()
    if not can_create:
        return None, message
    
    conn = get_connection()
    if not conn:
        return None, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Créer le lobby
            c.execute('INSERT INTO lobbies (room_code) VALUES (%s) RETURNING id', (room_code,))
            lobby_id = c.fetchone()['id']
            
            # Mettre à jour le cooldown
            c.execute('UPDATE lobby_cooldown SET last_creation = CURRENT_TIMESTAMP WHERE id = 1')
            
            conn.commit()
            return lobby_id, "Créé avec succès"
    except Exception as e:
        logger.error(f"Erreur create_lobby: {e}")
        return None, "Erreur interne"
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

def get_cooldown_info():
    """Récupère les informations sur le cooldown"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT last_creation FROM lobby_cooldown WHERE id = 1')
            result = c.fetchone()
            if result:
                last_creation = result['last_creation']
                cooldown_end = last_creation + timedelta(minutes=LOBBY_COOLDOWN_MINUTES)
                now = datetime.now()
                
                if now < cooldown_end:
                    remaining = cooldown_end - now
                    return {
                        'active': True,
                        'remaining_minutes': int(remaining.total_seconds() // 60),
                        'remaining_seconds': int(remaining.total_seconds() % 60)
                    }
                else:
                    return {'active': False}
            return None
    except Exception as e:
        logger.error(f"Erreur get_cooldown_info: {e}")
        return None
    finally:
        conn.close()

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