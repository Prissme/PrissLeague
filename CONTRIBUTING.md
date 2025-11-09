# Contribuer à PrissLeague Unified

Merci de votre intérêt ! Ce guide couvre le workflow pour proposer des changements.

## Préparer votre environnement
1. Forkez le dépôt et clonez votre fork.
2. Installez les dépendances :
   ```bash
   npm run install:all
   ```
3. Copiez `.env.example` vers `.env` et remplissez les valeurs nécessaires.

## Convention de branches
- `main` : toujours déployable.
- `develop` : intégration continue (optionnel).
- Préfixes recommandés pour les branches :
  - `feat/` pour les nouvelles fonctionnalités
  - `fix/` pour les correctifs
  - `chore/` pour la maintenance
  - `docs/` pour la documentation

## Style de code
- Python : suivez `black` et `isort`. Linter automatique :
  ```bash
  black discord-bot
  isort discord-bot
  ```
- JavaScript : respectez ESLint (configuration dans `web/.eslintrc.*`).

## Tests
- Bot Python :
  ```bash
  python3 -m unittest
  ```
- Application web :
  ```bash
  npm test --workspace web
  ```

## Commits
- Utilisez des messages explicites : `feat(web): ajout du classement top 50`.
- Un seul sujet par commit.
- Ajoutez des références d'issue lorsque pertinent.

## Pull Requests
- Décrivez les changements et leur impact.
- Listez les tests effectués.
- Ajoutez des captures d'écran pour les modifications UI.

Merci de contribuer à l'écosystème PrissLeague !
