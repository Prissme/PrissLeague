#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié - COMMANDES
Toutes les commandes du bot (prefix et slash) avec système de dodge et validation par boutons
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
import asyncio

# Import des fonctions depuis main.py
from main import (
    get_player, create_player, update_player_elo, get_leaderboard,
    create_lobby, get_lobby, add_player_to_lobby, remove_player_from_lobby,
    get_all_lobbies, create_random_teams, select_random_maps,
    calculate_elo_change, get_connection, get_cooldown_info,
    MAX_CONCURRENT_LOBBIES, LOBBY_COOLDOWN_MINUTES, PING_ROLE_ID,
    record_dodge, get_player_dodge_count, calculate_dodge_penalty,
    save_match_history, undo_last_match
)

# Salon de validation des résultats
RESULT_CHANNEL_ID = 1408595087331430520

# ================================
# CLASSES POUR LES BOUTONS
# ================================

class MatchResultView(discord.ui.View):
    """Vue avec boutons pour valider le résultat d'un match"""
    
    def __init__(self, team1_ids, team2_ids, lobby_id, room_code):
        super().__init__(timeout=1800)  # 30 minutes de timeout
        self.team1_ids = team1_ids  # Équipe bleue
        self.team2_ids = team2_ids  # Équipe rouge
        self.lobby_id = lobby_id
        self.room_code = room_code
        self.match_validated = False
    
    @discord.ui.button(label='🔵 Victoire Équipe Bleue', style=discord.ButtonStyle.primary, emoji='🔵')
    async def team1_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_match_result(interaction, team1_wins=True)
    
    @discord.ui.button(label='🔴 Victoire Équipe Rouge', style=discord.ButtonStyle.danger, emoji='🔴')
    async def team2_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_match_result(interaction, team1_wins=False)
    
    async def handle_match_result(self, interaction: discord.Interaction, team1_wins: bool):
        """Traite le résultat du match"""
        try:
            # Vérifier les permissions admin
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Seuls les administrateurs peuvent valider les résultats!", ephemeral=True)
                return
            
            # Vérifier que le match n'a pas déjà été validé
            if self.match_validated:
                await interaction.response.send_message("❌ Ce match a déjà été validé!", ephemeral=True)
                return
            
            # Répondre immédiatement pour éviter le timeout
            await interaction.response.send_message("⏳ Validation en cours...", ephemeral=True)
            
            # Marquer comme validé dès le début
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
                await interaction.edit_original_response(content="❌ Erreur: Impossible de récupérer tous les joueurs")
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
                    await interaction.edit_original_response(content="❌ Erreur lors de la mise à jour des ELO")
                    return
            
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                elo_change = calculate_elo_change(old_elo, winner_avg, False)
                new_elo = max(0, old_elo + elo_change)
                
                if update_player_elo(player['discord_id'], new_elo, False):
                    loser_elo_changes.append(elo_change)
                else:
                    await interaction.edit_original_response(content="❌ Erreur lors de la mise à jour des ELO")
                    return
            
            # Désactiver tous les boutons
            for item in self.children:
                item.disabled = True
            
            # Construire le message de résultat
            result_message = f"✅ MATCH VALIDÉ PAR {interaction.user.display_name}\n\n"
            result_message += f"🏆 VICTOIRE ÉQUIPE {winning_team} {winning_color}\n"
            result_message += f"Lobby #{self.lobby_id} - Code: {self.room_code}\n\n"
            
            result_message += f"{winning_color} GAGNANTS:\n"
            for i, player in enumerate(winners):
                old_elo = winner_elos[i]
                change = winner_elo_changes[i]
                new_elo = old_elo + change
                result_message += f"{player['name']}: {old_elo} → {new_elo} (+{change})\n"
            
            losing_color = "🔴" if team1_wins else "🔵"
            result_message += f"\n{losing_color} PERDANTS:\n"
            for i, player in enumerate(losers):
                old_elo = loser_elos[i]
                change = loser_elo_changes[i]
                new_elo = old_elo + change
                result_message += f"{player['name']}: {old_elo} → {new_elo} ({change:+})\n"
            
            # Statistiques
            elo_diff = abs(winner_avg - loser_avg)
            result_message += f"\n📊 ANALYSE:\n"
            result_message += f"ELO moyen gagnants: {round(winner_avg)}\n"
            result_message += f"ELO moyen perdants: {round(loser_avg)}\n"
            result_message += f"Écart: {round(elo_diff)} points"
            
            # Sauvegarder pour l'historique (undo)
            # Créer des objets mock pour la compatibilité
            class MockMember:
                def __init__(self, discord_id, name):
                    self.id = int(discord_id)
                    self.display_name = name
            
            mock_winners = [MockMember(p['discord_id'], p['name']) for p in winners]
            mock_losers = [MockMember(p['discord_id'], p['name']) for p in losers]
            
            save_match_history(mock_winners, mock_losers, winner_elo_changes, loser_elo_changes)
            
            # Mettre à jour le message avec les boutons désactivés
            await interaction.edit_original_response(content=f"✅ **MATCH VALIDÉ**\n\nÉquipe {winning_team} {winning_color} a gagné!")
            
            # Mettre à jour le message original avec les boutons désactivés
            original_message = interaction.message
            if original_message:
                try:
                    new_content = f"✅ **MATCH VALIDÉ** - Équipe {winning_team} {winning_color} a gagné!\n\n" + original_message.content.split('\n\n', 1)[1]
                    await original_message.edit(content=new_content, view=self)
                except:
                    pass
            
            # Envoyer le résultat dans le salon principal
            channel = interaction.guild.get_channel(RESULT_CHANNEL_ID)
            if channel:
                await channel.send(result_message, suppress_embeds=True)
            
        except Exception as e:
            print(f"Erreur dans handle_match_result: {e}")
            try:
                await interaction.edit_original_response(content=f"❌ Erreur lors de la validation: {str(e)}")
            except:
                await interaction.followup.send(f"❌ Erreur lors de la validation: {str(e)}", ephemeral=True)
    
    async def on_timeout(self):
        """Appelé quand la vue expire"""
        for item in self.children:
            item.disabled = True
        # Le message sera automatiquement mis à jour si possible

# ================================
# COMMANDES ULTRA SIMPLES - SANS EMBEDS
# ================================

async def create_lobby_cmd(ctx, room_code: str = None):
    """!create <code_room> - Créer un lobby"""
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
                team1_ids, team2_ids = create_random_teams(players_list)
                
                # Récupérer les noms des joueurs
                team1_names = []
                team2_names = []
                
                for player_id in team1_ids:
                    player = get_player(player_id)
                    if player:
                        team1_names.append(player['name'])
                
                for player_id in team2_ids:
                    player = get_player(player_id)
                    if player:
                        team2_names.append(player['name'])
                
                # Sélectionner 3 maps aléatoires
                selected_maps = select_random_maps(3)
                
                team1_text = '\n'.join([f"• {name}" for name in team1_names])
                team2_text = '\n'.join([f"• {name}" for name in team2_names])
                maps_text = '\n'.join([f"• {map_name}" for map_name in selected_maps])
                
                message = (f"🚀 MATCH LANCE!\n"
                          f"Lobby #{lobby_id} complet! Équipes créées!\n\n"
                          f"🔵 Équipe 1:\n{team1_text}\n\n"
                          f"🔴 Équipe 2:\n{team2_text}\n\n"
                          f"🗺️ Maps:\n{maps_text}\n\n"
                          f"🎮 Code: {lobby['room_code']}")
                
                # Envoyer le message principal
                await ctx.send(message, suppress_embeds=True)
                
                # Envoyer une copie avec boutons dans le salon de validation
                result_channel = ctx.guild.get_channel(RESULT_CHANNEL_ID)
                if result_channel:
                    validation_message = (f"🎮 **NOUVEAU MATCH EN COURS**\n"
                                        f"Lobby #{lobby_id} - Code: {lobby['room_code']}\n\n"
                                        f"🔵 **Équipe Bleue:**\n{team1_text}\n\n"
                                        f"🔴 **Équipe Rouge:**\n{team2_text}\n\n"
                                        f"🗺️ **Maps:**\n{maps_text}\n\n"
                                        f"⚡ Cliquez sur le bouton de l'équipe gagnante pour valider le résultat!")
                    
                    view = MatchResultView(team1_ids, team2_ids, lobby_id, lobby['room_code'])
                    await result_channel.send(validation_message, view=view, suppress_embeds=True)
                
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
    success, msg = remove_player_from_lobby(ctx.author.id)
    
    if success:
        message = f"👋 Quitté: {msg}"
    else:
        message = f"❌ Erreur: {msg}"
    
    await ctx.send(message, suppress_embeds=True)

async def list_lobbies_cmd(ctx):
    """!lobbies - Liste des lobbies actifs"""
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
    player = get_player(ctx.author.id)
    
    if not player:
        message = ("❌ NON INSCRIT\n"
                  "Utilisez !create <code> ou !join <id> pour vous inscrire automatiquement")
        await ctx.send(message, suppress_embeds=True)
        return
    
    name = player['name']
    elo = player['elo']
    wins = player['wins']
    losses = player['losses']
    dodge_count = get_player_dodge_count(ctx.author.id)
    
    total_games = wins + losses
    winrate = round(wins / total_games * 100, 1) if total_games > 0 else 0
    
    # Calculer le rang
    players = get_leaderboard()
    rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(ctx.author.id)), len(players))
    
    message = (f"📊 {name}\n"
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
    players = get_leaderboard()
    
    if not players:
        message = "📊 CLASSEMENT VIDE\nAucun joueur inscrit"
        await ctx.send(message, suppress_embeds=True)
        return
    
    message = "🏆 CLASSEMENT ELO\n\n"
    
    for i, player in enumerate(players[:10], 1):
        name = player['name']
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
        
        message += f"{emoji} {name} - {elo} ELO ({winrate}%)\n"
    
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
# COMMANDES ADMIN - SANS EMBEDS
# ================================

async def record_match_result(
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
    """Enregistrer le résultat d'un match avec gestion des dodges"""
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
        # Enregistrer le dodge dans la base
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
    
    # Mettre à jour ELO avec gestion des dodges
    message = "⚔️ MATCH ENREGISTRE!\n\n"
    
    # Afficher le score si fourni
    if score:
        message += f"🏆 Score: {score}\n\n"
    
    # Afficher info dodge
    if dodge_joueur:
        message += f"🚨 DODGE: {dodge_joueur.display_name}\n"
        dodge_count = get_player_dodge_count(dodge_joueur.id)
        message += f"Dodges total: {dodge_count} (-{dodge_penalty} ELO supplémentaire)\n\n"
    
    message += "🏆 GAGNANTS:\n"
    for i, member in enumerate(winners):
        old_elo = winner_elos[i]
        base_change = calculate_elo_change(old_elo, loser_avg, True)
        
        # Réduction si dodge (les gagnants gagnent un peu moins)
        if dodge_joueur:
            base_change = int(base_change * 0.8)  # 20% de réduction
        
        new_elo = max(0, old_elo + base_change)
        if update_player_elo(member.id, new_elo, True):
            message += f"{member.display_name}: {old_elo} → {new_elo} (+{base_change})\n"
        else:
            message += f"{member.display_name}: Erreur mise à jour\n"
    
    message += "\n💀 PERDANTS:\n"
    for i, member in enumerate(losers):
        old_elo = loser_elos[i]
        base_change = calculate_elo_change(old_elo, winner_avg, False)
        
        if dodge_joueur and member.id == dodge_joueur.id:
            # Le joueur qui a dodge perd plus
            final_change = base_change - dodge_penalty
            new_elo = max(0, old_elo + final_change)
            if update_player_elo(member.id, new_elo, False):
                message += f"🚨 {member.display_name}: {old_elo} → {new_elo} ({final_change:+}) [DODGE]\n"
            else:
                message += f"🚨 {member.display_name}: Erreur mise à jour [DODGE]\n"
        else:
            # Ses coéquipiers perdent moins si dodge
            if dodge_joueur and dodge_joueur in losers:
                base_change = int(base_change * 0.3)  # Seulement 30% de la perte normale
            
            new_elo = max(0, old_elo + base_change)
            if update_player_elo(member.id, new_elo, False):
                dodge_indicator = " [Victime]" if dodge_joueur and dodge_joueur in losers else ""
                message += f"{member.display_name}: {old_elo} → {new_elo} ({base_change:+}){dodge_indicator}\n"
            else:
                message += f"{member.display_name}: Erreur mise à jour\n"
    
    # Statistiques du match
    elo_diff = abs(winner_avg - loser_avg)
    message += f"\n📊 ANALYSE:\n"
    message += f"ELO moyen gagnants: {round(winner_avg)}\n"
    message += f"ELO moyen perdants: {round(loser_avg)}\n"
    message += f"Écart: {round(elo_diff)} points"
    
    if dodge_joueur:
        message += f"\n\n⚠️ SYSTÈME ANTI-DODGE:\n"
        message += f"• Pénalité dodge: -{dodge_penalty} ELO\n"
        message += f"• Coéquipiers protégés: -70% perte\n"
        message += f"• Gagnants: -20% gain"
    
    # Envoyer le message final dans le canal (pas en éphémère)
    await interaction.followup.send(message, suppress_embeds=True)
    await interaction.edit_original_response(content="✅ Match traité avec succès!")

async def old_record_match_result(ctx, winner1: discord.Member, winner2: discord.Member, winner3: discord.Member,
                             loser1: discord.Member, loser2: discord.Member, loser3: discord.Member):
    """!result @w1 @w2 @w3 @l1 @l2 @l3 - Enregistrer un match (ancienne version)"""
    message = ("⚠️ COMMANDE OBSOLETE\n"
              "Utilisez la nouvelle commande /results avec les arguments nommés :\n"
              "• gagnant1, gagnant2, gagnant3\n"
              "• perdant1, perdant2, perdant3\n"
              "• dodge_joueur (optionnel)\n"
              "• score (optionnel): 2-0 ou 2-1\n\n"
              "OU utilisez les boutons automatiques dans le salon de validation!")
    await ctx.send(message, suppress_embeds=True)

async def reset_cooldown_cmd(ctx):
    """!resetcd - Reset le cooldown (admin seulement)"""
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

async def reduce_losses_cmd(ctx):
    """!reducelosses - Retirer 3 défaites et ajouter 30 ELO aux joueurs avec 4+ défaites (admin seulement)"""
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
            # Récupérer les joueurs avec 4 défaites ou plus
            c.execute('''
                SELECT discord_id, name, elo, wins, losses 
                FROM players 
                WHERE losses >= 4
                ORDER BY losses DESC
            ''')
            players = c.fetchall()
            
            if not players:
                message = "ℹ️ Aucun joueur trouvé avec 4 défaites ou plus"
                await ctx.send(message, suppress_embeds=True)
                return
            
            # Effectuer les ajustements
            affected_count = 0
            adjustments = []
            
            for player in players:
                old_elo = player['elo']
                old_losses = player['losses']
                wins = player['wins']
                
                new_elo = old_elo + 30
                new_losses = old_losses - 3
                
                # Mettre à jour en base
                c.execute('''
                    UPDATE players 
                    SET elo = %s, losses = %s 
                    WHERE discord_id = %s
                ''', (new_elo, new_losses, player['discord_id']))
                
                # Calculer le nouveau winrate
                total_games = wins + new_losses
                new_winrate = round(wins / total_games * 100, 1) if total_games > 0 else 0
                
                adjustments.append({
                    'name': player['name'],
                    'old_elo': old_elo,
                    'new_elo': new_elo,
                    'old_losses': old_losses,
                    'new_losses': new_losses,
                    'winrate': new_winrate
                })
                affected_count += 1
            
            conn.commit()
            
            # Construire le message de réponse
            message = f"✅ AJUSTEMENT TERMINE!\n\n"
            message += f"📊 {affected_count} joueur(s) ajusté(s):\n\n"
            
            for adj in adjustments[:10]:  # Limiter à 10 pour éviter les messages trop longs
                message += f"{adj['name']}:\n"
                message += f"  ELO: {adj['old_elo']} → {adj['new_elo']} (+30)\n"
                message += f"  Défaites: {adj['old_losses']} → {adj['new_losses']} (-3)\n"
                message += f"  Winrate: {adj['winrate']}%\n\n"
            
            if len(adjustments) > 10:
                message += f"... et {len(adjustments) - 10} autre(s) joueur(s)\n\n"
            
            message += f"🔧 Total traité: {affected_count} joueur(s)"
            
            await ctx.send(message, suppress_embeds=True)
            
    except Exception as e:
        message = f"❌ Erreur lors de l'ajustement: {str(e)}"
        await ctx.send(message, suppress_embeds=True)
    finally:
        conn.close()

async def undo_match_cmd(ctx):
    """!undo - Annuler le dernier match (admin seulement)"""
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
# SETUP FONCTION
# ================================

async def setup_commands(bot):
    """Configure toutes les commandes du bot"""
    
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
    
    @bot.command(name='result')
    @commands.has_permissions(administrator=True)
    async def _result(ctx, winner1: discord.Member, winner2: discord.Member, winner3: discord.Member,
                     loser1: discord.Member, loser2: discord.Member, loser3: discord.Member):
        await old_record_match_result(ctx, winner1, winner2, winner3, loser1, loser2, loser3)
    
    @bot.command(name='resetcd')
    async def _resetcd(ctx):
        await reset_cooldown_cmd(ctx)
    
    @bot.command(name='clearlobbies')
    async def _clearlobbies(ctx):
        await clear_lobbies_cmd(ctx)
    
    @bot.command(name='reducelosses')
    async def _reducelosses(ctx):
        await reduce_losses_cmd(ctx)
    
    @bot.command(name='undo')
    async def _undo(ctx):
        await undo_match_cmd(ctx)
    
    # Commande slash admin avec système de dodge
    @app_commands.command(name="results", description="Enregistrer un résultat de match (avec gestion des dodges)")
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
    async def _results(
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
        await record_match_result(
            interaction, gagnant1, gagnant2, gagnant3, 
            perdant1, perdant2, perdant3, dodge_joueur, score
        )
    
    # Ajouter la commande slash au bot
    bot.tree.add_command(_results)
    
    print("✅ Toutes les commandes chargées depuis commands.py")
    print(f"📊 Limite lobbies: {MAX_CONCURRENT_LOBBIES}")
    print(f"⏰ Cooldown: {LOBBY_COOLDOWN_MINUTES} minutes")
    print(f"🔔 Rôle ping: {PING_ROLE_ID}")
    print(f"📺 Salon validation: {RESULT_CHANNEL_ID}")
    print("🚨 Système anti-dodge activé")
    print("🔘 Système de boutons de validation activé")
    print("🔧 Commandes admin disponibles: !resetcd, !clearlobbies, !reducelosses, !undo")