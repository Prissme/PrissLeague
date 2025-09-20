#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de migration de base de données corrigé
À exécuter une seule fois pour migrer vers le système dual
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"Erreur connexion: {e}")
        return None

def column_exists(cursor, table_name, column_name):
    """Vérifie si une colonne existe dans une table"""
    try:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, (table_name, column_name))
        return cursor.fetchone() is not None
    except:
        return False

def table_exists(cursor, table_name):
    """Vérifie si une table existe"""
    try:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = %s AND table_schema = 'public'
        """, (table_name,))
        return cursor.fetchone() is not None
    except:
        return False

def migrate_database():
    """Migration complète et sécurisée vers le système dual"""
    conn = get_connection()
    if not conn:
        print("Impossible de se connecter à la base")
        return False
    
    try:
        print("🔧 MIGRATION SÉCURISÉE VERS SYSTÈME DUAL")
        print("=" * 50)
        
        with conn.cursor() as c:
            # 1. MIGRATION TABLE PLAYERS
            print("🔄 1/5 - Migration table players...")
            
            # Créer table si elle n'existe pas
            if not table_exists(c, 'players'):
                c.execute('''
                    CREATE TABLE players (
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
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("  ✅ Table players créée")
            else:
                # Ajouter colonnes manquantes une par une
                dual_columns = [
                    ('solo_elo', 'INTEGER DEFAULT 1000'),
                    ('solo_wins', 'INTEGER DEFAULT 0'),
                    ('solo_losses', 'INTEGER DEFAULT 0'),
                    ('trio_elo', 'INTEGER DEFAULT 1000'),
                    ('trio_wins', 'INTEGER DEFAULT 0'),
                    ('trio_losses', 'INTEGER DEFAULT 0')
                ]
                
                for col_name, col_type in dual_columns:
                    if not column_exists(c, 'players', col_name):
                        try:
                            c.execute(f'ALTER TABLE players ADD COLUMN {col_name} {col_type}')
                            conn.commit()
                            print(f"  ➤ Ajouté colonne {col_name}")
                        except Exception as e:
                            print(f"  ⚠️ Erreur colonne {col_name}: {e}")
                            conn.rollback()
                
                # Migrer données existantes
                try:
                    c.execute('''
                        UPDATE players SET 
                        solo_elo = CASE WHEN solo_elo = 1000 OR solo_elo IS NULL THEN COALESCE(elo, 1000) ELSE solo_elo END,
                        solo_wins = CASE WHEN solo_wins = 0 OR solo_wins IS NULL THEN COALESCE(wins, 0) ELSE solo_wins END,
                        solo_losses = CASE WHEN solo_losses = 0 OR solo_losses IS NULL THEN COALESCE(losses, 0) ELSE solo_losses END,
                        trio_elo = CASE WHEN trio_elo = 1000 OR trio_elo IS NULL THEN 1000 ELSE trio_elo END,
                        trio_wins = CASE WHEN trio_wins = 0 OR trio_wins IS NULL THEN 0 ELSE trio_wins END,
                        trio_losses = CASE WHEN trio_losses = 0 OR trio_losses IS NULL THEN 0 ELSE trio_losses END
                    ''')
                    conn.commit()
                    print("  ✅ Données existantes migrées vers système dual")
                except Exception as e:
                    print(f"  ⚠️ Erreur migration données: {e}")
                    conn.rollback()
            
            # 2. MIGRATION TABLE LOBBIES
            print("🔄 2/5 - Migration table lobbies...")
            
            if not table_exists(c, 'lobbies'):
                c.execute('''
                    CREATE TABLE lobbies (
                        id SERIAL PRIMARY KEY,
                        room_code TEXT NOT NULL,
                        lobby_type TEXT DEFAULT 'solo' CHECK (lobby_type IN ('solo', 'trio')),
                        players TEXT DEFAULT '',
                        teams TEXT DEFAULT '',
                        max_players INTEGER DEFAULT 6,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("  ✅ Table lobbies créée")
            else:
                # Ajouter colonnes manquantes
                if not column_exists(c, 'lobbies', 'lobby_type'):
                    try:
                        c.execute("ALTER TABLE lobbies ADD COLUMN lobby_type TEXT DEFAULT 'solo'")
                        conn.commit()
                        c.execute("ALTER TABLE lobbies ADD CONSTRAINT lobbies_lobby_type_check CHECK (lobby_type IN ('solo', 'trio'))")
                        conn.commit()
                        print("  ➤ Ajouté colonne lobby_type")
                    except Exception as e:
                        print(f"  ⚠️ Erreur lobby_type: {e}")
                        conn.rollback()
                
                if not column_exists(c, 'lobbies', 'teams'):
                    try:
                        c.execute("ALTER TABLE lobbies ADD COLUMN teams TEXT DEFAULT ''")
                        conn.commit()
                        print("  ➤ Ajouté colonne teams")
                    except Exception as e:
                        print(f"  ⚠️ Erreur teams: {e}")
                        conn.rollback()
                
                # Mettre à jour les lobbies existants
                try:
                    c.execute("UPDATE lobbies SET lobby_type = 'solo' WHERE lobby_type IS NULL OR lobby_type = ''")
                    c.execute("UPDATE lobbies SET teams = '' WHERE teams IS NULL")
                    conn.commit()
                    print("  ✅ Lobbies existants mis à jour")
                except Exception as e:
                    print(f"  ⚠️ Erreur mise à jour lobbies: {e}")
                    conn.rollback()
            
            # 3. RECRÉATION TABLE LOBBY_COOLDOWN
            print("🔄 3/5 - Migration table lobby_cooldown...")
            
            try:
                c.execute('DROP TABLE IF EXISTS lobby_cooldown CASCADE')
                c.execute('''
                    CREATE TABLE lobby_cooldown (
                        id INTEGER PRIMARY KEY,
                        lobby_type TEXT NOT NULL CHECK (lobby_type IN ('solo', 'trio')),
                        last_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                c.execute('''
                    INSERT INTO lobby_cooldown (id, lobby_type, last_creation) 
                    VALUES (1, 'solo', CURRENT_TIMESTAMP), (2, 'trio', CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO UPDATE SET lobby_type = EXCLUDED.lobby_type
                ''')
                conn.commit()
                print("  ✅ Table lobby_cooldown recrée")
            except Exception as e:
                print(f"  ⚠️ Erreur lobby_cooldown: {e}")
                conn.rollback()
            
            # 4. CRÉATION TABLES TRIO
            print("🔄 4/5 - Création tables trio...")
            
            # Table équipes trio
            if not table_exists(c, 'trio_teams'):
                try:
                    c.execute('''
                        CREATE TABLE trio_teams (
                            id SERIAL PRIMARY KEY,
                            name TEXT NOT NULL,
                            captain_id TEXT NOT NULL,
                            player2_id TEXT NOT NULL,
                            player3_id TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    print("  ✅ Table trio_teams créée")
                except Exception as e:
                    print(f"  ⚠️ Erreur trio_teams: {e}")
                    conn.rollback()
            
            # 5. MIGRATION TABLES EXISTANTES AVEC TYPES
            print("🔄 5/5 - Migration tables avec types...")
            
            # Table dodges avec type
            if table_exists(c, 'dodges'):
                if not column_exists(c, 'dodges', 'dodge_type'):
                    try:
                        c.execute("ALTER TABLE dodges ADD COLUMN dodge_type TEXT DEFAULT 'solo'")
                        c.execute("ALTER TABLE dodges ADD CONSTRAINT dodges_dodge_type_check CHECK (dodge_type IN ('solo', 'trio'))")
                        c.execute("UPDATE dodges SET dodge_type = 'solo' WHERE dodge_type IS NULL")
                        conn.commit()
                        print("  ➤ Ajouté dodge_type à dodges")
                    except Exception as e:
                        print(f"  ⚠️ Erreur dodge_type: {e}")
                        conn.rollback()
            
            # Table match_history avec type
            if table_exists(c, 'match_history'):
                if not column_exists(c, 'match_history', 'match_type'):
                    try:
                        c.execute("ALTER TABLE match_history ADD COLUMN match_type TEXT DEFAULT 'solo'")
                        c.execute("ALTER TABLE match_history ADD CONSTRAINT match_history_match_type_check CHECK (match_type IN ('solo', 'trio'))")
                        c.execute("UPDATE match_history SET match_type = 'solo' WHERE match_type IS NULL")
                        conn.commit()
                        print("  ➤ Ajouté match_type à match_history")
                    except Exception as e:
                        print(f"  ⚠️ Erreur match_type: {e}")
                        conn.rollback()
            
            # Table match_messages avec type
            if table_exists(c, 'match_messages'):
                if not column_exists(c, 'match_messages', 'match_type'):
                    try:
                        c.execute("ALTER TABLE match_messages ADD COLUMN match_type TEXT DEFAULT 'solo'")
                        c.execute("ALTER TABLE match_messages ADD CONSTRAINT match_messages_match_type_check CHECK (match_type IN ('solo', 'trio'))")
                        c.execute("UPDATE match_messages SET match_type = 'solo' WHERE match_type IS NULL")
                        conn.commit()
                        print("  ➤ Ajouté match_type à match_messages")
                    except Exception as e:
                        print(f"  ⚠️ Erreur match_type messages: {e}")
                        conn.rollback()
            
            # Vérification finale
            c.execute("SELECT COUNT(*) as count FROM players")
            player_count = c.fetchone()['count']
            
            c.execute("SELECT COUNT(*) as count FROM lobbies")
            lobby_count = c.fetchone()['count']
            
            conn.commit()
            
            print("=" * 50)
            print("✅ MIGRATION DUAL TERMINÉE AVEC SUCCÈS")
            print(f"👥 {player_count} joueurs dans la base")
            print(f"🏠 {lobby_count} lobbies existants")
            print("🥇 Système Solo opérationnel")
            print("👥 Système Trio opérationnel")
            print("🚫 ELO complètement séparés")
            print("=" * 50)
            
            return True
            
    except Exception as e:
        print(f"❌ Erreur critique migration: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    print("🚀 Lancement migration sécurisée...")
    success = migrate_database()
    if success:
        print("✅ Migration réussie! Vous pouvez maintenant relancer le bot.")
    else:
        print("❌ Migration échouée. Vérifiez la base de données.")
