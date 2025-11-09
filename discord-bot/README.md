# Bot Discord Matchmaking (Python)

Ce dossier contient le bot historique de matchmaking solo 3v3. Il repose sur `discord.py`, `psycopg2` et une base Supabase partagée.

## Installation
```bash
pip install -r requirements.txt
```

## Configuration
Les variables nécessaires sont décrites dans la racine `.env.example` :
- `DISCORD_TOKEN`
- `DATABASE_URL`
- `MATCH_CHANNEL_ID`
- `LOG_CHANNEL_ID`
- `PING_ROLE_ID`

Optionnel : ajustez la taille de file (`QUEUE_TARGET_SIZE`) via la variable d'environnement.

## Lancer le bot
```bash
python3 run.py
```
`run.py` charge automatiquement `.env` si présent, vérifie les variables obligatoires puis lance `main.py`.

## Migrations
`smart_migration.py` assure la cohérence de la table `players` et peut créer la table `solo_matches`.
```bash
python3 smart_migration.py
```

## Scripts supplémentaires
Des scripts utilitaires (sauvegardes, réparations) sont disponibles dans `scripts/`. Utilisez-les avec précaution après avoir réalisé une sauvegarde.

## Déploiement Heroku / Koyeb
Le fichier `Procfile` contient la commande recommandée :
```
worker: python3 run.py
```
Assurez-vous d'ajouter les variables d'environnement nécessaires dans le dashboard de votre fournisseur.
