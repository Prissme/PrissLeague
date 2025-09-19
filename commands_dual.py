#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Dual - COMMANDES SÉPARÉES SOLO ET TRIO
Version complète avec système entièrement séparé
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
import asyncio
import json
from datetime import datetime, timedelta

# Configuration des salons
RESULT_CHANNEL_ID = 1408595087331430520
MATCH_SUMMARY_CHANNEL_ID = 1385919316569886732

# ================================
# UTILITAIRES RÔLES
# ================================

async def ensure_player_has_ping_role(guild, user_id):
    """S'assure qu'un joueur a le rôle ping"""
    try:
        from main import PING_ROLE_ID
        
        member = guild.get_member(user_id)
        if not member:
            return False
            
        role = guild.get_role(PING_ROLE_ID)
        if not role:
            return False
            
        if role not in member.roles:
            await member.add_roles(role, reason="Joueur ELO inscrit automatiquement")
            print(f"Rôle ping attribué à {member.display_name}")
            
        return True
    except Exception as e:
        print(f"Erreur ensure_player_has_ping_role: {e}")
        return False

async def assign_ping_role_to_all_players(guild):
    """Attribue le rôle ping à tous les joueurs en base"""
    try:
        from main import get_leaderboard, PING_ROLE_ID
        
        # Récupérer tous les joueurs (solo et trio)
        solo_players = get_leaderboard('solo')
        trio_players = get_leaderboard('trio')
        
        # Combiner les listes et éliminer les doublons
        all_players = {}
        for player in solo_players + trio_players:
            all_players[player['discord_id']] = player
        
        role = guild.get_role(PING_ROLE_ID)
        if not role:
            print(f"Rôle ping {PING_ROLE_ID} introuvable")
            return 0
        
        assigned_count = 0
        for player in all_players.values():
            member = guild.get_member(int(player['discord_id']))
            if member and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Attribution automatique rôle ELO")
                    assigned_count += 1
                    print(f"Rôle attribué à {member.display_name}")
                except Exception as e:
                    print(f"Erreur attribution rôle pour {member.display_name}: {e}")
        
        return assigned_count
    except Exception as e:
        print(f"Erreur assign_ping_role_to_all_players: {e}")
        return 0

# ================================
# FONCTIONS DATABASE UTILITAIRES
# ================================

def get_connection():
    """Obtient connexion DB"""
    from main import get_connection as main_get_connection
    return main_get_connection()

def save_match_message_id(message_id, match_type):
    """Sauvegarde ID message avec type"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            c.execute('''
                INSERT INTO match_messages (message_id, match_type) 
                VALUES (%s, %s)
            ''', (message_id, match_type))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur save_match_message_id: {e}")
        return False
    finally:
        conn.close()

def get_player_dodge_count(discord_id, match_type):
    """Récupère le nombre de dodges selon le type"""
    conn = get_connection()
    if not conn:
        return 0
    
    try:
        with conn.cursor() as c:
            c.execute('''
                SELECT COUNT(*) as count 
                FROM dodges 
                WHERE discord_id = %s AND dodge_type = %s
            ''', (str(discord_id), match_type))
            result = c.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        print(f"Erreur get_player_dodge_count: {e}")
        return 0
    finally:
        conn.close()

def record_dodge(discord_id, match_type):
    """Enregistre un dodge avec type"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as c:
            c.execute('''
                INSERT INTO dodges (discord_id, dodge_type) 
                VALUES (%s, %s)
            ''', (str(discord_id), match_type))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur record_dodge: {e}")
        return False
    finally:
        conn.close()

# ================================
# FONCTIONS LOBBY SPÉCIALISÉES
# ================================

def add_player_to_solo_lobby(lobby_id, discord_id):
    """Ajoute un joueur au lobby solo"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT players, lobby_type FROM lobbies WHERE id = %s', (lobby_id,))
            result = c.fetchone()
            if not result or result['lobby_type'] != 'solo':
                return False, "Lobby solo inexistant"
            
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
        print(f"Erreur add_player_to_solo_lobby: {e}")
        return False, "Erreur interne"
    finally:
        conn.close()

def add_team_to_trio_lobby(lobby_id, team_id):
    """Ajoute une équipe au lobby trio"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT teams, lobby_type FROM lobbies WHERE id = %s', (lobby_id,))
            result = c.fetchone()
            if not result or result['lobby_type'] != 'trio':
                return False, "Lobby trio inexistant"
            
            teams = result['teams'].split(',') if result['teams'] else []
            
            if str(team_id) in teams:
                return False, "Équipe déjà dans ce lobby"
            
            if len(teams) >= 2:
                return False, "Lobby complet (2 équipes max)"
            
            teams.append(str(team_id))
            teams_str = ','.join(filter(None, teams))
            
            c.execute('UPDATE lobbies SET teams = %s WHERE id = %s', (teams_str, lobby_id))
            conn.commit()
            
            return True, f"Équipe ajoutée! ({len(teams)}/2 équipes)"
    except Exception as e:
        print(f"Erreur add_team_to_trio_lobby: {e}")
        return False, "Erreur interne"
    finally:
        conn.close()

# ================================
# CLASSES DE VOTE DUAL
# ================================

class DualPlayerVoteView(discord.ui.View):
    """Vue de vote séparée selon le mode"""
    
    def __init__(self, team1_ids, team2_ids, lobby_id, room_code, guild, match_type):
        super().__init__(timeout=None)
        self.team1_ids = team1_ids
        self.team2_ids = team2_ids
        self.lobby_id = lobby_id
        self.room_code = room_code
        self.guild = guild
        self.match_type = match_type  # 'solo' ou 'trio'
        self.votes = {'team1': set(), 'team2': set()}
        self.dodge_reports = {}
        self.cancel_votes = set()
        self.match_validated = False
        self.match_cancelled = False
        self.current_message = None
        self.refresh_task = None
        
    async def start_auto_refresh(self):
        """Démarre le refresh automatique"""
        self.refresh_task = asyncio.create_task(self._refresh_loop())
        
    async def _refresh_loop(self):
        """Boucle de refresh toutes les 15 minutes"""
        try:
            while not self.match_validated and not self.match_cancelled:
                await asyncio.sleep(900)  # 15 minutes
                if not self.match_validated and not self.match_cancelled:
                    await self._refresh_message()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Erreur refresh: {e}")
    
    async def _refresh_message(self):
        """Refresh le message"""
        try:
            if not self.current_message or self.match_validated or self.match_cancelled:
                return
                
            channel = self.guild.get_channel(RESULT_CHANNEL_ID)
            if not channel:
                return
                
            # Créer nouvelle vue avec état actuel
            new_view = DualPlayerVoteView(self.team1_ids, self.team2_ids, 
                                         self.lobby_id, self.room_code, self.guild, self.match_type)
            new_view.votes = self.votes.copy()
            new_view.dodge_reports = self.dodge_reports.copy()
            new_view.cancel_votes = self.cancel_votes.copy()
            
            # Supprimer ancien message et créer le nouveau
            try:
                await self.current_message.delete()
            except:
                pass
                
            new_message = await channel.send(new_view._build_message(), view=new_view)
            new_view.current_message = new_message
            await new_view.start_auto_refresh()
            
            # Arrêter ancien refresh
            if self.refresh_task:
                self.refresh_task.cancel()
                
        except Exception as e:
            print(f"Erreur _refresh_message: {e}")
    
    def _build_message(self):
        """Construit le message selon le mode"""
        from main import select_random_maps
        
        # Équipes
        team1_mentions = [f"<@{pid}>" for pid in self.team1_ids]
        team2_mentions = [f"<@{pid}>" for pid in self.team2_ids]
        
        # Maps
        maps = select_random_maps(3)
        maps_text = '\n'.join([f"• {m}" for m in maps])
        
        # Statistiques
        votes1 = len(self.votes['team1'])
        votes2 = len(self.votes['team2'])
        cancel_count = len(self.cancel_votes)
        total_votes = votes1 + votes2
        
        mode_emoji = "🥇" if self.match_type == 'solo' else "👥"
        mode_name = "SOLO" if self.match_type == 'solo' else "TRIO"
        
        message = f"{mode_emoji} **VOTE RÉSULTAT {mode_name}** - Lobby #{self.lobby_id}\n"
        message += f"Code: {self.room_code}\n\n"
        message += f"🔵 **Équipe Bleue** ({votes1} votes):\n{chr(10).join(team1_mentions)}\n\n"
        message += f"🔴 **Équipe Rouge** ({votes2} votes):\n{chr(10).join(team2_mentions)}\n\n"
        message += f"🗺️ **Maps:**\n{maps_text}\n\n"
        message += f"🎮 **Lien:** https://link.nulls.gg/nb/invite/gameroom/fr?tag={self.room_code}\n\n"
        
        # Signalements dodge
        if self.dodge_reports:
            report_counts = {}
            for reported_id in self.dodge_reports.values():
                report_counts[reported_id] = report_counts.get(reported_id, 0) + 1
            message += "🚨 **SIGNALEMENTS DODGE:**\n"
            for player_id, count in report_counts.items():
                message += f"<@{player_id}>: {count} signalement(s)\n"
            message += "\n"
        
        # Votes d'annulation
        if cancel_count > 0:
            message += f"❌ **VOTES ANNULATION:** {cancel_count}/4\n\n"
        
        message += f"📊 Votes: {total_votes}/6 | Majorité: 4/6\n"
        message += "🔄 Auto-refresh: 15min"
        
        return message
    
    async def safe_respond(self, interaction, content, ephemeral=False):
        """Réponse sécurisée"""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content, ephemeral=ephemeral)
        except:
            pass
    
    @discord.ui.button(label='🔵 Équipe Bleue', style=discord.ButtonStyle.primary)
    async def team1_win(self, interaction, button):
        await self.handle_vote(interaction, 'team1')
    
    @discord.ui.button(label='🔴 Équipe Rouge', style=discord.ButtonStyle.danger)
    async def team2_win(self, interaction, button):
        await self.handle_vote(interaction, 'team2')
    
    @discord.ui.button(label='🚨 Signaler Dodge', style=discord.ButtonStyle.secondary)
    async def report_dodge(self, interaction, button):
        await self.handle_dodge_report(interaction)
    
    @discord.ui.button(label='❌ Annuler Game', style=discord.ButtonStyle.secondary)
    async def cancel_game(self, interaction, button):
        await self.handle_cancel_vote(interaction)
    
    async def handle_vote(self, interaction, team):
        """Gère un vote de résultat"""
        try:
            user_id = interaction.user.id
            all_players = set(self.team1_ids + self.team2_ids)
            
            if user_id not in all_players:
                await self.safe_respond(interaction, "❌ Seuls les joueurs du match peuvent voter!", ephemeral=True)
                return
                
            if self.match_validated or self.match_cancelled:
                await self.safe_respond(interaction, "❌ Match déjà terminé!", ephemeral=True)
                return
            
            # Retirer vote précédent et ajouter nouveau
            self.votes['team1'].discard(user_id)
            self.votes['team2'].discard(user_id)
            self.votes[team].add(user_id)
            
            # Retirer du vote d'annulation si présent
            self.cancel_votes.discard(user_id)
            
            team_name = "Bleue 🔵" if team == 'team1' else "Rouge 🔴"
            await self.safe_respond(interaction, f"✅ Vote équipe {team_name} enregistré!", ephemeral=True)
            
            # Vérifier conditions de victoire
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
            print(f"Erreur handle_vote: {e}")
    
    async def handle_cancel_vote(self, interaction):
        """Gère un vote d'annulation"""
        try:
            user_id = interaction.user.id
            all_players = set(self.team1_ids + self.team2_ids)
            
            if user_id not in all_players:
                await self.safe_respond(interaction, "❌ Seuls les joueurs du match peuvent voter!", ephemeral=True)
                return
                
            if self.match_validated or self.match_cancelled:
                await self.safe_respond(interaction, "❌ Match déjà terminé!", ephemeral=True)
                return
            
            # Toggle vote d'annulation
            if user_id in self.cancel_votes:
                self.cancel_votes.remove(user_id)
                await self.safe_respond(interaction, "🔄 Vote d'annulation retiré", ephemeral=True)
            else:
                self.cancel_votes.add(user_id)
                # Retirer des votes de résultat
                self.votes['team1'].discard(user_id)
                self.votes['team2'].discard(user_id)
                await self.safe_respond(interaction, "❌ Vote d'annulation enregistré", ephemeral=True)
            
            # Vérifier si annulation validée
            if len(self.cancel_votes) >= 4:
                await self.cancel_match()
            else:
                await self._update_message(self._build_message())
                
        except Exception as e:
            print(f"Erreur handle_cancel_vote: {e}")
    
    async def handle_dodge_report(self, interaction):
        """Gère signalement dodge"""
        try:
            user_id = interaction.user.id
            all_players = set(self.team1_ids + self.team2_ids)
            
            if user_id not in all_players:
                await self.safe_respond(interaction, "❌ Seuls les joueurs du match peuvent signaler!", ephemeral=True)
                return
                
            if self.match_validated or self.match_cancelled:
                await self.safe_respond(interaction, "❌ Match terminé!", ephemeral=True)
                return
            
            # Créer menu avec tous les autres joueurs
            options = []
            for pid in all_players:
                if pid != user_id:
                    member = self.guild.get_member(pid)
                    display_name = member.display_name if member else f"Joueur {pid}"
                    options.append(discord.SelectOption(
                        label=display_name,
                        value=str(pid),
                        description=f"ID: {pid}"
                    ))
            
            if options:
                select = DodgeSelect(options, self, user_id)
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await self.safe_respond(interaction, "🚨 Sélectionnez le joueur qui a dodge:", view=view, ephemeral=True)
            else:
                await self.safe_respond(interaction, "❌ Aucun autre joueur à signaler", ephemeral=True)
                
        except Exception as e:
            print(f"Erreur handle_dodge_report: {e}")
            await self.safe_respond(interaction, "❌ Erreur interne", ephemeral=True)
    
    async def validate_match(self, team1_wins, reason, dodge_player_id=None, dodge_penalty=0):
        """Valide le match selon le mode"""
        try:
            from main import get_player, update_player_elo, calculate_elo_change, save_match_history
            
            self.match_validated = True
            if self.refresh_task:
                self.refresh_task.cancel()
            
            # Déterminer gagnants/perdants
            winner_ids = self.team1_ids if team1_wins else self.team2_ids
            loser_ids = self.team2_ids if team1_wins else self.team1_ids
            
            # Récupérer joueurs et ELO selon le mode
            winners, losers = [], []
            winner_elos, loser_elos = [], []
            
            elo_field = 'solo_elo' if self.match_type == 'solo' else 'trio_elo'
            
            for pid in winner_ids:
                player = get_player(pid)
                if player:
                    winners.append(player)
                    winner_elos.append(player[elo_field])
            
            for pid in loser_ids:
                player = get_player(pid)
                if player:
                    losers.append(player)
                    loser_elos.append(player[elo_field])
            
            if len(winners) != 3 or len(losers) != 3:
                return
            
            # Calculer changements ELO
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            
            winner_changes, loser_changes = [], []
            
            # Appliquer changements
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                change = calculate_elo_change(old_elo, loser_avg, True)
                if dodge_player_id:
                    change = int(change * 0.8)
                new_elo = max(0, old_elo + change)
                update_player_elo(player['discord_id'], new_elo, True, self.match_type)
                winner_changes.append(change)
            
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                change = calculate_elo_change(old_elo, winner_avg, False)
                
                if dodge_player_id and int(player['discord_id']) == dodge_player_id:
                    change -= dodge_penalty
                elif dodge_player_id:
                    change = int(change * 0.3)
                
                new_elo = max(0, old_elo + change)
                update_player_elo(player['discord_id'], new_elo, False, self.match_type)
                loser_changes.append(change)
            
            # Désactiver boutons
            for item in self.children:
                item.disabled = True
            
            # Message de validation
            team_name = "Bleue" if team1_wins else "Rouge"
            mode_name = "SOLO" if self.match_type == 'solo' else "TRIO"
            validation_msg = f"✅ **MATCH {mode_name} VALIDÉ** ({reason})\n🏆 Victoire Équipe {team_name}\nLobby #{self.lobby_id}"
            await self._update_message(validation_msg)
            
            # Créer objets mock pour l'historique
            class MockMember:
                def __init__(self, discord_id, name):
                    self.id = int(discord_id)
                    self.display_name = name
            
            mock_winners = [MockMember(p['discord_id'], p['name']) for p in winners]
            mock_losers = [MockMember(p['discord_id'], p['name']) for p in losers]
            
            save_match_history(mock_winners, mock_losers, winner_changes, loser_changes,
                             dodge_player_id if dodge_player_id else None, self.match_type)
            
            # Envoyer résumé
            await self.send_match_summary(winners, losers, winner_elos, loser_elos,
                                        winner_changes, loser_changes, reason, dodge_player_id, dodge_penalty)
            
        except Exception as e:
            print(f"Erreur validate_match: {e}")
    
    async def cancel_match(self):
        """Annule le match"""
        try:
            self.match_cancelled = True
            if self.refresh_task:
                self.refresh_task.cancel()
            
            for item in self.children:
                item.disabled = True
            
            mode_name = "SOLO" if self.match_type == 'solo' else "TRIO"
            cancel_msg = f"❌ **MATCH {mode_name} ANNULÉ** - Lobby #{self.lobby_id}\n"
            cancel_msg += f"🗳️ Annulation votée par {len(self.cancel_votes)} joueurs\n"
            cancel_msg += f"Code room: {self.room_code}"
            
            await self._update_message(cancel_msg)
            
        except Exception as e:
            print(f"Erreur cancel_match: {e}")
    
    async def send_match_summary(self, winners, losers, winner_elos, loser_elos,
                               winner_changes, loser_changes, reason, dodge_player_id=None, dodge_penalty=0):
        """Envoie le résumé selon le mode"""
        try:
            winning_team = "Bleue 🔵" if winners[0]['discord_id'] in [str(i) for i in self.team1_ids] else "Rouge 🔴"
            mode_emoji = "🥇" if self.match_type == 'solo' else "👥"
            mode_name = "SOLO" if self.match_type == 'solo' else "TRIO"
            
            message = f"{mode_emoji} **RÉSULTAT MATCH {mode_name}**\n\n"
            message += f"**Victoire Équipe {winning_team}** ({reason})\n"
            message += f"Lobby #{self.lobby_id} - Code: {self.room_code}\n\n"
            
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
                elif dodge_player_id:
                    message += f"<@{player['discord_id']}>: {old_elo} → {new_elo} ({change:+}) [Protégé]\n"
                else:
                    message += f"<@{player['discord_id']}>: {old_elo} → {new_elo} ({change:+})\n"
            
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            message += f"\n📊 ELO moyen: Gagnants {round(winner_avg)} | Perdants {round(loser_avg)}"
            message += f"\n↩️ *Réagissez avec ↩️ pour annuler ce match*"
            
            # Envoyer avec réaction
            summary_channel = self.guild.get_channel(MATCH_SUMMARY_CHANNEL_ID)
            if summary_channel:
                summary_msg = await summary_channel.send(message)
                await summary_msg.add_reaction("↩️")
                save_match_message_id(summary_msg.id, self.match_type)
                
        except Exception as e:
            print(f"Erreur send_match_summary: {e}")
    
    async def _update_message(self, content):
        """Met à jour le message"""
        try:
            if self.current_message:
                disabled_view = None
                if self.match_validated or self.match_cancelled:
                    disabled_view = discord.ui.View()
                    for item in self.children:
                        item.disabled = True
                        disabled_view.add_item(item)
                
                await self.current_message.edit(
                    content=content, 
                    view=disabled_view if disabled_view else self
                )
        except Exception as e:
            print(f"Erreur _update_message: {e}")

class DodgeSelect(discord.ui.Select):
    """Menu de sélection pour dodge"""
    
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
            
            # Compter signalements
            counts = {}
            for rep_id in self.vote_view.dodge_reports.values():
                counts[rep_id] = counts.get(rep_id, 0) + 1
            
            # Vérifier majorité (3+ signalements)
            for player_id, count in counts.items():
                if count >= 3:
                    await self.handle_confirmed_dodge(player_id)
                    return
            
            await self.vote_view.safe_respond(
                interaction, 
                f"✅ {reported_name} signalé pour dodge", 
                ephemeral=True
            )
        except Exception as e:
            print(f"Erreur DodgeSelect callback: {e}")
            await self.vote_view.safe_respond(
                interaction, 
                "❌ Erreur lors du signalement", 
                ephemeral=True
            )
    
    async def handle_confirmed_dodge(self, dodge_player_id):
        """Gère dodge confirmé"""
        try:
            from main import calculate_dodge_penalty
            
            # Enregistrer dodge avec type
            record_dodge(dodge_player_id, self.vote_view.match_type)
            
            # Calculer pénalité selon le type
            dodge_count = get_player_dodge_count(dodge_player_id, self.vote_view.match_type)
            penalty = calculate_dodge_penalty(dodge_count)
            
            # Équipe du dodger perd automatiquement
            team1_wins = dodge_player_id not in self.vote_view.team1_ids
            await self.vote_view.validate_match(team1_wins, "dodge confirmé", dodge_player_id, penalty)
            
        except Exception as e:
            print(f"Erreur handle_confirmed_dodge: {e}")

# ================================
# COMMANDES SOLO
# ================================

async def create_solo_lobby_cmd(ctx, room_code: str = None):
    """!solo <code> - Créer un lobby solo"""
    from main import (get_player, create_player, create_lobby, 
                     MAX_CONCURRENT_LOBBIES_SOLO, PING_ROLE_ID)
    
    if not room_code:
        await ctx.send("❌ Usage: !solo <code_room>")
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    
    # Créer lobby solo
    lobby_id, msg = create_lobby(room_code.upper(), 'solo')
    if not lobby_id:
        await ctx.send(f"❌ {msg}")
        return
    
    # Ajouter créateur
    success, join_msg = add_player_to_solo_lobby(lobby_id, ctx.author.id)
    if success:
        role_mention = f"<@&{PING_ROLE_ID}>"
        message = (f"{role_mention}\n\n🥇 **NOUVEAU LOBBY SOLO #{lobby_id}**\n"
                  f"Code: {room_code.upper()}\n"
                  f"Créateur: {ctx.author.display_name}\n"
                  f"Rejoindre: !joinsolo {lobby_id}")
        await ctx.send(message)
    else:
        await ctx.send(f"❌ {join_msg}")

async def join_solo_lobby_cmd(ctx, lobby_id: int = None):
    """!joinsolo <id> - Rejoindre un lobby solo"""
    if not lobby_id:
        await ctx.send("❌ Usage: !joinsolo <id_lobby>")
        return
    
    from main import get_player, create_player, get_lobby, create_random_teams
    
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    else:
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    
    success, msg = add_player_to_solo_lobby(lobby_id, ctx.author.id)
    if not success:
        await ctx.send(f"❌ {msg}")
        return
    
    # Vérifier si lobby complet
    lobby = get_lobby(lobby_id)
    if lobby and lobby['lobby_type'] == 'solo':
        players = lobby['players'].split(',') if lobby['players'] else []
        if len(players) >= 6:
            team1_ids, team2_ids = create_random_teams([int(id) for id in players])
            
            await ctx.send(f"🚀 **MATCH SOLO LANCÉ!** Lobby #{lobby_id}")
            
            vote_channel = ctx.guild.get_channel(RESULT_CHANNEL_ID)
            if vote_channel:
                vote_view = DualPlayerVoteView(team1_ids, team2_ids, lobby_id, 
                                             lobby['room_code'], ctx.guild, 'solo')
                vote_msg = await vote_channel.send(vote_view._build_message(), view=vote_view)
                vote_view.current_message = vote_msg
                await vote_view.start_auto_refresh()
            
            # Supprimer lobby
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor() as c:
                        c.execute('DELETE FROM lobbies WHERE id = %s', (lobby_id,))
                        conn.commit()
                finally:
                    conn.close()
        else:
            await ctx.send(f"✅ Rejoint lobby solo! ({len(players)}/6 joueurs)")

# ================================
# COMMANDES TRIO
# ================================

async def create_trio_lobby_cmd(ctx, room_code: str = None):
    """!trio <code> - Créer un lobby trio (avec équipe)"""
    from main import (get_player, create_player, create_lobby, get_player_trio_team,
                     MAX_CONCURRENT_LOBBIES_TRIO, PING_ROLE_ID)
    
    if not room_code:
        await ctx.send("❌ Usage: !trio <code_room>")
        return
    
    # Vérifier que le joueur a une équipe
    team = get_player_trio_team(ctx.author.id)
    if not team:
        await ctx.send("❌ Vous devez avoir une équipe trio! Utilisez `!createteam`")
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    
    # Créer lobby trio
    lobby_id, msg = create_lobby(room_code.upper(), 'trio')
    if not lobby_id:
        await ctx.send(f"❌ {msg}")
        return
    
    # Ajouter équipe
    success, join_msg = add_team_to_trio_lobby(lobby_id, team['id'])
    if success:
        role_mention = f"<@&{PING_ROLE_ID}>"
        message = (f"{role_mention}\n\n👥 **NOUVEAU LOBBY TRIO #{lobby_id}**\n"
                  f"Code: {room_code.upper()}\n"
                  f"Équipe: {team['name']}\n"
                  f"Rejoindre: !jointrio {lobby_id}")
        await ctx.send(message)
    else:
        await ctx.send(f"❌ {join_msg}")

async def join_trio_lobby_cmd(ctx, lobby_id: int = None):
    """!jointrio <id> - Rejoindre un lobby trio"""
    if not lobby_id:
        await ctx.send("❌ Usage: !jointrio <id_lobby>")
        return
    
    from main import get_player, create_player, get_lobby, get_player_trio_team
    
    # Vérifier que le joueur a une équipe
    team = get_player_trio_team(ctx.author.id)
    if not team:
        await ctx.send("❌ Vous devez avoir une équipe trio! Utilisez `!createteam`")
        return
    
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    else:
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    
    success, msg = add_team_to_trio_lobby(lobby_id, team['id'])
    if not success:
        await ctx.send(f"❌ {msg}")
        return
    
    # Vérifier si lobby complet (2 équipes)
    lobby = get_lobby(lobby_id)
    if lobby and lobby['lobby_type'] == 'trio':
        teams = lobby['teams'].split(',') if lobby['teams'] else []
        if len(teams) >= 2:
            # Récupérer les équipes
            conn = get_connection()
            team1_players = []
            team2_players = []
            
            if conn:
                try:
                    with conn.cursor() as c:
                        # Équipe 1
                        c.execute('SELECT * FROM trio_teams WHERE id = %s', (int(teams[0]),))
                        team1 = c.fetchone()
                        if team1:
                            team1_players = [int(team1['captain_id']), int(team1['player2_id']), int(team1['player3_id'])]
                        
                        # Équipe 2
                        c.execute('SELECT * FROM trio_teams WHERE id = %s', (int(teams[1]),))
                        team2 = c.fetchone()
                        if team2:
                            team2_players = [int(team2['captain_id']), int(team2['player2_id']), int(team2['player3_id'])]
                finally:
                    conn.close()
            
            if team1_players and team2_players:
                await ctx.send(f"🚀 **MATCH TRIO LANCÉ!** Lobby #{lobby_id}")
                
                vote_channel = ctx.guild.get_channel(RESULT_CHANNEL_ID)
                if vote_channel:
                    vote_view = DualPlayerVoteView(team1_players, team2_players, lobby_id, 
                                                 lobby['room_code'], ctx.guild, 'trio')
                    vote_msg = await vote_channel.send(vote_view._build_message(), view=vote_view)
                    vote_view.current_message = vote_msg
                    await vote_view.start_auto_refresh()
                
                # Supprimer lobby
                conn = get_connection()
                if conn:
                    try:
                        with conn.cursor() as c:
                            c.execute('DELETE FROM lobbies WHERE id = %s', (lobby_id,))
                            conn.commit()
                    finally:
                        conn.close()
        else:
            await ctx.send(f"✅ Équipe ajoutée au lobby trio! ({len(teams)}/2 équipes)")

# ================================
# FONCTION UNDO MODIFIÉE
# ================================

def undo_last_match_by_type(match_type):
    """Annule le dernier match selon le type"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            # Récupérer le dernier match du type
            c.execute('''
                SELECT * FROM match_history 
                WHERE match_type = %s 
                ORDER BY match_date DESC 
                LIMIT 1
            ''', (match_type,))
            last_match = c.fetchone()
            
            if not last_match:
                return False, f"Aucun match {match_type} à annuler"
            
            match_data = json.loads(last_match['match_data'])
            
            # Déterminer les champs ELO selon le type
            if match_type == 'solo':
                elo_field = 'solo_elo'
                wins_field = 'solo_wins'
                losses_field = 'solo_losses'
            else:
                elo_field = 'trio_elo'
                wins_field = 'trio_wins'
                losses_field = 'trio_losses'
            
            # Annuler les changements d'ELO pour les gagnants
            winners = match_data['winners']
            winner_changes = match_data['winner_elo_changes']
            
            for i, player_id in enumerate(winners):
                old_change = winner_changes[i]
                c.execute(f'''
                    UPDATE players 
                    SET {elo_field} = {elo_field} - %s,
                        {wins_field} = GREATEST({wins_field} - 1, 0)
                    WHERE discord_id = %s
                ''', (old_change, player_id))
            
            # Annuler pour les perdants
            losers = match_data['losers']
            loser_changes = match_data['loser_elo_changes']
            
            for i, player_id in enumerate(losers):
                old_change = loser_changes[i]
                c.execute(f'''
                    UPDATE players 
                    SET {elo_field} = {elo_field} - %s,
                        {losses_field} = GREATEST({losses_field} - 1, 0)
                    WHERE discord_id = %s
                ''', (old_change, player_id))
            
            # Annuler dodge si nécessaire
            dodge_player_id = match_data.get('dodge_player_id')
            if dodge_player_id:
                c.execute('''
                    DELETE FROM dodges 
                    WHERE id = (
                        SELECT id FROM dodges 
                        WHERE discord_id = %s AND dodge_type = %s
                        ORDER BY dodge_date DESC 
                        LIMIT 1
                    )
                ''', (dodge_player_id, match_type))
            
            # Supprimer le match de l'historique
            c.execute('DELETE FROM match_history WHERE id = %s', (last_match['id'],))
            
            conn.commit()
            
            # Construire résultat
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
        print(f"Erreur undo_last_match_by_type: {e}")
        return False, f"Erreur interne: {str(e)}"
    finally:
        conn.close()

# ================================
# SETUP FONCTION PRINCIPALE
# ================================

async def setup_commands(bot):
    """Configure toutes les commandes du bot dual"""
    
    # Attribution automatique des rôles au démarrage
    @bot.event
    async def on_ready_role_assignment():
        """Attribue le rôle ping à tous les joueurs existants au démarrage"""
        for guild in bot.guilds:
            assigned = await assign_ping_role_to_all_players(guild)
            if assigned > 0:
                print(f"🎯 {assigned} rôles ping attribués dans {guild.name}")
    
    # Appeler l'attribution au démarrage
    bot.add_listener(on_ready_role_assignment, 'on_ready')
    
    # Commandes Solo
    @bot.command(name='solo')
    async def _create_solo(ctx, room_code: str = None):
        await create_solo_lobby_cmd(ctx, room_code)
    
    @bot.command(name='joinsolo')
    async def _join_solo(ctx, lobby_id: int = None):
        await join_solo_lobby_cmd(ctx, lobby_id)
    
    # Commandes Trio
    @bot.command(name='trio')
    async def _create_trio(ctx, room_code: str = None):
        await create_trio_lobby_cmd(ctx, room_code)
    
    @bot.command(name='jointrio')
    async def _join_trio(ctx, lobby_id: int = None):
        await join_trio_lobby_cmd(ctx, lobby_id)
    
    # Commandes ELO séparées
    @bot.command(name='elosolo')
    async def _elo_solo(ctx, member: discord.Member = None):
        target = member or ctx.author
        from main import get_player, get_leaderboard
        
        player = get_player(target.id)
        if not player:
            await ctx.send("❌ Joueur non inscrit")
            return
        
        await ensure_player_has_ping_role(ctx.guild, target.id)
        
        # Calculer rang solo
        players = get_leaderboard('solo')
        rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(target.id)), len(players))
        
        winrate = round(player['solo_wins'] / max(1, player['solo_wins'] + player['solo_losses']) * 100, 1)
        dodge_count = get_player_dodge_count(target.id, 'solo')
        
        message = (f"🥇 **{target.display_name} - SOLO**\n"
                  f"ELO: {player['solo_elo']} | Rang: #{rank}\n"
                  f"W/L: {player['solo_wins']}/{player['solo_losses']} ({winrate}%)")
        
        if dodge_count > 0:
            message += f"\n🚨 Dodges: {dodge_count}"
        
        await ctx.send(message)
    
    @bot.command(name='elotrio')
    async def _elo_trio(ctx, member: discord.Member = None):
        target = member or ctx.author
        from main import get_player, get_leaderboard
        
        player = get_player(target.id)
        if not player:
            await ctx.send("❌ Joueur non inscrit")
            return
        
        await ensure_player_has_ping_role(ctx.guild, target.id)
        
        # Calculer rang trio
        players = get_leaderboard('trio')
        rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(target.id)), len(players))
        
        winrate = round(player['trio_wins'] / max(1, player['trio_wins'] + player['trio_losses']) * 100, 1)
        dodge_count = get_player_dodge_count(target.id, 'trio')
        
        message = (f"👥 **{target.display_name} - TRIO**\n"
                  f"ELO: {player['trio_elo']} | Rang: #{rank}\n"
                  f"W/L: {player['trio_wins']}/{player['trio_losses']} ({winrate}%)")
        
        if dodge_count > 0:
            message += f"\n🚨 Dodges: {dodge_count}"
        
        await ctx.send(message)
    
    # Classements séparés
    @bot.command(name='topsolo')
    async def _leaderboard_solo(ctx):
        from main import get_leaderboard, get_player
        
        players = get_leaderboard('solo')[:10]
        if not players:
            await ctx.send("📊 Classement solo vide")
            return
        
        message = "🥇 **CLASSEMENT SOLO**\n\n"
        
        for i, player in enumerate(players, 1):
            try:
                member = ctx.guild.get_member(int(player['discord_id']))
                name = member.display_name if member else player['name']
            except:
                name = player['name']
            
            winrate = round(player['solo_wins'] / max(1, player['solo_wins'] + player['solo_losses']) * 100, 1)
            emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            message += f"{emoji} {name} - {player['solo_elo']} ELO ({winrate}%)\n"
        
        # Position joueur actuel
        current_player = get_player(ctx.author.id)
        if current_player:
            all_players = get_leaderboard('solo')
            pos = next((i for i, p in enumerate(all_players, 1) if p['discord_id'] == str(ctx.author.id)), None)
            if pos:
                message += f"\n**Votre position:** #{pos} - {current_player['solo_elo']} ELO"
        
        await ctx.send(message)
    
    @bot.command(name='toptrio')
    async def _leaderboard_trio(ctx):
        from main import get_leaderboard, get_player
        
        players = get_leaderboard('trio')[:10]
        if not players:
            await ctx.send("📊 Classement trio vide")
            return
        
        message = "👥 **CLASSEMENT TRIO**\n\n"
        
        for i, player in enumerate(players, 1):
            try:
                member = ctx.guild.get_member(int(player['discord_id']))
                name = member.display_name if member else player['name']
            except:
                name = player['name']
            
            winrate = round(player['trio_wins'] / max(1, player['trio_wins'] + player['trio_losses']) * 100, 1)
            emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            message += f"{emoji} {name} - {player['trio_elo']} ELO ({winrate}%)\n"
        
        # Position joueur actuel
        current_player = get_player(ctx.author.id)
        if current_player:
            all_players = get_leaderboard('trio')
            pos = next((i for i, p in enumerate(all_players, 1) if p['discord_id'] == str(ctx.author.id)), None)
            if pos:
                message += f"\n**Votre position:** #{pos} - {current_player['trio_elo']} ELO"
        
        await ctx.send(message)
    
    # Commandes lobbies séparées
    @bot.command(name='soloqueue')
    async def _list_solo_lobbies(ctx):
        from main import MAX_CONCURRENT_LOBBIES_SOLO, LOBBY_COOLDOWN_MINUTES_SOLO
        
        conn = get_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion")
            return
        
        try:
            with conn.cursor() as c:
                c.execute("SELECT * FROM lobbies WHERE lobby_type = 'solo' ORDER BY created_at DESC")
                lobbies = c.fetchall()
                
                # Cooldown
                c.execute("SELECT last_creation FROM lobby_cooldown WHERE id = 1")
                result = c.fetchone()
                
                cooldown_active = False
                if result:
                    last_creation = result['last_creation']
                    cooldown_end = last_creation + timedelta(minutes=LOBBY_COOLDOWN_MINUTES_SOLO)
                    now = datetime.now()
                    cooldown_active = now < cooldown_end
        finally:
            conn.close()
        
        message = f"🥇 **LOBBIES SOLO** ({len(lobbies)}/{MAX_CONCURRENT_LOBBIES_SOLO})\n\n"
        
        if not lobbies:
            message += "Aucun lobby solo actif\n"
        else:
            for lobby in lobbies:
                players_count = len(lobby['players'].split(',')) if lobby['players'] else 0
                status = "🟢" if players_count < 6 else "🔴"
                message += f"{status} #{lobby['id']} - {lobby['room_code']} ({players_count}/6)\n"
        
        if cooldown_active:
            remaining = cooldown_end - datetime.now()
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            message += f"\n⏰ Cooldown: {minutes}m {seconds}s"
        else:
            message += "\n✅ Création possible"
        
        await ctx.send(message)
    
    @bot.command(name='trioqueue')
    async def _list_trio_lobbies(ctx):
        from main import MAX_CONCURRENT_LOBBIES_TRIO, LOBBY_COOLDOWN_MINUTES_TRIO
        
        conn = get_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion")
            return
        
        try:
            with conn.cursor() as c:
                c.execute("SELECT * FROM lobbies WHERE lobby_type = 'trio' ORDER BY created_at DESC")
                lobbies = c.fetchall()
                
                # Cooldown
                c.execute("SELECT last_creation FROM lobby_cooldown WHERE id = 2")
                result = c.fetchone()
                
                cooldown_active = False
                if result:
                    last_creation = result['last_creation']
                    cooldown_end = last_creation + timedelta(minutes=LOBBY_COOLDOWN_MINUTES_TRIO)
                    now = datetime.now()
                    cooldown_active = now < cooldown_end
        finally:
            conn.close()
        
        message = f"👥 **LOBBIES TRIO** ({len(lobbies)}/{MAX_CONCURRENT_LOBBIES_TRIO})\n\n"
        
        if not lobbies:
            message += "Aucun lobby trio actif\n"
        else:
            for lobby in lobbies:
                teams_count = len(lobby['teams'].split(',')) if lobby['teams'] else 0
                status = "🟢" if teams_count < 2 else "🔴"
                message += f"{status} #{lobby['id']} - {lobby['room_code']} ({teams_count}/2 équipes)\n"
        
        if cooldown_active:
            remaining = cooldown_end - datetime.now()
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            message += f"\n⏰ Cooldown: {minutes}m {seconds}s"
        else:
            message += "\n✅ Création possible"
        
        await ctx.send(message)
    
    # Commandes équipe
    @bot.command(name='createteam')
    async def _create_team(ctx, teammate1: discord.Member, teammate2: discord.Member, *, team_name: str):
        from main import get_player, create_player, create_trio_team
        
        if len(team_name) > 30:
            await ctx.send("❌ Nom d'équipe trop long (30 caractères max)")
            return
        
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
                          f"👥 Équipiers: {teammate1.display_name}, {teammate2.display_name}\n\n"
                          f"Vous pouvez maintenant rejoindre des lobbies trio avec `!trio <code>`")
        else:
            await ctx.send(f"❌ {msg}")
    
    @bot.command(name='myteam')
    async def _my_team(ctx):
        from main import get_player_trio_team
        
        team = get_player_trio_team(ctx.author.id)
        if not team:
            await ctx.send("❌ Vous n'avez pas d'équipe trio. Utilisez `!createteam @joueur1 @joueur2 Nom`")
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
        message += f"📅 Créée: {team['created_at'].strftime('%d/%m/%Y')}\n\n"
        message += f"💡 Rejoignez des lobbies trio avec `!trio <code>`"
        
        await ctx.send(message)
    
    @bot.command(name='dissolveteam')
    async def _dissolve_team(ctx):
        from main import get_player_trio_team, delete_trio_team
        
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
    
    # Commandes anciennes redirigées
    @bot.command(name='create')
    async def _create_redirect(ctx, room_code: str = None):
        await ctx.send("🎯 **NOUVEAU SYSTÈME DUAL**\n\n"
                      "🥇 **Mode Solo:** `!solo <code>` puis `!joinsolo <id>`\n"
                      "👥 **Mode Trio:** `!trio <code>` puis `!jointrio <id>`\n\n"
                      "Pour le trio, créez d'abord votre équipe: `!createteam @joueur1 @joueur2 Nom`")
    
    @bot.command(name='join')
    async def _join_redirect(ctx, lobby_id: int = None):
        await ctx.send("🎯 **NOUVEAU SYSTÈME DUAL**\n\n"
                      "🥇 **Rejoindre Solo:** `!joinsolo <id>`\n"
                      "👥 **Rejoindre Trio:** `!jointrio <id>`\n\n"
                      "Voir les lobbies: `!soloqueue` ou `!trioqueue`")
    
    @bot.command(name='elo')
    async def _elo_redirect(ctx):
        await ctx.send("🎯 **NOUVEAU SYSTÈME DUAL**\n\n"
                      "🥇 **ELO Solo:** `!elosolo`\n"
                      "👥 **ELO Trio:** `!elotrio`\n\n"
                      "Classements: `!topsolo` ou `!toptrio`")
    
    @bot.command(name='leaderboard')
    async def _leaderboard_redirect(ctx):
        await ctx.send("🎯 **NOUVEAU SYSTÈME DUAL**\n\n"
                      "🥇 **Classement Solo:** `!topsolo`\n"
                      "👥 **Classement Trio:** `!toptrio`")
    
    @bot.command(name='lobbies')
    async def _lobbies_redirect(ctx):
        await ctx.send("🎯 **NOUVEAU SYSTÈME DUAL**\n\n"
                      "🥇 **Queue Solo:** `!soloqueue`\n"
                      "👥 **Queue Trio:** `!trioqueue`")
    
    # Commande help dual
    @bot.command(name='help')
    async def _help_dual(ctx):
        message = "🎯 **BOT ELO DUAL - GUIDE COMPLET**\n\n"
        
        message += "🥇 **MODE SOLO (Matchmaking individuel)**\n"
        message += "• `!solo <code>` - Créer un lobby solo\n"
        message += "• `!joinsolo <id>` - Rejoindre un lobby solo\n"
        message += "• `!soloqueue` - Voir les lobbies solo\n"
        message += "• `!elosolo` - Voir son ELO solo\n"
        message += "• `!topsolo` - Classement solo\n\n"
        
        message += "👥 **MODE TRIO (Équipes fixes)**\n"
        message += "• `!createteam @joueur1 @joueur2 Nom` - Créer équipe\n"
        message += "• `!myteam` - Voir son équipe\n"
        message += "• `!dissolveteam` - Dissoudre équipe (capitaine)\n"
        message += "• `!trio <code>` - Créer lobby trio\n"
        message += "• `!jointrio <id>` - Rejoindre lobby trio\n"
        message += "• `!trioqueue` - Voir lobbies trio\n"
        message += "• `!elotrio` - Voir son ELO trio\n"
        message += "• `!toptrio` - Classement trio\n\n"
        
        message += "🚫 **IMPORTANT:**\n"
        message += "• ELO Solo et Trio sont **complètement séparés**\n"
        message += "• Aucun mélange entre les deux modes\n"
        message += "• Classements et stats indépendants\n"
        message += "• Pour le trio, créez d'abord votre équipe fixe"
        
        await ctx.send(message)
    
    # Commandes admin modifiées pour dual
    @bot.command(name='resetcd')
    async def _resetcd(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        from main import LOBBY_COOLDOWN_MINUTES_SOLO, LOBBY_COOLDOWN_MINUTES_TRIO
        conn = get_connection()
        if conn:
            try:
                with conn.cursor() as c:
                    c.execute('UPDATE lobby_cooldown SET last_creation = CURRENT_TIMESTAMP - INTERVAL %s WHERE id = 1', 
                             (f"{LOBBY_COOLDOWN_MINUTES_SOLO + 1} minutes",))
                    c.execute('UPDATE lobby_cooldown SET last_creation = CURRENT_TIMESTAMP - INTERVAL %s WHERE id = 2', 
                             (f"{LOBBY_COOLDOWN_MINUTES_TRIO + 1} minutes",))
                    conn.commit()
                await ctx.send("✅ Cooldowns solo et trio reset!")
            except Exception as e:
                await ctx.send(f"❌ Erreur: {e}")
            finally:
                conn.close()
    
    @bot.command(name='clearlobbies')
    async def _clearlobbies(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        conn = get_connection()
        if conn:
            try:
                with conn.cursor() as c:
                    c.execute('SELECT COUNT(*) as count FROM lobbies')
                    count = c.fetchone()['count']
                    c.execute('DELETE FROM lobbies')
                    conn.commit()
                await ctx.send(f"🗑️ {count} lobby(s) supprimé(s)")
            except Exception as e:
                await ctx.send(f"❌ Erreur: {e}")
            finally:
                conn.close()
    
    @bot.command(name='undosolo')
    async def _undo_solo(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        success, result = undo_last_match_by_type('solo')
        if success:
            message = f"🔄 **MATCH SOLO ANNULÉ!**\n"
            message += f"Gagnants: {', '.join(result['winners'])}\n"
            message += f"Perdants: {', '.join(result['losers'])}\n"
            message += f"✅ Changements ELO inversés"
            if result['had_dodge']:
                message += f"\n🚨 Dodge annulé"
        else:
            message = f"❌ Erreur: {result}"
        await ctx.send(message)
    
    @bot.command(name='undotrio')
    async def _undo_trio(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        success, result = undo_last_match_by_type('trio')
        if success:
            message = f"🔄 **MATCH TRIO ANNULÉ!**\n"
            message += f"Gagnants: {', '.join(result['winners'])}\n"
            message += f"Perdants: {', '.join(result['losers'])}\n"
            message += f"✅ Changements ELO inversés"
            if result['had_dodge']:
                message += f"\n🚨 Dodge annulé"
        else:
            message = f"❌ Erreur: {result}"
        await ctx.send(message)
    
    @bot.command(name='undo')
    async def _undo_redirect(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        await ctx.send("🎯 **COMMANDES UNDO SÉPARÉES**\n\n"
                      "🥇 **Annuler match solo:** `!undosolo`\n"
                      "👥 **Annuler match trio:** `!undotrio`")
    
    @bot.command(name='addelo')
    async def _addelo(ctx, member: discord.Member = None, amount: int = None, elo_type: str = "solo"):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        if not member or not amount or amount <= 0:
            await ctx.send("❌ Usage: !addelo @joueur montant [solo/trio]")
            return
        
        if elo_type not in ['solo', 'trio']:
            elo_type = 'solo'
        
        from main import get_player, create_player
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
            player = get_player(member.id)
        
        await ensure_player_has_ping_role(ctx.guild, member.id)
        
        elo_field = f'{elo_type}_elo'
        old_elo = player[elo_field]
        new_elo = old_elo + amount
        
        conn = get_connection()
        if conn:
            try:
                with conn.cursor() as c:
                    c.execute(f'UPDATE players SET {elo_field} = %s WHERE discord_id = %s', 
                             (new_elo, str(member.id)))
                    conn.commit()
                await ctx.send(f"✅ {member.display_name} ({elo_type.upper()}): {old_elo} → {new_elo} (+{amount})")
            except Exception as e:
                await ctx.send(f"❌ Erreur: {e}")
            finally:
                conn.close()
    
    @bot.command(name='removeelo')
    async def _removeelo(ctx, member: discord.Member = None, amount: int = None, elo_type: str = "solo"):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        if not member or not amount or amount <= 0:
            await ctx.send("❌ Usage: !removeelo @joueur montant [solo/trio]")
            return
        
        if elo_type not in ['solo', 'trio']:
            elo_type = 'solo'
        
        from main import get_player, create_player
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
            player = get_player(member.id)
        
        await ensure_player_has_ping_role(ctx.guild, member.id)
        
        elo_field = f'{elo_type}_elo'
        old_elo = player[elo_field]
        new_elo = max(0, old_elo - amount)
        actual_removed = old_elo - new_elo
        
        conn = get_connection()
        if conn:
            try:
                with conn.cursor() as c:
                    c.execute(f'UPDATE players SET {elo_field} = %s WHERE discord_id = %s', 
                             (new_elo, str(member.id)))
                    conn.commit()
                message = f"✅ {member.display_name} ({elo_type.upper()}): {old_elo} → {new_elo} (-{actual_removed})"
                if actual_removed < amount:
                    message += f" (min 0)"
                await ctx.send(message)
            except Exception as e:
                await ctx.send(f"❌ Erreur: {e}")
            finally:
                conn.close()
    
    @bot.command(name='assignroles')
    async def _assignroles(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        
        assigned = await assign_ping_role_to_all_players(ctx.guild)
        await ctx.send(f"🎯 {assigned} rôles ping attribués aux joueurs en base!")
    
    # Commandes slash admin dual
    @app_commands.command(name="resultsolo", description="Enregistrer un match solo manuellement (admin)")
    @app_commands.describe(
        gagnant1="Premier gagnant", gagnant2="Deuxième gagnant", gagnant3="Troisième gagnant",
        perdant1="Premier perdant", perdant2="Deuxième perdant", perdant3="Troisième perdant",
        dodge_joueur="Joueur qui a dodge (optionnel)", score="Score du match (optionnel)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(score=[
        app_commands.Choice(name="2-0", value="2-0"),
        app_commands.Choice(name="2-1", value="2-1")
    ])
    async def _result_solo(interaction, gagnant1: discord.Member, gagnant2: discord.Member,
                          gagnant3: discord.Member, perdant1: discord.Member, perdant2: discord.Member,
                          perdant3: discord.Member, dodge_joueur: Optional[discord.Member] = None,
                          score: Optional[Literal["2-0", "2-1"]] = None):
        await record_manual_match_result(interaction, gagnant1, gagnant2, gagnant3,
                                       perdant1, perdant2, perdant3, dodge_joueur, score, 'solo')
    
    @app_commands.command(name="resulttrio", description="Enregistrer un match trio manuellement (admin)")
    @app_commands.describe(
        gagnant1="Premier gagnant", gagnant2="Deuxième gagnant", gagnant3="Troisième gagnant",
        perdant1="Premier perdant", perdant2="Deuxième perdant", perdant3="Troisième perdant",
        dodge_joueur="Joueur qui a dodge (optionnel)", score="Score du match (optionnel)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(score=[
        app_commands.Choice(name="2-0", value="2-0"),
        app_commands.Choice(name="2-1", value="2-1")
    ])
    async def _result_trio(interaction, gagnant1: discord.Member, gagnant2: discord.Member,
                          gagnant3: discord.Member, perdant1: discord.Member, perdant2: discord.Member,
                          perdant3: discord.Member, dodge_joueur: Optional[discord.Member] = None,
                          score: Optional[Literal["2-0", "2-1"]] = None):
        await record_manual_match_result(interaction, gagnant1, gagnant2, gagnant3,
                                       perdant1, perdant2, perdant3, dodge_joueur, score, 'trio')
    
    bot.tree.add_command(_result_solo)
    bot.tree.add_command(_result_trio)
    
    # Event handler pour annulation avec type
    @bot.event
    async def on_raw_reaction_add(payload):
        if payload.user_id == bot.user.id:
            return
        
        if str(payload.emoji) != "↩️" or payload.channel_id != MATCH_SUMMARY_CHANNEL_ID:
            return
        
        # Vérifier si c'est un message de match
        conn = get_connection()
        if not conn:
            return
        
        try:
            with conn.cursor() as c:
                c.execute('SELECT match_type FROM match_messages WHERE message_id = %s', (payload.message_id,))
                result = c.fetchone()
                if not result:
                    return
                
                match_type = result['match_type']
        finally:
            conn.close()
        
        # Vérifier permissions admin
        guild = payload.member.guild if payload.member else None
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        if not member or not member.guild_permissions.administrator:
            return
        
        # Annuler le match selon le type
        success, result = undo_last_match_by_type(match_type)
        if success:
            channel = guild.get_channel(payload.channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(payload.message_id)
                    mode_name = "SOLO" if match_type == 'solo' else "TRIO"
                    cancel_msg = f"❌ **MATCH {mode_name} ANNULÉ** par {member.display_name}\n\n"
                    cancel_msg += f"🔄 Gagnants: {', '.join(result['winners'])}\n"
                    cancel_msg += f"🔄 Perdants: {', '.join(result['losers'])}\n"
                    cancel_msg += "📊 Changements ELO annulés"
                    
                    if result['had_dodge']:
                        cancel_msg += "\n🚨 Dodge annulé"
                    
                    await message.edit(content=cancel_msg)
                    await message.clear_reactions()
                    
                    # Retirer de la liste
                    conn = get_connection()
                    if conn:
                        try:
                            with conn.cursor() as c:
                                c.execute('DELETE FROM match_messages WHERE message_id = %s', (payload.message_id,))
                                conn.commit()
                        finally:
                            conn.close()
                except:
                    pass
    
    print("✅ Système ELO Dual configuré avec succès!")
    print("🥇 Mode SOLO - Matchmaking individuel")
    print("👥 Mode TRIO - Équipes fixes de 3 joueurs") 
    print("🚫 ELO et classements complètement séparés")
    print("📊 Aucun mélange entre les modes")
    print(f"📺 Salon votes: {RESULT_CHANNEL_ID}")
    print(f"📋 Salon résumés: {MATCH_SUMMARY_CHANNEL_ID}")
    print("🎯 Commandes principales: !help pour la liste complète")

# ================================
# FONCTION ADMIN MATCH MANUEL
# ================================

async def record_manual_match_result(interaction, gagnant1, gagnant2, gagnant3,
                                   perdant1, perdant2, perdant3, dodge_joueur=None, score=None, match_type='solo'):
    """Enregistrement manuel de match par admin selon le type"""
    from main import (get_player, create_player, update_player_elo, calculate_elo_change,
                     calculate_dodge_penalty, save_match_history)
    
    await interaction.response.send_message("⏳ Traitement...", ephemeral=True)
    
    winners = [gagnant1, gagnant2, gagnant3]
    losers = [perdant1, perdant2, perdant3]
    all_members = winners + losers
    
    # Vérifications
    if len(set(m.id for m in all_members)) != 6:
        await interaction.edit_original_response(content="❌ Chaque joueur ne peut apparaître qu'une fois")
        return
    
    if dodge_joueur and dodge_joueur not in all_members:
        await interaction.edit_original_response(content="❌ Le dodger doit faire partie des 6 joueurs")
        return
    
    # Créer/vérifier joueurs et attribuer rôles
    for member in all_members:
        if not get_player(member.id):
            create_player(member.id, member.display_name)
        await ensure_player_has_ping_role(interaction.guild, member.id)
    
    # Gestion dodge
    dodge_penalty = 0
    if dodge_joueur:
        record_dodge(dodge_joueur.id, match_type)
        dodge_penalty = calculate_dodge_penalty(get_player_dodge_count(dodge_joueur.id, match_type))
    
    # Calculer ELO selon le type
    elo_field = f'{match_type}_elo'
    winner_elos = [get_player(m.id)[elo_field] for m in winners]
    loser_elos = [get_player(m.id)[elo_field] for m in losers]
    winner_avg = sum(winner_elos) / 3
    loser_avg = sum(loser_elos) / 3
    
    winner_changes, loser_changes = [], []
    
    # Appliquer changements
    for i, member in enumerate(winners):
        old_elo = winner_elos[i]
        change = calculate_elo_change(old_elo, loser_avg, True)
        if dodge_joueur:
            change = int(change * 0.8)
        new_elo = max(0, old_elo + change)
        update_player_elo(member.id, new_elo, True, match_type)
        winner_changes.append(change)
    
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        change = calculate_elo_change(old_elo, winner_avg, False)
        
        if dodge_joueur and member.id == dodge_joueur.id:
            change -= dodge_penalty
        elif dodge_joueur:
            change = int(change * 0.3)
        
        new_elo = max(0, old_elo + change)
        update_player_elo(member.id, new_elo, False, match_type)
        loser_changes.append(change)
    
    # Sauvegarder historique
    save_match_history(winners, losers, winner_changes, loser_changes,
                      dodge_joueur.id if dodge_joueur else None, match_type)
    
    # Construire résumé
    mode_emoji = "🥇" if match_type == 'solo' else "👥"
    mode_name = match_type.upper()
    
    message = f"{mode_emoji} **RÉSULTAT MATCH {mode_name}** (Admin)\n\n"
    if score:
        message += f"Score: {score}\n"
    if dodge_joueur:
        message += f"🚨 Dodge: {dodge_joueur.display_name} (-{dodge_penalty})\n"
    
    message += "\n🏆 **GAGNANTS:**\n"
    for i, member in enumerate(winners):
        old_elo = winner_elos[i]
        change = winner_changes[i]
        message += f"{member.display_name}: {old_elo} → {old_elo + change} (+{change})\n"
    
    message += "\n💀 **PERDANTS:**\n"
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        change = loser_changes[i]
        suffix = " [DODGE]" if dodge_joueur and member.id == dodge_joueur.id else " [Protégé]" if dodge_joueur else ""
        message += f"{member.display_name}: {old_elo} → {old_elo + change} ({change:+}){suffix}\n"
    
    message += f"\n📊 ELO moyen: G{round(winner_avg)} | P{round(loser_avg)}"
    message += "\n↩️ *Réagissez ↩️ pour annuler*"
    
    # Envoyer résumé
    summary_channel = interaction.guild.get_channel(MATCH_SUMMARY_CHANNEL_ID)
    if summary_channel:
        summary_msg = await summary_channel.send(message)
        await summary_msg.add_reaction("↩️")
        save_match_message_id(summary_msg.id, match_type)
    
    await interaction.edit_original_response(content="✅ Match enregistré!")
._update_message(self.vote_view._build_message())
            
            reported_member = self.vote_view.guild.get_member(reported_id)
            reported_name = reported_member.display_name if reported_member else f"Joueur {reported_id}"
            
            await self.vote_view
