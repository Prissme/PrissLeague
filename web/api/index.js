import { createClient } from '@supabase/supabase-js';

const requiredEnv = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'];
requiredEnv.forEach((key) => {
  if (!process.env[key]) {
    console.warn(`[api] Variable ${key} manquante. Certaines routes seront indisponibles.`);
  }
});

const supabase = process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY
  ? createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, {
      auth: { persistSession: false },
    })
  : null;

const adminIds = (process.env.ADMIN_USER_IDS || '')
  .split(',')
  .map((entry) => entry.trim())
  .filter(Boolean);

function send(res, statusCode, payload, headers = {}) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    ...headers,
  });
  res.end(JSON.stringify(payload));
}

async function parseJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  if (!chunks.length) {
    return {};
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch (error) {
    throw new Error('INVALID_JSON');
  }
}

async function getLeaderboard() {
  if (!supabase) {
    throw new Error('SUPABASE_NOT_CONFIGURED');
  }
  const { data, error } = await supabase
    .from('players')
    .select('discord_id, name, solo_elo, solo_wins, solo_losses')
    .eq('division', 'solo')
    .order('solo_elo', { ascending: false })
    .limit(50);
  if (error) {
    throw error;
  }
  return data ?? [];
}

async function insertMatch(payload, adminId) {
  if (!supabase) {
    throw new Error('SUPABASE_NOT_CONFIGURED');
  }
  if (!adminIds.includes(adminId)) {
    const err = new Error('FORBIDDEN');
    err.statusCode = 403;
    throw err;
  }

  const { team1_ids, team2_ids, winner, room_code, division = 'solo' } = payload;
  if (!Array.isArray(team1_ids) || !Array.isArray(team2_ids) || !room_code) {
    const err = new Error('INVALID_PAYLOAD');
    err.statusCode = 400;
    throw err;
  }

  const { data, error } = await supabase
    .from('solo_matches')
    .insert({
      team1_ids: team1_ids.join(','),
      team2_ids: team2_ids.join(','),
      winner,
      room_code,
      division,
      status: 'pending',
    })
    .select('*')
    .single();

  if (error) {
    throw error;
  }
  return data;
}

async function getPlayer(discordId) {
  if (!supabase) {
    throw new Error('SUPABASE_NOT_CONFIGURED');
  }
  const { data, error } = await supabase
    .from('players')
    .select('discord_id, name, solo_elo, solo_wins, solo_losses, division')
    .eq('discord_id', discordId)
    .maybeSingle();
  if (error) {
    throw error;
  }
  return data;
}

export async function handleApiRequest(req, res) {
  if (!req.url) {
    return false;
  }
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (!url.pathname.startsWith('/api/')) {
    return false;
  }

  try {
    if (url.pathname === '/api/health' && req.method === 'GET') {
      send(res, 200, { status: 'ok', timestamp: new Date().toISOString() });
      return true;
    }

    if (url.pathname === '/api/leaderboard' && req.method === 'GET') {
      const data = await getLeaderboard();
      send(res, 200, { players: data });
      return true;
    }

    if (url.pathname === '/api/matches' && req.method === 'POST') {
      const adminId = req.headers['x-admin-id'];
      const payload = await parseJsonBody(req);
      const inserted = await insertMatch(payload, typeof adminId === 'string' ? adminId : '');
      send(res, 201, { match: inserted });
      return true;
    }

    if (url.pathname.startsWith('/api/player/') && req.method === 'GET') {
      const discordId = url.pathname.replace('/api/player/', '');
      if (!discordId) {
        send(res, 400, { error: 'discord_id requis' });
        return true;
      }
      const player = await getPlayer(discordId);
      if (!player) {
        send(res, 404, { error: 'Joueur introuvable' });
        return true;
      }
      send(res, 200, { player });
      return true;
    }

    send(res, 404, { error: 'Route non trouvée' });
    return true;
  } catch (error) {
    if (error.message === 'INVALID_JSON') {
      send(res, 400, { error: 'Corps JSON invalide' });
      return true;
    }
    if (error.message === 'SUPABASE_NOT_CONFIGURED') {
      send(res, 500, { error: 'Supabase n\'est pas configuré' });
      return true;
    }
    const statusCode = error.statusCode ?? 500;
    console.error('[api] Error while processing request', error);
    send(res, statusCode, { error: error.message || 'Erreur interne' });
    return true;
  }
}
