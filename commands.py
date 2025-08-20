#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Ultra Simplifié - COMMANDES
Toutes les commandes du bot (prefix et slash) avec système de dodge
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal

# Import des fonctions depuis main.py
from main import (
    get_player, create_player, update_player_elo, get_leaderboard,
    create_lobby, get_lobby, add_player_to_lobby, remove_player_from_lobby,
    get_all_lobbies, create_random_teams, select_random_maps,
    calculate_elo_change, get_connection, get_cooldown_info,
    MAX_CONCURRENT_LOBBIES, LOBBY_COOLDOWN_MINUTES, PING_ROLE_ID,
    record_dodge, get_player_dodge_count, calculate_dodge_penalty
)

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
              "• score (optionnel): 2-0 ou 2-1")
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
    print("🚨 Système anti-dodge activé")