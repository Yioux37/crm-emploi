# CRM Emploi V6 — installation sans carte bancaire

## Ce qui change

- Aucune carte bancaire, aucun compte Brave, aucune clé payante n'est nécessaire.
- Les collectes directes sur ATS publics (Greenhouse, Lever, Ashby, SmartRecruiters ; Workday historique) restent disponibles sans authentification. Deux connecteurs **configurables** supplémentaires : Workable et Recruitee. Ils restent inactifs tant qu'une entreprise et son identifiant vérifié ne sont pas ajoutés dans `sources_plus.json`.
- Les 109 **domaines de découverte** du catalogue restent référencés. La recherche indexée gratuite essaie jusqu'à 30 domaines par scan, avec des requêtes plus courtes. Si le moteur DDGS échoue 3 fois d'affilée, il arrête les requêtes plutôt que de masquer la panne.
- Les collectes automatiques de l'endpoint invité LinkedIn et les anciennes requêtes complexes sont désactivées par défaut. LinkedIn, Indeed, Welcome to the Jungle restent consultables manuellement et, lorsque l'index le permet, découvrables via des liens publics. Une cible référencée n'est pas une garantie de résultats.
- `scan_rapport.json` distingue les résultats publics lus, les offres retenues, les sources en erreur / non interrogées et les nouvelles annonces.
- Un scan dégradé conserve `offres_detectees.csv` existant ; jamais les données personnelles (stockées séparément).

## Installer sur le Mac

Télécharger et décompresser `crm-emploi-v6.zip` dans Téléchargements, puis dans le terminal :

```bash
bash ~/Downloads/crm-emploi-v6/mettre_a_jour_mac.sh
```

Le script retrouve automatiquement ton dépôt cloné dans `~/crm-emploi-github` (ou `~/Downloads/crm-emploi-github`), vérifie l'adresse GitHub et prépare **uniquement le code**. Il n'écrase pas les fichiers de flux public mis à jour par GitHub Actions et n'ajoute pas de base personnelle.

Ensuite, après vérification de `git status` :

```bash
cd ~/crm-emploi-github
git commit -m "CRM V6 - sources gratuites et diagnostic"
git pull --rebase origin main
git push origin main
```

Si le dépôt est dans Téléchargements, adapte seulement le `cd`. Si la synchronisation affiche un conflit, **n'utilise pas `--force`** et arrête-toi pour traiter le conflit.

## Tester le radar

1. Ouvrir : https://github.com/Yioux37/crm-emploi/actions/workflows/scan_quotidien.yml
2. **Run workflow** sur `main`, puis ouvrir la nouvelle exécution.
3. Consulter le journal de l'étape **Mettre à jour uniquement les annonces publiques**.
4. Ouvrir le CRM Streamlit > **Sources surveillées** > **Santé du radar**. Alternativement, le rapport `scan_rapport.json` est publié par le workflow et joint en artifact `diagnostic-radar`.
5. Regarder **Résultats publics**, **Offres retenues**, **Nouvelles offres**, **Sources en erreur**. Ne pas confondre `vide` (source accessible sans résultat) et `erreur` (source indisponible).

## Ajouter des sources directes

Dans `sources_plus.json`, renseigner uniquement des identifiants de pages carrières **publics et vérifiés** :

```json
{
  "workable": [{"company": "Entreprise verifiee", "account": "identifiant-verifie"}],
  "recruitee": [{"company": "Entreprise verifiee", "account": "identifiant-verifie"}]
}
```

Ce bloc est un **exemple partiel**, ne remplace pas le fichier JSON complet. Ne jamais inventer d'identifiant pour une maison, ni interroger des pages privées. Les identifiants V5 existants doivent également être vérifiés au fil des tests réels.

## Données privées et hébergement

Le scan GitHub ne doit publier que les annonces publiques et des statistiques agrégées. Le mot de passe Streamlit reste dans **App secrets**. Les dossiers locaux, mots de passe, candidatures et notes ne doivent pas être commités.

Une base PostgreSQL persistante (`DATABASE_URL` dans les secrets Streamlit) reste nécessaire pour sauvegarder durablement les candidatures sur Streamlit Cloud. La V6 **ne configure pas cette base automatiquement**.

## Tests

Depuis le dossier décompressé, dans un environnement Python avec les dépendances installées :

```bash
python -m unittest discover -s tests -v
```

Tests hors réseau : valident les transformations et règles, **pas la disponibilité réelle de chaque site**.
