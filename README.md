# CRM Carrière — Direction Opérations & Supply Chain (v6)

Un CRM **personnel** de recherche d'emploi pour les secteurs luxe, horlogerie, joaillerie et couture en France, Suisse et Italie. L'application associe la collecte d'offres à un **suivi des candidatures** (statuts, notes privées, contacts, prochaines actions, historique).

## V6 — sources gratuites et radar qui explique ses résultats (novembre 2026)

**Aucune carte bancaire et aucun abonnement/API payante requis.** La collecte s'appuie sur les pages d'emploi publiques des ATS déjà configurés, sur deux formats configurables supplémentaires (**Workable et Recruitee**) et sur un index web public gratuit, lorsque celui-ci répond. Tous les identifiants d'entreprises doivent être vérifiés : un connecteur pris en charge n'est pas nécessairement connecté à une maison réelle.

- **109 domaines restent dans le catalogue de découverte**, dont 12 prioritaires. Jusqu'à **30 requêtes d'index** sont tentées par jour, mais dès que DDGS échoue 3 fois de suite, le moteur arrête la série. Les sites restants sont signalés **« non interrogés »**, et non **« sans offres »**.
- Les recherches d'index utilisent des expressions courtes plutôt que des filtres OR géants. Cela améliore la tolérance, **sans garantir** des résultats depuis Indeed, LinkedIn ou les autres jobboards protégés.
- **Collecte directe en priorité** sur Workday (endpoints historiques à valider), Greenhouse, Lever, Ashby, SmartRecruiters et RSS/Atom ; les API publiques Workable et Recruitee sont ajoutées, **à activer avec des identifiants connus**. Les appels non autorisés à l'endpoint invité LinkedIn et les anciennes recherches web complexes **ne sont plus lancés**.
- Les étapes **Sources surveillées → Santé du radar** et **Statistiques** affichent les annonces accessibles, celles conservées après filtrage, les erreurs et les sources reportées. Un scan avec 0 offre ne vide jamais le flux existant.
- **Déploiement sûr** : `mettre_a_jour_mac.sh` utilise `~/crm-emploi-github`, vérifie le dépôt, et préserve `offres_detectees.csv`, `signaux_marche.csv`, `scan_rapport.json` collectés par GitHub Actions.

Voir **`DEPLOIEMENT_V6.md`**. Le radar a été testé **hors réseau seulement** : l'état réel des sources sera connu après le prochain scan GitHub. Les candidatures privées nécessitent toujours PostgreSQL persistant sur Streamlit Cloud.

---

## Nouveautés V5 — grands portails d'emploi

Le catalogue comprend maintenant **109 cibles de découverte indexée** (contre 75 en V4) : les incontournables Indeed, Welcome to the Jungle, HelloWork, Cadremploi, APEC, FashionJobs et jobs.ch sont désormais en priorité quotidienne, ainsi que les trois versions nationales d'Indeed. La V5 interrogeait initialement 20 domaines par scan ; la V6 en prévoit jusqu'à 30, mais peut s'arrêter en cas de panne du moteur. Un site dans le catalogue est une piste de recherche, **pas un connecteur direct qui garantit une annonce**. Les principaux nouveaux sites sont Meteojob, Monster FR, Figaro Emploi, Jobijoba, Jobrapido, Jooble, Job-Room suisse, Jobtic, Jobeo, Trovolavoro, Cliclavoro, les agences Adecco/Manpower et le portail EURES. Voir `SITES_PHARES.md`.

## Nouveautés V4 - radar élargi et mode d'emploi simple

- **75 cibles de recherche d'offres**, dont 6 prioritaires chaque jour : luxe, horlogerie, cadres, maisons, cabinets et ATS. Les autres tournent sur plusieurs jours via index public. La présence dans la liste **ne prouve pas** une collecte réussie ou autorisée en direct.
- **18 médias** pour les signaux de marché, interrogés en rotation. Ils donnent des pistes de prospection, jamais des postes vacants confirmés.
- **API publiques configurables** pour Lever, Ashby, Greenhouse, SmartRecruiters et flux RSS/Atom de sites carrières, uniquement si les identifiants des tableaux publics sont corrects. Les sources Workday et les autres connecteurs V3 sont conservés.
- **Guide simple intégré dans Streamlit** : chaque matin, comment lire une offre, utiliser le score, noter une candidature et suivre une relance.
- **Page Sources surveillées** : liste des sources par famille, différence entre recherche indexée / connexion directe / presse, limites connues.
- **Pistes de prise de contact** pour les actualités d'entreprise, avec brouillon personnalisable non envoyé automatiquement.

Pour transmettre le mode d'emploi à papa, ouvre [`GUIDE_PAPA.md`](GUIDE_PAPA.md). Pour mettre à jour l'app, ouvre [`DEPLOIEMENT_V5.md`](DEPLOIEMENT_V5.md).

---

## Historique : V3 — Force de frappe renforcée (novembre 2026)

La V3 apporte **quatre nouvelles voies** sans toucher aux notes et candidatures privées de la V2 :

1. **Lever + Ashby + RSS/Teamtailor** : lecture d'annonces publiques depuis les interfaces autorisées et explicitement configurées dans `sources_plus.json`. Deux identifiants historiques servent d'exemples (à revalider) ; tu peux en ajouter d'autres au fil de la veille.
2. **24 sites initialement explorés** via leurs liens indexés : portails spécialisés luxe (FashionJobs), emploi cadres (APEC, Cadremploi, jobs.ch, jobup.ch, JobScout24, Welcome to the Jungle), cabinets de recrutement (Michael Page, Robert Walters, Hays, Morgan Philips, Luxe Talent), et offres d'autres ATS. Le scan explorait ces cibles en rotation avant les extensions V4 et V5 ; un index peut ne pas retourner de résultat.
3. **Signaux marché** : articles publics d'investissement, extension de manufactures, nominations et acquisitions chez les maisons ciblées ; visibles dans la page dédiée **Signaux marché**. Ce ne sont **pas** des postes ouverts.
4. **Recherche Brave facultative** : si `BRAVE_SEARCH_API_KEY` est enregistré dans les Secrets GitHub, les recherches indexées et la veille presse passent par l'API Brave, sinon par `ddgs`. Aucune clé n'est nécessaire pour les flux ATS publics.

Dans la V5, Indeed (FR/CH/IT), Welcome to the Jungle, Cadremploi et HelloWork passent **en priorité quotidienne via recherche indexée**. Il ne s'agit pas d'un accès direct à leurs sites ni d'une garantie de résultat. Consulte les diagnostics de scan pour vérifier les retours et les éventuelles limitations.

Le scan conserve le filtrage France/Suisse/Italie, le niveau direction et le métier opérations/supply chain, la déduplication intersources et le scoring existants. Les **pays ne sont jamais devinés depuis les domaines des sites**.

### Limites et bonnes pratiques

- Il n'existe pas d'accès légal et gratuit universel à toutes les offres. Les sites sans flux ouvert sont seulement repérés via les liens indexés, et tous les résultats ne sont pas forcément indexés ou actuels.
- Les identifiants de tableaux et URLs d'API sont spécifiques à chaque entreprise. Ne pas deviner des endpoints ni contourner login, CAPTCHA ou blocage. Respecter les conditions et les limites de requêtes de chaque site.
- LinkedIn interdit le scraping automatisé non autorisé ; la V3 **n'étend pas** son ancien collecteur LinkedIn. Un remplacement conforme par alertes/fournisseurs autorisés est recommandé avant d'industrialiser le scan.
- L'API Offres d'emploi de France Travail n'est actuellement pas en libre distribution ; demander l'accès via France Travail si nécessaire plutôt que de tenter de la contourner.
- **Aucun scan des sources externes n'a été exécuté dans l'environnement de livraison** ; les nouveaux parseurs sont testés hors réseau. Contrôler la première exécution dans GitHub Actions.

Lis [`DEPLOIEMENT_V6.md`](DEPLOIEMENT_V6.md) pour remplacer l'ancienne version sur GitHub puis déployer dans Streamlit Cloud sans exposer des secrets.

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

Ou utiliser le bouton **Rechercher de nouvelles offres** dans la barre latérale. Les scans V6 utilisent les ATS publics configurés, les flux RSS et la recherche web via `ddgs`. Les collecteurs LinkedIn invités et la recherche historique complexe ne sont plus exécutés. Les sites tiers peuvent bloquer ou changer leurs API ; le diagnostic l'indique, et un scan sans résultat **ne supprime aucune offre**. Le fonctionnement des sources externes doit être vérifié sur le réseau du déploiement.

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

`.github/workflows/scan_quotidien.yml` lance la collecte quotidienne à 06:30 **UTC** et committe le flux public. Le CRM privé reste en base ; il n'y a **plus de synchronisation GitHub des statuts/notes**. Un incident de collecte apparaît dans `scan_rapport.json`, et le workflow émet un avertissement. Le flux existant reste intact même avec 0 offre. L'heure à Paris varie avec le passage heure d'été/hiver.

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
scraper.py                    Collecte LinkedIn historique/ATS/web + intégration V3
sources_plus.py               Lever, Ashby, RSS, index spécialisé
sources_plus.json             Maisons et flux ATS additionnels (sans secrets)
search_gateway.py             Brave Search API facultative ou DDGS
market_signals.py             Signaux économiques séparés des annonces
signaux_marche.csv             Signaux publics séparés du CRM
DEPLOIEMENT_V3.md             Guide de publication GitHub + Streamlit
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
