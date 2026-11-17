#!/bin/sh
set -eu
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR="$HOME/Downloads/crm-emploi-github"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "Depot GitHub introuvable: $REPO_DIR" >&2
  echo "Le clone local doit se nommer crm-emploi-github dans Downloads." >&2
  exit 1
fi
if [ "$(git -C "$REPO_DIR" branch --show-current)" != "main" ]; then
  echo "La branche locale doit etre main. Aucun fichier modifie." >&2
  exit 1
fi
if [ -n "$(git -C "$REPO_DIR" status --porcelain)" ]; then
  echo "Le depot contient deja des changements. Verifie git status avant de continuer." >&2
  exit 1
fi

git -C "$REPO_DIR" pull --ff-only origin main
rsync -av \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='node_modules/' \
  --exclude='__pycache__/' \
  --exclude='.DS_Store' \
  --exclude='data/' \
  --exclude='backups/' \
  --exclude='*.sqlite*' \
  --exclude='*.db' \
  --exclude='.env*' \
  --exclude='secrets.toml' \
  --exclude='offres_emploi.csv' \
  --exclude='package*.json' \
  "$SOURCE_DIR/" "$REPO_DIR/"

# Stage known source files only. Private files are never automatically staged.
git -C "$REPO_DIR" rm --cached --ignore-unmatch offres_emploi.csv
git -C "$REPO_DIR" rm --ignore-unmatch DEPLOIEMENT_V3.md
git -C "$REPO_DIR" add \
  .gitignore .streamlit/config.toml \
  .github/workflows/scan_quotidien.yml .github/workflows/notifications.yml \
  app.py scraper.py storage.py matching.py merge_feed.py scoring.py \
  notifications.py link_health.py search_gateway.py sources_plus.py \
  source_catalog.py market_signals.py sources_plus.json requirements.txt \
  offres_detectees.csv signaux_marche.csv \
  README.md DEPLOIEMENT_V4.md GUIDE_PAPA.md mettre_a_jour_mac.sh tests/

printf '\n--- MODIFICATIONS PRETES (non publiees) ---\n'
git -C "$REPO_DIR" status --short
printf '\nVerifier qu aucun fichier prive ne figure dans cette liste.\n'
printf 'Ensuite, dans un Terminal: \n'
printf 'cd ~/Downloads/crm-emploi-github\n'
printf 'git commit -m "CRM V4 - radar elargi et guide simple"\n'
printf 'git push origin main\n'
