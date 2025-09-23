#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Triple - FICHIER PRINCIPAL MODIFIÉ
Configuration avec système Solo + Trio + Chaos séparés avec modules de commandes séparés
"""

import discord
from discord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import logging
import random
import signal
import sys
import atexit
import asyncio
from datetime import datetime, timedelta
import json

# Import du système de backup Python pur
from backup import init_python_backup_system, get_backup_manager

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
MAX_CONCURRENT_LOBBIES_SOLO = 3
MAX_CONCURRENT_LOBBIES_TRIO = 2
MAX_CONCURRENT_LOBBIES_CHAOS = 3  # Nouveau
LOBBY_COOLDOWN_MINUTES_SOLO = 10
LOBBY_COOLDOWN_MINUTES_TRIO = 15
LOBBY_COOLDOWN_MINUTES_CHAOS = 5  # Plus court pour le fun
PING_ROLE_ID = 1396673817769803827

# Paramètres système anti-dodge
DODGE_PENALTY_BASE = 15
DODGE_PENALTY_MULTIPLIER = 5

# Bot instance
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Gestionnaire de backup
backup_manager = None

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
        return DODGE_PENALTY_BASE + ((dodge_count - 1) * DODGE_PENALTY_MULTIPLIER)

# ================================
# HANDLERS POUR ARRÊT PROPRE
# ================================

def signal_handler(sig, frame):
    """Gestionnaire pour arrêt propre du bot"""
    print(f"\nðŸ›' Signal {sig} reçu, arrêt en cours...")
    cleanup_and_exit()

def cleanup_and_exit():
    """Nettoyage avant arrêt"""
    global backup_manager
    
    if backup_manager:
        print("💾 Backup final en cours...")
        backup_manager.backup_on_shutdown()
    
    print("👋 Bot arrêté proprement")
    sys.exit(0)

# Enregistrer les handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_and_exit)

# ================================
# DATABASE POSTGRESQL - MIGRATION COMPLÈTE TRIPLE
# ================================

def get_connection():
    """Obtient une connexion à la base PostgreSQL"""
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Erreur connexion DB: {e}")
        return None

def init_db():
    """Initialise et migre complètement la base vers le système triple"""
    conn = get_connection()
    if not conn:
        logger.error("Impossible de se connecter à la base de données")
        return
    
    try:
        with conn.cursor() as c:
            print("🔧 MIGRATION COMPLÈTE VERS SYSTÈME TRIPLE")
            print("=" * 50)
            
            # 1. MIGRATION TABLE PLAYERS AVEC CHAOS
            print("📄 1/4 - Migration table players avec mode Chaos...")
            
            # Créer table players avec toutes les colonnes incluant chaos
            c.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    discord_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    elo INTEGER DEFAULT 1000,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    solo_elo INTEGER DEFAULT 1000,
                    solo_wins INTEGER DEFAULT 0,
                    solo_losses INTEGER DEFAULT 0,
                    trio_elo INTEGER DEFAULT 1000,
                    trio_wins INTEGER DEFAULT 0,
                    trio_losses INTEGER DEFAULT 0,
                    chaos_elo INTEGER DEFAULT 1000,
                    chaos_wins INTEGER DEFAULT 0,
                    chaos_losses INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Ajouter colonnes triple si manquantes
            triple_columns = {
                'solo_elo': 'INTEGER DEFAULT 1000',
                'solo_wins': 'INTEGER DEFAULT 0',
                'solo_losses': 'INTEGER DEFAULT 0',
                'trio_elo': 'INTEGER DEFAULT 1000',
                'trio_wins': 'INTEGER DEFAULT 0',
                'trio_losses': 'INTEGER DEFAULT 0',
                'chaos_elo': 'INTEGER DEFAULT 1000',
                'chaos_wins': 'INTEGER DEFAULT 0',
                'chaos_losses': 'INTEGER DEFAULT 0'
            }
            
            for col_name, col_type in triple_columns.items():
                try:
                    c.execute(f'ALTER TABLE players ADD COLUMN {col_name} {col_type}')
                    print(f"  ➤ Ajouté colonne {col_name}")
                except psycopg2.errors.DuplicateColumn:
                    pass
                except Exception as e:
                    if "already exists" not in str(e):
                        print(f"  ⚠️ Erreur colonne {col_name}: {e}")
            
            # Migrer données existantes
            c.execute('''
                UPDATE players SET 
                solo_elo = COALESCE(NULLIF(solo_elo, 1000), elo, 1000),
                solo_wins = COALESCE(NULLIF(solo_wins, 0), wins, 0),
                solo_losses = COALESCE(NULLIF(solo_losses, 0), losses, 0)
                WHERE (solo_elo = 1000 OR solo_elo IS NULL)
                AND (elo IS NOT NULL AND elo != 1000)
            ''')
            
            c.execute('SELECT COUNT(*) as count FROM players WHERE solo_elo != 1000')
            migrated_players = c.fetchone()['count']
            print(f"  ✅ {migrated_players} joueurs migrés vers système triple")
            
            # 2. MIGRATION TABLE LOBBIES AVEC CHAOS
            print("📄 2/4 - Migration table lobbies avec mode Chaos...")
            
            # Créer table lobbies complète
            c.execute('''
                CREATE TABLE IF NOT EXISTS lobbies (
                    id SERIAL PRIMARY KEY,
                    room_code TEXT NOT NULL,
                    lobby_type TEXT DEFAULT 'solo' CHECK (lobby_type IN ('solo', 'trio', 'chaos')),
                    players TEXT DEFAULT '',
                    teams TEXT DEFAULT '',
                    max_players INTEGER DEFAULT 6,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Ajouter colonnes manquantes
            lobby_columns = {
                'lobby_type': "TEXT DEFAULT 'solo'",
                'teams': "TEXT DEFAULT ''"
            }
            
            for col_name, col_type in lobby_columns.items():
                try:
                    c.execute(f'ALTER TABLE lobbies ADD COLUMN {col_name} {col_type}')
                    print(f"  ➤ Ajouté colonne {col_name}")
                except psycopg2.errors.DuplicateColumn:
                    pass
                except Exception as e:
                    if "already exists" not in str(e):
                        print(f"  ⚠️ Erreur colonne {col_name}: {e}")
            
            # Mettre à jour la contrainte pour inclure chaos
            try:
                c.execute('ALTER TABLE lobbies DROP CONSTRAINT IF EXISTS lobbies_lobby_type_check')
                c.execute("ALTER TABLE lobbies ADD CONSTRAINT lobbies_lobby_type_check CHECK (lobby_type IN ('solo', 'trio', 'chaos'))")
                print("  ✅ Contrainte lobby_type mise à jour pour inclure chaos")
            except Exception as e:
                print(f"  ⚠️ Erreur contrainte: {e}")
            
            # Définir lobbies existants comme solo
            c.execute("UPDATE lobbies SET lobby_type = 'solo' WHERE lobby_type IS NULL")
            print("  ✅ Lobbies existants définis comme solo")
            
            # 3. MIGRATION TABLE LOBBY_COOLDOWN AVEC CHAOS
            print("📄 3/4 - Migration table lobby_cooldown avec mode Chaos...")
            
            # Supprimer et recréer proprement
            c.execute('DROP TABLE IF EXISTS lobby_cooldown CASCADE')
            c.execute('''
                CREATE TABLE lobby_cooldown (
                    id INTEGER PRIMARY KEY,
                    lobby_type TEXT NOT NULL CHECK (lobby_type IN ('solo', 'trio', 'chaos')),
                    last_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insérer valeurs par défaut pour les 3 modes
            c.execute('''
                INSERT INTO lobby_cooldown (id, lobby_type, last_creation) 
                VALUES (1, 'solo', CURRENT_TIMESTAMP), 
                       (2, 'trio', CURRENT_TIMESTAMP),
                       (3, 'chaos', CURRENT_TIMESTAMP)
            ''')
            print("  ✅ Table lobby_cooldown recréée avec types triple")
            
            # 4. CRÉATION TABLES MANQUANTES
            print("📄 4/4 - Création tables système triple...")
            
            # Table équipes trio
            c.execute('''
                CREATE TABLE IF NOT EXISTS trio_teams (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    captain_id TEXT NOT NULL,
                    player2_id TEXT NOT NULL,
                    player3_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (captain_id) REFERENCES players(discord_id),
                    FOREIGN KEY (player2_id) REFERENCES players(discord_id),
                    FOREIGN KEY (player3_id) REFERENCES players(discord_id)
                )
            ''')
            
            # Table dodges avec type (incluant chaos)
            c.execute('''
                CREATE TABLE IF NOT EXISTS dodges (
                    id SERIAL PRIMARY KEY,
                    discord_id TEXT NOT NULL,
                    dodge_type TEXT NOT NULL CHECK (dodge_type IN ('solo', 'trio', 'chaos')),
                    dodge_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (discord_id) REFERENCES players(discord_id)
                )
            ''')
            
            # Table historique avec type (incluant chaos)
            c.execute('''
                CREATE TABLE IF NOT EXISTS match_history (
                    id SERIAL PRIMARY KEY,
                    match_type TEXT NOT NULL CHECK (match_type IN ('solo', 'trio', 'chaos')),
                    match_data TEXT NOT NULL,
                    match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table messages match avec type (incluant chaos)
            c.execute('''
                CREATE TABLE IF NOT EXISTS match_messages (
                    message_id BIGINT PRIMARY KEY,
                    match_type TEXT NOT NULL CHECK (match_type IN ('solo', 'trio', 'chaos')),
                    match_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            print("  ✅ Toutes les tables triple créées")
            
            # MIGRATION COLONNES EXISTANTES POUR INCLURE CHAOS
            try:
                c.execute('ALTER TABLE dodges DROP CONSTRAINT IF EXISTS dodges_dodge_type_check')
                c.execute("ALTER TABLE dodges ADD CONSTRAINT dodges_dodge_type_check CHECK (dodge_type IN ('solo', 'trio', 'chaos'))")
                print("  ➤ Contrainte dodges mise à jour")
            except:
                pass
            
            try:
                c.execute('ALTER TABLE match_history DROP CONSTRAINT IF EXISTS match_history_match_type_check')
                c.execute("ALTER TABLE match_history ADD CONSTRAINT match_history_match_type_check CHECK (match_type IN ('solo', 'trio', 'chaos'))")
                print("  ➤ Contrainte match_history mise à jour")
            except:
                pass
            
            try:
                c.execute('ALTER TABLE match_messages DROP CONSTRAINT IF EXISTS match_messages_match_type_check')
                c.execute("ALTER TABLE match_messages ADD CONSTRAINT match_messages_match_type_check CHECK (match_type IN ('solo', 'trio', 'chaos'))")
                print("  ➤ Contrainte match_messages mise à jour")
            except:
                pass
            
            # Mettre à jour les enregistrements NULL
            c.execute("UPDATE dodges SET dodge_type = 'solo' WHERE dodge_type IS NULL")
            c.execute("UPDATE match_history SET match_type = 'solo' WHERE match_type IS NULL")
            c.execute("UPDATE match_messages SET match_type = 'solo' WHERE match_type IS NULL")
            
            conn.commit()
            
            print("=" * 50)
            print("✅ MIGRATION COMPLÈTE TERMINÉE")
            print("🥇 Système Solo opérationnel")
            print("👥 Système Trio opérationnel")
            print("🎲 Système Chaos opérationnel")
            print("🚫 ELO complètement séparés (3 classements)")
            
            logger.info("Base de données triple complètement migrée")
            
    except Exception as e:
        logger.error(f"Erreur migration DB: {e}")
        print(f"❌ Erreur migration: {e}")
        conn.rollback()
    finally:
        conn.close()

# ================================
# FONCTIONS DATABASE TRIPLE
# ================================

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

def update_player_elo(discord_id, new_elo, won, match_type):
    """Met à jour l'ELO d'un joueur avec win/loss selon le type (solo/trio/chaos)"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            if match_type == 'solo':
                if won:
                    c.execute('''
                        UPDATE players 
                        SET solo_elo = %s, solo_wins = solo_wins + 1 
                        WHERE discord_id = %s
                    ''', (new_elo, str(discord_id)))
                else:
                    c.execute('''
                        UPDATE players 
                        SET solo_elo = %s, solo_losses = solo_losses + 1 
                        WHERE discord_id = %s
                    ''', (new_elo, str(discord_id)))
            elif match_type == 'trio':
                if won:
                    c.execute('''
                        UPDATE players 
                        SET trio_elo = %s, trio_wins = trio_wins + 1 
                        WHERE discord_id = %s
                    ''', (new_elo, str(discord_id)))
                else:
                    c.execute('''
                        UPDATE players 
                        SET trio_elo = %s, trio_losses = trio_losses + 1 
                        WHERE discord_id = %s
                    ''', (new_elo, str(discord_id)))
            elif match_type == 'chaos':
                if won:
                    c.execute('''
                        UPDATE players 
                        SET chaos_elo = COALESCE(chaos_elo, 1000) + (%s - COALESCE(chaos_elo, 1000)), 
                            chaos_wins = COALESCE(chaos_wins, 0) + 1 
                        WHERE discord_id = %s
                    ''', (new_elo, str(discord_id)))
                else:
                    c.execute('''
                        UPDATE players 
                        SET chaos_elo = COALESCE(chaos_elo, 1000) + (%s - COALESCE(chaos_elo, 1000)), 
                            chaos_losses = COALESCE(chaos_losses, 0) + 1 
                        WHERE discord_id = %s
                    ''', (new_elo, str(discord_id)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur update_player_elo: {e}")
        return False
    finally:
        conn.close()

def get_leaderboard(match_type='solo'):
    """Récupère le classement selon le type (solo/trio/chaos)"""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as c:
            if match_type == 'solo':
                c.execute('SELECT * FROM players ORDER BY solo_elo DESC LIMIT 20')
            elif match_type == 'trio':
                c.execute('SELECT * FROM players ORDER BY trio_elo DESC LIMIT 20')
            elif match_type == 'chaos':
                c.execute('SELECT * FROM players ORDER BY COALESCE(chaos_elo, 1000) DESC LIMIT 20')
            else:
                return []
            
            results = c.fetchall()
            return [dict(row) for row in results] if results else []
    except Exception as e:
        logger.error(f"Erreur get_leaderboard: {e}")
        return []
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

def save_match_history(winners, losers, winner_elo_changes, loser_elo_changes, 
                      dodge_player_id=None, match_type='solo'):
    """Sauvegarde l'historique d'un match avec type"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            match_data = {
                'winners': [str(w.id) if hasattr(w, 'id') else str(w['discord_id']) for w in winners],
                'losers': [str(l.id) if hasattr(l, 'id') else str(l['discord_id']) for l in losers],
                'winner_elo_changes': winner_elo_changes,
                'loser_elo_changes': loser_elo_changes,
                'dodge_player_id': str(dodge_player_id) if dodge_player_id else None,
                'winner_team_leader': str(winners[0].id if hasattr(winners[0], 'id') else winners[0]['discord_id']),
                'loser_team_leader': str(losers[0].id if hasattr(losers[0], 'id') else losers[0]['discord_id'])
            }
            
            c.execute('''
                INSERT INTO match_history (match_type, match_data) 
                VALUES (%s, %s)
            ''', (match_type, json.dumps(match_data)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur save_match_history: {e}")
        return False
    finally:
        conn.close()

# ================================
# FONCTIONS TRIO TEAMS
# ================================

def create_trio_team(captain_id, player2_id, player3_id, team_name):
    """Crée une équipe trio"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Vérifier que les 3 joueurs existent
            for player_id in [captain_id, player2_id, player3_id]:
                c.execute('SELECT discord_id FROM players WHERE discord_id = %s', (str(player_id),))
                if not c.fetchone():
                    return False, f"Joueur {player_id} non inscrit"
            
            # Vérifier qu'aucun n'est déjà dans une équipe
            c.execute('''
                SELECT name FROM trio_teams 
                WHERE captain_id = %s OR player2_id = %s OR player3_id = %s
                OR captain_id = %s OR player2_id = %s OR player3_id = %s
                OR captain_id = %s OR player2_id = %s OR player3_id = %s
            ''', (str(captain_id), str(captain_id), str(captain_id),
                  str(player2_id), str(player2_id), str(player2_id),
                  str(player3_id), str(player3_id), str(player3_id)))
            
            if c.fetchone():
                return False, "Un des joueurs est déjà dans une équipe trio"
            
            # Créer l'équipe
            c.execute('''
                INSERT INTO trio_teams (name, captain_id, player2_id, player3_id)
                VALUES (%s, %s, %s, %s)
            ''', (team_name, str(captain_id), str(player2_id), str(player3_id)))
            
            conn.commit()
            return True, "Équipe créée avec succès"
    except Exception as e:
        logger.error(f"Erreur create_trio_team: {e}")
        return False, "Erreur interne"
    finally:
        conn.close()

def get_player_trio_team(discord_id):
    """Récupère l'équipe trio d'un joueur"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as c:
            c.execute('''
                SELECT * FROM trio_teams 
                WHERE captain_id = %s OR player2_id = %s OR player3_id = %s
            ''', (str(discord_id), str(discord_id), str(discord_id)))
            result = c.fetchone()
            return dict(result) if result else None
    except Exception as e:
        logger.error(f"Erreur get_player_trio_team: {e}")
        return None
    finally:
        conn.close()

def delete_trio_team(team_id):
    """Supprime une équipe trio"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            c.execute('DELETE FROM trio_teams WHERE id = %s', (team_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur delete_trio_team: {e}")
        return False
    finally:
        conn.close()

# ================================
# FONCTIONS LOBBY TRIPLE
# ================================

def check_lobby_limits(lobby_type):
    """Vérifie les limites selon le type (solo/trio/chaos)"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Vérifier le nombre de lobbies actifs du type
            c.execute('SELECT COUNT(*) as count FROM lobbies WHERE lobby_type = %s', (lobby_type,))
            lobby_count = c.fetchone()['count']
            
            if lobby_type == 'solo':
                max_lobbies = MAX_CONCURRENT_LOBBIES_SOLO
                cooldown_minutes = LOBBY_COOLDOWN_MINUTES_SOLO
                cooldown_id = 1
            elif lobby_type == 'trio':
                max_lobbies = MAX_CONCURRENT_LOBBIES_TRIO
                cooldown_minutes = LOBBY_COOLDOWN_MINUTES_TRIO
                cooldown_id = 2
            elif lobby_type == 'chaos':
                max_lobbies = MAX_CONCURRENT_LOBBIES_CHAOS
                cooldown_minutes = LOBBY_COOLDOWN_MINUTES_CHAOS
                cooldown_id = 3
            else:
                return False, "Type de lobby inconnu"
            
            if lobby_count >= max_lobbies:
                return False, f"Limite atteinte: {max_lobbies} lobbies {lobby_type} maximum"
            
            # Vérifier le cooldown
            c.execute('SELECT last_creation FROM lobby_cooldown WHERE id = %s', (cooldown_id,))
            result = c.fetchone()
            
            if result:
                last_creation = result['last_creation']
                cooldown_end = last_creation + timedelta(minutes=cooldown_minutes)
                now = datetime.now()
                
                if now < cooldown_end:
                    remaining = cooldown_end - now
                    minutes = int(remaining.total_seconds() // 60)
                    seconds = int(remaining.total_seconds() % 60)
                    return False, f"Cooldown {lobby_type}: attendez {minutes}m {seconds}s"
            
            return True, "OK"
    except Exception as e:
        logger.error(f"Erreur check_lobby_limits: {e}")
        return False, "Erreur interne"
    finally:
        conn.close()

def create_lobby(room_code, lobby_type):
    """Crée un lobby selon le type (solo/trio/chaos)"""
    can_create, message = check_lobby_limits(lobby_type)
    if not can_create:
        return None, message
    
    conn = get_connection()
    if not conn:
        return None, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            c.execute('INSERT INTO lobbies (room_code, lobby_type) VALUES (%s, %s) RETURNING id', 
                     (room_code, lobby_type))
            lobby_id = c.fetchone()['id']
            
            # Mettre à jour le cooldown approprié
            if lobby_type == 'solo':
                cooldown_id = 1
            elif lobby_type == 'trio':
                cooldown_id = 2
            elif lobby_type == 'chaos':
                cooldown_id = 3
            else:
                return None, "Type de lobby inconnu"
                
            c.execute('UPDATE lobby_cooldown SET last_creation = CURRENT_TIMESTAMP WHERE id = %s', 
                     (cooldown_id,))
            
            conn.commit()
            return lobby_id, "Créé avec succès"
    except Exception as e:
        logger.error(f"Erreur create_lobby: {e}")
        return None, "Erreur interne"
    finally:
        conn.close()

# ================================
# EVENTS BOT
# ================================

@bot.event
async def on_ready():
    """Quand le bot se connecte"""
    global backup_manager
    
    print(f'Bot {bot.user} connecté!')
    print(f'Serveurs: {len(bot.guilds)}')
    
    # Initialiser la base de données triple avec migration complète
    init_db()
    
    # Initialiser le système de backup
    backup_manager = init_python_backup_system(DATABASE_URL)
    if backup_manager:
        await backup_manager.start_auto_backup()
        print("Système backup Python activé (compatible Koyeb)")
    else:
        print("Erreur initialisation backup")
    
    # Synchroniser les commandes slash
    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)} commande(s) slash synchronisée(s)')
    except Exception as e:
        print(f'Erreur sync commandes slash: {e}')

@bot.event
async def on_command_error(ctx, error):
    """Gestion globale des erreurs"""
    
    # Ignorer les commandes inconnues silencieusement
    if isinstance(error, commands.CommandNotFound):
        return
    
    # Logger l'erreur dans la console pour debug
    error_msg = f"[ERROR] {ctx.author} dans #{ctx.channel}: {type(error).__name__}: {error}"
    print(error_msg)
    logger.error(error_msg)
    
    # Déterminer le message d'erreur approprié
    user_message = None
    
    if isinstance(error, commands.MissingPermissions):
        user_message = "Permissions insuffisantes"
    elif isinstance(error, commands.MissingRequiredArgument):
        user_message = f"Argument manquant: {error.param.name}"
    elif isinstance(error, commands.BadArgument):
        user_message = "Arguments invalides"
    elif isinstance(error, commands.CommandOnCooldown):
        user_message = f"Cooldown: {error.retry_after:.1f}s"
    elif isinstance(error, discord.Forbidden):
        print(f"[PERMISSION] Bot n'a pas les droits dans #{ctx.channel}")
        return
    elif isinstance(error, discord.HTTPException):
        print(f"[HTTP_ERROR] Erreur Discord API: {error}")
        user_message = "Erreur réseau Discord"
    else:
        user_message = "Erreur interne"
    
    # Essayer d'envoyer le message d'erreur de manière sécurisée
    if user_message:
        try:
            await ctx.send(user_message)
        except discord.Forbidden:
            print(f"[PERMISSION] Impossible d'envoyer message d'erreur dans #{ctx.channel}")
        except discord.HTTPException as e:
            print(f"[HTTP_ERROR] Erreur envoi message: {e}")
        except Exception as e:
            print(f"[UNKNOWN_ERROR] Erreur inattendue envoi message: {e}")

# Commande help globale mise à jour
@bot.command(name='help')
async def help_triple(ctx):
    message = "🎯 **BOT ELO TRIPLE - GUIDE COMPLET**\n\n"
    
    message += "🥇 **MODE SOLO**\n"
    message += "• `!solo <code>` - Créer lobby solo\n"
    message += "• `!joinsolo <id>` - Rejoindre lobby\n"
    message += "• `!elosolo` - Voir son ELO solo\n"
    message += "• `!leaderboardsolo` - Classement solo\n\n"
    
    message += "👥 **MODE TRIO**\n"
    message += "• `!createteam @j1 @j2 Nom` - Créer équipe\n"
    message += "• `!myteam` - Voir son équipe\n"
    message += "• `!leaveteam` - Dissoudre équipe (capitaine)\n"
    message += "• `!teams` - Liste des équipes\n"
    message += "• `!trio <code>` - Créer lobby trio\n"
    message += "• `!jointrio <id>` - Rejoindre lobby\n"
    message += "• `!elotrio` - Voir son ELO trio\n"
    message += "• `!leaderboardtrio` - Classement trio\n\n"
    
    message += "🎲 **MODE CHAOS**\n"
    message += "• `!chaos <code>` - Créer lobby chaos\n"
    message += "• `!joinchaos <id>` - Rejoindre lobby\n"
    message += "• `!elochaos` - Voir son ELO chaos\n"
    message += "• `!leaderboardchaos` - Classement chaos\n"
    message += "• `!chaosinfo` - Guide du mode chaos\n\n"
    
    message += "🚫 **IMPORTANT:**\n"
    message += "• ELO Solo, Trio et Chaos complètement séparés\n"
    message += "• Pour le trio, créez d'abord votre équipe fixe\n"
    message += "• Le chaos est 100% aléatoire et fun\n"
    message += "• 3 classements indépendants"
    
    await ctx.send(message)

# ================================
# FONCTION MAIN
# ================================

async def main():
    """Fonction principale pour lancer le bot"""
    global backup_manager
    
    if not TOKEN:
        print("DISCORD_TOKEN manquant!")
        return
    
    if not DATABASE_URL:
        print("DATABASE_URL manquant!")
        return
    
    # Importer et configurer les commandes séparées
    try:
        from commands_solo import setup_solo_commands
        from commands_trio import setup_trio_commands
        from chaos import setup_chaos_commands  # Nouveau module
        
        await setup_solo_commands(bot)
        await setup_trio_commands(bot)
        await setup_chaos_commands(bot)  # Nouveau
        
        print("Bot ELO Triple démarré avec modules séparés:")
        print("🥇 Module SOLO - Matchmaking individuel")
        print("👥 Module TRIO - Équipes fixes de 3 joueurs")
        print("🎲 Module CHAOS - Mode aléatoire et fun")
        print("🚫 3 ELO et classements complètement séparés")
        print("📁 Architecture modulaire pour maintenance facilitée")
        
    except ImportError as e:
        print(f"Erreur import modules de commandes: {e}")
        return
    
    # Lancer le bot avec gestion d'erreurs
    try:
        print("Démarrage du bot Discord...")
        await bot.start(TOKEN)
    except discord.LoginFailure:
        print("Token Discord invalide!")
    except discord.HTTPException as e:
        print(f"Erreur HTTP Discord: {e}")
    except Exception as e:
        print(f"Erreur lancement bot: {e}")
    finally:
        # Arrêt propre du système de backup
        if backup_manager:
            await backup_manager.stop_auto_backup()
            print("Système backup arrêté")
        print("Bot arrêté")

if __name__ == '__main__':
    import asyncio
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt demandé par l'utilisateur")
    except Exception as e:
        print(f"Erreur fatale: {e}")
        sys.exit(1)
