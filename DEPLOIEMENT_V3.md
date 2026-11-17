# Mise à jour de ton CRM Streamlit Cloud depuis ton Mac

La V3 conserve l'interface, le CRM de candidatures et le fichier de données publiques de la V2. Elle ajoute la recherche spécialisée et les signaux de marché. Tu n'as pas à connecter ton GitHub à ChatGPT.

## 1. Dézipper `crm-emploi-v3.zip` dans Téléchargements

Tu dois obtenir deux dossiers côte à côte : `~/Downloads/crm-emploi-v3/` et `~/Downloads/crm-emploi-github/` (clone GitHub que tu as déjà créé).

## 2. Copier V3 dans ton clone, sans secrets ni données privées

```bash
cd ~/Downloads
rsync -av \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='data/' \
  --exclude='backups/' \
  --exclude='__pycache__/' \
  --exclude='*.sqlite*' \
  --exclude='*.db' \
  --exclude='.env*' \
  --exclude='secrets.toml' \
  --exclude='offres_emploi.csv' \
  crm-emploi-v3/ crm-emploi-github/

cd crm-emploi-github
git add -A
git status
```

**Vérifie** que les modifications concernent du code, le flux public, la documentation et éventuellement `signaux_marche.csv` ; aucun mot de passe, `.env`, `secrets.toml`, donnée personnelle ou base SQLite ne doit apparaître.

## 3. Publier

```bash
git commit -m "Etendre la veille emploi: ATS, portails et signaux marche"
git push origin main
```

Ton application `https://crm-emploi.streamlit.app/` se met normalement à jour automatiquement après un déploiement réussi de `main`. Le mot de passe `APP_PASSWORD` déjà défini dans les secrets Streamlit reste actif.

## 4. Activer et contrôler le scan quotidien

Ouvre GitHub → ton dépôt `Yioux37/crm-emploi` → **Actions** → **Veille emploi quotidienne** → **Run workflow**. Vérifie les logs. L'automatisation continue de publier `offres_detectees.csv` et `scan_rapport.json`, et ajoute maintenant `signaux_marche.csv`.

L'indexation élargie fonctionne sans clé avec DDGS, mais peut être incomplète ou limitée. Pour un moteur plus stable, tu peux créer une clé **Brave Search API** et l'ajouter à **GitHub → Settings → Secrets and variables → Actions → New repository secret**, avec le nom `BRAVE_SEARCH_API_KEY`. Ne mets jamais cette clé dans le dépôt, le terminal partagé ou la conversation. Le service peut avoir des frais selon son offre.

Le scan GitHub Actions est quotidien. Les **6 sources prioritaires** sont interrogées chaque jour, les autres sites tournent pour limiter les requêtes. La presse professionnelle est interrogée sur 4 sources tournantes par jour. Les statistiques et erreurs par source sont dans `scan_rapport.json` et la page **Statistiques** du CRM.

## 5. Adapter les sources directes

Ouvre `sources_plus.json`. Tu peux ajouter des sites publics **Lever**, **Ashby** ou des **flux RSS/Atom** en reprenant le modèle ci-dessous (n'utiliser que les vrais identifiants trouvés sur les sites officiels) :

```json
{
  "lever": [{"company":"Karl Lagerfeld","site":"karllagerfeld","region":"eu"}],
  "ashby": [{"company":"Veliu","board":"veliu"}],
  "rss": [{"company":"Nom de maison","url":"https://careers.example.com/jobs.rss"}]
}
```

L'URL `https://careers.example.com/jobs.rss` est un **exemple fictif** : ne la colle pas telle quelle dans la configuration. Teamtailor fournit parfois un flux en ajoutant `.rss` à sa page `/jobs` ; vérifier publiquement avant de l'ajouter.

## 6. Attention aux données persistantes

Avant de saisir des notes, contacts ou statuts importants sur Streamlit Cloud, vérifie que le secret `DATABASE_URL` pointe vers une base PostgreSQL persistante. Sinon les données SQLite locales du serveur risquent d'être perdues au redémarrage. La V3 ne modifie **pas** ce point de la V2.

**Important** : les signaux économiques ne sont pas des offres d'emploi. Une nomination ou une ouverture de site donne une piste de réseau, jamais la certitude qu'un poste est ouvert. Vérifie chaque article avant une prise de contact.
