#!/usr/bin/env bash
set -euo pipefail

# Migration des anciens dépôts (bot Python + app Node) vers la monorepo unifiée.
# À exécuter depuis la racine de l'ancien dépôt Python.

if [[ ! -d .git ]]; then
  echo "Ce script doit être exécuté depuis la racine du dépôt." >&2
  exit 1
fi

TARGET_DIR="prissleague-unified"

if [[ -d "$TARGET_DIR" ]]; then
  echo "Le dossier $TARGET_DIR existe déjà. Supprimez-le ou choisissez un autre emplacement." >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
mkdir -p "$TARGET_DIR/discord-bot"
mkdir -p "$TARGET_DIR/scripts"

rsync -av --exclude '.git' --exclude '__pycache__' ./ "$TARGET_DIR/discord-bot/"

cat <<'DOC' > "$TARGET_DIR/scripts/MIGRATION_NOTES.md"
# Migration vers la monorepo

## Étapes réalisées
- Copie du bot Python dans `discord-bot/`
- Copie manuelle requise de l'application web Node.js dans `web/`
- Ajout des fichiers de configuration partagés (`.env.example`, `docker-compose.yml`, etc.)

## À faire
1. Copier le répertoire de l'application web existante dans `web/`.
2. Copier le bot Node.js de synchronisation dans `web/discord-bot/`.
3. Mettre à jour `.env` avec toutes les variables listées dans `.env.example`.
4. Lancer `npm run install:all` pour installer toutes les dépendances.
5. Tester chaque service :
   - `npm run start:bot`
   - `npm run start:web`
   - `npm --workspace web/discord-bot run start`
DOC

cat <<'DOC' > "$TARGET_DIR/scripts/POST_MIGRATION_CHECKLIST.md"
# Checklist post-migration
- [ ] Les services Discord (Python & Node) démarrent sans erreur
- [ ] Les variables d'environnement sont définies pour tous les services
- [ ] La table `players` contient les colonnes attendues (`discord_id`, `solo_elo`, etc.)
- [ ] L'API `/api/leaderboard` renvoie des données correctes
- [ ] Le panneau admin enregistre correctement les matchs via `/api/matches`
- [ ] Les rôles Discord sont synchronisés via le bot Node.js
- [ ] Les scripts utilitaires fonctionnent (`scripts/migrate-auth-users.js`, etc.)
DOC

echo "Migration initiale effectuée dans $TARGET_DIR/. Terminez la copie des fichiers Node.js manuellement."
