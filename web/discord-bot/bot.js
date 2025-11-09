import 'dotenv/config';
import { Client, GatewayIntentBits } from 'discord.js';
import cron from 'node-cron';
import { createClient } from '@supabase/supabase-js';

const token = process.env.DISCORD_BOT_TOKEN;
const guildId = process.env.DISCORD_GUILD_ID;

if (!token || !guildId) {
  console.error('[role-sync] DISCORD_BOT_TOKEN ou DISCORD_GUILD_ID manquant.');
  process.exit(1);
}

if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
  console.error('[role-sync] Config Supabase manquante.');
  process.exit(1);
}

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false },
});

const tierConfig = [
  { name: 'MYTHIC', minElo: 1800, roleId: process.env.ROLE_TIER_MYTHIC },
  { name: 'DIAMOND', minElo: 1600, roleId: process.env.ROLE_TIER_DIAMOND },
  { name: 'GOLD', minElo: 1400, roleId: process.env.ROLE_TIER_GOLD },
  { name: 'SILVER', minElo: 1200, roleId: process.env.ROLE_TIER_SILVER },
  { name: 'BRONZE', minElo: 0, roleId: process.env.ROLE_TIER_BRONZE },
].filter((tier) => tier.roleId);

const logChannelId = process.env.ROLE_SYNC_CHANNEL_ID;
const cronExpression = process.env.ROLE_SYNC_CRON || '*/10 * * * *';

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers],
});

async function fetchTopPlayers() {
  const { data, error } = await supabase
    .from('players')
    .select('discord_id, name, solo_elo')
    .eq('division', 'solo');
  if (error) {
    throw error;
  }
  return data ?? [];
}

function pickTier(elo) {
  return tierConfig.find((tier) => elo >= tier.minElo) ?? tierConfig[tierConfig.length - 1];
}

async function notify(guild, message) {
  if (!logChannelId) {
    console.log(`[role-sync] ${message}`);
    return;
  }
  try {
    const channel = await guild.channels.fetch(logChannelId);
    if (channel && channel.isTextBased()) {
      await channel.send(message);
    }
  } catch (error) {
    console.warn('[role-sync] Impossible d\'envoyer le message de log', error.message);
  }
}

async function syncGuildRoles() {
  const guild = await client.guilds.fetch(guildId);
  const players = await fetchTopPlayers();

  await notify(guild, `Synchronisation des rôles pour ${players.length} joueurs.`);

  for (const player of players) {
    const memberId = player.discord_id?.toString();
    if (!memberId) {
      continue;
    }
    try {
      const member = await guild.members.fetch(memberId);
      const targetTier = pickTier(player.solo_elo || 0);
      const tierRole = targetTier?.roleId ? await guild.roles.fetch(targetTier.roleId) : null;
      if (!tierRole) {
        continue;
      }

      const tierRoleIds = tierConfig.map((tier) => tier.roleId).filter(Boolean);
      const rolesToRemove = member.roles.cache.filter((role) => tierRoleIds.includes(role.id) && role.id !== tierRole.id);

      if (!member.roles.cache.has(tierRole.id)) {
        await member.roles.add(tierRole);
      }
      for (const role of rolesToRemove.values()) {
        await member.roles.remove(role);
      }
    } catch (error) {
      console.warn(`[role-sync] Impossible de mettre à jour ${memberId}: ${error.message}`);
    }
  }

  await notify(guild, 'Synchronisation terminée.');
}

client.once('ready', async () => {
  console.log(`[role-sync] Connecté en tant que ${client.user.tag}`);
  try {
    await syncGuildRoles();
  } catch (error) {
    console.error('[role-sync] Erreur initiale', error);
  }

  cron.schedule(cronExpression, () => {
    syncGuildRoles().catch((error) => console.error('[role-sync] Erreur cron', error));
  });
});

client.login(token).catch((error) => {
  console.error('[role-sync] Connexion échouée', error);
  process.exit(1);
});
