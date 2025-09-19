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
# COMMANDES PRINCIPALES MODIFIÉES
# ================================

# Les commandes seront ajoutées dans setup_commands() dans commands_dual.py

@bot.event
async def on_ready():
    """Quand le bot se connecte"""
    global backup_manager
    
    print(f'Bot {bot.user} connecté!')
    print(f'Serveurs: {len(bot.guilds)}')
    
    # Initialiser la base de données dual
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
    """Gestion globale des erreurs - Version sécurisée"""
    
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

async def main():
    """Fonction principale pour lancer le bot"""
    global backup_manager
    
    if not TOKEN:
        print("DISCORD_TOKEN manquant!")
        return
    
    if not DATABASE_URL:
        print("DATABASE_URL manquant!")
        return
    
    # Importer et configurer les commandes dual
    try:
        from commands_dual import setup_commands
        await setup_commands(bot)
        
        # Ajouter les commandes backup admin
        @bot.command(name='backup')
        async def _backup(ctx):
            if not ctx.author.guild_permissions.administrator:
                await ctx.send("Admin uniquement")
                return
            
            if not backup_manager:
                await ctx.send("Système backup non initialisé")
                return
            
            try:
                await ctx.send("Backup en cours...")
                success = backup_manager.create_backup("manual")
                
                if success:
                    await ctx.send("Backup créé avec succès!")
                else:
                    await ctx.send("Erreur lors du backup")
            except Exception as e:
                print(f"Erreur commande backup: {e}")
                try:
                    await ctx.send("Erreur interne")
                except:
                    pass
        
        @bot.command(name='backupstatus')
        async def _backupstatus(ctx):
            if not ctx.author.guild_permissions.administrator:
                await ctx.send("Admin uniquement")
                return
                
            if not backup_manager:
                await ctx.send("Système backup non initialisé")
                return
            
            try:
                backups = backup_manager.list_backups()
                
                message = f"SYSTÈME BACKUP\n\n"
                message += f"Type: Python pur (compatible Koyeb)\n"
                message += f"Dossier: /tmp/backups\n"
                message += f"Fréquence: 6 heures\n"
                message += f"Fichiers: {len(backups)}/{backup_manager.max_backups}\n"
                
                if backups:
                    total_size = sum(b['size_kb'] for b in backups)
                    message += f"Taille totale: {total_size:.1f} KB\n"
                    
                    latest = backups[0]
                    message += f"\nDernier backup:\n"
                    message += f"Fichier: {latest['filename']}\n"
                    message += f"Date: {latest['date'].strftime('%d/%m/%Y %H:%M:%S')}\n"
                    message += f"Taille: {latest['size_kb']:.1f} KB"
                else:
                    message += "\nAucun backup trouvé"
                
                await ctx.send(message)
                
            except Exception as e:
                print(f"Erreur backupstatus: {e}")
                try:
                    await ctx.send("Erreur lors du statut")
                except:
                    pass
        
        print("Bot ELO Dual démarré avec:")
        print("Mode SOLO - Matchmaking individuel")
        print("Mode TRIO - Équipes fixes de 3 joueurs")
        print("ELO et classements séparés")
        print("Aucun mélange entre les modes")
        
    except ImportError as e:
        print(f"Erreur import commands_dual.py: {e}")
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
        sys.exit(1)#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Dual - FICHIER PRINCIPAL
Configuration avec système Solo + Trio séparés
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
LOBBY_COOLDOWN_MINUTES_SOLO = 10
LOBBY_COOLDOWN_MINUTES_TRIO = 15
PING_ROLE_ID = 1396673817769803827

# Paramètres système anti-dodge
DODGE_PENALTY_BASE = 15  # Pénalité de base pour un dodge
DODGE_PENALTY_MULTIPLIER = 5  # Multiplicateur par dodge supplémentaire

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
    print(f"\n🛑 Signal {sig} reçu, arrêt en cours...")
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
# DATABASE POSTGRESQL - VERSION DUAL
# ================================

def get_connection():
    """Obtient une connexion à la base PostgreSQL"""
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Erreur connexion DB: {e}")
        return None

def init_db():
    """Initialise la base de données PostgreSQL avec système dual"""
    conn = get_connection()
    if not conn:
        logger.error("Impossible de se connecter à la base de données")
        return
    
    try:
        with conn.cursor() as c:
            # Table joueurs avec ELO séparés Solo/Trio
            c.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    discord_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    solo_elo INTEGER DEFAULT 1000,
                    solo_wins INTEGER DEFAULT 0,
                    solo_losses INTEGER DEFAULT 0,
                    trio_elo INTEGER DEFAULT 1000,
                    trio_wins INTEGER DEFAULT 0,
                    trio_losses INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
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
            
            # Table lobbies avec type (solo/trio)
            c.execute('''
                CREATE TABLE IF NOT EXISTS lobbies (
                    id SERIAL PRIMARY KEY,
                    room_code TEXT NOT NULL,
                    lobby_type TEXT NOT NULL CHECK (lobby_type IN ('solo', 'trio')),
                    players TEXT DEFAULT '',
                    teams TEXT DEFAULT '',
                    max_players INTEGER DEFAULT 6,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table pour cooldowns séparés
            c.execute('''
                CREATE TABLE IF NOT EXISTS lobby_cooldown (
                    id INTEGER PRIMARY KEY,
                    lobby_type TEXT NOT NULL CHECK (lobby_type IN ('solo', 'trio')),
                    last_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table dodges avec type
            c.execute('''
                CREATE TABLE IF NOT EXISTS dodges (
                    id SERIAL PRIMARY KEY,
                    discord_id TEXT NOT NULL,
                    dodge_type TEXT NOT NULL CHECK (dodge_type IN ('solo', 'trio')),
                    dodge_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (discord_id) REFERENCES players(discord_id)
                )
            ''')
            
            # Table historique avec type
            c.execute('''
                CREATE TABLE IF NOT EXISTS match_history (
                    id SERIAL PRIMARY KEY,
                    match_type TEXT NOT NULL CHECK (match_type IN ('solo', 'trio')),
                    match_data TEXT NOT NULL,
                    match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table messages match avec type
            c.execute('''
                CREATE TABLE IF NOT EXISTS match_messages (
                    message_id BIGINT PRIMARY KEY,
                    match_type TEXT NOT NULL CHECK (match_type IN ('solo', 'trio')),
                    match_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insérer cooldowns par défaut
            c.execute('''
                INSERT INTO lobby_cooldown (id, lobby_type, last_creation) 
                VALUES (1, 'solo', CURRENT_TIMESTAMP), (2, 'trio', CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING
            ''')
            
            # Migrer les anciennes données si nécessaire
            # Vérifier si les nouvelles colonnes existent déjà
            c.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'players' AND column_name IN ('solo_elo', 'trio_elo')
            """)
            new_columns = [row['column_name'] for row in c.fetchall()]
            
            if 'solo_elo' not in new_columns:
                # Migration depuis l'ancien système
                c.execute('ALTER TABLE players ADD COLUMN solo_elo INTEGER DEFAULT 1000')
                c.execute('ALTER TABLE players ADD COLUMN solo_wins INTEGER DEFAULT 0') 
                c.execute('ALTER TABLE players ADD COLUMN solo_losses INTEGER DEFAULT 0')
                c.execute('ALTER TABLE players ADD COLUMN trio_elo INTEGER DEFAULT 1000')
                c.execute('ALTER TABLE players ADD COLUMN trio_wins INTEGER DEFAULT 0')
                c.execute('ALTER TABLE players ADD COLUMN trio_losses INTEGER DEFAULT 0')
                
                # Migrer données existantes vers solo
                c.execute('''
                    UPDATE players SET 
                    solo_elo = COALESCE(elo, 1000),
                    solo_wins = COALESCE(wins, 0),
                    solo_losses = COALESCE(losses, 0)
                ''')
                
                print("✅ Migration vers système dual terminée")
            
            conn.commit()
            logger.info("Base de données dual initialisée avec succès")
    except Exception as e:
        logger.error(f"Erreur initialisation DB: {e}")
    finally:
        conn.close()

# ================================
# FONCTIONS DATABASE DUAL
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
    """Met à jour l'ELO d'un joueur avec win/loss selon le type"""
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
            else:  # trio
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
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Erreur update_player_elo: {e}")
        return False
    finally:
        conn.close()

def get_leaderboard(match_type='solo'):
    """Récupère le classement selon le type"""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as c:
            if match_type == 'solo':
                c.execute('SELECT * FROM players ORDER BY solo_elo DESC LIMIT 20')
            else:
                c.execute('SELECT * FROM players ORDER BY trio_elo DESC LIMIT 20')
            results = c.fetchall()
            return [dict(row) for row in results] if results else []
    except Exception as e:
        logger.error(f"Erreur get_leaderboard: {e}")
        return []
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
# FONCTIONS LOBBY DUAL
# ================================

def check_lobby_limits(lobby_type):
    """Vérifie les limites selon le type"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Vérifier le nombre de lobbies actifs du type
            c.execute('SELECT COUNT(*) as count FROM lobbies WHERE lobby_type = %s', (lobby_type,))
            lobby_count = c.fetchone()['count']
            
            max_lobbies = MAX_CONCURRENT_LOBBIES_SOLO if lobby_type == 'solo' else MAX_CONCURRENT_LOBBIES_TRIO
            if lobby_count >= max_lobbies:
                return False, f"Limite atteinte: {max_lobbies} lobbies {lobby_type} maximum"
            
            # Vérifier le cooldown
            cooldown_id = 1 if lobby_type == 'solo' else 2
            cooldown_minutes = LOBBY_COOLDOWN_MINUTES_SOLO if lobby_type == 'solo' else LOBBY_COOLDOWN_MINUTES_TRIO
            
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
    """Crée un lobby selon le type"""
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
            cooldown_id = 1 if lobby_type == 'solo' else 2
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
# COMMANDES PRINCIPALES
# ================================

@bot.command(name='createteam')
async def create_team_cmd(ctx, teammate1: discord.Member, teammate2: discord.Member, *, team_name: str):
    """!createteam @joueur1 @joueur2 Nom de l'équipe - Créer une équipe trio"""
    from commands_dual import ensure_player_has_ping_role
    
    # Vérifier que tous les joueurs existent
    for member in [ctx.author, teammate1, teammate2]:
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
        await ensure_player_has_ping_role(ctx.guild, member.id)
    
    # Créer l'équipe
    success, msg = create_trio_team(ctx.author.id, teammate1.id, teammate2.id, team_name)
    if success:
        await ctx.send(f"✅ **Équipe Trio créée!**\n"
                      f"📝 Nom: {team_name}\n"
                      f"👑 Capitaine: {ctx.author.display_name}\n"
                      f"👥 Équipiers: {teammate1.display_name}, {teammate2.display_name}")
    else:
        await ctx.send(f"❌ {msg}")

@bot.command(name='myteam')
async def my_team_cmd(ctx):
    """!myteam - Voir son équipe trio"""
    team = get_player_trio_team(ctx.author.id)
    if not team:
        await ctx.send("❌ Vous n'avez pas d'équipe trio. Utilisez `!createteam`")
        return
    
    # Récupérer les noms des joueurs
    captain = ctx.guild.get_member(int(team['captain_id']))
    player2 = ctx.guild.get_member(int(team['player2_id']))
    player3 = ctx.guild.get_member(int(team['player3_id']))
    
    captain_name = captain.display_name if captain else f"ID:{team['captain_id']}"
    player2_name = player2.display_name if player2 else f"ID:{team['player2_id']}"
    player3_name = player3.display_name if player3 else f"ID:{team['player3_id']}"
    
    message = f"👥 **Équipe: {team['name']}**\n"
    message += f"👑 Capitaine: {captain_name}\n"
    message += f"👤 Équipiers: {player2_name}, {player3_name}\n"
    message += f"📅 Créée: {team['created_at'].strftime('%d/%m/%Y')}"
    
    await ctx.send(message)

@bot.command(name='dissolveteam')
async def dissolve_team_cmd(ctx):
    """!dissolveteam - Dissoudre son équipe trio (capitaine seulement)"""
    team = get_player_trio_team(ctx.author.id)
    if not team:
        await ctx.send("❌ Vous n'avez pas d'équipe trio")
        return
    
    if team['captain_id'] != str(ctx.author.id):
        await ctx.send("❌ Seul le capitaine peut dissoudre l'équipe")
        return
    
    if delete_trio_team(team['id']):
        await ctx.send(f"💥 **Équipe '{team['name']}' dissoute**")
    else:
        await ctx.send("❌ Erreur lors de la dissolution")

async def main():
    """Fonction principale pour lancer le bot"""
    global backup_manager
    
    if not TOKEN:
        print("❌ DISCORD_TOKEN manquant!")
        return
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL manquant!")
        return
    
    # Importer et configurer les commandes dual
    try:
        from commands_dual import setup_commands
        await setup_commands(bot)
        
        print("🎯 Bot ELO Dual démarré avec:")
        print("🥇 Mode SOLO - Matchmaking individuel")
        print("👥 Mode TRIO - Équipes fixes de 3 joueurs")
        print("📊 ELO et classements séparés")
        print("🚫 Aucun mélange entre les modes")
        
    except ImportError as e:
        print(f"❌ Erreur import commands_dual.py: {e}")
        return
    
    # Lancer le bot
    try:
        print("🚀 Démarrage du bot Discord...")
        await bot.start(TOKEN)
    except discord.LoginFailure:
        print("❌ Token Discord invalide!")
    except discord.HTTPException as e:
        print(f"❌ Erreur HTTP Discord: {e}")
    except Exception as e:
        print(f"❌ Erreur lancement bot: {e}")
    finally:
        if backup_manager:
            await backup_manager.stop_auto_backup()
            print("💾 Système backup arrêté")
        print("👋 Bot arrêté")

if __name__ == '__main__':
    import asyncio
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Arrêt demandé par l'utilisateur")
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")
        sys.exit(1)
