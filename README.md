# 🎯 Job Aggregator - Recherche d'emploi

Un tableau de bord centralisé pour simplifier la recherche d'emploi de ton papa. 
Ce projet extrait automatiquement les offres d'emploi (via RapidAPI pour LinkedIn) et les affiche dans une interface claire avec des filtres d'inclusion et d'exclusion.

## 🚀 Que contient ce projet ?

- `scraper.py` : Le script qui va chercher les offres sur internet (via API) et les sauvegarde dans un fichier CSV.
- `app.py` : L'interface visuelle (le tableau de bord) créée avec Streamlit.
- `requirements.txt` : La liste des outils Python dont le projet a besoin pour fonctionner.

## 🛠️ Installation

1. Ouvre un terminal dans le dossier où tu as extrait ce projet.
2. Installe les dépendances Python nécessaires en tapant :
   ```bash
   pip install -r requirements.txt
   ```

## ⚙️ Configuration (Étape 1)

1. Crée un compte gratuit sur [RapidAPI](https://rapidapi.com).
2. Cherche "LinkedIn Jobs Search" (ou similaire) et abonne-toi à l'offre gratuite (Basic).
3. Récupère ta clé "X-RapidAPI-Key".
4. Ouvre le fichier `scraper.py` avec un éditeur de texte et colle ta clé à la place de `"TA_CLE_SECRETE_ICI"`.

## ▶️ Utilisation (Étape 2)

1. **Lancer l'extraction des offres :**
   Dans ton terminal, tape :
   ```bash
   python scraper.py
   ```
   *(Cela va créer un fichier offres_emploi.csv contenant les annonces)*

2. **Lancer le tableau de bord :**
   Dans ton terminal, tape :
   ```bash
   streamlit run app.py
   ```
   *(Une page web va s'ouvrir automatiquement sur ton navigateur avec le tableau de bord)*
