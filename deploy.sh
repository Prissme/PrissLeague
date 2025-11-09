#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------------
# Déploiement automatisé pour PrissLeague Unified
# -------------------------------------------------------------
# Usage:
#   ./deploy.sh [environment]
# Environnements supportés : local, koyeb, railway, render
# -------------------------------------------------------------

ENVIRONMENT="${1:-local}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; }

load_env() {
  local env_file="$PROJECT_ROOT/.env"
  if [[ -f "$env_file" ]]; then
    info "Chargement des variables depuis .env"
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  else
    info "Aucun fichier .env détecté. Utilisation des variables existantes."
  fi
}

check_prerequisites() {
  command -v npm >/dev/null || { error "npm est requis"; exit 1; }
  command -v python3 >/dev/null || { error "python3 est requis"; exit 1; }
}

build_local() {
  info "Installation des dépendances Node (workspaces)"
  npm install --workspaces --include-workspace-root

  info "Installation des dépendances Python"
  pip install -r "$PROJECT_ROOT/discord-bot/requirements.txt"

  info "Construction des assets statiques"
  npm run build --workspace web || info "Aucun build frontend explicite."
}

case "$ENVIRONMENT" in
  local)
    check_prerequisites
    load_env
    build_local
    info "Démarrage via docker compose"
    docker compose up --build -d
    ;;
  koyeb)
    load_env
    info "Déploiement Koyeb : push Git et déclenchement via dashboard."
    info "Configurer les services :" \
      "\n - Bot Python : buildpack Python, commande 'python3 run.py'" \
      "\n - App Web : buildpack Node 20, commande 'npm run start --prefix web'" \
      "\n - Bot Sync : buildpack Node 20, commande 'npm run start --prefix web/discord-bot'"
    ;;
  railway|render)
    load_env
    info "Déploiement $ENVIRONMENT :" \
      "\n - Service 1 : dossier discord-bot" \
      "\n - Service 2 : dossier web" \
      "\n - Service 3 (optionnel) : dossier web/discord-bot"
    info "Définir les variables d'environnement depuis .env.example"
    ;;
  *)
    error "Environnement inconnu : $ENVIRONMENT"
    exit 1
    ;;
esac
