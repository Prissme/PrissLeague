#!/usr/bin/env node
/*
 * Supprime les joueurs sans activité ou inconnus de la base PrissLeague.
 */

const { createClient } = require('@supabase/supabase-js');
require('dotenv').config({ path: require('path').resolve(__dirname, '..', '.env') });

const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const supabaseUrl = process.env.SUPABASE_URL;
const inactivityThreshold = Number(process.env.CLEANUP_INACTIVITY_DAYS || 180);

if (!serviceRoleKey || !supabaseUrl) {
  console.error('SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquant.');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, serviceRoleKey, {
  auth: { persistSession: false },
});

async function cleanup() {
  console.log(`[cleanup-unknown] Suppression des joueurs inactifs depuis ${inactivityThreshold} jours`);
  const { data, error } = await supabase
    .from('players')
    .select('discord_id, name, updated_at, created_at')
    .order('updated_at', { ascending: true });
  if (error) {
    throw error;
  }

  const now = Date.now();
  const limitMs = inactivityThreshold * 24 * 3600 * 1000;
  const toDelete = [];

  for (const player of data || []) {
    const updatedAt = player.updated_at || player.created_at;
    if (!updatedAt) {
      toDelete.push(player.discord_id);
      continue;
    }
    const lastActivity = new Date(updatedAt).getTime();
    if (Number.isFinite(lastActivity) && now - lastActivity > limitMs) {
      toDelete.push(player.discord_id);
    }
  }

  if (!toDelete.length) {
    console.log('[cleanup-unknown] Aucun joueur à supprimer.');
    return;
  }

  const { error: deleteError } = await supabase
    .from('players')
    .delete()
    .in('discord_id', toDelete);
  if (deleteError) {
    throw deleteError;
  }

  console.log(`[cleanup-unknown] ${toDelete.length} joueurs supprimés.`);
}

cleanup().catch((error) => {
  console.error('[cleanup-unknown] Échec', error);
  process.exit(1);
});
