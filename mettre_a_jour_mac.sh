#!/bin/sh
set -eu
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR="${CRM_REPO_DIR:-$HOME/crm-emploi-github}"
if [ ! -d "$REPO_DIR/.git" ] && [ -d "$HOME/Downloads/crm-emploi-github/.git" ]; then
  REPO_DIR="$HOME/Downloads/crm-emploi-github"
fi
if [ ! -d "$REPO_DIR/.git" ]; then
  echo "Depot introuvable dans ~/crm-emploi-github. Utilise git clone d'abord." >&2
  exit 1
fi
REMOTE=$(git -C "$REPO_DIR" remote get-url origin)
case "$REMOTE" in
  git@github.com:Yioux37/crm-emploi.git|https://github.com/Yioux37/crm-emploi.git|https://github.com/Yioux37/crm-emploi) ;;
  *) echo "Arret: depot inattendu ($REMOTE). Aucune modification." >&2; exit 1 ;;
esac
if [ "$(git -C "$REPO_DIR" branch --show-current)" != main ]; then
  echo "Arret: le depot doit etre sur main." >&2
  exit 1
fi
if [ -n "$(git -C "$REPO_DIR" status --porcelain)" ]; then
  echo "Arret: modifications locales non enregistrees. Consulte git status." >&2
  exit 1
fi

git -C "$REPO_DIR" pull --ff-only origin main
rsync -av \
  --exclude='.git/' --exclude='.venv/' --exclude='node_modules/' \
  --exclude='__pycache__/' --exclude='.DS_Store' --exclude='.env*' \
  --exclude='data/' --exclude='backups/' --exclude='*.sqlite*' --exclude='*.db' \
  --exclude='secrets.toml' --exclude='offres_emploi.csv' \
  --exclude='offres_detectees.csv' --exclude='signaux_marche.csv' \
  --exclude='scan_rapport.json' --exclude='package*.json' \
  "$SOURCE_DIR/" "$REPO_DIR/"
# Stage UNIQUEMENT code/documentation: ne pas publier des contacts ni ecraser le flux existant.
git -C "$REPO_DIR" add \
  .gitignore .streamlit/config.toml \
  .github/workflows/scan_quotidien.yml .github/workflows/notifications.yml \
  app.py scraper.py storage.py matching.py merge_feed.py scoring.py \
  notifications.py link_health.py search_gateway.py sources_plus.py \
  source_catalog.py market_signals.py sources_plus.json requirements.txt \
  README.md DEPLOIEMENT_V4.md DEPLOIEMENT_V5.md DEPLOIEMENT_V6.md \
  GUIDE_PAPA.md SITES_PHARES.md mettre_a_jour_mac.sh tests/
printf '\n--- MODIFICATIONS V6 (NON publiees) ---\n'
git -C "$REPO_DIR" status --short
printf '\nSi aucun fichier prive ne figure dans la liste, copier :\n'
printf 'cd ~/crm-emploi-github\n'
printf 'git commit -m "CRM V6 - sources gratuites et diagnostic"\n'
printf 'git pull --rebase origin main\n'
printf 'git push origin main\n'
