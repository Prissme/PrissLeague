import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';
import { readFile } from 'fs/promises';
import 'dotenv/config';

import { handleApiRequest } from './api/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicDir = path.join(__dirname, 'public');

const PORT = Number(process.env.PORT || 3000);

function send(res, statusCode, body, headers = {}) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    ...headers,
  });
  res.end(typeof body === 'string' ? body : JSON.stringify(body));
}

async function serveStatic(res) {
  const indexPath = path.join(publicDir, 'index.html');
  const html = await readFile(indexPath, 'utf8');
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(html);
}

const server = http.createServer(async (req, res) => {
  if (!req.url) {
    send(res, 400, { error: 'Bad Request' });
    return;
  }

  try {
    const handled = await handleApiRequest(req, res);
    if (handled) {
      return;
    }

    if (req.method === 'GET') {
      await serveStatic(res);
    } else {
      send(res, 405, { error: 'Méthode non supportée' });
    }
  } catch (error) {
    console.error('[server] Unhandled error', error);
    if (!res.headersSent) {
      send(res, 500, { error: 'Erreur interne du serveur' });
    } else {
      res.end();
    }
  }
});

server.listen(PORT, () => {
  console.log(`[web] Serveur HTTP démarré sur http://localhost:${PORT}`);
});
