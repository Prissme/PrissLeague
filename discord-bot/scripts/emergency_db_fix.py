#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMERGENCY DATABASE FIX
Résout les problèmes de transaction rollback en cours
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os

DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"Erreur connexion: {e}")
        return None

def emergency_fix():
    """Fix d'urgence pour résoudre les transactions bloquées"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        print("🚨 EMERGENCY DATABASE FIX")
        print("=" * 40)
        
        with conn.cursor() as c:
            # 1. Forcer rollback de toutes les transactions en cours
            try:
                conn.rollback()
                print("✅ Rollback forcé")
            except:
                pass
            
            # 2. Vérifier et ajouter colonnes chaos manquantes
            print("🔧 Ajout colonnes chaos...")
            
            # Vérifier existence des colonnes une par une
            c.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'players' 
                AND column_name IN ('chaos_elo', 'chaos_wins', 'chaos_losses')
                AND table_schema = 'public'
            """)
            existing_cols = [row['column_name'] for row in c.fetchall()]
            
            chaos_columns = {
                'chaos_elo': 'INTEGER DEFAULT 1000',
                'chaos_wins': 'INTEGER DEFAULT 0', 
                'chaos_losses': 'INTEGER DEFAULT 0'
            }
            
            for col_name, col_def in chaos_columns.items():
                if col_name not in existing_cols:
                    try:
                        c.execute(f'ALTER TABLE players ADD COLUMN {col_name} {col_def}')
                        conn.commit()
                        print(f"  ✅ {col_name} ajoutée")
                    except Exception as e:
                        print(f"  ❌ Erreur {col_name}: {e}")
                        conn.rollback()
                else:
                    print(f"  ℹ️ {col_name} existe déjà")
            
            # 3. Fix contrainte lobbies
            print("🏠 Fix contrainte lobbies...")
            try:
                c.execute('ALTER TABLE lobbies DROP CONSTRAINT IF EXISTS lobbies_lobby_type_check')
                conn.commit()
                c.execute("""
                    ALTER TABLE lobbies 
                    ADD CONSTRAINT lobbies_lobby_type_check 
                    CHECK (lobby_type IN ('solo', 'trio', 'chaos'))
                """)
                conn.commit()
                print("  ✅ Contrainte lobbies mise à jour")
            except Exception as e:
                print(f"  ❌ Erreur contrainte: {e}")
                conn.rollback()
            
            # 4. Nettoyer lobbies invalides
            print("🧹 Nettoyage lobbies...")
            try:
                c.execute("DELETE FROM lobbies WHERE lobby_type NOT IN ('solo', 'trio', 'chaos') OR lobby_type IS NULL")
                deleted = c.rowcount
                conn.commit()
                print(f"  ✅ {deleted} lobbies invalides supprimés")
            except Exception as e:
                print(f"  ❌ Erreur nettoyage: {e}")
                conn.rollback()
            
            # 5. Update lobby_cooldown pour chaos
            print("⏰ Fix lobby_cooldown...")
            try:
                # Vérifier si l'entrée chaos existe
                c.execute("SELECT id FROM lobby_cooldown WHERE lobby_type = 'chaos'")
                if not c.fetchone():
                    c.execute("""
                        INSERT INTO lobby_cooldown (id, lobby_type, last_creation) 
                        VALUES (3, 'chaos', CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET lobby_type = 'chaos'
                    """)
                    conn.commit()
                    print("  ✅ Entrée chaos ajoutée")
                else:
                    print("  ℹ️ Entrée chaos existe déjà")
            except Exception as e:
                print(f"  ❌ Erreur lobby_cooldown: {e}")
                conn.rollback()
            
            # 6. Vérification finale
            print("📊 Vérification...")
            
            # Vérifier colonnes chaos
            c.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'players' 
                AND column_name IN ('chaos_elo', 'chaos_wins', 'chaos_losses')
                AND table_schema = 'public'
            """)
            chaos_cols = len(c.fetchall())
            
            # Vérifier contrainte
            c.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'lobbies' 
                AND constraint_name = 'lobbies_lobby_type_check'
            """)
            constraint_ok = c.fetchone() is not None
            
            # Vérifier cooldown chaos
            c.execute("SELECT COUNT(*) as count FROM lobby_cooldown WHERE lobby_type = 'chaos'")
            chaos_cooldown = c.fetchone()['count'] > 0
            
            print("=" * 40)
            print("📊 RÉSULTATS:")
            print(f"🎲 Colonnes chaos: {chaos_cols}/3 ({'✅' if chaos_cols == 3 else '❌'})")
            print(f"🏠 Contrainte lobbies: {'✅' if constraint_ok else '❌'}")
            print(f"⏰ Cooldown chaos: {'✅' if chaos_cooldown else '❌'}")
            
            success = chaos_cols == 3 and constraint_ok and chaos_cooldown
            
            if success:
                print("✅ BASE DE DONNÉES RÉPARÉE")
                print("🚀 Vous pouvez relancer le bot")
            else:
                print("⚠️ PROBLÈMES RESTANTS")
                print("❌ Vérifiez les erreurs ci-dessus")
            
            return success
            
    except Exception as e:
        print(f"❌ Erreur critique: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False
    finally:
        conn.close()

def test_chaos_functionality():
    """Test si les fonctionnalités chaos marchent"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        print("\n🧪 TEST FONCTIONNALITÉS CHAOS")
        print("-" * 30)
        
        with conn.cursor() as c:
            # Test 1: Lecture colonnes chaos
            try:
                c.execute("SELECT chaos_elo, chaos_wins, chaos_losses FROM players LIMIT 1")
                c.fetchone()
                print("✅ Lecture colonnes chaos OK")
            except Exception as e:
                print(f"❌ Lecture colonnes chaos: {e}")
                return False
            
            # Test 2: Insertion lobby chaos
            try:
                c.execute("INSERT INTO lobbies (room_code, lobby_type) VALUES ('TEST123', 'chaos')")
                lobby_id = c.lastrowid
                c.execute("DELETE FROM lobbies WHERE room_code = 'TEST123'")
                conn.commit()
                print("✅ Création lobby chaos OK")
            except Exception as e:
                print(f"❌ Création lobby chaos: {e}")
                conn.rollback()
                return False
            
            # Test 3: Update ELO chaos
            try:
                # Trouver un joueur existant
                c.execute("SELECT discord_id FROM players LIMIT 1")
                player = c.fetchone()
                if player:
                    c.execute("""
                        UPDATE players 
                        SET chaos_elo = 1050, chaos_wins = chaos_wins + 1 
                        WHERE discord_id = %s
                    """, (player['discord_id'],))
                    conn.commit()
                    print("✅ Update ELO chaos OK")
                else:
                    print("⚠️ Aucun joueur pour test")
            except Exception as e:
                print(f"❌ Update ELO chaos: {e}")
                conn.rollback()
                return False
            
            print("🎉 TOUS LES TESTS PASSÉS")
            return True
            
    except Exception as e:
        print(f"❌ Erreur test: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    if not DATABASE_URL:
        print("❌ DATABASE_URL manquant!")
        exit(1)
    
    print("🚨 LANCEMENT FIX D'URGENCE")
    
    # Fix principal
    success = emergency_fix()
    
    if success:
        # Test des fonctionnalités
        test_success = test_chaos_functionality()
        
        if test_success:
            print("\n🎉 RÉPARATION COMPLÈTE RÉUSSIE!")
            print("✅ Redémarrez votre bot maintenant")
        else:
            print("\n⚠️ Fix partiel - certains problèmes subsistent")
    else:
        print("\n❌ ÉCHEC DE LA RÉPARATION")
        print("Contactez le support technique")