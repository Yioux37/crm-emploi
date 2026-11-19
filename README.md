# CRM Carrière

**Direction des opérations & de la supply chain**  
Luxe · Horlogerie · Joaillerie · Couture  
France · Suisse · Italie

Un CRM personnel pour repérer les postes de direction, choisir les offres à examiner en premier et garder une trace de chaque candidature jusqu’à la prochaine relance.

[Prise en main](#prise-en-main) · [Installation](#installation) · [Radar V6](#radar-v6) · [Déploiement](DEPLOIEMENT_V6.md)

---

## Prise en main

| Pour… | Ouvre | Puis… |
| --- | --- | --- |
| Préparer ta journée | **Accueil** | Repère les nouvelles offres bien classées, les entretiens et les relances urgentes. |
| Examiner un poste | **Opportunités** | Filtre par pays, ouvre la fiche et vérifie l’annonce d’origine. |
| Suivre une candidature | **Opportunités** | Mets à jour le statut, ajoute le contact et tes notes, puis renseigne **Prochaine action** au format `AAAA-MM-JJ`. |
| Reprendre un échange | **Relances** | Retrouve la fiche à échéance. Après l’échange, fixe la prochaine date ou archive la candidature si le suivi est terminé. |
| Identifier une maison à contacter | **Signaux marché** | Consulte les investissements, extensions de manufactures et nominations. Un brouillon de prise de contact peut être personnalisé avant envoi. |

Le **score sur 100** sert à décider quelle fiche ouvrir en premier. Le barème accorde 35 points au niveau du poste, 25 au métier, 15 au secteur, 10 au pays, 10 à la maison et 5 à la fraîcheur de détection. Tu peux ajuster tes préférences et le seuil d’alerte dans **Préférences**. Le score mesure l’adéquation à tes critères. Les chances de recrutement restent inconnues.

[Consulter le guide d’utilisation pas à pas](GUIDE_PAPA.md)

## Installation

Depuis le dossier du projet, utilise **Python 3.11 ou 3.12**. L’installation des dépendances et la recherche de nouvelles offres nécessitent un accès Internet.

**macOS ou Linux**

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export APP_PASSWORD="remplacer-par-un-mot-de-passe-long-et-unique"
streamlit run app.py
```

<details>
<summary><strong>Windows PowerShell</strong></summary>

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$secret = Read-Host "Mot de passe du CRM" -AsSecureString
$env:APP_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password
streamlit run app.py
```

</details>

Au premier lancement, l’application crée `data/crm.sqlite3`, importe l’ancien `offres_emploi.csv` s’il est présent, puis intègre les annonces de `offres_detectees.csv`. Les statuts, priorités et notes déjà enregistrés sont conservés.

## Radar V6

La collecte privilégie les pages carrières et les flux publics configurés. Elle fonctionne sans carte bancaire ni abonnement à une API payante.

| Source | Couverture | Comment lire le résultat |
| --- | --- | --- |
| **Collecte directe** | Workday, Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee et flux RSS/Atom | Chaque maison doit disposer d’un flux ou d’un identifiant public valide. Les anciens points d’accès Workday restent à vérifier. |
| **Recherche indexée** | 109 domaines au catalogue. La sélection quotidienne annoncée comprend 12 portails prioritaires et 24 grandes maisons. | L’index peut renvoyer des liens vers Indeed, FashionJobs, jobs.ch ou d’autres portails. Sa couverture varie selon le jour et le site. |
| **Veille presse** | 18 médias consultés en rotation | Une actualité peut suggérer une prise de contact. Seule une annonce permet de vérifier qu’un poste est ouvert. |

Le radar tente jusqu’à **60 requêtes d’index par jour**. Après trois échecs consécutifs de DDGS, il interrompt la série et marque les sources restantes **« non interrogées »**. Les appels à l’ancien accès invité de LinkedIn sont désactivés.

**Lancer une recherche.** Clique sur **Rechercher de nouvelles offres** dans la barre latérale, ou lance la commande suivante depuis le projet.

```bash
python scraper.py --output offres_detectees.csv --report scan_rapport.json
```

**Comprendre un résultat vide.** Ouvre **Sources surveillées → Santé du radar** pour comparer les annonces accessibles, celles retenues après filtrage, les erreurs et les sources reportées. Le pays provient de la localisation publiée dans l’annonce. Le rapprochement des doublons conserve les liens alternatifs. Un scan vide préserve le flux existant.

> [!NOTE]
> La V6 a été testée hors réseau. Après déploiement, consulte le premier rapport GitHub Actions pour vérifier quelles sources répondent réellement.

[Voir le catalogue des principaux sites](SITES_PHARES.md)

## Hébergement et données privées

| Données | Stockage | Conservation |
| --- | --- | --- |
| Annonces, signaux et diagnostic publics | `offres_detectees.csv`, `signaux_marche.csv`, `scan_rapport.json` | Le script Mac `mettre_a_jour_mac.sh` vérifie le dépôt dans `~/crm-emploi-github` et préserve les fichiers collectés. |
| Candidatures sur ton poste | SQLite dans `data/crm.sqlite3` | Une sauvegarde par journée d’utilisation dans `data/backups/`, avec conservation des 14 derniers jours. |
| Candidatures sur Streamlit Community Cloud | PostgreSQL persistant | Les contacts, notes, statuts et relances restent en base. Prévois des sauvegardes chez l’hébergeur. |

> [!IMPORTANT]
> Le disque local de Streamlit Community Cloud peut être réinitialisé lors d’un redémarrage. Configure PostgreSQL avant d’y saisir des candidatures.

Dans **Streamlit → Settings → Secrets**, remplace ces valeurs d’exemple par tes identifiants privés. Garde-les hors du dépôt Git.

```toml
APP_PASSWORD = "remplacer-par-un-mot-de-passe-long-et-unique"
DATABASE_URL = "postgresql+psycopg://utilisateur:motdepasse@serveur:5432/crm?sslmode=require"
```

<details>
<summary><strong>Migrer depuis l’ancien CRM</strong></summary>

1. Conserve une copie privée de `offres_emploi.csv`. Il peut contenir des notes personnelles.
2. Lance l’application et vérifie que l’import unique a repris les statuts, priorités et notes.
3. Si Git suivait déjà ce fichier, exécute `git rm --cached offres_emploi.csv` puis enregistre le retrait dans un commit. Ta copie locale est conservée.
4. Si le CSV a été publié, ses anciennes versions peuvent rester dans l’historique. Restreins l’accès au dépôt et examine la nécessité de purger cet historique.

</details>

[Suivre le guide de déploiement V6](DEPLOIEMENT_V6.md)

## Collecte planifiée et alertes

**Chaque jour à 06 h 30 UTC**, `.github/workflows/scan_quotidien.yml` lance la collecte. À Paris, cela correspond à 07 h 30 en hiver et 08 h 30 en été. Les incidents figurent dans `scan_rapport.json`. Les statistiques de l’application permettent ensuite de suivre les volumes par source, pays, statut et mois.

Les alertes s’affichent dans l’application par défaut. L’envoi d’e-mails est facultatif.

<details>
<summary><strong>Activer ou prévisualiser les e-mails</strong></summary>

| Emplacement | Configuration |
| --- | --- |
| Secrets Streamlit et GitHub | `DATABASE_URL` pointant vers la même base PostgreSQL persistante |
| Secrets GitHub | `SMTP_HOST`, `SMTP_PORT` (587 ou 465), `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_TO` et, si nécessaire, `ALERT_FROM` |
| Variables GitHub Actions | `EMAIL_ALERTS_ENABLED=true` pour activer `.github/workflows/notifications.yml` |

Le workflow envoie un e-mail quotidien et un récapitulatif le lundi (UTC). Une offre à score élevé est signalée une seule fois. Une relance échue réapparaît chaque jour jusqu’à la mise à jour de sa date ou à l’archivage de la candidature.

Pour prévisualiser les messages sans les envoyer :

```bash
python notifications.py --mode daily --dry-run
python notifications.py --mode weekly --dry-run
```

</details>

## Repères techniques

<details>
<summary><strong>Fichiers du projet et vérifications</strong></summary>

| Fichiers | Rôle |
| --- | --- |
| `app.py`, `storage.py` | Interface Streamlit, accès par mot de passe, stockage privé, imports et sauvegardes |
| `scraper.py`, `sources_plus.py`, `sources_plus.json`, `search_gateway.py` | Collecte, configuration des sources et recherche indexée |
| `matching.py`, `merge_feed.py`, `scoring.py` | Localisation, rapprochement des doublons, fusion des annonces et calcul du score |
| `market_signals.py`, `link_health.py`, `notifications.py` | Veille presse, vérification manuelle d’un lien depuis sa fiche et alertes |

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py scraper.py storage.py matching.py merge_feed.py scoring.py notifications.py link_health.py
```

Les tests hors réseau couvrent notamment la migration, les doublons, la conservation des notes, les modifications concurrentes et les alertes. L’authentification dans le navigateur, les sources externes et les envois SMTP restent à valider sur le déploiement. Une réponse HTTP 403 ou 429 ne déclenche pas la suppression d’une offre.

</details>

<details>
<summary><strong>Historique des versions</strong></summary>

| Version | Évolution principale |
| --- | --- |
| **V6 · novembre 2026** | Workable et Recruitee configurables, diagnostic de collecte et arrêt après échecs répétés de l’index. |
| **V5** | Catalogue porté à 109 domaines et priorité quotidienne aux grands portails d’emploi. |
| **V4** | 75 cibles de découverte, rotation de 18 médias et guide intégré à Streamlit. |
| **V3** | Premiers signaux de marché, sources Lever, Ashby et RSS, recherche Brave facultative. |
| **V2** | Stockage privé séparé du flux public, score explicable, relances et import du CRM historique. |

</details>
