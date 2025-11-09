# PrissLeague Unified Platform

PrissLeague Unified regroupe le bot Discord de matchmaking en Python, l'application web de classement en Node.js et le bot de synchronisation de rôles. Cette monorepo facilite l'installation, le déploiement et la maintenance d'un seul environnement Supabase partagé.

## Sommaire
- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation rapide](#installation-rapide)
- [Configuration de l'environnement](#configuration-de-lenvironnement)
- [Commandes npm](#commandes-npm)
- [Services](#services)
- [Déploiement](#déploiement)
- [Contribution](#contribution)

## Architecture
```
prissleague-unified/
├── discord-bot/             # Bot Discord matchmaking (Python 3.11)
├── web/                     # Application web + API REST + bot Node.js
├── scripts/                 # Scripts utilitaires (Supabase, migrations, nettoyage)
├── docker-compose.yml       # Lancement orchestré en local
├── deploy.sh                # Script de déploiement générique
├── .env.example             # Modèle de variables d'environnement
└── package.json             # Gestion des workspaces npm
```

- **Base de données** : Supabase (PostgreSQL) partagée par tous les services
- **File d'attente** : bot Python `discord.py`
- **Classement & Admin** : serveur HTTP Node.js 20 + frontend statique
- **Synchronisation des rôles** : bot Node.js utilisant Discord.js v14

## Prérequis
- Python 3.11+
- Node.js 20+
- npm 9+ ou pnpm 8+
- Accès à une instance Supabase (URL + clés anon et service role)
- Tokens Discord pour les deux bots

## Installation rapide
```bash
# 1. Cloner le dépôt
 git clone https://github.com/your-org/prissleague-unified.git
 cd prissleague-unified

# 2. Copier et remplir la configuration
 cp .env.example .env

# 3. Installer les dépendances Node.js
 npm install --workspaces --include-workspace-root

# 4. Installer les dépendances Python
 pip install -r discord-bot/requirements.txt
```

## Configuration de l'environnement
Toutes les variables requises sont décrites dans `.env.example`. Les tokens Discord et clés Supabase ne doivent **jamais** être commités. Pour la production, renseignez les variables dans vos fournisseurs (Koyeb, Railway, Render, etc.).

## Commandes npm
Les scripts globaux sont définis dans `package.json` à la racine :

| Script | Description |
| ------ | ----------- |
| `npm run install:all` | Installe toutes les dépendances Node et Python |
| `npm run start:web` | Lance le serveur web `web/server.js` |
| `npm run start:bot` | Lance le bot Python (`discord-bot/run.py`) |
| `npm run start:all` | Lance le bot Python et l'app web en parallèle |
| `npm run dev` | Mode développement (nodemon + rechargement live) |
| `npm run migrate:db` | Exécute le script `smart_migration.py` pour la base |
| `npm run lint` | Agrège les linters des workspaces |

## Services
- **discord-bot/** : contient le code existant du bot matchmaking, la configuration Heroku/Koyeb (`Procfile`), la documentation dédiée et un Dockerfile pour les déploiements conteneurisés.
- **web/** : serveur Node.js minimaliste avec API REST, frontend statique et bot de synchronisation de rôles. Utilise Supabase pour lire/écrire dans la table `players` et enregistrer des matchs.
- **scripts/** : scripts utilitaires écrits en Node.js ou Bash pour gérer des migrations Supabase, nettoyer des joueurs inconnus et restaurer des display names.

## Déploiement
Les environnements cibles (Heroku, Railway, Koyeb) peuvent utiliser `deploy.sh` comme point de départ. Le fichier `docker-compose.yml` démarre :
- le bot Python,
- l'application web Node.js,
- le bot de synchronisation des rôles.

Adaptez les profils `Procfile` ou les commandes `Dockerfile` selon votre fournisseur.

### Koyeb / Railway / Render
1. Renseignez toutes les variables d'environnement via le dashboard fournisseur.
2. Créez un service pour le bot Python (commande `python3 run.py` dans `discord-bot`).
3. Créez un service pour l'app web (`npm run start --prefix web`).
4. (Optionnel) Créez un service séparé pour le bot Node.js (`npm run start --prefix web/discord-bot`).

### Docker Compose
```bash
docker compose up --build
```
Cela construit les deux images et lance les containers avec les variables de `.env`.

## Contribution
Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les conventions de commit, les branches et les revues de code.
