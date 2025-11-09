#!/usr/bin/env node
/*
 * Synchronise les utilisateurs Supabase Auth avec la table players.
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

async function migrate() {
  console.log('[migrate-auth-users] Lecture des utilisateurs auth...');
  const { data: users, error } = await supabase.auth.admin.listUsers({ page: 1, perPage: 1000 });
  if (error) {
    throw error;
  }

  console.log(`[migrate-auth-users] ${users?.users?.length ?? 0} utilisateurs trouvés.`);

  for (const user of users.users) {
    const discordId = user.user_metadata?.discord_id;
    const displayName = user.user_metadata?.display_name || user.email;
    if (!discordId) {
      continue;
    }

    const payload = {
      discord_id: discordId.toString(),
      name: displayName || 'Joueur',
    };

    const { error: upsertError } = await supabase
      .from('players')
      .upsert(payload, { onConflict: 'discord_id' });
    if (upsertError) {
      console.error('[migrate-auth-users] Erreur pour', discordId, upsertError.message);
    }
  }

  console.log('[migrate-auth-users] Synchronisation terminée.');
}

migrate().catch((error) => {
  console.error('[migrate-auth-users] Échec', error);
  process.exit(1);
});
