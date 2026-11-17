# CRM Carrière — Direction Opérations & Supply Chain (v2)

Un CRM **personnel** de recherche d'emploi pour les secteurs luxe, horlogerie, joaillerie et couture en France, Suisse et Italie. L'application associe la collecte d'offres à un **suivi des candidatures** (statuts, notes privées, contacts, prochaines actions, historique).

## Nouveautés de la v2

- **Stockage séparé :** les annonces publiques sont dans `offres_detectees.csv` ; les contacts, dates de relance et notes sont dans une base **SQLite locale** ou **PostgreSQL persistante**. Un scan ne peut pas écraser les données privées du CRM.
- **Import de l'ancien CRM :** `offres_emploi.csv` est importé **une seule fois**, avec statuts/priorités/notes existants. Le fichier est ensuite ignoré par Git.
- **Doublons :** rapprochement d'URL LinkedIn, d'intitulé et de maison, y compris certains couples groupe/maison avec identifiant de poste. Liens alternatifs conservés. Deux postes génériques dans différentes maisons restent distincts.
- **Localisation :** les filtres de recherche LinkedIn et domaines de sites ne déterminent plus le pays du poste ; c'est la localisation annoncée qui compte. Une localisation ambiguë n'est pas classée au hasard.
- **Score sur 100 explicable :** niveau du poste (35 points), métier (25), secteur (15), pays (10), maison (10), fraîcheur de détection (5). Les préférences sont modifiables.
- **Relances :** date de prochaine action, page de relances à traiter, historique des modifications, édition en tableau et en fiche.
- **Tableau de bord :** nouvelles offres, scores élevés, relances et entretiens ; statistiques par source, pays, statut et mois.
- **Alertes :** alertes **dans l'application** par défaut ; e-mails SMTP en option, avec garde anti-doublon et rapports hebdomadaires.
- **Sécurité :** accès par mot de passe obligatoire, sauvegarde SQLite locale automatique (14 jours), vérification prudente des liens (403/429 ne supprime pas une offre), contrôle des écrasements concurrents.

> Le score est une **priorisation heuristique**, **pas** une estimation des chances de recrutement. Les liens sont vérifiables manuellement dans chaque fiche, pas contrôlés automatiquement en masse.

## Démarrage en local

Prérequis : **Python 3.11 ou 3.12**, accès Internet pour installer les dépendances et interroger les sources externes.

```bash
# Depuis le dossier du projet
python -m venv .venv
source .venv/bin/activate           # Windows : .venv\Scripts\activate
pip install -r requirements.txt

# Choisir un vrai mot de passe privé (ne pas le mettre dans Git)
export APP_PASSWORD="un-mot-de-passe-long-et-unique"
streamlit run app.py
```

Sous Windows PowerShell : `$env:APP_PASSWORD="un-mot-de-passe-long-et-unique"` à la place de `export`.

Au premier lancement :

1. La base locale est créée dans `data/crm.sqlite3`.
2. Le fichier historique `offres_emploi.csv` est importé avec ses champs CRM, s'il est présent.
3. Les nouvelles offres publiques de `offres_detectees.csv` sont ajoutées, sans modifier les statuts et notes déjà enregistrés.
4. Les sauvegardes SQLite sont placées dans `data/backups/`. Le dernier état de chaque journée d'utilisation remplace la sauvegarde du jour ; les 14 derniers jours sont conservés.

Pour lancer un scan manuel depuis le terminal :

```bash
python scraper.py --output offres_detectees.csv --report scan_rapport.json
```

Ou utiliser le bouton **Rechercher de nouvelles offres** dans la barre latérale. Les scans utilisent LinkedIn public, les ATS des maisons et la recherche web via `ddgs`, sans clé RapidAPI. Les sites tiers peuvent bloquer ou changer leur HTML/API ; un scan en panne **ne supprime aucune offre** et remonte une erreur. Le fonctionnement des sources externes doit être vérifié sur le réseau du déploiement.

## Hébergement et préservation des données — important

**SQLite convient au poste local ou à un serveur doté d'un disque persistant.** Le disque local de Streamlit Community Cloud peut être réinitialisé lors des redémarrages/déploiements. **N'utilise pas SQLite seul sur Streamlit Cloud pour des notes/candidatures importantes.**

Pour un hébergement Cloud, configure une **base PostgreSQL persistante** (par exemple chez ton hébergeur ou un service de base de données) et ajoute les secrets de l'application dans Streamlit > Settings > Secrets :

```toml
APP_PASSWORD = "ton-secret-long"
DATABASE_URL = "postgresql+psycopg://utilisateur:motdepasse@serveur:5432/crm?sslmode=require"
```

Cette configuration est **un exemple** : remplace les valeurs par les identifiants de ta base. Utilise TLS, une base privée, des sauvegardes gérées par l'hébergeur et idéalement un contrôle d'accès externe (SSO/OAuth) si l'application est exposée à Internet. Le mot de passe applicatif est une barrière simple d'accès, pas une gestion multi-utilisateurs.

### Migration depuis l'ancien dépôt GitHub

L'ancien `offres_emploi.csv` mélangeait les informations publiques et privées. La v2 le conserve **localement pour l'import uniquement** ; les données personnelles ne doivent plus être publiées ou committées.

- Conserve une copie privée du CSV avant toute mise à jour.
- Si le fichier était **déjà suivi par Git** : après import, exécute `git rm --cached offres_emploi.csv` (ne supprime pas ta copie locale), puis committe le retrait. `.gitignore` seul ne dépublie pas un fichier déjà suivi.
- Si des informations sensibles ont déjà été poussées dans un dépôt public, leur présence peut rester dans **l'historique Git** : passe le dépôt en privé et examine la nécessité de purger l'historique.
- `offres_detectees.csv` est, lui, **public et sans colonnes CRM** : le workflow GitHub ne modifie **que** ce fichier et `scan_rapport.json`.

## GitHub Actions

`.github/workflows/scan_quotidien.yml` lance la collecte quotidienne à 06:30 **UTC** et committe le flux public. Le CRM privé reste en base ; il n'y a **plus de synchronisation GitHub des statuts/notes**. Un incident de collecte apparaît comme échec du workflow et le flux existant reste intact. L'heure à Paris varie avec le passage heure d'été/hiver.

Pour utiliser les e-mails facultatifs dans `.github/workflows/notifications.yml`, il faut :

1. Une **base PostgreSQL persistante commune à l'app et au workflow** (`DATABASE_URL` dans les Secrets GitHub et les Secrets Streamlit).
2. Les Secrets GitHub `SMTP_HOST`, `SMTP_PORT` (587 ou 465), `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_TO` et éventuellement `ALERT_FROM`.
3. La variable de dépôt GitHub Actions **`EMAIL_ALERTS_ENABLED=true`**. Par défaut, le job est désactivé.

Ce workflow envoie un e-mail quotidien et un récapitulatif hebdomadaire le lundi UTC. Les relances sont répétées quotidiennement tant que leur date n'a pas été mise à jour ; une nouvelle offre à score élevé n'est signalée qu'une fois. Le contrôle SMTP et les envois n'ont pas été testés ici avec des identifiants réels.

Pour prévisualiser les e-mails en local **sans envoyer** :

```bash
python notifications.py --mode daily --dry-run
python notifications.py --mode weekly --dry-run
```

## Guide d'utilisation

| Écran | À quoi il sert |
| --- | --- |
| **Accueil** | Voir les opportunités prioritaires, les nouvelles annonces, les relances urgentes et les entretiens. |
| **Opportunités** | Filtrer les offres, changer directement statut/priorité en tableau, gérer la fiche, vérifier le lien et consulter l'historique. |
| **Relances** | Voir les prochaines actions à traiter ou à venir. |
| **Statistiques** | Visualiser les volumes par statut, source principale, pays et mois. |
| **Préférences** | Adapter le scoring et son seuil d'alerte, exporter un backup CSV, se déconnecter. |

Pour une relance, renseigne **Prochaine action (AAAA-MM-JJ)** dans la fiche. Pour la clore, reporte la date ou passe l'offre à un statut archivé. L'application n'invente pas un historique de candidatures passées : les métriques d'entonnoir restent limitées tant que chaque réponse n'est pas tracée.

## Structure du projet

```text
app.py                        Interface Streamlit et contrôles d'accès
storage.py                    Base de données, import historique, actions, backups
matching.py                   Pays, URL, rapprochement des doublons
merge_feed.py                 Fusion du flux public avec sources alternatives
scoring.py                    Priorisation et explications du score
scraper.py                    Collecte LinkedIn/ATS/web
link_health.py                Vérification prudente d'un lien
notifications.py              Alertes SMTP facultatives + aperçu CLI
offres_detectees.csv          Annonces publiques (committables)
offres_emploi.csv             CSV v1 privé, à importer une fois (ignoré par Git)
tests/test_crm.py             Tests automatiques hors réseau
```

## Vérifications et limites

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py scraper.py storage.py matching.py merge_feed.py scoring.py notifications.py link_health.py
```

- Les tests unitaires n'ont besoin d'aucun réseau et couvrent pays, doublons, migration, conservation des notes, modifications concurrentes, score, dates et alertes.
- Les scans réels, l'authentification via navigateur Streamlit et l'envoi d'e-mails nécessitent un environnement correctement configuré. Ils doivent être validés après déploiement.
- Aucun contrôle de l'existence réelle du poste n'est garanti par la simple présence d'un lien ; les pages LinkedIn peuvent retourner des codes 403/429 même si le poste existe toujours.
- Le rapprochement groupe/maison est conservateur : il peut rester quelques doublons difficiles à distinguer sans identifiant commun.
