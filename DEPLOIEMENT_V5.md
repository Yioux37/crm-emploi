# Mettre le CRM V5 sur Streamlit Cloud

## Sur Mac (depot GitHub deja clone)

1. Telecharge et decompresse `crm-emploi-v5.zip` dans `~/Downloads`.
2. Depuis Terminal, lance `bash ~/Downloads/crm-emploi-v5/mettre_a_jour_mac.sh`.
3. **Verifie `git status`** depuis `~/Downloads/crm-emploi-github`. Aucun secret `.env`, `.streamlit/secrets.toml`, dossier `data/` ni fichier `offres_emploi.csv` ne doit etre ajoute.
4. Lance `git commit -m "CRM V5 - sites emploi majeurs"` puis `git push origin main`.
5. Streamlit Cloud se met normalement a jour automatiquement si le depot et la branche sont correctement lies.
6. Dans GitHub : `Actions > Veille emploi quotidienne > Run workflow` pour tester le scan. Lire le journal et le fichier `scan_rapport.json` pour voir les retours par site.

## Avant d'utiliser le suivi des candidatures sur Streamlit Cloud

- Regler `APP_PASSWORD` dans les **Secrets Streamlit**. Ne jamais le mettre dans GitHub.
- Configurer `DATABASE_URL` sur une **base PostgreSQL persistante** pour ne pas perdre notes et candidatures. SQLite local sur Streamlit Cloud n'est pas une sauvegarde fiable.
- Les identifiants de recherche Brave (`BRAVE_SEARCH_API_KEY`) sont facultatifs et se mettent dans les **Secrets GitHub Actions**, pas dans les fichiers publics.

## Couverture reelle

Le catalogue compte **109 cibles indexees** dont **12 prioritaires par jour** ; **20 recherches indexees** par scan puis rotation quotidienne. C'est une liste de domaines a rechercher sur le moteur, **pas 109 connecteurs directs**. Les liens publics retrouves sont controles et filtres avant import. Le nombre d'annonces pertinentes varie selon l'index et le bon fonctionnement des sources.

Le CRM ne contourne ni CAPTCHA ni identifiants. Certains sites (Indeed, LinkedIn et d'autres) ne doivent pas faire l'objet de scraping direct non autorise. Les alertes officielles et la recherche indexee sont des solutions de repli, sous reserve des regles applicables.
