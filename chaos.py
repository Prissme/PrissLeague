#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Chaos - Mode de jeu chaotique et fun
Version corrigée avec gestion robuste des erreurs de base de données
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio
import json
import random
from datetime import datetime, timedelta

# Configuration
RESULT_CHANNEL_ID = 1408595087331430520
MATCH_SUMMARY_CHANNEL_ID = 1385919316569886732

# Maps Null's Brawl - Liste complète
CHAOS_MAPS = [
    # Maps Gemmes
    "Mine Hard Rock", "Fort de Gemmes", "Tunnel de Mine", "Cachette Secrète",
    "Ligue Junior", "Retour à la Terre", "Précis et Concis", "Zone Sécurisée",
    "Dernière Station", "Catacombes", "Temple des Gemmes", "Passage Étroit",
    
    # Maps Bounty
    "Triple Dribble", "Milieu de Scène", "Étoile Filante", "Pont au Loin",
    "Canal Étroit", "Terrain d'Entraînement", "Ligne de Mire", "Temple Enchanté",
    "Poursuite Mortelle", "Retour au Lac", "Shooting Star", "Treasure Hunt",
    
    # Maps Heist
    "C'est Chaud Patate", "C'est Ouvert !", "Coffre-Fort Facile", "Terrain Miné",
    "Pont-Levis", "Nether", "G.G. Corral", "Kaboom Canyon",
    "Assault on Mount Doom", "Bridge Too Far", "Pit Stop", "Hot Potato",
    
    # Maps Brawl Ball
    "Mille-Feuille", "Cercle de Feu", "Backyard Bowl", "Super Stadium",
    "Sneaky Fields", "Triple Dribble", "Center Stage", "Galaxy Arena",
    "Pinball Dreams", "Sunny Soccer", "Penalty Kick", "Scorched Stone",
    
    # Maps Knockout
    "Rocher de la Belle", "Ravin du Bras d'Or", "Island Invasion", "Out in the Open",
    "Flaring Phoenix", "Goldarm Gulch", "Belle's Rock", "Riverside Ring",
    "Hard Rock Mine", "Layer Cake", "Skull Creek", "Dry Season",
    
    # Maps Hot Zone
    "Parallel Plays", "Ring of Fire", "Dueling Beetles", "Split",
    "Open Business", "Controller Chaos", "Square Off", "Public Eye",
    
    # Maps Siege
    "Factory Rush", "Nuts & Bolts", "Junk Park", "Bot Drop",
    "Mech Workshop", "Robo Rumble", "Machine Learning", "Assembly Attack",
    
    # Maps spéciales
    "Showdown - Feast or Famine", "Showdown - Stormy Plains", "Showdown - Death Valley",
    "Showdown - Rockwall Brawl", "Showdown - Thousand Lakes", "Showdown - Cavern Churn"
]

# Brawlers Null's Brawl - Liste complète des 96 brawlers
CHAOS_BRAWLERS = [
    # Rarity: Common
    "Shelly", "Nita", "Colt", "Bull", "Jessie", "Brock", "Dynamike", "Bo", "Tick", "8-Bit", "Emz",
    
    # Rarity: Rare  
    "El Primo", "Barley", "Poco", "Rosa", "Penny", "Carl", "Jacky", "Gus",
    
    # Rarity: Super Rare
    "Ricochet", "Darryl", "Penny", "Rico", "Piper", "Pam", "Frank", "Bibi", "Bea", "Nani", "Edgar", "Griff", "Grom", "Bonnie", "Otis", "Sam", "Gus", "Chester", "Gray", "Mandy", "R-T", "Willow", "Maisie",
    
    # Rarity: Epic
    "Mortis", "Tara", "Gene", "Max", "Mr. P", "Sprout", "Byron", "Squeak", "Lou", "Colonel Ruffs", "Belle", "Buzz", "Ash", "Lola", "Eve", "Janet", "Stu", "Buster", "Fang", "Bonnie", "Janet", "Otis", "Sam", "Gus", "Hank", "Pearl", "Larry & Lawrie", "Angelo",
    
    # Rarity: Mythic
    "Tara", "Gene", "Mortis", "Max", "Mr. P", "Sprout", "Byron", "Squeak", "Lou", "Ruffs", "Belle", "Buzz", "Ash", "Lola", "Meg", "Grom", "Fang", "Eve", "Janet", "Bonnie", "Otis", "Sam", "Buster", "Chester", "Gray", "Mandy", "R-T", "Willow", "Maisie", "Hank", "Pearl", "Larry & Lawrie", "Angelo", "Berry",
    
    # Rarity: Legendary
    "Spike", "Crow", "Leon", "Sandy", "Amber", "Meg", "Chester", "Cordelius", "Kit", "Draco"
]

# Modificateurs Null's Brawl
CHAOS_MODIFIERS = [
    "Vitesse x2", "Dégâts x2", "Santé x2", "Rechargement Rapide", 
    "Super Charge Rapide", "Invisibilité Aléatoire", "Bouclier Permanent",
    "Projectiles qui Rebondissent", "Dégâts de Zone", "Guérison Continue",
    "Téléportation Aléatoire", "Gravité Réduite", "Taille Géante",
    "Taille Miniature", "Missiles qui Suivent", "Explosion à la Mort",
    "Double Saut", "Murs qui Bougent", "Sol de Lave", "Brouillard de Guerre",
    "Boost d'Énergie", "Vision Nocturne", "Rage Mode", "Chaos Total"
]

def get_connection():
    from main import get_connection as main_get_connection
    return main_get_connection()

def ensure_chaos_database():
    """S'assure que la base de données est prête pour le chaos"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            # Vérifier/créer colonnes chaos
            chaos_columns = [
                ('chaos_elo', 'INTEGER DEFAULT 1000'),
                ('chaos_wins', 'INTEGER DEFAULT 0'),
                ('chaos_losses', 'INTEGER DEFAULT 0')
            ]
            
            for col_name, col_def in chaos_columns:
                try:
                    # Test si la colonne existe
                    c.execute(f"SELECT {col_name} FROM players LIMIT 1")
                except Exception:
                    # Colonne manquante, l'ajouter
                    try:
                        c.execute(f'ALTER TABLE players ADD COLUMN {col_name} {col_def}')
                        conn.commit()
                        print(f"Colonne {col_name} ajoutée automatiquement")
                    except Exception as e:
                        print(f"Impossible d'ajouter {col_name}: {e}")
                        conn.rollback()
            
            # Vérifier/créer entrée cooldown chaos
            try:
                c.execute("SELECT COUNT(*) as count FROM lobby_cooldown WHERE lobby_type = 'chaos'")
                if c.fetchone()['count'] == 0:
                    c.execute("""
                        INSERT INTO lobby_cooldown (id, lobby_type, last_creation) 
                        VALUES (3, 'chaos', CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET lobby_type = 'chaos'
                    """)
                    conn.commit()
                    print("Entrée cooldown chaos créée automatiquement")
            except Exception as e:
                print(f"Erreur cooldown chaos: {e}")
                conn.rollback()
            
            return True
    except Exception as e:
        print(f"Erreur ensure_chaos_database: {e}")
        return False
    finally:
        conn.close()

def save_match_message_id(message_id, match_type):
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as c:
            c.execute('INSERT INTO match_messages (message_id, match_type) VALUES (%s, %s)', 
                     (message_id, match_type))
            conn.commit()
        return True
    except Exception as e:
        print(f"Erreur save_match_message_id: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_player_dodge_count(discord_id, match_type):
    conn = get_connection()
    if not conn:
        return 0
    try:
        with conn.cursor() as c:
            c.execute('SELECT COUNT(*) as count FROM dodges WHERE discord_id = %s AND dodge_type = %s', 
                     (str(discord_id), match_type))
            result = c.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        print(f"Erreur get_player_dodge_count: {e}")
        return 0
    finally:
        conn.close()

def record_dodge(discord_id, match_type):
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as c:
            c.execute('INSERT INTO dodges (discord_id, dodge_type) VALUES (%s, %s)', 
                     (str(discord_id), match_type))
            conn.commit()
        return True
    except Exception as e:
        print(f"Erreur record_dodge: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def add_player_to_chaos_lobby(lobby_id, discord_id):
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT players, lobby_type FROM lobbies WHERE id = %s', (lobby_id,))
            result = c.fetchone()
            if not result or result['lobby_type'] != 'chaos':
                return False, "Lobby chaos inexistant"
            
            players = result['players'].split(',') if result['players'] else []
            
            if str(discord_id) in players:
                return False, "Déjà dans ce lobby"
            if len(players) >= 6:
                return False, "Lobby complet"
            
            players.append(str(discord_id))
            players_str = ','.join(filter(None, players))
            
            c.execute('UPDATE lobbies SET players = %s WHERE id = %s', (players_str, lobby_id))
            conn.commit()
            
            return True, f"Rejoint! ({len(players)}/6 joueurs)"
    except Exception as e:
        print(f"Erreur add_player_to_chaos_lobby: {e}")
        conn.rollback()
        return False, "Erreur interne"
    finally:
        conn.close()

def generate_chaos_match_info():
    """Génère les éléments aléatoires pour le match chaos"""
    selected_map = random.choice(CHAOS_MAPS)
    selected_brawlers = random.sample(CHAOS_BRAWLERS, 6)  # 6 brawlers différents
    selected_modifier = random.choice(CHAOS_MODIFIERS)
    
    return {
        'map': selected_map,
        'brawlers': selected_brawlers,
        'modifier': selected_modifier
    }

class ChaosVoteView(discord.ui.View):
    def __init__(self, team1_ids, team2_ids, lobby_id, room_code, guild, chaos_info):
        super().__init__(timeout=None)
        self.team1_ids = team1_ids
        self.team2_ids = team2_ids
        self.lobby_id = lobby_id
        self.room_code = room_code
        self.guild = guild
        self.chaos_info = chaos_info
        self.match_type = 'chaos'
        self.votes = {'team1': set(), 'team2': set()}
        self.dodge_reports = {}
        self.match_validated = False
        
    def _build_message(self):
        team1_mentions = []
        team2_mentions = []
        
        # Assigner les brawlers aux joueurs
        brawler_assignments = self.chaos_info['brawlers'].copy()
        random.shuffle(brawler_assignments)
        
        for i, pid in enumerate(self.team1_ids):
            brawler = brawler_assignments[i] if i < len(brawler_assignments) else "Brawler Aléatoire"
            team1_mentions.append(f"<@{pid}> ({brawler})")
        
        for i, pid in enumerate(self.team2_ids):
            brawler = brawler_assignments[i + 3] if i + 3 < len(brawler_assignments) else "Brawler Aléatoire"
            team2_mentions.append(f"<@{pid}> ({brawler})")
        
        votes1 = len(self.votes['team1'])
        votes2 = len(self.votes['team2'])
        
        message = f"🎲 **VOTE RÉSULTAT CHAOS** - Lobby #{self.lobby_id}\n"
        message += f"Code: {self.room_code}\n\n"
        message += f"🗺️ **Map:** {self.chaos_info['map']}\n"
        message += f"⚡ **Modificateur:** {self.chaos_info['modifier']}\n\n"
        message += f"🔵 **Équipe Bleue** ({votes1} votes):\n{chr(10).join(team1_mentions)}\n\n"
        message += f"🔴 **Équipe Rouge** ({votes2} votes):\n{chr(10).join(team2_mentions)}\n\n"
        message += f"🎮 **Lien:** https://link.nulls.gg/nb/invite/gameroom/fr?tag={self.room_code}\n\n"
        message += f"📊 Votes: {votes1 + votes2}/6 | Majorité: 4/6\n"
        message += f"🎲 **MODE CHAOS** - Tout est aléatoire!"
        
        return message
    
    @discord.ui.button(label='🔵 Équipe Bleue', style=discord.ButtonStyle.primary)
    async def team1_win(self, interaction, button):
        await self.handle_vote(interaction, 'team1')
    
    @discord.ui.button(label='🔴 Équipe Rouge', style=discord.ButtonStyle.danger)
    async def team2_win(self, interaction, button):
        await self.handle_vote(interaction, 'team2')
    
    @discord.ui.button(label='🚨 Signaler Dodge', style=discord.ButtonStyle.secondary)
    async def report_dodge(self, interaction, button):
        await self.handle_dodge_report(interaction)
    
    async def safe_respond(self, interaction, content, ephemeral=False):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content, ephemeral=ephemeral)
        except:
            pass
    
    async def handle_vote(self, interaction, team):
        try:
            user_id = interaction.user.id
            all_players = set(self.team1_ids + self.team2_ids)
            
            if user_id not in all_players:
                await self.safe_respond(interaction, "❌ Seuls les joueurs du match peuvent voter!", ephemeral=True)
                return
                
            if self.match_validated:
                await self.safe_respond(interaction, "❌ Match déjà terminé!", ephemeral=True)
                return
            
            self.votes['team1'].discard(user_id)
            self.votes['team2'].discard(user_id)
            self.votes[team].add(user_id)
            
            team_name = "Bleue 🔵" if team == 'team1' else "Rouge 🔴"
            await self.safe_respond(interaction, f"✅ Vote équipe {team_name} enregistré!", ephemeral=True)
            
            votes1 = len(self.votes['team1'])
            votes2 = len(self.votes['team2'])
            
            if votes1 >= 4:
                await self.validate_match(True, f"majorité ({votes1} votes)")
            elif votes2 >= 4:
                await self.validate_match(False, f"majorité ({votes2} votes)")
            elif votes1 + votes2 == 6:
                if votes1 > votes2:
                    await self.validate_match(True, f"votes finaux ({votes1}-{votes2})")
                elif votes2 > votes1:
                    await self.validate_match(False, f"votes finaux ({votes2}-{votes1})")
                else:
                    await self._update_message(self._build_message())
            else:
                await self._update_message(self._build_message())
                
        except Exception as e:
            print(f"Erreur handle_vote chaos: {e}")
    
    async def handle_dodge_report(self, interaction):
        try:
            user_id = interaction.user.id
            all_players = set(self.team1_ids + self.team2_ids)
            
            if user_id not in all_players:
                await self.safe_respond(interaction, "❌ Seuls les joueurs du match peuvent signaler!", ephemeral=True)
                return
            
            options = []
            for pid in all_players:
                if pid != user_id:
                    member = self.guild.get_member(pid)
                    display_name = member.display_name if member else f"Joueur {pid}"
                    options.append(discord.SelectOption(
                        label=display_name,
                        value=str(pid)
                    ))
            
            if options:
                select = ChaosDodgeSelect(options, self, user_id)
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await self.safe_respond(interaction, "🚨 Sélectionnez le joueur qui a dodge:", view=view, ephemeral=True)
            else:
                await self.safe_respond(interaction, "❌ Aucun autre joueur à signaler", ephemeral=True)
                
        except Exception as e:
            print(f"Erreur handle_dodge_report chaos: {e}")
    
    async def validate_match(self, team1_wins, reason, dodge_player_id=None, dodge_penalty=0):
        try:
            from main import get_player, calculate_elo_change, save_match_history
            
            self.match_validated = True
            
            winner_ids = self.team1_ids if team1_wins else self.team2_ids
            loser_ids = self.team2_ids if team1_wins else self.team1_ids
            
            winners, losers = [], []
            winner_elos, loser_elos = [], []
            
            # Utiliser chaos_elo avec gestion sécurisée
            for pid in winner_ids:
                player = get_player(pid)
                if player:
                    winners.append(player)
                    chaos_elo = player.get('chaos_elo', 1000) or 1000
                    winner_elos.append(chaos_elo)
            
            for pid in loser_ids:
                player = get_player(pid)
                if player:
                    losers.append(player)
                    chaos_elo = player.get('chaos_elo', 1000) or 1000
                    loser_elos.append(chaos_elo)
            
            if len(winners) != 3 or len(losers) != 3:
                await self.safe_respond(None, "Erreur validation: joueurs manquants")
                return
            
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            
            winner_changes, loser_changes = [], []
            
            # Calculer et appliquer les changements ELO
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                change = calculate_elo_change(old_elo, loser_avg, True)
                if dodge_player_id:
                    change = int(change * 0.8)
                new_elo = max(0, old_elo + change)
                update_chaos_player_elo_safe(player['discord_id'], new_elo, True)
                winner_changes.append(change)
            
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                change = calculate_elo_change(old_elo, winner_avg, False)
                
                if dodge_player_id and int(player['discord_id']) == dodge_player_id:
                    change -= dodge_penalty
                elif dodge_player_id:
                    change = int(change * 0.3)
                
                new_elo = max(0, old_elo + change)
                update_chaos_player_elo_safe(player['discord_id'], new_elo, False)
                loser_changes.append(change)
            
            for item in self.children:
                item.disabled = True
            
            team_name = "Bleue" if team1_wins else "Rouge"
            validation_msg = f"✅ **MATCH CHAOS VALIDÉ** ({reason})\n🏆 Victoire Équipe {team_name}\nLobby #{self.lobby_id}"
            await self._update_message(validation_msg)
            
            # Sauvegarder l'historique du match
            class MockMember:
                def __init__(self, discord_id, name):
                    self.id = int(discord_id)
                    self.display_name = name
            
            mock_winners = [MockMember(p['discord_id'], p['name']) for p in winners]
            mock_losers = [MockMember(p['discord_id'], p['name']) for p in losers]
            
            save_match_history(mock_winners, mock_losers, winner_changes, loser_changes,
                             dodge_player_id if dodge_player_id else None, self.match_type)
            
            await self.send_match_summary(winners, losers, winner_elos, loser_elos,
                                        winner_changes, loser_changes, reason, dodge_player_id, dodge_penalty)
            
        except Exception as e:
            print(f"Erreur validate_match chaos: {e}")
    
    async def send_match_summary(self, winners, losers, winner_elos, loser_elos,
                               winner_changes, loser_changes, reason, dodge_player_id=None, dodge_penalty=0):
        try:
            winning_team = "Bleue 🔵" if winners[0]['discord_id'] in [str(i) for i in self.team1_ids] else "Rouge 🔴"
            
            message = f"🎲 **RÉSULTAT MATCH CHAOS**\n\n"
            message += f"**Victoire Équipe {winning_team}** ({reason})\n"
            message += f"Lobby #{self.lobby_id} - Code: {self.room_code}\n\n"
            message += f"🗺️ Map: {self.chaos_info['map']}\n"
            message += f"⚡ Modificateur: {self.chaos_info['modifier']}\n\n"
            
            if dodge_player_id:
                message += f"🚨 **DODGE:** <@{dodge_player_id}> (-{dodge_penalty} ELO)\n\n"
            
            message += "🏆 **GAGNANTS:**\n"
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                change = winner_changes[i]
                new_elo = old_elo + change
                message += f"<@{player['discord_id']}>: {old_elo} → {new_elo} (+{change})\n"
            
            message += "\n💀 **PERDANTS:**\n"
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                change = loser_changes[i]
                new_elo = old_elo + change
                
                if dodge_player_id and int(player['discord_id']) == dodge_player_id:
                    message += f"🚨 <@{player['discord_id']}>: {old_elo} → {new_elo} ({change:+}) [DODGER]\n"
                else:
                    message += f"<@{player['discord_id']}>: {old_elo} → {new_elo} ({change:+})\n"
            
            message += f"\n↩️ *Réagissez avec ↩️ pour annuler ce match*"
            
            summary_channel = self.guild.get_channel(MATCH_SUMMARY_CHANNEL_ID)
            if summary_channel:
                summary_msg = await summary_channel.send(message)
                await summary_msg.add_reaction("↩️")
                save_match_message_id(summary_msg.id, self.match_type)
                
        except Exception as e:
            print(f"Erreur send_match_summary chaos: {e}")
    
    async def _update_message(self, content):
        try:
            if hasattr(self, 'current_message') and self.current_message:
                disabled_view = None
                if self.match_validated:
                    disabled_view = discord.ui.View()
                    for item in self.children:
                        item.disabled = True
                        disabled_view.add_item(item)
                
                await self.current_message.edit(
                    content=content, 
                    view=disabled_view if disabled_view else self
                )
        except Exception as e:
            print(f"Erreur _update_message chaos: {e}")

class ChaosDodgeSelect(discord.ui.Select):
    def __init__(self, options, vote_view, reporter_id):
        super().__init__(
            placeholder="Choisir le joueur qui a dodge...", 
            options=options,
            min_values=1,
            max_values=1
        )
        self.vote_view = vote_view
        self.reporter_id = reporter_id
    
    async def callback(self, interaction):
        try:
            reported_id = int(self.values[0])
            self.vote_view.dodge_reports[self.reporter_id] = reported_id
            
            counts = {}
            for rep_id in self.vote_view.dodge_reports.values():
                counts[rep_id] = counts.get(rep_id, 0) + 1
            
            for player_id, count in counts.items():
                if count >= 3:
                    await self.handle_confirmed_dodge(player_id)
                    return
            
            reported_member = self.vote_view.guild.get_member(reported_id)
            reported_name = reported_member.display_name if reported_member else f"Joueur {reported_id}"
            
            await self.vote_view.safe_respond(
                interaction, 
                f"✅ {reported_name} signalé pour dodge", 
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Erreur ChaosDodgeSelect callback: {e}")
    
    async def handle_confirmed_dodge(self, dodge_player_id):
        try:
            from main import calculate_dodge_penalty
            
            record_dodge(dodge_player_id, self.vote_view.match_type)
            dodge_count = get_player_dodge_count(dodge_player_id, self.vote_view.match_type)
            penalty = calculate_dodge_penalty(dodge_count)
            
            team1_wins = dodge_player_id not in self.vote_view.team1_ids
            await self.vote_view.validate_match(team1_wins, "dodge confirmé", dodge_player_id, penalty)
            
        except Exception as e:
            print(f"Erreur handle_confirmed_dodge chaos: {e}")

def update_chaos_player_elo_safe(discord_id, new_elo, won):
    """Version sécurisée de l'update ELO chaos avec gestion robuste des erreurs"""
    conn = get_connection()
    if not conn:
        print(f"Erreur update_chaos_player_elo_safe: Impossible de se connecter")
        return False
    
    try:
        with conn.cursor() as c:
            # Vérifier que les colonnes chaos existent
            try:
                c.execute("SELECT chaos_elo, chaos_wins, chaos_losses FROM players LIMIT 1")
            except Exception:
                # Colonnes manquantes, essayer de les créer
                print("Tentative de création automatique des colonnes chaos...")
                chaos_columns = [
                    ('chaos_elo', 'INTEGER DEFAULT 1000'),
                    ('chaos_wins', 'INTEGER DEFAULT 0'),
                    ('chaos_losses', 'INTEGER DEFAULT 0')
                ]
                
                for col_name, col_def in chaos_columns:
                    try:
                        c.execute(f'ALTER TABLE players ADD COLUMN {col_name} {col_def}')
                        conn.commit()
                        print(f"Colonne {col_name} créée")
                    except Exception as e:
                        print(f"Impossible de créer {col_name}: {e}")
                        conn.rollback()
                        return False
            
            # Effectuer la mise à jour
            if won:
                c.execute('''
                    UPDATE players 
                    SET chaos_elo = %s, chaos_wins = COALESCE(chaos_wins, 0) + 1 
                    WHERE discord_id = %s
                ''', (new_elo, str(discord_id)))
            else:
                c.execute('''
                    UPDATE players 
                    SET chaos_elo = %s, chaos_losses = COALESCE(chaos_losses, 0) + 1 
                    WHERE discord_id = %s
                ''', (new_elo, str(discord_id)))
            
            # Vérifier que la mise à jour a réussi
            if c.rowcount == 0:
                print(f"Aucun joueur trouvé pour l'ID {discord_id}")
                return False
            
            conn.commit()
            return True
            
    except Exception as e:
        print(f"Erreur update_chaos_player_elo_safe: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False
    finally:
        conn.close()

def get_chaos_leaderboard():
    """Récupère le classement chaos avec gestion robuste des erreurs"""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as c:
            # Vérifier que les colonnes chaos existent
            try:
                c.execute('''
                    SELECT *, 
                           COALESCE(chaos_elo, 1000) as chaos_elo,
                           COALESCE(chaos_wins, 0) as chaos_wins,
                           COALESCE(chaos_losses, 0) as chaos_losses
                    FROM players 
                    ORDER BY COALESCE(chaos_elo, 1000) DESC 
                    LIMIT 20
                ''')
                results = c.fetchall()
                return [dict(row) for row in results] if results else []
            except Exception as e:
                if "does not exist" in str(e).lower():
                    print("Colonnes chaos manquantes dans get_chaos_leaderboard")
                    # S'assurer que la base est configurée
                    ensure_chaos_database()
                    return []
                else:
                    raise e
    except Exception as e:
        print(f"Erreur get_chaos_leaderboard: {e}")
        return []
    finally:
        conn.close()

def undo_last_chaos_match():
    """Annule le dernier match chaos avec gestion robuste"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            c.execute('''
                SELECT * FROM match_history 
                WHERE match_type = 'chaos' 
                ORDER BY match_date DESC 
                LIMIT 1
            ''')
            last_match = c.fetchone()
            
            if not last_match:
                return False, "Aucun match chaos à annuler"
            
            match_data = json.loads(last_match['match_data'])
            
            # Annuler les changements ELO avec gestion sécurisée
            winners = match_data['winners']
            winner_changes = match_data['winner_elo_changes']
            
            for i, player_id in enumerate(winners):
                old_change = winner_changes[i]
                try:
                    c.execute('''
                        UPDATE players 
                        SET chaos_elo = COALESCE(chaos_elo, 1000) - %s,
                            chaos_wins = GREATEST(COALESCE(chaos_wins, 0) - 1, 0)
                        WHERE discord_id = %s
                    ''', (old_change, player_id))
                except Exception as e:
                    print(f"Erreur annulation winner {player_id}: {e}")
            
            losers = match_data['losers']
            loser_changes = match_data['loser_elo_changes']
            
            for i, player_id in enumerate(losers):
                old_change = loser_changes[i]
                try:
                    c.execute('''
                        UPDATE players 
                        SET chaos_elo = COALESCE(chaos_elo, 1000) - %s,
                            chaos_losses = GREATEST(COALESCE(chaos_losses, 0) - 1, 0)
                        WHERE discord_id = %s
                    ''', (old_change, player_id))
                except Exception as e:
                    print(f"Erreur annulation loser {player_id}: {e}")
            
            # Annuler le dodge si il y en avait un
            dodge_player_id = match_data.get('dodge_player_id')
            if dodge_player_id:
                try:
                    c.execute('''
                        DELETE FROM dodges 
                        WHERE id = (
                            SELECT id FROM dodges 
                            WHERE discord_id = %s AND dodge_type = 'chaos'
                            ORDER BY dodge_date DESC 
                            LIMIT 1
                        )
                    ''', (dodge_player_id,))
                except Exception as e:
                    print(f"Erreur annulation dodge: {e}")
            
            # Supprimer l'historique
            c.execute('DELETE FROM match_history WHERE id = %s', (last_match['id'],))
            
            conn.commit()
            
            # Récupérer les noms pour retour
            from main import get_player
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
        print(f"Erreur undo_last_chaos_match: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False, f"Erreur interne: {str(e)}"
    finally:
        conn.close()

async def setup_chaos_commands(bot):
    """Configure toutes les commandes chaos avec vérification préalable"""
    
    # S'assurer que la base de données est prête
    if not ensure_chaos_database():
        print("⚠️ Problème configuration base de données chaos")
    
    @bot.command(name='chaos')
    async def create_chaos(ctx, room_code: str = None):
        from main import get_player, create_player, create_lobby, PING_ROLE_ID
        
        if not room_code:
            await ctx.send("❌ Usage: !chaos <code_room>")
            return
        
        player = get_player(ctx.author.id)
        if not player:
            create_player(ctx.author.id, ctx.author.display_name)
        
        # S'assurer que la base supporte chaos avant de créer le lobby
        if not ensure_chaos_database():
            await ctx.send("❌ Système chaos temporairement indisponible")
            return
        
        lobby_id, msg = create_lobby(room_code.upper(), 'chaos')
        if not lobby_id:
            await ctx.send(f"❌ {msg}")
            return
        
        success, join_msg = add_player_to_chaos_lobby(lobby_id, ctx.author.id)
        if success:
            message = (f"<@&{PING_ROLE_ID}>\n\n🎲 **NOUVEAU LOBBY CHAOS #{lobby_id}**\n"
                      f"Code: {room_code.upper()}\n"
                      f"Créateur: {ctx.author.display_name}\n"
                      f"Rejoindre: !joinchaos {lobby_id}\n\n"
                      f"⚡ **Mode Chaos activé!**\n"
                      f"• Map aléatoire parmi toutes celles du jeu\n"
                      f"• Brawler aléatoire pour chaque joueur\n"
                      f"• Modificateur fou au hasard\n"
                      f"• ELO séparé des autres modes")
            await ctx.send(message)
        else:
            await ctx.send(f"❌ {join_msg}")
    
    @bot.command(name='joinchaos')
    async def join_chaos(ctx, lobby_id: int = None):
        from main import get_player, create_player, get_lobby, create_random_teams
        
        if not lobby_id:
            await ctx.send("❌ Usage: !joinchaos <id_lobby>")
            return
        
        player = get_player(ctx.author.id)
        if not player:
            create_player(ctx.author.id, ctx.author.display_name)
        
        success, msg = add_player_to_chaos_lobby(lobby_id, ctx.author.id)
        if not success:
            await ctx.send(f"❌ {msg}")
            return
        
        lobby = get_lobby(lobby_id)
        if lobby and lobby['lobby_type'] == 'chaos':
            players = lobby['players'].split(',') if lobby['players'] else []
            if len(players) >= 6:
                team1_ids, team2_ids = create_random_teams([int(id) for id in players])
                
                # Générer les éléments chaos
                chaos_info = generate_chaos_match_info()
                
                await ctx.send(f"🎲 **MATCH CHAOS LANCÉ!** Lobby #{lobby_id}\n"
                              f"🗺️ Map: **{chaos_info['map']}**\n"
                              f"⚡ Modificateur: **{chaos_info['modifier']}**\n"
                              f"🎮 Préparez-vous au chaos total!")
                
                vote_channel = ctx.guild.get_channel(RESULT_CHANNEL_ID)
                if vote_channel:
                    vote_view = ChaosVoteView(team1_ids, team2_ids, lobby_id, 
                                            lobby['room_code'], ctx.guild, chaos_info)
                    vote_msg = await vote_channel.send(vote_view._build_message(), view=vote_view)
                    vote_view.current_message = vote_msg
                
                # Supprimer le lobby
                conn = get_connection()
                if conn:
                    try:
                        with conn.cursor() as c:
                            c.execute('DELETE FROM lobbies WHERE id = %s', (lobby_id,))
                            conn.commit()
                    finally:
                        conn.close()
            else:
                await ctx.send(f"✅ Rejoint lobby chaos! ({len(players)}/6 joueurs)")
    
    @bot.command(name='elochaos')
    async def elo_chaos(ctx, member: discord.Member = None):
        from main import get_player
        
        target = member or ctx.author
        player = get_player(target.id)
        if not player:
            await ctx.send("❌ Joueur non inscrit")
            return
        
        players = get_chaos_leaderboard()
        rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(target.id)), len(players) + 1)
        
        chaos_elo = player.get('chaos_elo', 1000) or 1000
        chaos_wins = player.get('chaos_wins', 0) or 0
        chaos_losses = player.get('chaos_losses', 0) or 0
        
        winrate = round(chaos_wins / max(1, chaos_wins + chaos_losses) * 100, 1)
        dodge_count = get_player_dodge_count(target.id, 'chaos')
        
        message = (f"🎲 **{target.display_name} - CHAOS**\n"
                  f"ELO: {chaos_elo} | Rang: #{rank}\n"
                  f"W/L: {chaos_wins}/{chaos_losses} ({winrate}%)")
        
        if dodge_count > 0:
            message += f"\n🚨 Dodges: {dodge_count}"
        
        await ctx.send(message)
    
    @bot.command(name='leaderboardchaos')
    async def leaderboard_chaos(ctx):
        players = get_chaos_leaderboard()[:10]  # Top 10
        
        if not players:
            await ctx.send("❌ Aucun joueur inscrit en chaos")
            return
        
        message = "🎲 **CLASSEMENT CHAOS - TOP 10**\n\n"
        
        for i, player in enumerate(players, 1):
            chaos_wins = player.get('chaos_wins', 0) or 0
            chaos_losses = player.get('chaos_losses', 0) or 0
            winrate = round(chaos_wins / max(1, chaos_wins + chaos_losses) * 100, 1)
            
            if i == 1:
                emoji = "🏆"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = f"`{i}.`"
            
            chaos_elo = player.get('chaos_elo', 1000) or 1000
            message += f"{emoji} **{player['name']}** - {chaos_elo} ELO\n"
            message += f"    W/L: {chaos_wins}/{chaos_losses} ({winrate}%)\n\n"
        
        await ctx.send(message)
    
    @bot.command(name='undochaos')
    async def undo_chaos(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        
        success, result = undo_last_chaos_match()
        if success:
            message = f"🔄 **MATCH CHAOS ANNULÉ!**\n"
            message += f"Gagnants: {', '.join(result['winners'])}\n"
            message += f"Perdants: {', '.join(result['losers'])}"
        else:
            message = f"❌ Erreur: {result}"
        
        await ctx.send(message)
    
    @bot.command(name='chaosinfo')
    async def chaos_info(ctx):
        """Affiche les informations du mode chaos"""
        message = "🎲 **MODE CHAOS - GUIDE COMPLET**\n\n"
        
        message += "**🎯 Principe:**\n"
        message += "Mode de jeu complètement aléatoire et fun!\n\n"
        
        message += "**⚡ Fonctionnement:**\n"
        message += "• Map tirée au hasard parmi TOUTES celles du jeu\n"
        message += "• Chaque joueur a un brawler différent assigné\n"
        message += "• Modificateur de jeu complètement fou\n"
        message += "• ELO totalement séparé des modes Solo/Trio\n\n"
        
        message += "**🎮 Commandes:**\n"
        message += "• `!chaos <code>` - Créer lobby chaos\n"
        message += "• `!joinchaos <id>` - Rejoindre lobby\n"
        message += "• `!elochaos` - Voir son ELO chaos\n"
        message += "• `!leaderboardchaos` - Classement chaos\n"
        message += "• `!chaosinfo` - Ce guide\n\n"
        
        message += f"**📊 Statistiques actuelles:**\n"
        message += f"• {len(CHAOS_MAPS)} maps disponibles\n"
        message += f"• {len(CHAOS_BRAWLERS)} brawlers différents\n"
        message += f"• {len(CHAOS_MODIFIERS)} modificateurs fous\n\n"
        
        message += "**🎲 Exemples de modificateurs:**\n"
        message += "• Vitesse x2, Dégâts x2, Santé x2\n"
        message += "• Téléportation aléatoire, Gravité réduite\n"
        message += "• Explosion à la mort, Missiles qui suivent\n"
        message += "• Sol de lave, Brouillard de guerre, et bien d'autres!\n\n"
        
        message += "**🏆 Pourquoi jouer en Chaos?**\n"
        message += "• Expérience complètement différente à chaque match\n"
        message += "• Pas de méta, tout peut arriver!\n"
        message += "• Mode détendu et amusant\n"
        message += "• Classement spécial pour les plus fous"
        
        await ctx.send(message)
    
    @bot.command(name='chaostest')
    async def chaos_test(ctx):
        """Test les fonctionnalités chaos (admin seulement)"""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        
        success = ensure_chaos_database()
        if success:
            await ctx.send("✅ Base de données chaos opérationnelle")
        else:
            await ctx.send("❌ Problème avec la base de données chaos")
    
    print("✅ Commandes CHAOS configurées avec gestion robuste")
    print("🎲 Mode CHAOS - Expérience aléatoire et fun")
    print("🗺️ Maps, brawlers et modificateurs au hasard")
    print("⚡ ELO complètement séparé des autres modes")
    print("🛡️ Protection contre les erreurs de base de données")