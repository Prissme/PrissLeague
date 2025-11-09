# Checklist Post-Migration

- [ ] `.env` complété avec toutes les variables des bots et de l'app web
- [ ] `python3 discord-bot/run.py` fonctionne avec Supabase connecté
- [ ] `npm run start --workspace web` démarre le serveur HTTP
- [ ] `npm run start --workspace web/discord-bot` synchronise les rôles sans erreur
- [ ] `npm run migrate:db` assure la cohérence des tables
- [ ] Les scripts utilitaires (`scripts/*.js`) s'exécutent sans erreur
- [ ] Les tests automatisés passent (`npm test --workspace web`, `python3 -m unittest`)
- [ ] Docker Compose démarre correctement (`docker compose up --build`)
- [ ] Documentation mise à jour si des personnalisations ont été ajoutées
