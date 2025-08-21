#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script temporaire pour retirer 3 défaites aux joueurs ayant minimum 4 défaites
À SUPPRIMER après utilisation !
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    """Obtient une connexion à la base PostgreSQL"""
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"❌ Erreur connexion DB: {e}")
        return None

def reduce_losses():
    """Retire 3 défaites aux joueurs ayant minimum 4 défaites"""
    conn = get_connection()
    if not conn:
        print("❌ Impossible de se connecter à la base de données")
        return False
    
    try:
        with conn.cursor() as c:
            # Récupérer les joueurs avec minimum 4 défaites
            c.execute('''
                SELECT discord_id, name, losses 
                FROM players 
                WHERE losses >= 4
                ORDER BY losses DESC
            ''')
            players = c.fetchall()
            
            if not players:
                print("ℹ️  Aucun joueur trouvé avec 4 défaites ou plus")
                return True
            
            print(f"🔍 {len(players)} joueur(s) trouvé(s) avec 4+ défaites:")
            for player in players:
                print(f"   • {player['name']}: {player['losses']} défaites")
            
            # Demander confirmation
            print("\n⚠️  ATTENTION: Cette action va retirer 3 défaites à chaque joueur listé ci-dessus.")
            confirmation = input("Confirmer l'opération ? (tapez 'OUI' en majuscules): ")
            
            if confirmation != 'OUI':
                print("❌ Opération annulée")
                return False
            
            # Effectuer la réduction
            affected_count = 0
            print("\n🔄 Traitement en cours...")
            
            for player in players:
                old_losses = player['losses']
                new_losses = max(0, old_losses - 3)  # S'assurer qu'on ne descend pas en dessous de 0
                
                c.execute('''
                    UPDATE players 
                    SET losses = %s 
                    WHERE discord_id = %s
                ''', (new_losses, player['discord_id']))
                
                print(f"   ✅ {player['name']}: {old_losses} → {new_losses} défaites (-3)")
                affected_count += 1
            
            # Valider les changements
            conn.commit()
            
            print(f"\n✅ Opération terminée avec succès!")
            print(f"📊 {affected_count} joueur(s) traité(s)")
            print("\n⚠️  N'oubliez pas de supprimer ce script après utilisation!")
            
            return True
            
    except Exception as e:
        print(f"❌ Erreur lors de l'opération: {e}")
        conn.rollback()  # Annuler les changements en cas d'erreur
        return False
    finally:
        conn.close()

def show_statistics():
    """Affiche les statistiques avant/après"""
    conn = get_connection()
    if not conn:
        return
    
    try:
        with conn.cursor() as c:
            # Statistiques générales
            c.execute('''
                SELECT 
                    COUNT(*) as total_players,
                    COUNT(CASE WHEN losses >= 4 THEN 1 END) as players_4plus_losses,
                    AVG(losses) as avg_losses,
                    MAX(losses) as max_losses,
                    MIN(losses) as min_losses
                FROM players
            ''')
            stats = c.fetchone()
            
            print("📊 STATISTIQUES ACTUELLES:")
            print(f"   • Joueurs total: {stats['total_players']}")
            print(f"   • Joueurs avec 4+ défaites: {stats['players_4plus_losses']}")
            print(f"   • Défaites moyenne: {round(stats['avg_losses'], 2) if stats['avg_losses'] else 0}")
            print(f"   • Maximum défaites: {stats['max_losses'] or 0}")
            print(f"   • Minimum défaites: {stats['min_losses'] or 0}")
            
    except Exception as e:
        print(f"❌ Erreur statistiques: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    if not DATABASE_URL:
        print("❌ DATABASE_URL manquant dans les variables d'environnement!")
        exit(1)
    
    print("🚀 Script de réduction des défaites")
    print("=" * 50)
    
    # Afficher les statistiques actuelles
    show_statistics()
    print()
    
    # Effectuer la réduction
    success = reduce_losses()
    
    if success:
        print()
        print("📊 STATISTIQUES APRÈS TRAITEMENT:")
        show_statistics()
    
    print("\n🗑️  IMPORTANT: Supprimez ce script après utilisation!")
