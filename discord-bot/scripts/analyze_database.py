#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import RealDictCursor
import os

DATABASE_URL = os.getenv('DATABASE_URL')

conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
with conn.cursor() as c:
    # Lister toutes les tables
    c.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name
    """)
    tables = [r['table_name'] for r in c.fetchall()]
    
    print("📋 TABLES EXISTANTES:")
    for table in tables:
        print(f"\n🔹 {table}")
        
        # Colonnes de chaque table
        c.execute("""
            SELECT column_name, data_type, column_default, is_nullable
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table,))
        
        for col in c.fetchall():
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
            print(f"  - {col['column_name']}: {col['data_type']} {nullable}{default}")
        
        # Compter les enregistrements
        c.execute(f'SELECT COUNT(*) as count FROM "{table}"')
        count = c.fetchone()['count']
        print(f"  📊 {count} enregistrements")

conn.close()
