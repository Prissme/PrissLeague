#!/usr/bin/env python3
"""
Fix display_name column issue
Ce script résout le problème de colonne display_name manquante
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

def fix_display_name():
    """Corrige le problème display_name vs name"""
    if not DATABASE_URL:
        print("❌ DATABASE_URL manquant!")
        return False
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    
    try:
        print("🔧 CORRECTION COLONNE DISPLAY_NAME")
        print("=" * 50)
        
        with conn.cursor() as c:
            # Vérifier quelle colonne existe
            c.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'players' 
                AND column_name IN ('name', 'display_name')
                AND table_schema = 'public'
            """)
            existing_cols = [row['column_name'] for row in c.fetchall()]
            
            print(f"Colonnes existantes: {existing_cols}")
            
            if 'display_name' in existing_cols and 'name' not in existing_cols:
                # Cas 1: Renommer display_name en name
                print("📝 Renommage display_name → name...")
                c.execute('ALTER TABLE players RENAME COLUMN display_name TO name')
                conn.commit()
                print("✅ Colonne renommée")
                
            elif 'display_name' in existing_cols and 'name' in existing_cols:
                # Cas 2: Les deux existent, copier et supprimer
                print("📝 Migration display_name → name...")
                c.execute('UPDATE players SET name = display_name WHERE name IS NULL OR name = \'\'')
                c.execute('ALTER TABLE players DROP COLUMN display_name')
                conn.commit()
                print("✅ Migration effectuée")
                
            elif 'name' in existing_cols:
                # Cas 3: Tout est OK
                print("✅ Colonne 'name' déjà présente")
                
            else:
                # Cas 4: Aucune colonne (étrange)
                print("❌ Aucune colonne name/display_name trouvée!")
                print("Ajout colonne 'name'...")
                c.execute("ALTER TABLE players ADD COLUMN name TEXT NOT NULL DEFAULT 'Unknown'")
                conn.commit()
                print("✅ Colonne 'name' ajoutée")
            
            # Vérification finale
            c.execute("""
                SELECT column_name, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'players' 
                AND column_name = 'name'
                AND table_schema = 'public'
            """)
            result = c.fetchone()
            
            if result:
                print("=" * 50)
                print("✅ CORRECTION RÉUSSIE")
                print(f"Colonne: {result['column_name']}")
                print(f"Nullable: {result['is_nullable']}")
                print(f"Default: {result['column_default']}")
                return True
            else:
                print("❌ Problème persistant")
                return False
                
    except Exception as e:
        print(f"❌ Erreur: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    success = fix_display_name()
    if success:
        print("\n🚀 Vous pouvez maintenant relancer votre bot!")
    else:
        print("\n❌ Correction échouée, contactez le support")
