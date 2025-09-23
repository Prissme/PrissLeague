#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCRIPT DE MIGRATION COMPLÈTE - SYSTÈME TRIPLE
Résout tous les problèmes de base de données pour Solo + Trio + Chaos
À exécuter AVANT de relancer le bot
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
        print(f"❌ Erreur connexion: {e}")
        return None

def column_exists(cursor, table_name, column_name):
    """Vérifie si une colonne existe"""
    try:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s AND table_schema = 'public'
        """, (table_name, column_name))
        return cursor.fetchone() is not None
    except:
        return False

def constraint_exists(cursor, table_name, constraint_name):
    """Vérifie si une contrainte existe"""
    try:
        cursor.execute("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = %s AND constraint_name = %s AND table_schema = 'public'
        """, (table_name, constraint_name))
        return cursor.fetchone() is not None
    except:
        return False

def fix_database_complete():
    """Migration complète et sécurisée vers système triple"""
    conn = get_connection()
    if not conn:
        print("❌ Impossible de se connecter à la base de données")
        return False
    
    try:
        print("🔧 MIGRATION COMPLÈTE SYSTÈME TRIPLE")
        print("=" * 60)
        
        with conn.cursor() as c:
            
            # 1. FIX TABLE PLAYERS - AJOUTER COLONNES CHAOS
            print("📊 1/6 - Ajout colonnes Chaos à la table players...")
            
            chaos_columns = [
                ('chaos_elo', 'INTEGER DEFAULT 1000'),
                ('chaos_wins', 'INTEGER DEFAULT 0'),
                ('chaos_losses', 'INTEGER DEFAULT 0')
            ]
            
            for col_name, col_type in chaos_columns:
                if not column_exists(c, 'players', col_name):
                    try:
                        c.execute(f'ALTER TABLE players ADD COLUMN {col_name} {col_type}')
                        conn.commit()
                        print(f"  ✅ Ajouté colonne {col_name}")
                    except Exception as e:
                        print(f"  ⚠️ Erreur colonne {col_name}: {e}")
                        conn.rollback()
                else:
                    print(f"  ℹ️ Colonne {col_name} déjà existante")
            
            # Vérifier autres colonnes dual
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
                        print(f"  ✅ Ajouté colonne manquante {col_name}")
                    except Exception as e:
                        print(f"  ⚠️ Erreur colonne {col_name}: {e}")
                        conn.rollback()
            
            # Migrer données existantes vers solo si nécessaire
            try:
                c.execute("""
                    UPDATE players SET 
                    solo_elo = CASE 
                        WHEN solo_elo IS NULL OR solo_elo = 1000 
                        THEN COALESCE(elo, 1000) 
                        ELSE solo_elo 
                    END,
                    solo_wins = CASE 
                        WHEN solo_wins IS NULL OR solo_wins = 0 
                        THEN COALESCE(wins, 0) 
                        ELSE solo_wins 
                    END,
                    solo_losses = CASE 
                        WHEN solo_losses IS NULL OR solo_losses = 0 
                        THEN COALESCE(losses, 0) 
                        ELSE solo_losses 
                    END
                    WHERE (solo_elo IS NULL OR solo_elo = 1000) AND elo IS NOT NULL AND elo != 1000
                """)
                conn.commit()
                print("  ✅ Migration données existantes vers solo")
            except Exception as e:
                print(f"  ⚠️ Erreur migration données: {e}")
                conn.rollback()
            
            # 2. FIX TABLE LOBBIES - CONTRAINTE CHAOS
            print("🏠 2/6 - Mise à jour contrainte lobbies pour Chaos...")
            
            # Supprimer ancienne contrainte
            try:
                c.execute('ALTER TABLE lobbies DROP CONSTRAINT IF EXISTS lobbies_lobby_type_check')
                conn.commit()
                print("  ✅ Ancienne contrainte supprimée")
            except Exception as e:
                print(f"  ⚠️ Erreur suppression contrainte: {e}")
                conn.rollback()
            
            # Ajouter nouvelle contrainte avec chaos
            try:
                c.execute("""
                    ALTER TABLE lobbies 
                    ADD CONSTRAINT lobbies_lobby_type_check 
                    CHECK (lobby_type IN ('solo', 'trio', 'chaos'))
                """)
                conn.commit()
                print("  ✅ Nouvelle contrainte avec chaos ajoutée")
            except Exception as e:
                print(f"  ⚠️ Erreur nouvelle contrainte: {e}")
                conn.rollback()
            
            # Ajouter colonne lobby_type si manquante
            if not column_exists(c, 'lobbies', 'lobby_type'):
                try:
                    c.execute("ALTER TABLE lobbies ADD COLUMN lobby_type TEXT DEFAULT 'solo'")
                    conn.commit()
                    print("  ✅ Colonne lobby_type ajoutée")
                except Exception as e:
                    print(f"  ⚠️ Erreur lobby_type: {e}")
                    conn.rollback()
            
            # Ajouter colonne teams si manquante
            if not column_exists(c, 'lobbies', 'teams'):
                try:
                    c.execute("ALTER TABLE lobbies ADD COLUMN teams TEXT DEFAULT ''")
                    conn.commit()
                    print("  ✅ Colonne teams ajoutée")
                except Exception as e:
                    print(f"  ⚠️ Erreur teams: {e}")
                    conn.rollback()
            
            # 3. FIX TABLE LOBBY_COOLDOWN POUR CHAOS
            print("⏰ 3/6 - Mise à jour table lobby_cooldown pour Chaos...")
            
            # Recréer complètement la table
            try:
                c.execute('DROP TABLE IF EXISTS lobby_cooldown CASCADE')
                c.execute('''
                    CREATE TABLE lobby_cooldown (
                        id INTEGER PRIMARY KEY,
                        lobby_type TEXT NOT NULL CHECK (lobby_type IN ('solo', 'trio', 'chaos')),
                        last_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Insérer les 3 types
                c.execute('''
                    INSERT INTO lobby_cooldown (id, lobby_type, last_creation) 
                    VALUES 
                    (1, 'solo', CURRENT_TIMESTAMP),
                    (2, 'trio', CURRENT_TIMESTAMP),
                    (3, 'chaos', CURRENT_TIMESTAMP)
                ''')
                conn.commit()
                print("  ✅ Table lobby_cooldown recréée avec chaos")
            except Exception as e:
                print(f"  ⚠️ Erreur lobby_cooldown: {e}")
                conn.rollback()
            
            # 4. FIX TABLES AVEC CONTRAINTES CHAOS
            print("🚫 4/6 - Mise à jour contraintes pour chaos...")
            
            # Table dodges
            if not column_exists(c, 'dodges', 'dodge_type'):
                try:
                    c.execute("ALTER TABLE dodges ADD COLUMN dodge_type TEXT DEFAULT 'solo'")
                    conn.commit()
                    print("  ✅ Colonne dodge_type ajoutée")
                except Exception as e:
                    print(f"  ⚠️ Erreur dodge_type: {e}")
                    conn.rollback()
            
            try:
                c.execute('ALTER TABLE dodges DROP CONSTRAINT IF EXISTS dodges_dodge_type_check')
                c.execute("ALTER TABLE dodges ADD CONSTRAINT dodges_dodge_type_check CHECK (dodge_type IN ('solo', 'trio', 'chaos'))")
                c.execute("UPDATE dodges SET dodge_type = 'solo' WHERE dodge_type IS NULL")
                conn.commit()
                print("  ✅ Contrainte dodges mise à jour avec chaos")
            except Exception as e:
                print(f"  ⚠️ Erreur contrainte dodges: {e}")
                conn.rollback()
            
            # Table match_history
            if not column_exists(c, 'match_history', 'match_type'):
                try:
                    c.execute("ALTER TABLE match_history ADD COLUMN match_type TEXT DEFAULT 'solo'")
                    conn.commit()
                    print("  ✅ Colonne match_type ajoutée à match_history")
                except Exception as e:
                    print(f"  ⚠️ Erreur match_type: {e}")
                    conn.rollback()
            
            try:
                c.execute('ALTER TABLE match_history DROP CONSTRAINT IF EXISTS match_history_match_type_check')
                c.execute("ALTER TABLE match_history ADD CONSTRAINT match_history_match_type_check CHECK (match_type IN ('solo', 'trio', 'chaos'))")
                c.execute("UPDATE match_history SET match_type = 'solo' WHERE match_type IS NULL")
                conn.commit()
                print("  ✅ Contrainte match_history mise à jour avec chaos")
            except Exception as e:
                print(f"  ⚠️ Erreur contrainte match_history: {e}")
                conn.rollback()
            
            # Table match_messages
            if not column_exists(c, 'match_messages', 'match_type'):
                try:
                    c.execute("ALTER TABLE match_messages ADD COLUMN match_type TEXT DEFAULT 'solo'")
                    conn.commit()
                    print("  ✅ Colonne match_type ajoutée à match_messages")
                except Exception as e:
                    print(f"  ⚠️ Erreur match_type messages: {e}")
                    conn.rollback()
            
            try:
                c.execute('ALTER TABLE match_messages DROP CONSTRAINT IF EXISTS match_messages_match_type_check')
                c.execute("ALTER TABLE match_messages ADD CONSTRAINT match_messages_match_type_check CHECK (match_type IN ('solo', 'trio', 'chaos'))")
                c.execute("UPDATE match_messages SET match_type = 'solo' WHERE match_type IS NULL")
                conn.commit()
                print("  ✅ Contrainte match_messages mise à jour avec chaos")
            except Exception as e:
                print(f"  ⚠️ Erreur contrainte match_messages: {e}")
                conn.rollback()
            
            # 5. CRÉATION TABLE TRIO_TEAMS SI MANQUANTE
            print("👥 5/6 - Vérification table trio_teams...")
            
            try:
                c.execute('''
                    CREATE TABLE IF NOT EXISTS trio_teams (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        captain_id TEXT NOT NULL,
                        player2_id TEXT NOT NULL,
                        player3_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                print("  ✅ Table trio_teams vérifiée/créée")
            except Exception as e:
                print(f"  ⚠️ Erreur trio_teams: {e}")
                conn.rollback()
            
            # 6. VÉRIFICATION FINALE ET STATISTIQUES
            print("📊 6/6 - Vérification finale...")
            
            # Compter les joueurs
            c.execute("SELECT COUNT(*) as count FROM players")
            player_count = c.fetchone()['count']
            
            # Compter les équipes trio
            c.execute("SELECT COUNT(*) as count FROM trio_teams")
            team_count = c.fetchone()['count']
            
            # Vérifier colonnes chaos
            chaos_ready = True
            for col_name, _ in chaos_columns:
                if not column_exists(c, 'players', col_name):
                    chaos_ready = False
                    break
            
            # Vérifier contraintes
            c.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'lobbies' 
                AND constraint_name = 'lobbies_lobby_type_check'
                AND table_schema = 'public'
            """)
            constraint_ok = c.fetchone() is not None
            
            conn.commit()
            
            print("=" * 60)
            print("✅ MIGRATION SYSTÈME TRIPLE TERMINÉE")
            print(f"👥 {player_count} joueurs dans la base")
            print(f"🏆 {team_count} équipes trio existantes")
            print(f"🎲 Colonnes chaos: {'✅ OK' if chaos_ready else '❌ MANQUANTES'}")
            print(f"🏠 Contraintes lobbies: {'✅ OK' if constraint_ok else '❌ PROBLÈME'}")
            print()
            print("🥇 SYSTÈME SOLO: Opérationnel")
            print("👥 SYSTÈME TRIO: Opérationnel")
            print("🎲 SYSTÈME CHAOS: Opérationnel" if chaos_ready else "🎲 SYSTÈME CHAOS: ❌ Problème")
            print("🚫 ELO complètement séparés (3 classements)")
            print("=" * 60)
            
            return chaos_ready and constraint_ok
            
    except Exception as e:
        print(f"❌ Erreur critique migration: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False
    finally:
        conn.close()

def clean_failed_lobbies():
    """Nettoie les lobbies en échec à cause de contraintes"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            # Supprimer les lobbies avec des types invalides
            c.execute("DELETE FROM lobbies WHERE lobby_type NOT IN ('solo', 'trio', 'chaos')")
            deleted_count = c.rowcount
            conn.commit()
            
            if deleted_count > 0:
                print(f"🧹 {deleted_count} lobbies invalides supprimés")
            
            return True
    except Exception as e:
        print(f"❌ Erreur nettoyage lobbies: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    if not DATABASE_URL:
        print("❌ DATABASE_URL manquant dans les variables d'environnement!")
        exit(1)
    
    print("🚀 LANCEMENT MIGRATION SYSTÈME TRIPLE COMPLÈTE")
    print("=" * 60)
    
    # Nettoyer d'abord les lobbies problématiques
    print("🧹 Nettoyage préalable...")
    clean_failed_lobbies()
    
    print()
    
    # Lancer migration complète
    success = fix_database_complete()
    
    print()
    if success:
        print("🎉 MIGRATION RÉUSSIE!")
        print("✅ Vous pouvez maintenant relancer le bot")
        print("✅ Les 3 modes Solo/Trio/Chaos fonctionneront")
    else:
        print("⚠️ MIGRATION AVEC PROBLÈMES")
        print("❌ Vérifiez les erreurs ci-dessus")
        print("❌ Certaines fonctionnalités pourraient ne pas marcher")
    
    print("=" * 60)