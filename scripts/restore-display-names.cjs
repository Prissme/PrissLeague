#!/usr/bin/env node
/*
 * Restaure les display names perdus à partir de la table solo_matches.
 */

const { createClient } = require('@supabase/supabase-js');
require('dotenv').config({ path: require('path').resolve(__dirname, '..', '.env') });

const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const supabaseUrl = process.env.SUPABASE_URL;

if (!serviceRoleKey || !supabaseUrl) {
  console.error('SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquant.');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, serviceRoleKey, {
  auth: { persistSession: false },
});

async function restore() {
  const { data: matches, error } = await supabase
    .from('solo_matches')
    .select('team1_ids, team2_ids')
    .limit(1000);
  if (error) {
    throw error;
  }

  const seen = new Set();
  for (const match of matches || []) {
    [...(match.team1_ids || '').split(','), ...(match.team2_ids || '').split(',')]
      .map((id) => id.trim())
      .filter(Boolean)
      .forEach((id) => seen.add(id));
  }

  console.log(`[restore-display-names] ${seen.size} joueurs identifiés`);

  for (const discordId of seen) {
    const { data: player, error: fetchError } = await supabase
      .from('players')
      .select('discord_id, name')
      .eq('discord_id', discordId)
      .maybeSingle();
    if (fetchError) {
      console.error('[restore-display-names] Erreur lecture', discordId, fetchError.message);
      continue;
    }
    if (player?.name) {
      continue;
    }

    const fallbackName = `Joueur ${discordId.slice(-4)}`;
    const { error: updateError } = await supabase
      .from('players')
      .update({ name: fallbackName })
      .eq('discord_id', discordId);
    if (updateError) {
      console.error('[restore-display-names] Erreur update', discordId, updateError.message);
    }
  }

  console.log('[restore-display-names] Restauration terminée.');
}

restore().catch((error) => {
  console.error('[restore-display-names] Échec', error);
  process.exit(1);
});
