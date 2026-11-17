# Mettre le CRM V4 sur Streamlit : 4 étapes

**Ce fichier est pour la personne qui administre l'application. Papa n'a pas besoin d'exécuter ces commandes.**

## 1. Télécharger le ZIP

Télécharge `crm-emploi-v4.zip` et décompresse-le dans les **Téléchargements** de ton Mac. Tu auras normalement `~/Downloads/crm-emploi-v4/` à côté de `~/Downloads/crm-emploi-github/` (le dépôt Git déjà cloné).

## 2. Préparer la mise à jour sans publier de données privées

Dans le Terminal :

```bash
bash ~/Downloads/crm-emploi-v4/mettre_a_jour_mac.sh
```

Le script vérifie ton dossier, récupère les dernières modifications de `main`, copie le nouveau code (sans mots de passe ni base locale) et affiche `git status`. **Il ne publie rien automatiquement.**

## 3. Publier après contrôle

Vérifie que les changements ne contiennent **aucun** `.env`, `secrets.toml`, `offres_emploi.csv`, fichier SQLite, contact ou note privée.

```bash
cd ~/Downloads/crm-emploi-github
git commit -m "CRM V4 - radar et guide simple"
git push origin main
```

Le dépôt distant est `git@github.com:Yioux37/crm-emploi.git`. Si l'application est toujours liée à `main`, Streamlit actualisera normalement https://crm-emploi.streamlit.app.

## 4. Vérifier le scan automatique

Dans GitHub : **Yioux37/crm-emploi -> Actions -> Veille emploi quotidienne -> Run workflow**.

Ensuite, regarde le résultat de l'action, les journaux et les trois fichiers publics `offres_detectees.csv`, `signaux_marche.csv` et `scan_rapport.json`.

Le scan est réglé sur **14 cibles d'offres par jour**, dont 6 prioritaires, et **5 médias par jour**. Les autres sources sont interrogées progressivement, sur plusieurs jours. Une source ajoutée à la liste n'est pas une garantie d'offre ni de connexion réussie : vérifie les logs du premier scan.

### Réglages et secrets

**Streamlit Community Cloud :** dans l'application, clique **Manage app -> Settings -> Secrets**. Configure `APP_PASSWORD` (un secret fort) et `DATABASE_URL` (une vraie base PostgreSQL avec stockage persistant). Une simple base SQLite dans Streamlit Cloud peut être perdue au redéploiement.

**GitHub Actions :** la clé `BRAVE_SEARCH_API_KEY` est facultative. Elle permet d'utiliser l'API Brave Search plutôt que le moteur DDGS. Ajoute-la dans **Settings -> Secrets and variables -> Actions** si tu choisis ce service (coût possible). Les e-mails nécessitent une configuration supplémentaire, décrite dans le README.

### Confidentialité

`offres_detectees.csv`, `signaux_marche.csv` et le rapport contiennent uniquement la veille publique. **Ne publie jamais** les contacts, notes, statuts personnels, bases locales ou identifiants.

L'ancien `offres_emploi.csv` a peut-être déjà été publié dans l'historique GitHub. Le retirer de la version courante n'efface pas cet historique : traite-le s'il contient des informations privées.

Les sites protégés, les API à accès restreint et les réseaux sociaux ne sont pas à contourner. Les recherches indexées ne garantissent pas l'exhaustivité ni la fraîcheur des liens.
