# Application Web & API PrissLeague

Cette application Node.js fournit :
- une API REST pour enregistrer des matchs et récupérer le classement,
- une interface web statique affichant le top 50,
- un point d'entrée commun pour héberger un panel admin.

## Installation
```bash
npm install
```

## Scripts
| Commande | Description |
| -------- | ----------- |
| `npm start` | Lance le serveur HTTP vanilla Node.js |
| `npm run dev` | Démarre nodemon avec rechargement automatique |
| `npm run lint` | Exécute ESLint sur le code du dossier |
| `npm test` | Utilise l'exécuteur `node --test` |

## API
- `GET /api/health` : statut du service.
- `GET /api/leaderboard` : renvoie `{ players: [...] }` trié par ELO.
- `POST /api/matches` : insère un match (`x-admin-id` doit être autorisé).
- `GET /api/player/:discord_id` : détail d'un joueur.

Le Supabase Service Role Key est requis pour les routes d'écriture.

## Sécurité
- Ne jamais exposer `SUPABASE_SERVICE_ROLE_KEY` côté client.
- Utiliser des passerelles d'authentification (OAuth Discord) pour récupérer l'`adminId` envoyé dans l'en-tête `x-admin-id`.

## Déploiement
- **Koyeb / Railway** : commande `npm start`.
- **Docker** : voir `web/Dockerfile`.
- **Vercel** : non recommandé (serverless) car l'app utilise un serveur HTTP long-lived.
