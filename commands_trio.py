#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot ELO Trio - Commandes dédiées au mode Trio
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio
import json
from datetime import datetime, timedelta

# Configuration
RESULT_CHANNEL_ID = 1408595087331430520
MATCH_SUMMARY_CHANNEL_ID = 1385919316569886732

def get_connection():
    from main import get_connection as main_get_connection
    return main_get_connection()

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
    except:
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
    except:
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
    except:
        return False
    finally:
        conn.close()

def add_team_to_trio_lobby(lobby_id, team_id):
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
    except:
        return False, "Erreur interne"
    finally:
        conn.close()

class TrioVoteView(discord.ui.View):
    def __init__(self, team1_ids, team2_ids, lobby_id, room_code, guild):
        super().__init__(timeout=None)
        self.team1_ids = team1_ids
        self.team2_ids = team2_ids
        self.lobby_id = lobby_id
        self.room_code = room_code
        self.guild = guild
        self.match_type = 'trio'
        self.votes = {'team1': set(), 'team2': set()}
        self.dodge_reports = {}
        self.match_validated = False
        
    def _build_message(self):
        from main import select_random_maps
        
        team1_mentions = [f"<@{pid}>" for pid in self.team1_ids]
        team2_mentions = [f"<@{pid}>" for pid in self.team2_ids]
        
        maps = select_random_maps(3)
        maps_text = '\n'.join([f"• {m}" for m in maps])
        
        votes1 = len(self.votes['team1'])
        votes2 = len(self.votes['team2'])
        
        message = f"💥 **VOTE RÉSULTAT TRIO** - Lobby #{self.lobby_id}\n"
        message += f"Code: {self.room_code}\n\n"
        message += f"🔵 **Équipe Bleue** ({votes1} votes):\n{chr(10).join(team1_mentions)}\n\n"
        message += f"🔴 **Équipe Rouge** ({votes2} votes):\n{chr(10).join(team2_mentions)}\n\n"
        message += f"🗺️ **Maps:**\n{maps_text}\n\n"
        message += f"🎮 **Lien:** https://link.nulls.gg/nb/invite/gameroom/fr?tag={self.room_code}\n\n"
        message += f"📊 Votes: {votes1 + votes2}/6 | Majorité: 4/6"
        
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
            print(f"Erreur handle_vote: {e}")
    
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
                select = DodgeSelect(options, self, user_id)
                view = discord.ui.View(timeout=300)
                view.add_item(select)
                await self.safe_respond(interaction, "🚨 Sélectionnez le joueur qui a dodge:", view=view, ephemeral=True)
            else:
                await self.safe_respond(interaction, "❌ Aucun autre joueur à signaler", ephemeral=True)
                
        except Exception as e:
            print(f"Erreur handle_dodge_report: {e}")
    
    async def validate_match(self, team1_wins, reason, dodge_player_id=None, dodge_penalty=0):
        try:
            from main import get_player, update_player_elo, calculate_elo_change, save_match_history
            
            self.match_validated = True
            
            winner_ids = self.team1_ids if team1_wins else self.team2_ids
            loser_ids = self.team2_ids if team1_wins else self.team1_ids
            
            winners, losers = [], []
            winner_elos, loser_elos = [], []
            
            for pid in winner_ids:
                player = get_player(pid)
                if player:
                    winners.append(player)
                    winner_elos.append(player['trio_elo'])
            
            for pid in loser_ids:
                player = get_player(pid)
                if player:
                    losers.append(player)
                    loser_elos.append(player['trio_elo'])
            
            if len(winners) != 3 or len(losers) != 3:
                return
            
            winner_avg = sum(winner_elos) / 3
            loser_avg = sum(loser_elos) / 3
            
            winner_changes, loser_changes = [], []
            
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
            
            for item in self.children:
                item.disabled = True
            
            team_name = "Bleue" if team1_wins else "Rouge"
            validation_msg = f"✅ **MATCH TRIO VALIDÉ** ({reason})\n🏆 Victoire Équipe {team_name}\nLobby #{self.lobby_id}"
            await self._update_message(validation_msg)
            
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
            print(f"Erreur validate_match: {e}")
    
    async def send_match_summary(self, winners, losers, winner_elos, loser_elos,
                               winner_changes, loser_changes, reason, dodge_player_id=None, dodge_penalty=0):
        try:
            winning_team = "Bleue 🔵" if winners[0]['discord_id'] in [str(i) for i in self.team1_ids] else "Rouge 🔴"
            
            message = f"💥 **RÉSULTAT MATCH TRIO**\n\n"
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
                else:
                    message += f"<@{player['discord_id']}>: {old_elo} → {new_elo} ({change:+})\n"
            
            message += f"\n↩️ *Réagissez avec ↩️ pour annuler ce match*"
            
            summary_channel = self.guild.get_channel(MATCH_SUMMARY_CHANNEL_ID)
            if summary_channel:
                summary_msg = await summary_channel.send(message)
                await summary_msg.add_reaction("↩️")
                save_match_message_id(summary_msg.id, self.match_type)
                
        except Exception as e:
            print(f"Erreur send_match_summary: {e}")
    
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
            print(f"Erreur _update_message: {e}")

class DodgeSelect(discord.ui.Select):
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
            print(f"Erreur DodgeSelect callback: {e}")
    
    async def handle_confirmed_dodge(self, dodge_player_id):
        try:
            from main import calculate_dodge_penalty
            
            record_dodge(dodge_player_id, self.vote_view.match_type)
            dodge_count = get_player_dodge_count(dodge_player_id, self.vote_view.match_type)
            penalty = calculate_dodge_penalty(dodge_count)
            
            team1_wins = dodge_player_id not in self.vote_view.team1_ids
            await self.vote_view.validate_match(team1_wins, "dodge confirmé", dodge_player_id, penalty)
            
        except Exception as e:
            print(f"Erreur handle_confirmed_dodge: {e}")

def undo_last_trio_match():
    """Annule le dernier match trio"""
    conn = get_connection()
    if not conn:
        return False, "Erreur de connexion"
    
    try:
        with conn.cursor() as c:
            c.execute('''
                SELECT * FROM match_history 
                WHERE match_type = 'trio' 
                ORDER BY match_date DESC 
                LIMIT 1
            ''')
            last_match = c.fetchone()
            
            if not last_match:
                return False, "Aucun match trio à annuler"
            
            match_data = json.loads(last_match['match_data'])
            
            # Annuler les changements ELO
            winners = match_data['winners']
            winner_changes = match_data['winner_elo_changes']
            
            for i, player_id in enumerate(winners):
                old_change = winner_changes[i]
                c.execute('''
                    UPDATE players 
                    SET trio_elo = trio_elo - %s,
                        trio_wins = GREATEST(trio_wins - 1, 0)
                    WHERE discord_id = %s
                ''', (old_change, player_id))
            
            losers = match_data['losers']
            loser_changes = match_data['loser_elo_changes']
            
            for i, player_id in enumerate(losers):
                old_change = loser_changes[i]
                c.execute('''
                    UPDATE players 
                    SET trio_elo = trio_elo - %s,
                        trio_losses = GREATEST(trio_losses - 1, 0)
                    WHERE discord_id = %s
                ''', (old_change, player_id))
            
            # Annuler le dodge si il y en avait un
            dodge_player_id = match_data.get('dodge_player_id')
            if dodge_player_id:
                c.execute('''
                    DELETE FROM dodges 
                    WHERE id = (
                        SELECT id FROM dodges 
                        WHERE discord_id = %s AND dodge_type = 'trio'
                        ORDER BY dodge_date DESC 
                        LIMIT 1
                    )
                ''', (dodge_player_id,))
            
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
        print(f"Erreur undo_last_trio_match: {e}")
        return False, f"Erreur interne: {str(e)}"
    finally:
        conn.close()

async def setup_trio_commands(bot):
    """Configure toutes les commandes trio"""
    
    @bot.command(name='trio')
    async def create_trio(ctx, room_code: str = None):
        from main import get_player, create_player, create_lobby, get_player_trio_team, PING_ROLE_ID
        
        if not room_code:
            await ctx.send("❌ Usage: !trio <code_room>")
            return
        
        team = get_player_trio_team(ctx.author.id)
        if not team:
            await ctx.send("❌ Vous devez avoir une équipe trio! Utilisez `!createteam`")
            return
        
        player = get_player(ctx.author.id)
        if not player:
            create_player(ctx.author.id, ctx.author.display_name)
        
        lobby_id, msg = create_lobby(room_code.upper(), 'trio')
        if not lobby_id:
            await ctx.send(f"❌ {msg}")
            return
        
        success, join_msg = add_team_to_trio_lobby(lobby_id, team['id'])
        if success:
            message = (f"<@&{PING_ROLE_ID}>\n\n💥 **NOUVEAU LOBBY TRIO #{lobby_id}**\n"
                      f"Code: {room_code.upper()}\n"
                      f"Équipe: {team['name']}\n"
                      f"Rejoindre: !jointrio {lobby_id}")
            await ctx.send(message)
        else:
            await ctx.send(f"❌ {join_msg}")
    
    @bot.command(name='jointrio')
    async def join_trio(ctx, lobby_id: int = None):
        from main import get_player, create_player, get_lobby, get_player_trio_team
        
        if not lobby_id:
            await ctx.send("❌ Usage: !jointrio <id_lobby>")
            return
        
        team = get_player_trio_team(ctx.author.id)
        if not team:
            await ctx.send("❌ Vous devez avoir une équipe trio! Utilisez `!createteam`")
            return
        
        player = get_player(ctx.author.id)
        if not player:
            create_player(ctx.author.id, ctx.author.display_name)
        
        success, msg = add_team_to_trio_lobby(lobby_id, team['id'])
        if not success:
            await ctx.send(f"❌ {msg}")
            return
        
        lobby = get_lobby(lobby_id)
        if lobby and lobby['lobby_type'] == 'trio':
            teams = lobby['teams'].split(',') if lobby['teams'] else []
            if len(teams) >= 2:
                conn = get_connection()
                team1_players = []
                team2_players = []
                
                if conn:
                    try:
                        with conn.cursor() as c:
                            c.execute('SELECT * FROM trio_teams WHERE id = %s', (int(teams[0]),))
                            team1 = c.fetchone()
                            if team1:
                                team1_players = [int(team1['captain_id']), int(team1['player2_id']), int(team1['player3_id'])]
                            
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
                        vote_view = TrioVoteView(team1_players, team2_players, lobby_id, 
                                               lobby['room_code'], ctx.guild)
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
                await ctx.send(f"✅ Équipe ajoutée au lobby trio! ({len(teams)}/2 équipes)")
    
    @bot.command(name='createteam')
    async def create_team(ctx, teammate1: discord.Member, teammate2: discord.Member, *, team_name: str):
        from main import get_player, create_player, create_trio_team
        
        if len(team_name) > 30:
            await ctx.send("❌ Nom d'équipe trop long (30 caractères max)")
            return
        
        # Vérifier que les 3 joueurs sont différents
        if ctx.author.id == teammate1.id or ctx.author.id == teammate2.id or teammate1.id == teammate2.id:
            await ctx.send("❌ Les 3 joueurs doivent être différents")
            return
        
        # Créer les joueurs s'ils n'existent pas
        for member in [ctx.author, teammate1, teammate2]:
            player = get_player(member.id)
            if not player:
                create_player(member.id, member.display_name)
        
        success, msg = create_trio_team(ctx.author.id, teammate1.id, teammate2.id, team_name)
        if success:
            await ctx.send(f"✅ **Équipe Trio créée!**\n"
                          f"📝 Nom: {team_name}\n"
                          f"👑 Capitaine: {ctx.author.display_name}\n"
                          f"👥 Équipiers: {teammate1.display_name}, {teammate2.display_name}")
        else:
            await ctx.send(f"❌ {msg}")
    
    @bot.command(name='myteam')
    async def my_team(ctx):
        from main import get_player_trio_team
        
        team = get_player_trio_team(ctx.author.id)
        if not team:
            await ctx.send("❌ Vous n'avez pas d'équipe trio. Utilisez `!createteam @joueur1 @joueur2 Nom`")
            return
        
        captain = ctx.guild.get_member(int(team['captain_id']))
        player2 = ctx.guild.get_member(int(team['player2_id']))
        player3 = ctx.guild.get_member(int(team['player3_id']))
        
        captain_name = captain.display_name if captain else f"ID:{team['captain_id']}"
        player2_name = player2.display_name if player2 else f"ID:{team['player2_id']}"
        player3_name = player3.display_name if player3 else f"ID:{team['player3_id']}"
        
        message = f"💥 **Équipe: {team['name']}**\n"
        message += f"👑 Capitaine: {captain_name}\n"
        message += f"👤 Équipiers: {player2_name}, {player3_name}\n"
        message += f"📅 Créée: {team['created_at'].strftime('%d/%m/%Y')}"
        
        await ctx.send(message)
    
    @bot.command(name='leaveteam')
    async def leave_team(ctx):
        from main import get_player_trio_team, delete_trio_team
        
        team = get_player_trio_team(ctx.author.id)
        if not team:
            await ctx.send("❌ Vous n'êtes dans aucune équipe trio")
            return
        
        team_name = team['name']
        
        # Seul le capitaine peut dissoudre l'équipe
        if int(team['captain_id']) != ctx.author.id:
            await ctx.send("❌ Seul le capitaine peut dissoudre l'équipe")
            return
        
        # Confirmation
        confirmation_msg = await ctx.send(f"⚠️ **ATTENTION!**\n"
                                        f"Vous êtes sur le point de dissoudre l'équipe **{team_name}**\n"
                                        f"Cette action est **IRRÉVERSIBLE**!\n\n"
                                        f"Réagissez avec ✅ pour confirmer ou ❌ pour annuler")
        
        await confirmation_msg.add_reaction("✅")
        await confirmation_msg.add_reaction("❌")
        
        def check(reaction, user):
            return (user == ctx.author and 
                   str(reaction.emoji) in ["✅", "❌"] and 
                   reaction.message.id == confirmation_msg.id)
        
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "✅":
                success = delete_trio_team(team['id'])
                if success:
                    await ctx.send(f"✅ **Équipe {team_name} dissoute avec succès!**\n"
                                  f"Tous les membres peuvent maintenant créer ou rejoindre de nouvelles équipes.")
                else:
                    await ctx.send("❌ Erreur lors de la dissolution de l'équipe")
            else:
                await ctx.send("❌ Dissolution annulée")
                
        except asyncio.TimeoutError:
            await ctx.send("⏰ Temps écoulé - Dissolution annulée")
    
    @bot.command(name='elotrio')
    async def elo_trio(ctx, member: discord.Member = None):
        from main import get_player, get_leaderboard
        
        target = member or ctx.author
        player = get_player(target.id)
        if not player:
            await ctx.send("❌ Joueur non inscrit")
            return
        
        players = get_leaderboard('trio')
        rank = next((i for i, p in enumerate(players, 1) if p['discord_id'] == str(target.id)), len(players))
        
        winrate = round(player['trio_wins'] / max(1, player['trio_wins'] + player['trio_losses']) * 100, 1)
        dodge_count = get_player_dodge_count(target.id, 'trio')
        
        message = (f"💥 **{target.display_name} - TRIO**\n"
                  f"ELO: {player['trio_elo']} | Rang: #{rank}\n"
                  f"W/L: {player['trio_wins']}/{player['trio_losses']} ({winrate}%)")
        
        if dodge_count > 0:
            message += f"\n🚨 Dodges: {dodge_count}"
        
        await ctx.send(message)
    
    @bot.command(name='leaderboardtrio')
    async def leaderboard_trio(ctx):
        from main import get_leaderboard
        
        players = get_leaderboard('trio')[:10]  # Top 10
        
        if not players:
            await ctx.send("❌ Aucun joueur inscrit en trio")
            return
        
        message = "💥 **CLASSEMENT TRIO - TOP 10**\n\n"
        
        for i, player in enumerate(players, 1):
            winrate = round(player['trio_wins'] / max(1, player['trio_wins'] + player['trio_losses']) * 100, 1)
            
            if i == 1:
                emoji = "🥇"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = f"`{i}.`"
            
            message += f"{emoji} **{player['name']}** - {player['trio_elo']} ELO\n"
            message += f"    W/L: {player['trio_wins']}/{player['trio_losses']} ({winrate}%)\n\n"
        
        await ctx.send(message)
    
    @bot.command(name='teams')
    async def list_teams(ctx):
        """Affiche la liste des équipes trio existantes"""
        conn = get_connection()
        if not conn:
            await ctx.send("❌ Erreur de connexion")
            return
        
        try:
            with conn.cursor() as c:
                c.execute('SELECT * FROM trio_teams ORDER BY created_at DESC LIMIT 10')
                teams = c.fetchall()
                
                if not teams:
                    await ctx.send("❌ Aucune équipe trio créée")
                    return
                
                message = "💥 **ÉQUIPES TRIO ACTIVES**\n\n"
                
                for i, team in enumerate(teams, 1):
                    captain = ctx.guild.get_member(int(team['captain_id']))
                    player2 = ctx.guild.get_member(int(team['player2_id']))
                    player3 = ctx.guild.get_member(int(team['player3_id']))
                    
                    captain_name = captain.display_name if captain else f"ID:{team['captain_id']}"
                    player2_name = player2.display_name if player2 else f"ID:{team['player2_id']}"
                    player3_name = player3.display_name if player3 else f"ID:{team['player3_id']}"
                    
                    message += f"`{i}.` **{team['name']}**\n"
                    message += f"   👑 {captain_name}\n"
                    message += f"   👤 {player2_name}, {player3_name}\n\n"
                
                await ctx.send(message)
                
        except Exception as e:
            print(f"Erreur list_teams: {e}")
            await ctx.send("❌ Erreur lors de la récupération des équipes")
        finally:
            conn.close()
    
    @bot.command(name='undotrio')
    async def undo_trio(ctx):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Admin uniquement")
            return
        
        success, result = undo_last_trio_match()
        if success:
            message = f"🔄 **MATCH TRIO ANNULÉ!**\n"
            message += f"Gagnants: {', '.join(result['winners'])}\n"
            message += f"Perdants: {', '.join(result['losers'])}"
        else:
            message = f"❌ Erreur: {result}"
        
        await ctx.send(message)
    
    print("✅ Commandes TRIO configurées")
    print("💥 Mode TRIO - Équipes fixes de 3 joueurs")
    print("👑 Système de capitaine et dissolution d'équipe")
    print("📝 Commandes: !createteam, !myteam, !leaveteam, !teams")
