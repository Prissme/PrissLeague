#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Système de Backup Python pur (sans pg_dump)
Compatible avec Koyeb et environnements en lecture seule
"""

import os
import json
import logging
import asyncio
import gzip
from datetime import datetime
import glob
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class PythonBackupManager:
    def __init__(self, database_url, backup_path="/tmp/backups"):
        self.database_url = database_url
        self.backup_path = backup_path
        self.max_backups = 10
        self.backup_frequency_hours = 6
        self.backup_task = None
        self.is_running = False
        
        # Utiliser /tmp car c'est écrivable sur Koyeb
        os.makedirs(backup_path, exist_ok=True)
        
        print(f"📁 Backup Python configuré: {backup_path}")
        print(f"🕕 Fréquence: {self.backup_frequency_hours}h")
        print(f"🗂️ Max fichiers: {self.max_backups}")
        print("⚡ Mode: Python pur (compatible Koyeb)")
    
    def get_connection(self):
        """Obtient une connexion à la base"""
        try:
            return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
        except Exception as e:
            logger.error(f"Erreur connexion backup: {e}")
            return None
    
    def create_backup(self, reason="scheduled"):
        """Crée un backup complet de TOUTE la base Supabase"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"supabase_backup_{timestamp}.json.gz"
            filepath = os.path.join(self.backup_path, filename)
            
            print(f"🔄 Création backup complet Supabase ({reason})...")
            
            conn = self.get_connection()
            if not conn:
                print("❌ Impossible de se connecter à la base")
                return False
            
            backup_data = {}
            
            try:
                with conn.cursor() as c:
                    # Récupérer la liste de TOUTES les tables utilisateur
                    c.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_type = 'BASE TABLE'
                        ORDER BY table_name
                    """)
                    
                    tables = [row['table_name'] for row in c.fetchall()]
                    print(f"📋 Tables détectées: {', '.join(tables)}")
                    
                    total_records = 0
                    
                    # Backup de chaque table
                    for table in tables:
                        try:
                            c.execute(f'SELECT * FROM "{table}" ORDER BY 1')
                            rows = c.fetchall()
                            backup_data[table] = [dict(row) for row in rows]
                            table_count = len(backup_data[table])
                            total_records += table_count
                            print(f"  ✅ {table}: {table_count} enregistrements")
                        except Exception as table_error:
                            print(f"  ⚠️ Erreur table {table}: {table_error}")
                            backup_data[table] = []
                
                # Ajouter métadonnées
                backup_data['_metadata'] = {
                    'backup_date': timestamp,
                    'backup_reason': reason,
                    'database_type': 'supabase_complete',
                    'tables_backed_up': len(tables),
                    'total_records': total_records,
                    'tables_list': tables
                }
                
                # Convertir les datetime en string pour JSON
                def datetime_handler(obj):
                    if hasattr(obj, 'isoformat'):
                        return obj.isoformat()
                    raise TypeError(f'Object of type {type(obj)} is not JSON serializable')
                
                # Écrire en JSON compressé
                with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                    json.dump(backup_data, f, default=datetime_handler, indent=2, ensure_ascii=False)
                
                file_size = os.path.getsize(filepath) / 1024  # KB
                
                print(f"✅ Backup Supabase créé: {filename}")
                print(f"📊 {len(tables)} tables, {total_records} enregistrements")
                print(f"💾 Taille: {file_size:.1f} KB")
                
                # Nettoyer les anciens backups
                self.cleanup_old_backups()
                return True
                
            finally:
                conn.close()
                
        except Exception as e:
            print(f"❌ Erreur backup: {e}")
            return False
    
    def restore_from_backup(self, backup_file):
        """Restore depuis un backup complet (ATTENTION: écrase TOUTES les données!)"""
        try:
            filepath = os.path.join(self.backup_path, backup_file)
            
            if not os.path.exists(filepath):
                print(f"❌ Fichier {backup_file} introuvable")
                return False
            
            print(f"🔄 Restoration complète depuis {backup_file}...")
            print("⚠️  ATTENTION: Cela va ÉCRASER TOUTES les données de TOUTE la base!")
            
            # Lire les données
            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            metadata = backup_data.get('_metadata', {})
            tables_to_restore = [k for k in backup_data.keys() if k != '_metadata']
            
            print(f"📋 Tables à restaurer: {', '.join(tables_to_restore)}")
            
            conn = self.get_connection()
            if not conn:
                return False
            
            try:
                with conn.cursor() as c:
                    restored_count = 0
                    
                    # Restaurer chaque table
                    for table_name in tables_to_restore:
                        table_data = backup_data[table_name]
                        
                        if not table_data:
                            print(f"  ⏭️ {table_name}: vide")
                            continue
                        
                        try:
                            # Vider la table
                            c.execute(f'TRUNCATE "{table_name}" CASCADE')
                            
                            # Obtenir les colonnes
                            first_row = table_data[0]
                            columns = list(first_row.keys())
                            
                            # Construire la requête INSERT
                            columns_str = ', '.join(f'"{col}"' for col in columns)
                            placeholders = ', '.join(f'%({col})s' for col in columns)
                            
                            insert_query = f'''
                                INSERT INTO "{table_name}" ({columns_str})
                                VALUES ({placeholders})
                            '''
                            
                            # Insérer tous les enregistrements
                            c.executemany(insert_query, table_data)
                            
                            restored_count += len(table_data)
                            print(f"  ✅ {table_name}: {len(table_data)} enregistrements")
                            
                        except Exception as table_error:
                            print(f"  ❌ Erreur {table_name}: {table_error}")
                    
                    conn.commit()
                    
                    print(f"✅ Restoration terminée: {restored_count} enregistrements")
                    print(f"📊 Backup du {metadata.get('backup_date', 'date inconnue')}")
                    return True
                    
            finally:
                conn.close()
                
        except Exception as e:
            print(f"❌ Erreur restoration: {e}")
            return False
    
    def list_backups(self):
        """Liste tous les backups disponibles"""
        try:
            pattern = os.path.join(self.backup_path, "bot_backup_*.json.gz")
            backup_files = glob.glob(pattern)
            backup_files.sort(key=os.path.getmtime, reverse=True)
            
            backups = []
            for filepath in backup_files:
                filename = os.path.basename(filepath)
                size_kb = os.path.getsize(filepath) / 1024
                date = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                backups.append({
                    'filename': filename,
                    'date': date,
                    'size_kb': size_kb
                })
            
            return backups
            
        except Exception as e:
            print(f"❌ Erreur liste backups: {e}")
            return []
    
    def cleanup_old_backups(self):
        """Supprime les anciens backups"""
        try:
            pattern = os.path.join(self.backup_path, "bot_backup_*.json.gz")
            backup_files = glob.glob(pattern)
            
            if len(backup_files) > self.max_backups:
                backup_files.sort(key=os.path.getmtime)
                files_to_delete = backup_files[:len(backup_files) - self.max_backups]
                
                for file_path in files_to_delete:
                    os.remove(file_path)
                    filename = os.path.basename(file_path)
                    print(f"🗑️ Ancien backup supprimé: {filename}")
                    
        except Exception as e:
            print(f"❌ Erreur nettoyage: {e}")
    
    async def start_auto_backup(self):
        """Démarre le backup automatique"""
        if self.is_running:
            return
            
        self.is_running = True
        print(f"🕕 Backup automatique démarré (toutes les {self.backup_frequency_hours}h)")
        
        # Backup initial
        self.create_backup("startup")
        
        # Tâche périodique
        self.backup_task = asyncio.create_task(self._backup_loop())
    
    async def _backup_loop(self):
        """Boucle de backup"""
        try:
            while self.is_running:
                await asyncio.sleep(self.backup_frequency_hours * 3600)
                if self.is_running:
                    self.create_backup("scheduled")
        except asyncio.CancelledError:
            print("🛑 Backup automatique arrêté")
        except Exception as e:
            print(f"❌ Erreur boucle backup: {e}")
    
    async def stop_auto_backup(self):
        """Arrête le backup automatique"""
        self.is_running = False
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass
        print("🛑 Backup automatique arrêté")
    
    def backup_on_shutdown(self):
        """Backup synchrone au shutdown"""
        print("🔄 Backup final avant arrêt...")
        success = self.create_backup("shutdown")
        if success:
            print("✅ Backup final créé")
        else:
            print("❌ Échec backup final")

# Instance globale
backup_manager = None

def init_python_backup_system(database_url):
    """Initialise le système de backup Python"""
    global backup_manager
    backup_manager = PythonBackupManager(database_url)
    return backup_manager

def get_backup_manager():
    """Retourne l'instance du gestionnaire"""
    return backup_manager
