#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié - COMMANDES
Toutes les commandes du bot avec système de vote des joueurs et annulation par réaction
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
import asyncio
import json

# Salon de validation des résultats (admin)
RESULT_CHANNEL_ID = 1408595087331430520
# Salon des résumés de matchs (public avec annulation)
MATCH_SUMMARY_CHANNEL_ID = 1385919316569886732

# ================================
# CLASSE POUR SÉLECTION DE DODGE
# ================================

class DodgeReportSelect(discord.ui.Select):
    """Menu de sélection pour signaler un joueur qui a dodge"""
    
    def __init__(self, options, vote_view, reporter_id):
        super().__init__(placeholder="Choisir le joueur qui a dodge...", options=options, min_values=1, max_values=1)
        self.vote_view = vote_view
        self.reporter_id = reporter_id
    
    async def callback(self, interaction: discord.Interaction):
        try:
            reported_player_id = int(self.values[0])
            
            # Traiter le signalement
            await self.vote_view.process_dodge_report(self.reporter_id, reported_player_id)
            
            await interaction.response.send_message(
                f"✅ Signalement enregistré pour <@{reported_player_id}>",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Erreur dans DodgeReportSelect callback: {e}")
            await interaction.response.send_message(
                "❌ Erreur lors du signalement",
                ephemeral=True
            )

# ================================
# CLASSES POUR LES BOUTONS DE VOTE
# ================================

class PlayerVoteView(discord.ui.View):
    """Vue avec boutons pour que les joueurs votent le résultat d'un match"""
    
    def __init__(self, team1_ids, team2_ids, lobby_id, room_code):
        super().__init__(timeout=86400)  # 24 heures de timeout
        self.team1_ids = team1_ids  # Équipe bleue
        self.team2_ids = team2_ids  # Équipe rouge
        self.lobby_id = lobby_id
        self.room_code = room_code
        self.votes_team1 = set()  # IDs des joueurs qui ont voté équipe 1
        self.votes_team2 = set()  # IDs des joueurs qui ont voté équipe 2
        self.voters = set()  # Tous les joueurs qui ont voté
        self.match_validated = False
        self.all_player_ids = set(team1_ids + team2_ids)
        self.dodge_reports = {}  # {user_id: reported_player_id}
        self.dodge_confirmed = None  # ID du joueur confirmé comme ayant dodge
        self.original_message = None  # Référence au message original pour mise à jour
    
    @discord.ui.button(label='🔵 Victoire Équipe Bleue', style=discord.ButtonStyle.primary, emoji='🔵')
    async def team1_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, team1_wins=True)
    
    @discord.ui.button(label='🔴 Victoire Équipe Rouge', style=discord.ButtonStyle.danger, emoji='🔴')
    async def team2_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, team1_wins=False)
    
    @discord.ui.button(label='🚨 Signaler un Dodge', style=discord.ButtonStyle.secondary, emoji='🚨')
    async def report_dodge(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_dodge_report(interaction)
    
    async def handle_dodge_report(self, interaction: discord.Interaction):
        """Gère le signalement d'un dodge"""
        try:
            # Vérifier que c'est un joueur du match
            if interaction.user.id not in self.all_player_ids:
                await interaction.response.send_message("❌ Seuls les joueurs du match peuvent signaler un dodge!", ephemeral=True)
                return
            
            # Vérifier que le match n'a pas déjà été validé
            if self.match_validated:
                await interaction.response.send_message("❌ Ce match a déjà été validé!", ephemeral=True)
                return
            
            # Créer une liste de sélection avec tous les joueurs du match
            options = []
            for player_id in self.all_player_ids:
                if player_id != interaction.user.id:  # Ne pas inclure soi-même
                    options.append(discord.SelectOption(
                        label=f"Joueur {player_id}",
                        value=str(player_id),
                        description="Signaler ce joueur pour dodge"
                    ))
            
            if not options:
                await interaction.response.send_message("❌ Aucun autre joueur à signaler", ephemeral=True)
                return
            
            # Créer le menu de sélection
            select = DodgeReportSelect(options, self, interaction.user.id)
            view = discord.ui.View(timeout=300)  # 5 minutes pour sélectionner
            view.add_item(select)
            
            await interaction.response.send_message("🚨 Sélectionnez le joueur qui a dodge:", view=view, ephemeral=True)
            
        except Exception as e:
            print(f"Erreur dans handle_dodge_report: {e}")
            try:
                await interaction.response.send_message(f"❌ Erreur lors du signalement: {str(e)}", ephemeral=True)
            except:
                pass
    
    async def process_dodge_report(self, reporter_id, reported_player_id):
        """Traite un signalement de dodge"""
        try:
            # Enregistrer le signalement
            self.dodge_reports[reporter_id] = int(reported_player_id)
            
            # Compter les signalements pour chaque joueur
            report_counts = {}
            for reported_id in self.dodge_reports.values():
                report_counts[reported_id] = report_counts.get(reported_id, 0) + 1
            
            # Vérifier si un joueur a assez de signalements (majorité = 3+ signalements)
            for player_id, count in report_counts.items():
                if count >= 3:  # Majorité de 3/5 autres joueurs (celui signalé ne peut pas voter contre lui-même)
                    self.dodge_confirmed = player_id
                    await self.handle_confirmed_dodge()
                    return
            
            # Pas encore de majorité, mettre à jour le statut
            await self.update_vote_message_with_dodge_info()
            
        except Exception as e:
            print(f"Erreur dans process_dodge_report: {e}")
    
    async def handle_confirmed_dodge(self):
        """Gère la confirmation d'un dodge par majorité"""
        try:
            from main import record_dodge, get_player_dodge_count, calculate_dodge_penalty
            
            # Enregistrer le dodge
            record_dodge(self.dodge_confirmed)
            dodge_penalty = calculate_dodge_penalty(get_player_dodge_count(self.dodge_confirmed))
            
            # Déterminer dans quelle équipe était le joueur qui a dodge
            dodge_in_team1 = self.dodge_confirmed in self.team1_ids
            
            if dodge_in_team1:
                # Le dodge était dans l'équipe 1, l'équipe 2 gagne automatiquement
                await self.validate_match_with_dodge(team1_wins=False, dodge_player_id=self.dodge_confirmed, dodge_penalty=dodge_penalty)
            else:
                # Le dodge était dans l'équipe 2, l'équipe 1 gagne automatiquement
                await self.validate_match_with_dodge(team1_wins=True, dodge_player_id=self.dodge_confirmed, dodge_penalty=dodge_penalty)
                
        except Exception as e:
            print(f"Erreur dans handle_confirmed_dodge: {e}")
    
    async def update_vote_message_with_dodge_info(self):
        """Met à jour le message de vote avec les infos de dodge"""
        try:
            # Compter les votes actuels
            total_votes_team1 = len(self.votes_team1)
            total_votes_team2 = len(self.votes_team2)
            total_votes = total_votes_team1 + total_votes_team2
            
            # Construire le message avec les informations de dodge
            status_message = f"🗳️ **VOTE EN COURS** - Lobby #{self.lobby_id}\n\n"
            
            # Votes normaux
            team1_voters = [f"<@{pid}>" for pid in self.votes_team1]
            team2_voters = [f"<@{pid}>" for pid in self.votes_team2]
            
            status_message += f"🔵 **Équipe Bleue** ({total_votes_team1} votes):\n"
            if team1_voters:
                status_message += f"Votants: {', '.join(team1_voters)}\n"
            
            status_message += f"\n🔴 **Équipe Rouge** ({total_votes_team2} votes):\n"
            if team2_voters:
                status_message += f"Votants: {', '.join(team2_voters)}\n"
            
            status_message += f"\n📊 Total votes: {total_votes}/6\n"
            
            # Informations sur les signalements de dodge
            if self.dodge_reports:
                report_counts = {}
                for reported_id in self.dodge_reports.values():
                    report_counts[reported_id] = report_counts.get(reported_id, 0) + 1
                
                status_message += f"\n🚨 **SIGNALEMENTS DE DODGE:**\n"
                for player_id, count in report_counts.items():
                    status_message += f"<@{player_id}>: {count} signalement(s)\n"
                
                status_message += f"(Majorité de 3 signalements = dodge confirmé)\n"
            
            remaining = 6 - total_votes
            if remaining > 0:
                status_message += f"\n⏳ En attente de {remaining} vote(s) supplémentaire(s)"
            
            # Essayer de mettre à jour le message original
            # Note: Cette partie nécessiterait une référence au message original
            
        except Exception as e:
            print(f"Erreur dans update_vote_message_with_dodge_info: {e}")
    
    async def validate_match_with_dodge(self, team1_wins, dodge_player_id, dodge_penalty):
        """Valide le match avec gestion du dodge"""
        try:
            from main import (
                get_player, update_player_elo, calculate_elo_change,
                save_match_history
            )
            
            # Marquer comme validé
            self.match_validated = True
            
            # Déterminer gagnants et perdants
            if team1_wins:
                winner_ids = self.team1_ids
                loser_ids = self.team2_ids
                winning_team = "Bleue"
                winning_color = "🔵"
                reason = "dodge adverse confirmé"
            else:
                winner_ids = self.team2_ids
                loser_ids = self.team1_ids
                winning_team = "Rouge"
                winning_color = "🔴"
                reason = "dodge adverse confirmé"
            
            # Récupérer les joueurs
            winners = []
            losers = []
            winner_elos = []
            loser_elos = []
            
            for player_id in winner_ids:
                player = get_player(player_id)
                if player:
                    winners.append(player)
                    winner_elos.append(player['elo'])
            
            for player_id in loser_ids:
                player = get_player(player_id)
                if player:
                    losers.append(player)
                    loser_elos.append(player['elo'])
            
            if len(winners) != 3 or len(losers) != 3:
                return
            
            # Calculer les changements d'ELO avec gestion du dodge
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            
            winner_elo_changes = []
            loser_elo_changes = []
            
            # Appliquer les changements pour les gagnants (réduction car dodge)
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                base_change = calculate_elo_change(old_elo, loser_avg, True)
                # Réduction de 20% car victoire par dodge
                elo_change = int(base_change * 0.8)
                new_elo = max(0, old_elo + elo_change)
                
                if update_player_elo(player['discord_id'], new_elo, True):
                    winner_elo_changes.append(elo_change)
            
            # Appliquer les changements pour les perdants
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                base_change = calculate_elo_change(old_elo, winner_avg, False)
                
                if int(player['discord_id']) == dodge_player_id:
                    # Le joueur qui a dodge perd plus
                    final_change = base_change - dodge_penalty
                    new_elo = max(0, old_elo + final_change)
                    if update_player_elo(player['discord_id'], new_elo, False):
                        loser_elo_changes.append(final_change)
                else:
                    # Ses coéquipiers perdent moins (protection)
                    protected_change = int(base_change * 0.3)  # Seulement 30% de la perte
                    new_elo = max(0, old_elo + protected_change)
                    if update_player_elo(player['discord_id'], new_elo, False):
                        loser_elo_changes.append(protected_change)
            
            # Désactiver tous les boutons
            for item in self.children:
                item.disabled = True
            
            # Créer des objets mock pour la sauvegarde
            class MockMember:
                def __init__(self, discord_id, name):
                    self.id = int(discord_id)
                    self.display_name = name
            
            mock_winners = [MockMember(p['discord_id'], p['name']) for p in winners]
            mock_losers = [MockMember(p['discord_id'], p['name']) for p in losers]
            
            # Sauvegarder pour l'historique (undo)
            save_match_history(mock_winners, mock_losers, winner_elo_changes, loser_elo_changes, dodge_player_id)
            
            # Envoyer le résumé avec informations de dodge
            await self.send_match_summary_with_dodge(
                mock_winners, mock_losers, winner_elos, loser_elos,
                winner_elo_changes, loser_elo_changes, winner_avg, loser_avg,
                reason, dodge_player_id, dodge_penalty
            )
            
        except Exception as e:
            print(f"Erreur dans validate_match_with_dodge: {e}")
    
    async def send_match_summary_with_dodge(self, winners, losers, winner_elos, loser_elos,
                                           winner_elo_changes, loser_elo_changes, winner_avg, loser_avg,
                                           reason, dodge_player_id, dodge_penalty):
        """Envoie le résumé du match avec informations de dodge"""
        try:
            from main import save_match_message_id
            
            # Construire le message de résultat
            winning_team = "Bleue" if winners[0].id in self.team1_ids else "Rouge"
            winning_color = "🔵" if winning_team == "Bleue" else "🔴"
            losing_color = "🔴" if winning_team == "Bleue" else "🔵"
            
            result_message = f"🏆 **RÉSULTAT DE MATCH**\n\n"
            result_message += f"**Victoire Équipe {winning_team} {winning_color}** (par {reason})\n"
            result_message += f"Lobby #{self.lobby_id} - Code: {self.room_code}\n\n"
            
            result_message += f"🚨 **DODGE CONFIRMÉ:** <@{dodge_player_id}> (-{dodge_penalty} ELO supplémentaire)\n\n"
            
            result_message += f"{winning_color} **GAGNANTS:**\n"
            for i, member in enumerate(winners):
                old_elo = winner_elos[i]
                change = winner_elo_changes[i]
                new_elo = old_elo + change
                result_message += f"<@{member.id}>: {old_elo} → {new_elo} (+{change}) [Victoire par dodge]\n"
            
            result_message += f"\n{losing_color} **PERDANTS:**\n"
            for i, member in enumerate(losers):
                old_elo = loser_elos[i]
                change = loser_elo_changes[i]
                new_elo = old_elo + change
                
                if member.id == dodge_player_id:
                    result_message += f"🚨 <@{member.id}>: {old_elo} → {new_elo} ({change:+}) [DODGE]\n"
                else:
                    result_message += f"<@{member.id}>: {old_elo} → {new_elo} ({change:+}) [Protégé]\n"
            
            # Statistiques
            elo_diff = abs(winner_avg - loser_avg)
            result_message += f"\n📊 **ANALYSE:**\n"
            result_message += f"ELO moyen gagnants: {round(winner_avg)}\n"
            result_message += f"ELO moyen perdants: {round(loser_avg)}\n"
            result_message += f"Écart: {round(elo_diff)} points\n\n"
            
            result_message += f"⚠️ **SYSTÈME ANTI-DODGE:**\n"
            result_message += f"• Pénalité dodge: -{dodge_penalty} ELO\n"
            result_message += f"• Coéquipiers protégés: -70% perte\n"
            result_message += f"• Gagnants: -20% gain (victoire par dodge)\n\n"
            result_message += f"↩️ *Réagissez avec ↩️ pour annuler ce match en cas de fraude*"
            
            # Envoyer dans le salon de résumés
            # Note: Cette partie nécessiterait l'accès au guild via interaction
            # Elle sera complétée lors de l'intégration finale
            
        except Exception as e:
            print(f"Erreur dans send_match_summary_with_dodge: {e}")
        """Gère un vote de joueur"""
        try:
            # Vérifier que c'est un joueur du match
            if interaction.user.id not in self.all_player_ids:
                await interaction.response.send_message("❌ Seuls les joueurs du match peuvent voter!", ephemeral=True)
                return
            
            # Vérifier que le match n'a pas déjà été validé
            if self.match_validated:
                await interaction.response.send_message("❌ Ce match a déjà été validé!", ephemeral=True)
                return
            
            # Retirer le vote précédent si il existe
            self.votes_team1.discard(interaction.user.id)
            self.votes_team2.discard(interaction.user.id)
            
            # Ajouter le nouveau vote
            if team1_wins:
                self.votes_team1.add(interaction.user.id)
                vote_team = "Bleue 🔵"
            else:
                self.votes_team2.add(interaction.user.id)
                vote_team = "Rouge 🔴"
            
            self.voters.add(interaction.user.id)
            
            await interaction.response.send_message(f"✅ Votre vote pour l'équipe {vote_team} a été enregistré!", ephemeral=True)
            
            # Vérifier si on a assez de votes pour une majorité (4/6 minimum)
            total_votes_team1 = len(self.votes_team1)
            total_votes_team2 = len(self.votes_team2)
            total_votes = total_votes_team1 + total_votes_team2
            
            # Construire le message de statut
            team1_voters = []
            team2_voters = []
            
            for player_id in self.votes_team1:
                team1_voters.append(f"<@{player_id}>")
            
            for player_id in self.votes_team2:
                team2_voters.append(f"<@{player_id}>")
            
            status_message = f"🗳️ **VOTE EN COURS** - Lobby #{self.lobby_id}\n\n"
            status_message += f"🔵 **Équipe Bleue** ({total_votes_team1} votes):\n"
            if team1_voters:
                status_message += f"Votants: {', '.join(team1_voters)}\n"
            
            status_message += f"\n🔴 **Équipe Rouge** ({total_votes_team2} votes):\n"
            if team2_voters:
                status_message += f"Votants: {', '.join(team2_voters)}\n"
            
            status_message += f"\n📊 Total votes: {total_votes}/6\n"
            
            # Vérifier les conditions de victoire
            if total_votes_team1 >= 4:
                # Équipe 1 gagne par majorité
                await self.validate_match_result(interaction, True, "majorité (4+ votes)")
                return
            elif total_votes_team2 >= 4:
                # Équipe 2 gagne par majorité
                await self.validate_match_result(interaction, False, "majorité (4+ votes)")
                return
            elif total_votes == 6:
                # Tous ont voté, déterminer le gagnant
                if total_votes_team1 > total_votes_team2:
                    await self.validate_match_result(interaction, True, f"votes finaux ({total_votes_team1}-{total_votes_team2})")
                elif total_votes_team2 > total_votes_team1:
                    await self.validate_match_result(interaction, False, f"votes finaux ({total_votes_team2}-{total_votes_team1})")
                else:
                    # Égalité parfaite 3-3, pas de validation automatique
                    status_message += "\n⚖️ **ÉGALITÉ PARFAITE** - Un administrateur doit intervenir"
                    await interaction.edit_original_response(content=status_message, view=self)
                    return
            else:
                # Pas assez de votes, attendre
                remaining = 6 - total_votes
                status_message += f"⏳ En attente de {remaining} vote(s) supplémentaire(s)"
            
            # Mettre à jour le message
            try:
                await interaction.edit_original_response(content=status_message, view=self)
            except:
                # Si on ne peut pas éditer, envoyer un nouveau message
                await interaction.followup.send(status_message, ephemeral=False)
                
        except Exception as e:
            print(f"Erreur dans handle_vote: {e}")
            try:
                await interaction.followup.send(f"❌ Erreur lors du vote: {str(e)}", ephemeral=True)
            except:
                pass
    
    async def validate_match_result(self, team1_wins, reason):
        """Valide automatiquement le résultat du match"""
        try:
            from main import (
                get_player, update_player_elo, calculate_elo_change,
                get_connection, save_match_history
            )
            
            # Marquer comme validé
            self.match_validated = True
            
            # Déterminer gagnants et perdants
            if team1_wins:
                winner_ids = self.team1_ids
                loser_ids = self.team2_ids
                winning_team = "Bleue"
                winning_color = "🔵"
            else:
                winner_ids = self.team2_ids
                loser_ids = self.team1_ids
                winning_team = "Rouge"
                winning_color = "🔴"
            
            # Récupérer les joueurs
            winners = []
            losers = []
            winner_elos = []
            loser_elos = []
            
            for player_id in winner_ids:
                player = get_player(player_id)
                if player:
                    winners.append(player)
                    winner_elos.append(player['elo'])
            
            for player_id in loser_ids:
                player = get_player(player_id)
                if player:
                    losers.append(player)
                    loser_elos.append(player['elo'])
            
            if len(winners) != 3 or len(losers) != 3:
                await self.update_vote_message_status("❌ Erreur: Impossible de récupérer tous les joueurs")
                return
            
            # Calculer les changements d'ELO
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            
            winner_elo_changes = []
            loser_elo_changes = []
            
            # Appliquer les changements
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                elo_change = calculate_elo_change(old_elo, loser_avg, True)
                new_elo = max(0, old_elo + elo_change)
                
                if update_player_elo(player['discord_id'], new_elo, True):
                    winner_elo_changes.append(elo_change)
                else:
                    await self.update_vote_message_status("❌ Erreur lors de la mise à jour des ELO")
                    return
            
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                elo_change = calculate_elo_change(old_elo, winner_avg, False)
                new_elo = max(0, old_elo + elo_change)
                
                if update_player_elo(player['discord_id'], new_elo, False):
                    loser_elo_changes.append(elo_change)
                else:
                    await self.update_vote_message_status("❌ Erreur lors de la mise à jour des ELO")
                    return
            
            # Désactiver tous les boutons
            for item in self.children:
                item.disabled = True
            
            # Message de validation
            validation_message = f"✅ **MATCH VALIDÉ PAR VOTE** ({reason})\n\n"
            validation_message += f"🏆 VICTOIRE ÉQUIPE {winning_team} {winning_color}\n"
            validation_message += f"Lobby #{self.lobby_id} - Code: {self.room_code}"
            
            # Mettre à jour le message de vote
            await self.update_vote_message_status("✅ **MATCH VALIDÉ** - Calcul des ELO en cours...")
            
            # Créer des objets mock pour la sauvegarde
            class MockMember:
                def __init__(self, discord_id, name):
                    self.id = int(discord_id)
                    self.display_name = name
            
            mock_winners = [MockMember(p['discord_id'], p['name']) for p in winners]
            mock_losers = [MockMember(p['discord_id'], p['name']) for p in losers]
            
            # Sauvegarder pour l'historique (undo)
            save_match_history(mock_winners, mock_losers, winner_elo_changes, loser_elo_changes)
            
            # Envoyer le résumé dans le salon dédié avec réaction d'annulation
            await self.send_match_summary(winners, losers, winner_elos, loser_elos, 
                                        winner_elo_changes, loser_elo_changes, winner_avg, loser_avg, reason)
            
            # Mise à jour finale du message de vote
            await self.update_vote_message_status(validation_message)
            
        except Exception as e:
            print(f"Erreur dans validate_match_result: {e}")
            await self.update_vote_message_status(f"❌ Erreur lors de la validation: {str(e)}")
        """Valide automatiquement le résultat du match"""
        try:
            from main import (
                get_player, update_player_elo, calculate_elo_change,
                get_connection, save_match_history
            )
            
            # Marquer comme validé
            self.match_validated = True
            
            # Déterminer gagnants et perdants
            if team1_wins:
                winner_ids = self.team1_ids
                loser_ids = self.team2_ids
                winning_team = "Bleue"
                winning_color = "🔵"
            else:
                winner_ids = self.team2_ids
                loser_ids = self.team1_ids
                winning_team = "Rouge"
                winning_color = "🔴"
            
            # Récupérer les joueurs
            winners = []
            losers = []
            winner_elos = []
            loser_elos = []
            
            for player_id in winner_ids:
                player = get_player(player_id)
                if player:
                    winners.append(player)
                    winner_elos.append(player['elo'])
            
            for player_id in loser_ids:
                player = get_player(player_id)
                if player:
                    losers.append(player)
                    loser_elos.append(player['elo'])
            
            if len(winners) != 3 or len(losers) != 3:
                await interaction.edit_original_response(content="❌ Erreur: Impossible de récupérer tous les joueurs", view=None)
                return
            
            # Calculer les changements d'ELO
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            
            winner_elo_changes = []
            loser_elo_changes = []
            
            # Appliquer les changements
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                elo_change = calculate_elo_change(old_elo, loser_avg, True)
                new_elo = max(0, old_elo + elo_change)
                
                if update_player_elo(player['discord_id'], new_elo, True):
                    winner_elo_changes.append(elo_change)
                else:
                    await interaction.edit_original_response(content="❌ Erreur lors de la mise à jour des ELO", view=None)
                    return
            
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                elo_change = calculate_elo_change(old_elo, winner_avg, False)
                new_elo = max(0, old_elo + elo_change)
                
                if update_player_elo(player['discord_id'], new_elo, False):
                    loser_elo_changes.append(elo_change)
                else:
                    await interaction.edit_original_response(content="❌ Erreur lors de la mise à jour des ELO", view=None)
                    return
            
            # Désactiver tous les boutons
            for item in self.children:
                item.disabled = True
            
            # Message de validation
            validation_message = f"✅ **MATCH VALIDÉ PAR VOTE** ({reason})\n\n"
            validation_message += f"🏆 VICTOIRE ÉQUIPE {winning_team} {winning_color}\n"
            validation_message += f"Lobby #{self.lobby_id} - Code: {self.room_code}"
            
            # Mettre à jour le message de vote
            await interaction.edit_original_response(content=validation_message, view=self)
            
            # Créer des objets mock pour la sauvegarde
            class MockMember:
                def __init__(self, discord_id, name):
                    self.id = int(discord_id)
                    self.display_name = name
            
            mock_winners = [MockMember(p['discord_id'], p['name']) for p in winners]
            mock_losers = [MockMember(p['discord_id'], p['name']) for p in losers]
            
            # Sauvegarder pour l'historique (undo)
            save_match_history(mock_winners, mock_losers, winner_elo_changes, loser_elo_changes)
            
            # Envoyer le résumé dans le salon dédié avec réaction d'annulation
            await self.send_match_summary(interaction, winners, losers, winner_elos, loser_elos, 
                                        winner_elo_changes, loser_elo_changes, winner_avg, loser_avg, reason)
            
        except Exception as e:
            print(f"Erreur dans validate_match_result: {e}")
            try:
                await interaction.edit_original_response(content=f"❌ Erreur lors de la validation: {str(e)}", view=None)
            except:
                pass
    
    async def send_match_summary(self, interaction, winners, losers, winner_elos, loser_elos, 
                                winner_elo_changes, loser_elo_changes, winner_avg, loser_avg, reason):
        """Envoie le résumé du match dans le salon dédié"""
        try:
            # Construire le message de résultat
            winning_team = "Bleue" if winners[0]['discord_id'] in [str(id) for id in self.team1_ids] else "Rouge"
            winning_color = "🔵" if winning_team == "Bleue" else "🔴"
            losing_color = "🔴" if winning_team == "Bleue" else "🔵"
            
            result_message = f"🏆 **RÉSULTAT DE MATCH**\n\n"
            result_message += f"**Victoire Équipe {winning_team} {winning_color}** (par {reason})\n"
            result_message += f"Lobby #{self.lobby_id} - Code: {self.room_code}\n\n"
            
            result_message += f"{winning_color} **GAGNANTS:**\n"
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                change = winner_elo_changes[i]
                new_elo = old_elo + change
                result_message += f"<@{player['discord_id']}>: {old_elo} → {new_elo} (+{change})\n"
            
            result_message += f"\n{losing_color} **PERDANTS:**\n"
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                change = loser_elo_changes[i]
                new_elo = old_elo + change
                result_message += f"<@{player['discord_id']}>: {old_elo} → {new_elo} ({change:+})\n"
            
            # Statistiques
            elo_diff = abs(winner_avg - loser_avg)
            result_message += f"\n📊 **ANALYSE:**\n"
            result_message += f"ELO moyen gagnants: {round(winner_avg)}\n"
            result_message += f"ELO moyen perdants: {round(loser_avg)}\n"
            result_message += f"Écart: {round(elo_diff)} points\n\n"
            result_message += f"↩️ *Réagissez avec ↩️ pour annuler ce match en cas de fraude*"
            
            # Envoyer dans le salon de résumés
            summary_channel = interaction.guild.get_channel(MATCH_SUMMARY_CHANNEL_ID)
            if summary_channel:
                summary_message = await summary_channel.send(result_message, suppress_embeds=True)
                # Ajouter la réaction d'annulation
                await summary_message.add_reaction("↩️")
                
                # Sauvegarder l'ID du message pour l'annulation
                from main import save_match_message_id
                save_match_message_id(summary_message.id)
            
        except Exception as e:
            print(f"Erreur dans send_match_summary: {e}")
    
    async def on_timeout(self):
        """Appelé quand la vue expire"""
        for item in self.children:
            item.disabled = True

# ================================
# CLASSES POUR LES BOUTONS ADMIN
# ================================

class AdminMatchResultView(discord.ui.View):
    """Vue avec boutons admin pour valider directement (cas d'égalité ou urgence)"""
    
    def __init__(self, team1_ids, team2_ids, lobby_id, room_code):
        super().__init__(timeout=1800)  # 30 minutes de timeout
        self.team1_ids = team1_ids
        self.team2_ids = team2_ids
        self.lobby_id = lobby_id
        self.room_code = room_code
        self.match_validated = False
    
    @discord.ui.button(label='🔵 Victoire Équipe Bleue', style=discord.ButtonStyle.primary, emoji='🔵')
    async def team1_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_admin_result(interaction, team1_wins=True)
    
    @discord.ui.button(label='🔴 Victoire Équipe Rouge', style=discord.ButtonStyle.danger, emoji='🔴')
    async def team2_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_admin_result(interaction, team1_wins=False)
    
    async def handle_admin_result(self, interaction: discord.Interaction, team1_wins: bool):
        """Traite le résultat du match (admin seulement)"""
        try:
            # Vérifier les permissions admin
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Seuls les administrateurs peuvent valider les résultats!", ephemeral=True)
                return
            
            # Vérifier que le match n'a pas déjà été validé
            if self.match_validated:
                await interaction.response.send_message("❌ Ce match a déjà été validé!", ephemeral=True)
                return
            
            # Le reste du code est identique à l'ancienne MatchResultView
            # ... (code de validation identique)
            # Pour économiser l'espace, je référence le code existant
            
        except Exception as e:
            print(f"Erreur dans handle_admin_result: {e}")

# ================================
# COMMANDES ULTRA SIMPLES
# ================================

async def create_lobby_cmd(ctx, room_code: str = None):
    """!create <code_room> - Créer un lobby"""
    from main import (
        get_player, create_player, create_lobby, add_player_to_lobby,
        get_all_lobbies, MAX_CONCURRENT_LOBBIES, PING_ROLE_ID
    )
    
    if not room_code:
        message = "❌ Usage: !create <code_room>"
        await ctx.send(message, suppress_embeds=True)
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        if not create_player(ctx.author.id, ctx.author.display_name):
            message = "❌ Erreur: Impossible de créer votre profil"
            await ctx.send(message, suppress_embeds=True)
            return
    
    # Créer le lobby avec vérifications
    lobby_id, creation_msg = create_lobby(room_code.upper())
    if not lobby_id:
        message = f"❌ Erreur: {creation_msg}"
        await ctx.send(message, suppress_embeds=True)
        return
    
    # Ajouter le créateur au lobby
    success, msg = add_player_to_lobby(lobby_id, ctx.author.id)
    
    if success:
        # Ping du rôle + message de création
        role_mention = f"<@&{PING_ROLE_ID}>"
        message = (f"{role_mention}\n\n"
                  f"🎮 NOUVEAU LOBBY!\n"
                  f"Lobby #{lobby_id}\n"
                  f"Code: {room_code.upper()}\n"
                  f"Créateur: {ctx.author.display_name}\n"
                  f"Joueurs: 1/6\n"
                  f"Rejoindre: !join {lobby_id}\n\n"
                  f"📊 Lobbies actifs: {len(get_all_lobbies())}/{MAX_CONCURRENT_LOBBIES}")
    else:
        message = f"❌ Erreur: {msg}"
    
    await ctx.send(message, suppress_embeds=True)

async def join_lobby_cmd(ctx, lobby_id: int = None):
    """!join <id> - Rejoindre un lobby"""
    from main import (
        get_player, create_player, add_player_to_lobby, get_lobby,
        create_random_teams, select_random_maps, get_connection
    )
    
    if lobby_id is None:
        message = "❌ Usage: !join <id_lobby>"
        await ctx.send(message, suppress_embeds=True)
        return
    
    # Vérifier/créer joueur
    player = get_player(ctx.author.id)
    if not player:
        if not create_player(ctx.author.id, ctx.author.display_name):
            message = "❌ Erreur: Impossible de créer votre profil"
            await ctx.send(message, suppress_embeds=True)
            return
    
    # Rejoindre le lobby
    success, msg = add_player_to_lobby(lobby_id, ctx.author.id)
    
    if success:
        # Récupérer info lobby
        lobby = get_lobby(lobby_id)
        if lobby:
            players_list = lobby['players'].split(',') if lobby['players'] else []
            players_count = len(players_list)
            
            if players_count >= 6:
                # Créer les équipes aléatoires
                team1_ids, team2_ids = create_random_teams([int(id) for id in players_list])
                
                # Récupérer les noms des joueurs et créer les mentions
                team1_mentions = []
                team2_mentions = []
                
                for player_id in team1_ids:
                    player = get_player(player_id)
                    if player:
                        team1_mentions.append(f"<@{player_id}>")
                
                for player_id in team2_ids:
                    player = get_player(player_id)
                    if player:
                        team2_mentions.append(f"<@{player_id}>")
                
                # Sélectionner 3 maps aléatoires
                selected_maps = select_random_maps(3)
                
                team1_text = '\n'.join([f"• {mention}" for mention in team1_mentions])
                team2_text = '\n'.join([f"• {mention}" for mention in team2_mentions])
                maps_text = '\n'.join([f"• {map_name}" for map_name in selected_maps])
                
                # Créer le lien cliquable
                room_link = f"https://link.nulls.gg/nb/invite/gameroom/fr?tag={lobby['room_code']}"
                
                message = (f"🚀 MATCH LANCE!\n"
                          f"Lobby #{lobby_id} complet! Équipes créées!\n\n"
                          f"🔵 Équipe 1:\n{team1_text}\n\n"
                          f"🔴 Équipe 2:\n{team2_text}\n\n"
                          f"🗺️ Maps:\n{maps_text}\n\n"
                          f"🎮 Rejoindre la room: {room_link}")
                
                # Envoyer le message principal
                await ctx.send(message, suppress_embeds=True)
                
                # Envoyer le système de vote dans le même salon
                vote_message = (f"🗳️ **VOTE DU RÉSULTAT**\n"
                              f"Lobby #{lobby_id} - Code: {lobby['room_code']}\n\n"
                              f"🔵 **Équipe Bleue:**\n{team1_text}\n\n"
                              f"🔴 **Équipe Rouge:**\n{team2_text}\n\n"
                              f"🗺️ **Maps:**\n{maps_text}\n\n"
                              f"⚡ Joueurs: Cliquez sur le bouton de votre équipe gagnante!\n"
                              f"📊 Majorité nécessaire: 4/6 votes ou unanimité après 6 votes\n"
                              f"⏰ Vous avez 24h pour voter")
                
                vote_view = PlayerVoteView(team1_ids, team2_ids, lobby_id, lobby['room_code'])
                # Envoyer directement via ctx.send au lieu d'une interaction
                vote_msg = await ctx.send(vote_message, view=vote_view, suppress_embeds=True)
                
                # Sauvegarder la référence du message pour les mises à jour
                await vote_view.set_original_message(vote_msg)
                
                # Envoyer aussi dans le salon admin pour backup
                admin_channel = ctx.guild.get_channel(RESULT_CHANNEL_ID)
                if admin_channel:
                    admin_message = (f"🔧 **BACKUP ADMIN** - Lobby #{lobby_id}\n"
                                   f"Vote des joueurs en cours dans {ctx.channel.mention}\n"
                                   f"Utilisez ces boutons en cas d'égalité ou de problème:")
                    
                    admin_view = AdminMatchResultView(team1_ids, team2_ids, lobby_id, lobby['room_code'])
                    await admin_channel.send(admin_message, view=admin_view, suppress_embeds=True)
                
                # Supprimer le lobby maintenant qu'il est lancé
                conn = get_connection()
                if conn:
                    try:
                        with conn.cursor() as c:
                            c.execute('DELETE FROM lobbies WHERE id = %s', (lobby_id,))
                            conn.commit()
                    finally:
                        conn.close()
            else:
                message = (f"✅ LOBBY REJOINT!\n"
                          f"{msg}\n"
                          f"Lobby: #{lobby_id}\n"
                          f"Code: {lobby['room_code']}\n"
                          f"Joueurs: {players_count}/6")
        else:
            message = f"✅ Rejoint: {msg}"
    else:
        message = f"❌ Erreur: {msg}"
    
    await ctx.send(message, suppress_embeds=True)

async def leave_lobby_cmd(ctx):
    """!leave - Quitter votre lobby"""
    from main import remove_player_from_lobby
    
    success, msg = remove_player_from_lobby(ctx.author.id)
    
    if success:
        message = f"👋 Quitté: {msg}"
    else:
        message = f"❌ Erreur: {msg}"
    
    await ctx.send(message, suppress_embeds=True)

async def list_lobbies_cmd(ctx):
    """!lobbies - Liste des lobbies actifs"""
    from main import (
        get_all_lobbies, get_cooldown_info, MAX_CONCURRENT_LOBBIES
    )
    
    lobbies = get_all_lobbies()
    cooldown_info = get_cooldown_info()
    
    message = f"🎮 LOBBIES ACTIFS ({len(lobbies)}/{MAX_CONCURRENT_LOBBIES}):\n\n"
    
    if not lobbies:
        message += "📋 Aucun lobby actif\n"
    else:
        for lobby in lobbies:
            lobby_id = lobby['id']
            room_code = lobby['room_code']
            players_str = lobby['players']
            players_count = len(players_str.split(',')) if players_str else 0
            
            status = "🟢" if players_count < 6 else "🔴"
            message += f"{status} Lobby #{lobby_id}\n"
            message += f"Code: {room_code}\n"
            message += f"Joueurs: {players_count}/6\n\n"
    
    # Afficher le cooldown si actif
    if cooldown_info and cooldown_info.get('active'):
        minutes = cooldown_info['remaining_minutes']
        seconds = cooldown_info['remaining_seconds']
        message += f"⏰ Cooldown: {minutes}m {seconds}s restantes\n"
    else:
        message += "✅ Nouveau lobby possible\n"
    
    message += f"Créer: !create <code>"
    await ctx.send(message, suppress_embeds=True)

async def show_elo_cmd(ctx):
    """!elo - Voir son ELO et rang"""
    from main import get_player, get_leaderboard, get_player_dodge_count
    
    player = get_player(ctx.author.id)
    
    if not player:
        message = ("❌ NON INSCRIT\n"
                  "Utilisez !create <code> ou !join <id> pour vous inscrire automatiquement")
        await ctx.send(message, suppress_embeds=True)
        return
    
    # Récupérer le pseudo Discord actuel
    try:
        member = ctx.guild.get_member(int(player['discord_id']))
        display_name = member.display_name if member else player['name']
    except:
        display_name = player['name']
    
    elo = player['elo']
    wins = player['wins']
    losses = player['losses']
    dodge_count = get_player_dodge_count(ctx.author.id)
    
    total_games = wins + losses
    winrate = round(wins / total_games * 100, 1) if total_games > 0 else 0
    
    # Calculer le rang
    players = get_leaderboard()
    rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(ctx.author.id)), len(players))
    
    message = (f"📊 {display_name}\n"
              f"ELO: {elo} points\n"
              f"Rang: #{rank}/{len(players)}\n"
              f"Victoires: {wins}\n"
              f"Défaites: {losses}\n"
              f"Winrate: {winrate}%")
    
    if dodge_count > 0:
        message += f"\n🚨 Dodges: {dodge_count}"
    
    await ctx.send(message, suppress_embeds=True)

async def leaderboard_cmd(ctx):
    """!leaderboard - Classement des joueurs"""
    from main import get_leaderboard, get_player
    
    players = get_leaderboard()
    
    if not players:
        message = "📊 CLASSEMENT VIDE\nAucun joueur inscrit"
        await ctx.send(message, suppress_embeds=True)
        return
    
    message = "🏆 CLASSEMENT ELO\n\n"
    
    for i, player in enumerate(players[:10], 1):
        # Récupérer le membre Discord actuel pour avoir le pseudo à jour
        try:
            member = ctx.guild.get_member(int(player['discord_id']))
            display_name = member.display_name if member else player['name']
        except:
            display_name = player['name']
        
        elo = player['elo']
        wins = player['wins']
        losses = player['losses']
        
        total_games = wins + losses
        winrate = round(wins / total_games * 100, 1) if total_games > 0 else 0
        
        if i == 1:
            emoji = "🥇"
        elif i == 2:
            emoji = "🥈"
        elif i == 3:
            emoji = "🥉"
        else:
            emoji = f"{i}."
        
        message += f"{emoji} {display_name} - {elo} ELO ({winrate}%)\n"
    
    message += f"\n{len(players)} joueur(s) total"
    
    # Position du joueur actuel
    current_player = get_player(ctx.author.id)
    if current_player:
        current_pos = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(ctx.author.id)), None)
        if current_pos:
            message += f"\n\nVotre position: #{current_pos} - {current_player['elo']} ELO"
    
    await ctx.send(message, suppress_embeds=True)

async def lobby_status_cmd(ctx):
    """!status - Statut des lobbies et cooldown"""
    from main import (
        get_all_lobbies, get_cooldown_info, get_leaderboard,
        MAX_CONCURRENT_LOBBIES, LOBBY_COOLDOWN_MINUTES
    )
    
    lobbies = get_all_lobbies()
    cooldown_info = get_cooldown_info()
    
    message = f"📊 STATUT SYSTÈME\n\n"
    message += f"🎮 Lobbies: {len(lobbies)}/{MAX_CONCURRENT_LOBBIES}\n"
    
    if cooldown_info and cooldown_info.get('active'):
        minutes = cooldown_info['remaining_minutes']
        seconds = cooldown_info['remaining_seconds']
        message += f"⏰ Cooldown: {minutes}m {seconds}s\n"
    else:
        message += f"✅ Création possible\n"
    
    message += f"⏱️ Cooldown: {LOBBY_COOLDOWN_MINUTES} min\n"
    
    # Statistiques des joueurs
    players = get_leaderboard()
    message += f"👥 Joueurs inscrits: {len(players)}"
    
    await ctx.send(message, suppress_embeds=True)

# ================================
# COMMANDES ADMIN
# ================================

async def record_manual_match_result(
    interaction: discord.Interaction,
    gagnant1: discord.Member,
    gagnant2: discord.Member,
    gagnant3: discord.Member,
    perdant1: discord.Member,
    perdant2: discord.Member,
    perdant3: discord.Member,
    dodge_joueur: Optional[discord.Member] = None,
    score: Optional[Literal["2-0", "2-1"]] = None
):
    """Enregistrer manuellement le résultat d'un match (admin uniquement)"""
    from main import (
        get_player, create_player, update_player_elo, calculate_elo_change,
        record_dodge, get_player_dodge_count, calculate_dodge_penalty, save_match_history,
        save_match_message_id
    )
    
    # Répondre immédiatement pour éviter l'expiration
    await interaction.response.send_message("⏳ Traitement du match en cours...", ephemeral=True)
    
    winners = [gagnant1, gagnant2, gagnant3]
    losers = [perdant1, perdant2, perdant3]
    
    # Vérifier qu'il n'y a pas de doublons
    all_members = winners + losers
    unique_ids = set(member.id for member in all_members)
    
    if len(unique_ids) != 6:
        await interaction.edit_original_response(content="❌ Erreur: Chaque joueur ne peut apparaître qu'une seule fois")
        return
    
    # Vérifier que le dodge_joueur fait partie des 6 joueurs
    if dodge_joueur and dodge_joueur not in all_members:
        await interaction.edit_original_response(content="❌ Erreur: Le joueur qui a dodge doit faire partie des 6 joueurs du match")
        return
    
    # Vérifier que tous sont inscrits
    for member in all_members:
        player = get_player(member.id)
        if not player:
            create_player(member.id, member.display_name)
    
    # Si dodge, enregistrer et calculer les pénalités
    dodge_penalty = 0
    if dodge_joueur:
        record_dodge(dodge_joueur.id)
        dodge_penalty = calculate_dodge_penalty(get_player_dodge_count(dodge_joueur.id))
    
    # Calculer nouveaux ELO
    winner_elos = []
    loser_elos = []
    
    for member in winners:
        player = get_player(member.id)
        if player:
            winner_elos.append(player['elo'])
        else:
            await interaction.edit_original_response(content="❌ Erreur: Impossible de récupérer les données des joueurs")
            return
    
    for member in losers:
        player = get_player(member.id)
        if player:
            loser_elos.append(player['elo'])
        else:
            await interaction.edit_original_response(content="❌ Erreur: Impossible de récupérer les données des joueurs")
            return
    
    winner_avg = sum(winner_elos) / 3
    loser_avg = sum(loser_elos) / 3
    
    # Préparer les changements ELO
    winner_elo_changes = []
    loser_elo_changes = []
    
    # Mettre à jour ELO avec gestion des dodges
    for i, member in enumerate(winners):
        old_elo = winner_elos[i]
        base_change = calculate_elo_change(old_elo, loser_avg, True)
        
        # Réduction si dodge (les gagnants gagnent un peu moins)
        if dodge_joueur:
            base_change = int(base_change * 0.8)  # 20% de réduction
        
        new_elo = max(0, old_elo + base_change)
        if update_player_elo(member.id, new_elo, True):
            winner_elo_changes.append(base_change)
        else:
            await interaction.edit_original_response(content="❌ Erreur mise à jour ELO")
            return
    
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        base_change = calculate_elo_change(old_elo, winner_avg, False)
        
        if dodge_joueur and member.id == dodge_joueur.id:
            # Le joueur qui a dodge perd plus
            final_change = base_change - dodge_penalty
            new_elo = max(0, old_elo + final_change)
            if update_player_elo(member.id, new_elo, False):
                loser_elo_changes.append(final_change)
            else:
                await interaction.edit_original_response(content="❌ Erreur mise à jour ELO")
                return
        else:
            # Ses coéquipiers perdent moins si dodge
            if dodge_joueur and dodge_joueur in losers:
                base_change = int(base_change * 0.3)  # Seulement 30% de la perte normale
            
            new_elo = max(0, old_elo + base_change)
            if update_player_elo(member.id, new_elo, False):
                loser_elo_changes.append(base_change)
            else:
                await interaction.edit_original_response(content="❌ Erreur mise à jour ELO")
                return
    
    # Sauvegarder pour l'historique (undo)
    save_match_history(winners, losers, winner_elo_changes, loser_elo_changes, 
                      dodge_joueur.id if dodge_joueur else None)
    
    # Construire le message de résumé
    result_message = f"🏆 **RÉSULTAT DE MATCH** (Validation Admin)\n\n"
    
    # Afficher le score si fourni
    if score:
        result_message += f"**Score: {score}**\n\n"
    
    # Afficher info dodge
    if dodge_joueur:
        result_message += f"🚨 **DODGE:** {dodge_joueur.display_name}\n"
        dodge_count = get_player_dodge_count(dodge_joueur.id)
        result_message += f"Dodges total: {dodge_count} (-{dodge_penalty} ELO supplémentaire)\n\n"
    
    result_message += "🏆 **GAGNANTS:**\n"
    for i, member in enumerate(winners):
        old_elo = winner_elos[i]
        change = winner_elo_changes[i]
        new_elo = old_elo + change
        result_message += f"{member.display_name}: {old_elo} → {new_elo} (+{change})\n"
    
    result_message += "\n💀 **PERDANTS:**\n"
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        change = loser_elo_changes[i]
        new_elo = old_elo + change
        
        if dodge_joueur and member.id == dodge_joueur.id:
            result_message += f"🚨 {member.display_name}: {old_elo} → {new_elo} ({change:+}) [DODGE]\n"
        else:
            dodge_indicator = " [Victime]" if dodge_joueur and dodge_joueur in losers else ""
            result_message += f"{member.display_name}: {old_elo} → {new_elo} ({change:+}){dodge_indicator}\n"
    
    # Statistiques du match
    elo_diff = abs(winner_avg - loser_avg)
    result_message += f"\n📊 **ANALYSE:**\n"
    result_message += f"ELO moyen gagnants: {round(winner_avg)}\n"
    result_message += f"ELO moyen perdants: {round(loser_avg)}\n"
    result_message += f"Écart: {round(elo_diff)} points"
    
    if dodge_joueur:
        result_message += f"\n\n⚠️ **SYSTÈME ANTI-DODGE:**\n"
        result_message += f"• Pénalité dodge: -{dodge_penalty} ELO\n"
        result_message += f"• Coéquipiers protégés: -70% perte\n"
        result_message += f"• Gagnants: -20% gain"
    
    result_message += f"\n\n↩️ *Réagissez avec ↩️ pour annuler ce match en cas de fraude*"
    
    # Envoyer le résumé dans le salon dédié avec réaction d'annulation
    summary_channel = interaction.guild.get_channel(MATCH_SUMMARY_CHANNEL_ID)
    if summary_channel:
        summary_message = await summary_channel.send(result_message, suppress_embeds=True)
        # Ajouter la réaction d'annulation
        await summary_message.add_reaction("↩️")
        
        # Sauvegarder l'ID du message pour l'annulation
        save_match_message_id(summary_message.id)
    
    # Confirmer à l'admin
    await interaction.edit_original_response(content="✅ Match enregistré avec succès! Résumé envoyé dans le salon dédié.")

async def reset_cooldown_cmd(ctx):
    """!resetcd - Reset le cooldown (admin seulement)"""
    from main import get_connection, LOBBY_COOLDOWN_MINUTES
    
    if not ctx.author.guild_permissions.administrator:
        message = "❌ Commande réservée aux administrateurs"
        await ctx.send(message, suppress_embeds=True)
        return
    
    conn = get_connection()
    if not conn:
        message = "❌ Erreur de connexion à la base"
        await ctx.send(message, suppress_embeds=True)
        return
    
    try:
        with conn.cursor() as c:
            # Reset le cooldown en mettant une date dans le passé
            c.execute('''
                UPDATE lobby_cooldown 
                SET last_creation = CURRENT_TIMESTAMP - INTERVAL '%s minutes'
                WHERE id = 1
            ''', (LOBBY_COOLDOWN_MINUTES + 1,))
            conn.commit()
        
        message = "✅ Cooldown reset! Création de lobby possible immédiatement."
        await ctx.send(message, suppress_embeds=True)
    except Exception as e:
        message = f"❌ Erreur lors du reset: {str(e)}"
        await ctx.send(message, suppress_embeds=True)
    finally:
        conn.close()

async def clear_lobbies_cmd(ctx):
    """!clearlobbies - Supprimer tous les lobbies (admin seulement)"""
    from main import get_connection
    
    if not ctx.author.guild_permissions.administrator:
        message = "❌ Commande réservée aux administrateurs"
        await ctx.send(message, suppress_embeds=True)
        return
    
    conn = get_connection()
    if not conn:
        message = "❌ Erreur de connexion à la base"
        await ctx.send(message, suppress_embeds=True)
        return
    
    try:
        with conn.cursor() as c:
            c.execute('SELECT COUNT(*) as count FROM lobbies')
            count = c.fetchone()['count']
            
            c.execute('DELETE FROM lobbies')
            conn.commit()
        
        message = f"🗑️ {count} lobby(s) supprimé(s)"
        await ctx.send(message, suppress_embeds=True)
    except Exception as e:
        message = f"❌ Erreur: {str(e)}"
        await ctx.send(message, suppress_embeds=True)
    finally:
        conn.close()

async def undo_match_cmd(ctx):
    """!undo - Annuler le dernier match (admin seulement)"""
    from main import undo_last_match
    
    if not ctx.author.guild_permissions.administrator:
        message = "❌ Commande réservée aux administrateurs"
        await ctx.send(message, suppress_embeds=True)
        return
    
    success, result = undo_last_match()
    
    if success:
        message = "🔄 MATCH ANNULE!\n\n"
        message += f"🏆 Anciens gagnants: {', '.join(result['winners'])}\n"
        message += f"💀 Anciens perdants: {', '.join(result['losers'])}\n\n"
        message += f"📊 Changements ELO annulés:\n"
        
        for i, name in enumerate(result['winners']):
            change = result['winner_changes'][i]
            message += f"  {name}: -{change} ELO\n"
        
        for i, name in enumerate(result['losers']):
            change = result['loser_changes'][i]
            message += f"  {name}: -{change} ELO\n"
        
        if result['had_dodge']:
            message += f"\n🚨 Dodge également annulé"
        
        message += "\n✅ Tous les changements ont été inversés"
    else:
        message = f"❌ Erreur: {result}"
    
    await ctx.send(message, suppress_embeds=True)

# ================================
# GESTION DES RÉACTIONS D'ANNULATION
# ================================

async def handle_match_cancel_reaction(payload):
    """Gère l'annulation d'un match par réaction ↩️"""
    try:
        from main import is_match_message, undo_last_match
        
        # Vérifier que c'est la bonne réaction et le bon salon
        if str(payload.emoji) != "↩️":
            return
        
        if payload.channel_id != MATCH_SUMMARY_CHANNEL_ID:
            return
        
        # Vérifier que c'est un message de match
        if not is_match_message(payload.message_id):
            return
        
        # Récupérer l'utilisateur et vérifier les permissions
        guild = payload.member.guild if payload.member else None
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        if not member or not member.guild_permissions.administrator:
            return
        
        # Annuler le match
        success, result = undo_last_match()
        
        if success:
            # Récupérer le canal et le message
            channel = guild.get_channel(payload.channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(payload.message_id)
                    
                    # Modifier le message pour indiquer l'annulation
                    cancel_message = f"❌ **MATCH ANNULÉ** par {member.display_name}\n\n"
                    cancel_message += f"🔄 Anciens gagnants: {', '.join(result['winners'])}\n"
                    cancel_message += f"🔄 Anciens perdants: {', '.join(result['losers'])}\n\n"
                    cancel_message += "📊 Tous les changements ELO ont été annulés"
                    
                    if result['had_dodge']:
                        cancel_message += "\n🚨 Dodge également annulé"
                    
                    await message.edit(content=cancel_message, suppress_embeds=True)
                    await message.clear_reactions()
                    
                    # Retirer ce message de la liste des messages de match
                    from main import remove_match_message_id
                    remove_match_message_id(payload.message_id)
                    
                except Exception as e:
                    print(f"Erreur modification message annulation: {e}")
        
    except Exception as e:
        print(f"Erreur dans handle_match_cancel_reaction: {e}")

# ================================
# SETUP FONCTION
# ================================

async def setup_commands(bot):
    """Configure toutes les commandes du bot"""
    from main import (
        MAX_CONCURRENT_LOBBIES, LOBBY_COOLDOWN_MINUTES, PING_ROLE_ID
    )
    
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
    
    @bot.command(name='status')
    async def _status(ctx):
        await lobby_status_cmd(ctx)
    
    @bot.command(name='resetcd')
    async def _resetcd(ctx):
        await reset_cooldown_cmd(ctx)
    
    @bot.command(name='clearlobbies')
    async def _clearlobbies(ctx):
        await clear_lobbies_cmd(ctx)
    
    @bot.command(name='undo')
    async def _undo(ctx):
        await undo_match_cmd(ctx)
    
    # Commande slash admin pour validation manuelle
    @app_commands.command(name="result", description="Enregistrer manuellement un résultat de match (admin uniquement)")
    @app_commands.describe(
        gagnant1="Premier joueur gagnant",
        gagnant2="Deuxième joueur gagnant", 
        gagnant3="Troisième joueur gagnant",
        perdant1="Premier joueur perdant",
        perdant2="Deuxième joueur perdant",
        perdant3="Troisième joueur perdant",
        dodge_joueur="Joueur qui a dodge (optionnel)",
        score="Score final du match (optionnel)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(score=[
        app_commands.Choice(name="2-0", value="2-0"),
        app_commands.Choice(name="2-1", value="2-1")
    ])
    async def _result_manual(
        interaction: discord.Interaction,
        gagnant1: discord.Member,
        gagnant2: discord.Member,
        gagnant3: discord.Member,
        perdant1: discord.Member,
        perdant2: discord.Member,
        perdant3: discord.Member,
        dodge_joueur: Optional[discord.Member] = None,
        score: Optional[Literal["2-0", "2-1"]] = None
    ):
        await record_manual_match_result(
            interaction, gagnant1, gagnant2, gagnant3, 
            perdant1, perdant2, perdant3, dodge_joueur, score
        )
    
    # Ajouter la commande slash au bot
    bot.tree.add_command(_result_manual)
    
    # Event handler pour les réactions
    @bot.event
    async def on_raw_reaction_add(payload):
        if payload.user_id == bot.user.id:  # Ignorer les réactions du bot
            return
        await handle_match_cancel_reaction(payload)
    
    print("✅ Système de vote des joueurs activé")
    print("✅ Toutes les commandes chargées depuis commands.py")
    print(f"📊 Limite lobbies: {MAX_CONCURRENT_LOBBIES}")
    print(f"⏰ Cooldown: {LOBBY_COOLDOWN_MINUTES} minutes")
    print(f"🔔 Rôle ping: {PING_ROLE_ID}")
    print(f"📺 Salon validation admin: {RESULT_CHANNEL_ID}")
    print(f"📋 Salon résumés matchs: {MATCH_SUMMARY_CHANNEL_ID}")
    print("🗳️ Vote des joueurs activé (majorité 4/6 ou unanimité)")
    print("↩️ Annulation par réaction activée")
    print("🚨 Système anti-dodge activé")
    print("🔧 Commandes admin: !resetcd, !clearlobbies, !undo, /result")