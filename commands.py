#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié - COMMANDES
Version avec attribution automatique du rôle ping + bouton annulation game
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
import asyncio
import json

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
            print(f"✅ Rôle ping attribué à {member.display_name}")
            
        return True
    except Exception as e:
        print(f"Erreur ensure_player_has_ping_role: {e}")
        return False

async def assign_ping_role_to_all_players(guild):
    """Attribue le rôle ping à tous les joueurs en base"""
    try:
        from main import get_leaderboard, PING_ROLE_ID
        
        players = get_leaderboard()  # Récupère tous les joueurs
        role = guild.get_role(PING_ROLE_ID)
        
        if not role:
            print(f"❌ Rôle ping {PING_ROLE_ID} introuvable")
            return 0
        
        assigned_count = 0
        for player in players:
            member = guild.get_member(int(player['discord_id']))
            if member and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Attribution automatique rôle ELO")
                    assigned_count += 1
                    print(f"✅ Rôle attribué à {member.display_name}")
                except Exception as e:
                    print(f"❌ Erreur attribution rôle pour {member.display_name}: {e}")
        
        return assigned_count
    except Exception as e:
        print(f"Erreur assign_ping_role_to_all_players: {e}")
        return 0

# ================================
# CLASSES DE VOTE AMÉLIORÉES
# ================================

class PlayerVoteView(discord.ui.View):
    """Vue de vote des joueurs avec auto-refresh et vote d'annulation"""
    
    def __init__(self, team1_ids, team2_ids, lobby_id, room_code, guild):
        super().__init__(timeout=None)
        self.team1_ids = team1_ids
        self.team2_ids = team2_ids
        self.lobby_id = lobby_id
        self.room_code = room_code
        self.guild = guild
        self.votes = {'team1': set(), 'team2': set()}
        self.dodge_reports = {}
        self.cancel_votes = set()  # Nouveau : votes pour annuler
        self.match_validated = False
        self.match_cancelled = False  # Nouveau : état d'annulation
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
            new_view = PlayerVoteView(self.team1_ids, self.team2_ids, 
                                     self.lobby_id, self.room_code, self.guild)
            new_view.votes = self.votes.copy()
            new_view.dodge_reports = self.dodge_reports.copy()
            new_view.cancel_votes = self.cancel_votes.copy()
            
            # Supprimer ancien message et créer le nouveau
            try:
                await self.current_message.delete()
            except:
                pass
                
            new_message = await channel.send(self._build_message(), view=new_view)
            new_view.current_message = new_message
            await new_view.start_auto_refresh()
            
            # Arrêter ancien refresh
            if self.refresh_task:
                self.refresh_task.cancel()
                
        except Exception as e:
            print(f"Erreur _refresh_message: {e}")
    
    def _build_message(self):
        """Construit le message de vote"""
        from main import select_random_maps
        
        # Équipes
        team1_mentions = [f"<@{pid}>" for pid in self.team1_ids]
        team2_mentions = [f"<@{pid}>" for pid in self.team2_ids]
        
        # Maps
        maps = select_random_maps(3)
        maps_text = '\n'.join([f"• {m}" for m in maps])
        
        # Statistiques de vote
        votes1 = len(self.votes['team1'])
        votes2 = len(self.votes['team2'])
        cancel_count = len(self.cancel_votes)
        total_votes = votes1 + votes2
        
        message = f"🗳️ **VOTE DU RÉSULTAT** - Lobby #{self.lobby_id}\n"
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
                    await self._refresh_message()
            else:
                await self._refresh_message()
                
        except Exception as e:
            print(f"Erreur handle_vote: {e}")
    
    async def handle_cancel_vote(self, interaction):
        """Gère un vote d'annulation de game"""
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
            
            # Vérifier si annulation validée (4 votes)
            if len(self.cancel_votes) >= 4:
                await self.cancel_match()
            else:
                await self._refresh_message()
                
        except Exception as e:
            print(f"Erreur handle_cancel_vote: {e}")
    
    async def cancel_match(self):
        """Annule le match"""
        try:
            self.match_cancelled = True
            if self.refresh_task:
                self.refresh_task.cancel()
            
            # Désactiver tous les boutons
            for item in self.children:
                item.disabled = True
            
            # Message d'annulation
            cancel_msg = f"❌ **MATCH ANNULÉ** - Lobby #{self.lobby_id}\n"
            cancel_msg += f"🗳️ Annulation votée par {len(self.cancel_votes)} joueurs\n"
            cancel_msg += f"Code room: {self.room_code}"
            
            await self._update_message(cancel_msg)
            
            # Nettoyer le lobby de la base de données
            from main import get_connection
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor() as c:
                        # Pas besoin de supprimer le lobby car il est déjà supprimé au lancement
                        pass
                finally:
                    conn.close()
            
        except Exception as e:
            print(f"Erreur cancel_match: {e}")
    
    async def handle_dodge_report(self, interaction):
        """Gère signalement dodge avec menu simplifié"""
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
                    # Récupérer le nom du joueur
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
    
    async def process_dodge_report(self, reporter_id, reported_id):
        """Traite un signalement dodge"""
        try:
            self.dodge_reports[reporter_id] = int(reported_id)
            
            # Compter signalements
            counts = {}
            for rep_id in self.dodge_reports.values():
                counts[rep_id] = counts.get(rep_id, 0) + 1
            
            # Vérifier majorité (3+ signalements)
            for player_id, count in counts.items():
                if count >= 3:
                    await self.handle_confirmed_dodge(player_id)
                    return
            
            await self._refresh_message()
            
        except Exception as e:
            print(f"Erreur process_dodge_report: {e}")
    
    async def handle_confirmed_dodge(self, dodge_player_id):
        """Gère dodge confirmé"""
        try:
            from main import record_dodge, get_player_dodge_count, calculate_dodge_penalty
            
            record_dodge(dodge_player_id)
            penalty = calculate_dodge_penalty(get_player_dodge_count(dodge_player_id))
            
            # Équipe du dodger perd automatiquement
            team1_wins = dodge_player_id not in self.team1_ids
            await self.validate_match_with_dodge(team1_wins, dodge_player_id, penalty)
            
        except Exception as e:
            print(f"Erreur handle_confirmed_dodge: {e}")
    
    async def validate_match(self, team1_wins, reason):
        """Valide le match standard"""
        await self._validate_match_internal(team1_wins, reason)
    
    async def validate_match_with_dodge(self, team1_wins, dodge_player_id, penalty):
        """Valide le match avec dodge"""
        await self._validate_match_internal(team1_wins, "dodge confirmé", dodge_player_id, penalty)
    
    async def _validate_match_internal(self, team1_wins, reason, dodge_player_id=None, dodge_penalty=0):
        """Validation interne unifiée"""
        try:
            from main import get_player, update_player_elo, calculate_elo_change, save_match_history
            
            self.match_validated = True
            if self.refresh_task:
                self.refresh_task.cancel()
            
            # Déterminer gagnants/perdants
            winner_ids = self.team1_ids if team1_wins else self.team2_ids
            loser_ids = self.team2_ids if team1_wins else self.team1_ids
            
            # Récupérer joueurs et ELO
            winners, losers = [], []
            winner_elos, loser_elos = [], []
            
            for pid in winner_ids:
                player = get_player(pid)
                if player:
                    winners.append(player)
                    winner_elos.append(player['elo'])
            
            for pid in loser_ids:
                player = get_player(pid)
                if player:
                    losers.append(player)
                    loser_elos.append(player['elo'])
            
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
                    change = int(change * 0.8)  # Réduction si dodge
                new_elo = max(0, old_elo + change)
                update_player_elo(player['discord_id'], new_elo, True)
                winner_changes.append(change)
            
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                change = calculate_elo_change(old_elo, winner_avg, False)
                
                if dodge_player_id and int(player['discord_id']) == dodge_player_id:
                    change -= dodge_penalty
                elif dodge_player_id:
                    change = int(change * 0.3)  # Protection coéquipiers
                
                new_elo = max(0, old_elo + change)
                update_player_elo(player['discord_id'], new_elo, False)
                loser_changes.append(change)
            
            # Désactiver boutons
            for item in self.children:
                item.disabled = True
            
            # Message de validation
            team_name = "Bleue" if team1_wins else "Rouge"
            validation_msg = f"✅ **MATCH VALIDÉ** ({reason})\n🏆 Victoire Équipe {team_name}\nLobby #{self.lobby_id}"
            await self._update_message(validation_msg)
            
            # Créer objets mock et sauvegarder
            class MockMember:
                def __init__(self, discord_id, name):
                    self.id = int(discord_id)
                    self.display_name = name
            
            mock_winners = [MockMember(p['discord_id'], p['name']) for p in winners]
            mock_losers = [MockMember(p['discord_id'], p['name']) for p in losers]
            
            save_match_history(mock_winners, mock_losers, winner_changes, loser_changes,
                             dodge_player_id if dodge_player_id else None)
            
            # Envoyer résumé
            await self.send_match_summary(mock_winners, mock_losers, winner_elos, loser_elos,
                                        winner_changes, loser_changes, reason, dodge_player_id, dodge_penalty)
            
        except Exception as e:
            print(f"Erreur _validate_match_internal: {e}")
    
    async def _update_message(self, content):
        """Met à jour le message"""
        try:
            if self.current_message:
                # Désactiver tous les boutons si le match est terminé
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
    
    async def send_match_summary(self, winners, losers, winner_elos, loser_elos,
                               winner_changes, loser_changes, reason, dodge_player_id=None, dodge_penalty=0):
        """Envoie le résumé du match"""
        try:
            from main import save_match_message_id
            
            # Construire message
            winning_team = "Bleue 🔵" if winners[0].id in self.team1_ids else "Rouge 🔴"
            
            message = f"🏆 **RÉSULTAT DE MATCH**\n\n"
            message += f"**Victoire Équipe {winning_team}** ({reason})\n"
            message += f"Lobby #{self.lobby_id} - Code: {self.room_code}\n\n"
            
            if dodge_player_id:
                message += f"🚨 **DODGE:** <@{dodge_player_id}> (-{dodge_penalty} ELO)\n\n"
            
            message += "🏆 **GAGNANTS:**\n"
            for i, member in enumerate(winners):
                old_elo = winner_elos[i]
                change = winner_changes[i]
                new_elo = old_elo + change
                suffix = " [Dodge]" if dodge_player_id else ""
                message += f"<@{member.id}>: {old_elo} → {new_elo} (+{change}){suffix}\n"
            
            message += "\n💀 **PERDANTS:**\n"
            for i, member in enumerate(losers):
                old_elo = loser_elos[i]
                change = loser_changes[i]
                new_elo = old_elo + change
                
                if dodge_player_id and member.id == dodge_player_id:
                    message += f"🚨 <@{member.id}>: {old_elo} → {new_elo} ({change:+}) [DODGER]\n"
                elif dodge_player_id:
                    message += f"<@{member.id}>: {old_elo} → {new_elo} ({change:+}) [Protégé]\n"
                else:
                    message += f"<@{member.id}>: {old_elo} → {new_elo} ({change:+})\n"
            
            # Statistiques
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            message += f"\n📊 ELO moyen: Gagnants {round(winner_avg)} | Perdants {round(loser_avg)}"
            message += f"\n↩️ *Réagissez avec ↩️ pour annuler ce match*"
            
            # Envoyer avec réaction
            summary_channel = self.guild.get_channel(MATCH_SUMMARY_CHANNEL_ID)
            if summary_channel:
                summary_msg = await summary_channel.send(message)
                await summary_msg.add_reaction("↩️")
                save_match_message_id(summary_msg.id)
                
        except Exception as e:
            print(f"Erreur send_match_summary: {e}")

class DodgeSelect(discord.ui.Select):
    """Menu de sélection pour dodge - version corrigée"""
    
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
            await self.vote_view.process_dodge_report(self.reporter_id, reported_id)
            
            # Récupérer le nom du joueur signalé
            reported_member = self.vote_view.guild.get_member(reported_id)
            reported_name = reported_member.display_name if reported_member else f"Joueur {reported_id}"
            
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

# ================================
# COMMANDES SIMPLIFIÉES (inchangées)
# ================================

async def create_lobby_cmd(ctx, room_code: str = None):
    """!create <code> - Créer un lobby"""
    from main import (get_player, create_player, create_lobby, add_player_to_lobby,
                     get_all_lobbies, MAX_CONCURRENT_LOBBIES, PING_ROLE_ID)
    
    if not room_code:
        await ctx.send("❌ Usage: !create <code_room>")
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
        # Attribuer le rôle ping au nouveau joueur
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    
    # Créer lobby
    lobby_id, msg = create_lobby(room_code.upper())
    if not lobby_id:
        await ctx.send(f"❌ {msg}")
        return
    
    # Ajouter créateur
    success, join_msg = add_player_to_lobby(lobby_id, ctx.author.id)
    if success:
        role_mention = f"<@&{PING_ROLE_ID}>"
        message = (f"{role_mention}\n\n🎮 **NOUVEAU LOBBY #{lobby_id}**\n"
                  f"Code: {room_code.upper()}\n"
                  f"Créateur: {ctx.author.display_name}\n"
                  f"Rejoindre: !join {lobby_id}")
        await ctx.send(message)
    else:
        await ctx.send(f"❌ {join_msg}")

async def join_lobby_cmd(ctx, lobby_id: int = None):
    """!join <id> - Rejoindre un lobby"""
    from main import (get_player, create_player, add_player_to_lobby, get_lobby,
                     create_random_teams, get_connection)
    
    if not lobby_id:
        await ctx.send("❌ Usage: !join <id_lobby>")
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        create_player(ctx.author.id, ctx.author.display_name)
        # Attribuer le rôle ping au nouveau joueur
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    else:
        # S'assurer que le joueur existant a le rôle ping
        await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    
    # Rejoindre
    success, msg = add_player_to_lobby(lobby_id, ctx.author.id)
    if not success:
        await ctx.send(f"❌ {msg}")
        return
    
    # Vérifier si lobby complet
    lobby = get_lobby(lobby_id)
    if lobby:
        players = lobby['players'].split(',') if lobby['players'] else []
        if len(players) >= 6:
            # Lancer le match
            team1_ids, team2_ids = create_random_teams([int(id) for id in players])
            
            await ctx.send(f"🚀 **MATCH LANCÉ!** Lobby #{lobby_id} - Équipes créées!")
            
            # Créer vote dans salon admin
            vote_channel = ctx.guild.get_channel(RESULT_CHANNEL_ID)
            if vote_channel:
                vote_view = PlayerVoteView(team1_ids, team2_ids, lobby_id, lobby['room_code'], ctx.guild)
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
            await ctx.send(f"✅ Rejoint! ({len(players)}/6 joueurs)")

async def leave_lobby_cmd(ctx):
    """!leave - Quitter son lobby"""
    from main import remove_player_from_lobby
    success, msg = remove_player_from_lobby(ctx.author.id)
    await ctx.send(f"{'👋' if success else '❌'} {msg}")

async def show_elo_cmd(ctx):
    """!elo - Voir son ELO"""
    from main import get_player, get_leaderboard, get_player_dodge_count
    
    player = get_player(ctx.author.id)
    if not player:
        await ctx.send("❌ Non inscrit. Utilisez !create <code> pour vous inscrire.")
        return
    
    # S'assurer que le joueur a le rôle ping
    await ensure_player_has_ping_role(ctx.guild, ctx.author.id)
    
    # Calculer rang
    players = get_leaderboard()
    rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(ctx.author.id)), len(players))
    
    winrate = round(player['wins'] / max(1, player['wins'] + player['losses']) * 100, 1)
    dodge_count = get_player_dodge_count(ctx.author.id)
    
    message = (f"📊 **{ctx.author.display_name}**\n"
              f"ELO: {player['elo']} | Rang: #{rank}\n"
              f"W/L: {player['wins']}/{player['losses']} ({winrate}%)")
    
    if dodge_count > 0:
        message += f"\n🚨 Dodges: {dodge_count}"
    
    await ctx.send(message)

async def leaderboard_cmd(ctx):
    """!leaderboard - Classement"""
    from main import get_leaderboard, get_player
    
    players = get_leaderboard()[:10]
    if not players:
        await ctx.send("📊 Classement vide")
        return
    
    message = "🏆 **CLASSEMENT ELO**\n\n"
    
    for i, player in enumerate(players, 1):
        try:
            member = ctx.guild.get_member(int(player['discord_id']))
            name = member.display_name if member else player['name']
        except:
            name = player['name']
        
        winrate = round(player['wins'] / max(1, player['wins'] + player['losses']) * 100, 1)
        emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        message += f"{emoji} {name} - {player['elo']} ELO ({winrate}%)\n"
    
    # Position joueur actuel
    current_player = get_player(ctx.author.id)
    if current_player:
        all_players = get_leaderboard()
        pos = next((i for i, p in enumerate(all_players, 1) if p['discord_id'] == str(ctx.author.id)), None)
        if pos:
            message += f"\n**Votre position:** #{pos} - {current_player['elo']} ELO"
    
    await ctx.send(message)

async def list_lobbies_cmd(ctx):
    """!lobbies - Liste des lobbies"""
    from main import get_all_lobbies, get_cooldown_info, MAX_CONCURRENT_LOBBIES
    
    lobbies = get_all_lobbies()
    cooldown = get_cooldown_info()
    
    message = f"🎮 **LOBBIES** ({len(lobbies)}/{MAX_CONCURRENT_LOBBIES})\n\n"
    
    if not lobbies:
        message += "Aucun lobby actif\n"
    else:
        for lobby in lobbies:
            players_count = len(lobby['players'].split(',')) if lobby['players'] else 0
            status = "🟢" if players_count < 6 else "🔴"
            message += f"{status} #{lobby['id']} - {lobby['room_code']} ({players_count}/6)\n"
    
    if cooldown and cooldown.get('active'):
        message += f"\n⏰ Cooldown: {cooldown['remaining_minutes']}m {cooldown['remaining_seconds']}s"
    else:
        message += "\n✅ Création possible"
    
    await ctx.send(message)

# ================================
# COMMANDES ADMIN SIMPLIFIÉES
# ================================

async def record_manual_match_result(interaction, gagnant1, gagnant2, gagnant3,
                                   perdant1, perdant2, perdant3, dodge_joueur=None, score=None):
    """Enregistrement manuel de match par admin"""
    from main import (get_player, create_player, update_player_elo, calculate_elo_change,
                     record_dodge, get_player_dodge_count, calculate_dodge_penalty,
                     save_match_history, save_match_message_id)
    
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
        record_dodge(dodge_joueur.id)
        dodge_penalty = calculate_dodge_penalty(get_player_dodge_count(dodge_joueur.id))
    
    # Calculer ELO
    winner_elos = [get_player(m.id)['elo'] for m in winners]
    loser_elos = [get_player(m.id)['elo'] for m in losers]
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
        update_player_elo(member.id, new_elo, True)
        winner_changes.append(change)
    
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        change = calculate_elo_change(old_elo, winner_avg, False)
        
        if dodge_joueur and member.id == dodge_joueur.id:
            change -= dodge_penalty
        elif dodge_joueur:
            change = int(change * 0.3)
        
        new_elo = max(0, old_elo + change)
        update_player_elo(member.id, new_elo, False)
        loser_changes.append(change)
    
    # Sauvegarder historique
    save_match_history(winners, losers, winner_changes, loser_changes,
                      dodge_joueur.id if dodge_joueur else None)
    
    # Construire résumé
    message = "🏆 **RÉSULTAT MATCH** (Admin)\n\n"
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
        save_match_message_id(summary_msg.id)
    
    await interaction.edit_original_response(content="✅ Match enregistré!")

async def handle_match_cancel_reaction(payload):
    """Gère l'annulation par réaction ↩️"""
    try:
        from main import is_match_message, undo_last_match, remove_match_message_id
        
        if str(payload.emoji) != "↩️" or payload.channel_id != MATCH_SUMMARY_CHANNEL_ID:
            return
        
        if not is_match_message(payload.message_id):
            return
        
        # Vérifier permissions admin
        guild = payload.member.guild if payload.member else None
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        if not member or not member.guild_permissions.administrator:
            return
        
        # Annuler match
        success, result = undo_last_match()
        if success:
            channel = guild.get_channel(payload.channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(payload.message_id)
                    cancel_msg = f"❌ **MATCH ANNULÉ** par {member.display_name}\n\n"
                    cancel_msg += f"🔄 Gagnants: {', '.join(result['winners'])}\n"
                    cancel_msg += f"🔄 Perdants: {', '.join(result['losers'])}\n"
                    cancel_msg += "📊 Changements ELO annulés"
                    
                    if result['had_dodge']:
                        cancel_msg += "\n🚨 Dodge annulé"
                    
                    await message.edit(content=cancel_msg)
                    await message.clear_reactions()
                    remove_match_message_id(payload.message_id)
                except:
                    pass
    except Exception as e:
        print(f"Erreur handle_match_cancel_reaction: {e}")

# ================================
# SETUP FONCTION PRINCIPALE
# ================================

async def setup_commands(bot):
    """Configure toutes les commandes du bot"""
    
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
    
    # Commandes prefix
    @bot.command(name='create')
    async def _create(ctx, room_code: str = None):
        await create_lobby_cmd(ctx, room_code)
    
    @bot.command(name='join')
    async def _join(ctx, lobby_id: int = None):
        await join_lobby_cmd(ctx, lobby_id)
    
    @bot.command(name='leave')
    async def _leave(ctx):
        await leave_lobby_cmd(ctx)
    
    @bot.command(name='lobbies')
    async def _lobbies(ctx):
        await list_lobbies_cmd(ctx)
    
    @bot.command(name='elo')
    async def _elo(ctx):
        await show_elo_cmd(ctx)
    
    @bot.command(name='leaderboard', aliases=['top'])
    async def _leaderboard(ctx):
        await leaderboard_cmd(ctx)
    
    # Commandes admin simplifiées
    @bot.command(name='resetcd')
    async def _resetcd(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        from main import get_connection, LOBBY_COOLDOWN_MINUTES
        conn = get_connection()
        if conn:
            try:
                with conn.cursor() as c:
                    c.execute('UPDATE lobby_cooldown SET last_creation = CURRENT_TIMESTAMP - INTERVAL %s', 
                             (f"{LOBBY_COOLDOWN_MINUTES + 1} minutes",))
                    conn.commit()
                await ctx.send("✅ Cooldown reset!")
            except Exception as e:
                await ctx.send(f"❌ Erreur: {e}")
            finally:
                conn.close()
    
    @bot.command(name='clearlobbies')
    async def _clearlobbies(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        from main import get_connection
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
    
    @bot.command(name='undo')
    async def _undo(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        from main import undo_last_match
        success, result = undo_last_match()
        if success:
            message = f"🔄 **MATCH ANNULÉ!**\n"
            message += f"Gagnants: {', '.join(result['winners'])}\n"
            message += f"Perdants: {', '.join(result['losers'])}\n"
            message += f"✅ Changements ELO inversés"
            if result['had_dodge']:
                message += f"\n🚨 Dodge annulé"
        else:
            message = f"❌ Erreur: {result}"
        await ctx.send(message)
    
    @bot.command(name='addelo')
    async def _addelo(ctx, member: discord.Member = None, amount: int = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        if not member or not amount or amount <= 0:
            await ctx.send("❌ Usage: !addelo @joueur montant")
            return
        
        from main import get_player, create_player, update_player_elo_only
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
            player = get_player(member.id)
        
        # Attribuer le rôle ping
        await ensure_player_has_ping_role(ctx.guild, member.id)
        
        old_elo = player['elo']
        new_elo = old_elo + amount
        if update_player_elo_only(member.id, new_elo):
            await ctx.send(f"✅ {member.display_name}: {old_elo} → {new_elo} (+{amount})")
        else:
            await ctx.send("❌ Erreur mise à jour ELO")
    
    @bot.command(name='removeelo')
    async def _removeelo(ctx, member: discord.Member = None, amount: int = None):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        if not member or not amount or amount <= 0:
            await ctx.send("❌ Usage: !removeelo @joueur montant")
            return
        
        from main import get_player, create_player, update_player_elo_only
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
            player = get_player(member.id)
        
        # Attribuer le rôle ping
        await ensure_player_has_ping_role(ctx.guild, member.id)
        
        old_elo = player['elo']
        new_elo = max(0, old_elo - amount)
        actual_removed = old_elo - new_elo
        if update_player_elo_only(member.id, new_elo):
            message = f"✅ {member.display_name}: {old_elo} → {new_elo} (-{actual_removed})"
            if actual_removed < amount:
                message += f" (min 0)"
            await ctx.send(message)
        else:
            await ctx.send("❌ Erreur mise à jour ELO")
    
    # Commande admin pour attribuer manuellement tous les rôles
    @bot.command(name='assignroles')
    async def _assignroles(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        
        assigned = await assign_ping_role_to_all_players(ctx.guild)
        await ctx.send(f"🎯 {assigned} rôles ping attribués aux joueurs en base!")
    
    # Commande slash admin
    @app_commands.command(name="result", description="Enregistrer un match manuellement (admin)")
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
    async def _result_manual(interaction, gagnant1: discord.Member, gagnant2: discord.Member,
                            gagnant3: discord.Member, perdant1: discord.Member, perdant2: discord.Member,
                            perdant3: discord.Member, dodge_joueur: Optional[discord.Member] = None,
                            score: Optional[Literal["2-0", "2-1"]] = None):
        await record_manual_match_result(interaction, gagnant1, gagnant2, gagnant3,
                                       perdant1, perdant2, perdant3, dodge_joueur, score)
    
    bot.tree.add_command(_result_manual)
    
    # Event handler pour réactions d'annulation
    @bot.event
    async def on_raw_reaction_add(payload):
        if payload.user_id == bot.user.id:
            return
        await handle_match_cancel_reaction(payload)
    
    print("✅ Commandes améliorées chargées avec:")
    print("🎯 Attribution automatique du rôle ping")
    print("🗳️ Système de vote avec auto-refresh")
    print("🚨 Système anti-dodge CORRIGÉ")
    print("❌ Bouton d'annulation de game (4 votes requis)")
    print("↩️ Annulation par réaction")
    print(f"📺 Salon admin: {RESULT_CHANNEL_ID}")
    print(f"📋 Salon résumés: {MATCH_SUMMARY_CHANNEL_ID}")
    print("🔧 Commande admin: !assignroles")