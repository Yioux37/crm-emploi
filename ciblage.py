"""Ciblage du radar : secteurs, sociétés et recherche LinkedIn, modifiables dans l'appli.

Tout tient dans un seul fichier, ``ciblage.json``, versionné dans le dépôt :
- le scan (GitHub Actions ou bouton du Mac) le lit pour classer les offres ;
- l'appli Streamlit l'affiche et l'enregistre (page « Ciblage ») ;
- le score et les alertes s'en servent pour les secteurs et maisons prioritaires.

Ce fichier ne contient AUCUNE donnée personnelle (pas de candidature, pas de contact) :
seulement des mots-clés et des noms d'entreprises publiques.
"""
from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
CIBLAGE_PATH = ROOT / "ciblage.json"

# Catégories qui ne doivent pas changer de nom sans réflexion : le filtre « Luxe »
# est aussi ajouté automatiquement dès qu'une maison connue est l'employeur.
SECTEUR_LUXE = "Luxe"
TYPES_SOCIETE = ["Maison", "Groupe", "Atelier / façonnier", "Manufacture", "Cabinet"]
PRIORITES = ["Haute", "Moyenne", "Veille"]  # mêmes valeurs que storage.PRIORITIES
GROUPES_LINKEDIN = ["postes", "fonctions", "secteurs", "signaux", "exclure"]

# Un mot-clé de secteur trop court attraperait n'importe quoi (« it » est dans « digital »).
MIN_MOT_CLE = 3
MIN_NOM_SOCIETE = 2

# Utilisé si ciblage.json est absent ou illisible : le radar ne doit jamais s'arrêter.
_SECOURS = {
    "version": 1,
    "secteurs": [
        {"nom": "Luxe", "prioritaire": True, "mots_cles": ["luxe", "luxury", "lusso"]},
        {"nom": "Horlogerie", "prioritaire": True, "mots_cles": ["horlog", "watchmaking", "orolog"]},
        {"nom": "Joaillerie / Bijouterie", "prioritaire": True,
         "mots_cles": ["joaill", "bijou", "jewel", "gioiell"]},
        {"nom": "Textile / Couture", "prioritaire": True,
         "mots_cles": ["textile", "couture", "maroquinerie", "leather goods"]},
    ],
    "societes": [],
    "linkedin": {k: [] for k in GROUPES_LINKEDIN},
}


# ----------------------------------------------------------------------------
#  Normalisation : « Hermès », « HERMES » et « hermes » doivent se reconnaître.
# ----------------------------------------------------------------------------

def fold(text: object) -> str:
    """Minuscules, sans accents, apostrophes unifiées. Garde la ponctuation utile (- &)."""
    text = unicodedata.normalize("NFKD", str(text or "").replace("’", "'"))
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", text).strip()


def contient_mot(texte_plie: str, terme: str) -> bool:
    """Le terme apparaît comme mot entier (« SIS » ne doit pas matcher « analysis »)."""
    terme = fold(terme)
    if not terme:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(terme) + r"(?![a-z0-9])", texte_plie) is not None


def _liste(valeur) -> list[str]:
    """Accepte une liste ou un texte séparé par des virgules / retours à la ligne."""
    if valeur is None:
        return []
    if isinstance(valeur, str):
        valeur = re.split(r"[,\n;]", valeur)
    sortie, vus = [], set()
    for item in valeur:
        item = re.sub(r"\s+", " ", str(item or "")).strip().strip('"').strip()
        if item and fold(item) not in vus:
            vus.add(fold(item))
            sortie.append(item)
    return sortie


# ----------------------------------------------------------------------------
#  Lecture / validation / écriture
# ----------------------------------------------------------------------------

def valider(config: dict) -> tuple[dict, list[str]]:
    """Nettoie la configuration et renvoie (config propre, avertissements lisibles)."""
    avertissements: list[str] = []
    config = config or {}

    secteurs, noms_vus = [], set()
    for brut in config.get("secteurs") or []:
        nom = str(brut.get("nom") or "").strip()
        if not nom:
            continue
        if fold(nom) in noms_vus:
            avertissements.append(f"Secteur en double ignoré : {nom}")
            continue
        noms_vus.add(fold(nom))
        mots = []
        for mot in _liste(brut.get("mots_cles")):
            if len(fold(mot)) < MIN_MOT_CLE:
                avertissements.append(f"Mot-clé trop court ignoré dans {nom} : « {mot} »")
            else:
                mots.append(mot)
        if not mots:
            avertissements.append(f"Le secteur {nom} n'a aucun mot-clé : il ne détectera rien.")
        secteurs.append({"nom": nom, "prioritaire": bool(brut.get("prioritaire", True)),
                         "mots_cles": mots})
    if not secteurs:
        avertissements.append("Aucun secteur : retour aux secteurs de secours.")
        secteurs = json.loads(json.dumps(_SECOURS["secteurs"]))
    noms_secteurs = [s["nom"] for s in secteurs]

    societes, soc_vues = [], set()
    for brut in config.get("societes") or []:
        nom = re.sub(r"\s+", " ", str(brut.get("nom") or "")).strip()
        if not nom:
            continue
        if len(fold(nom)) < MIN_NOM_SOCIETE:
            avertissements.append(f"Nom de société trop court ignoré : « {nom} »")
            continue
        if fold(nom) in soc_vues:
            avertissements.append(f"Société en double ignorée : {nom}")
            continue
        soc_vues.add(fold(nom))
        secteur = str(brut.get("secteur") or "").strip()
        if secteur and secteur not in noms_secteurs:
            avertissements.append(f"{nom} : secteur « {secteur} » inconnu, laissé vide.")
            secteur = ""
        type_ = str(brut.get("type") or "Maison").strip()
        priorite = str(brut.get("priorite") or "Moyenne").strip()
        societes.append({
            "nom": nom,
            "alias": [a for a in _liste(brut.get("alias")) if fold(a) != fold(nom)],
            "secteur": secteur,
            "type": type_ if type_ in TYPES_SOCIETE else "Maison",
            "priorite": priorite if priorite in PRIORITES else "Moyenne",
        })

    linkedin_brut = config.get("linkedin") or {}
    linkedin = {g: _liste(linkedin_brut.get(g)) for g in GROUPES_LINKEDIN}

    return {"version": 1, "secteurs": secteurs, "societes": societes, "linkedin": linkedin}, avertissements


_CACHE: dict = {"cle": None, "config": None}


def charger(path: str | Path | None = None) -> dict:
    """Lit ciblage.json (mis en cache tant que le fichier ne change pas)."""
    path = Path(path or os.getenv("CIBLAGE_PATH") or CIBLAGE_PATH)
    try:
        stat = path.stat()
        cle = (str(path), stat.st_mtime_ns, stat.st_size)
        if _CACHE["cle"] == cle:
            return _CACHE["config"]
        config, _ = valider(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"⚠️ Ciblage illisible ({type(exc).__name__}) : valeurs de secours utilisées.")
        config, cle = valider(_SECOURS)[0], None
    _CACHE.update(cle=cle, config=config)
    return config


def vers_json(config: dict) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def enregistrer(config: dict, path: str | Path | None = None) -> tuple[dict, list[str]]:
    """Valide puis écrit de façon atomique. Renvoie la config réellement enregistrée."""
    propre, avertissements = valider(config)
    path = Path(path or os.getenv("CIBLAGE_PATH") or CIBLAGE_PATH)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(vers_json(propre), encoding="utf-8")
    os.replace(temp, path)
    _CACHE.update(cle=None, config=None)
    return propre, avertissements


def publier_sur_github(config: dict, token: str, repo: str, branche: str = "main",
                       chemin: str = "ciblage.json", session=None) -> tuple[bool, str]:
    """Commit ciblage.json via l'API GitHub, pour que le scan quotidien l'utilise.

    Nécessaire quand l'appli tourne sur Streamlit Cloud : le disque y est éphémère,
    une simple écriture de fichier serait perdue au redémarrage.
    """
    import requests
    session = session or requests.Session()
    url = f"https://api.github.com/repos/{repo}/contents/{chemin}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        actuel = session.get(url, headers=headers, params={"ref": branche}, timeout=15)
        sha = actuel.json().get("sha") if actuel.status_code == 200 else None
        contenu = vers_json(config)
        if sha:
            distant = base64.b64decode(actuel.json().get("content", "")).decode("utf-8", "ignore")
            if distant == contenu:
                return True, "GitHub était déjà à jour."
        corps = {"message": "Ciblage mis à jour depuis le CRM",
                 "content": base64.b64encode(contenu.encode("utf-8")).decode("ascii"),
                 "branch": branche}
        if sha:
            corps["sha"] = sha
        reponse = session.put(url, headers=headers, json=corps, timeout=15)
        if reponse.status_code in (200, 201):
            return True, "Enregistré sur GitHub : le prochain scan l'utilisera."
        if reponse.status_code in (401, 403, 404):
            return False, ("GitHub a refusé l'enregistrement : le jeton est expiré ou n'a pas "
                           "le droit « Contents : Read and write » sur ce dépôt.")
        return False, f"GitHub a refusé l'enregistrement (code {reponse.status_code})."
    except Exception as exc:  # réseau, JSON… : on n'empêche jamais l'enregistrement local
        return False, f"GitHub injoignable ({type(exc).__name__})."


# ----------------------------------------------------------------------------
#  Utilisation par le radar et le score
# ----------------------------------------------------------------------------

def secteurs_detectes(texte: str, config: dict | None = None) -> list[str]:
    """Secteurs dont au moins un mot-clé apparaît dans le texte (recherche par fragment,
    comme l'historique : « joaill » couvre joaillerie, joaillier, joaillière)."""
    config = config or charger()
    plie = fold(texte)
    return [s["nom"] for s in config["secteurs"]
            if any(fold(m) in plie for m in s["mots_cles"])]


def noms_societe(societe: dict) -> list[str]:
    return [societe["nom"], *societe.get("alias", [])]


def societe_reconnue(texte: str, config: dict | None = None, longueur_min: int = 2) -> dict | None:
    """Première société ciblée citée comme mot entier dans le texte (nom le plus long d'abord)."""
    config = config or charger()
    plie = fold(texte)
    candidats = [(fold(n), s) for s in config["societes"] for n in noms_societe(s)
                 if len(fold(n)) >= longueur_min]
    for nom, societe in sorted(candidats, key=lambda c: -len(c[0])):
        if contient_mot(plie, nom):
            return societe
    return None


def societes_par_priorite(priorite: str = "Haute", config: dict | None = None) -> list[dict]:
    config = config or charger()
    return [s for s in config["societes"] if s["priorite"] == priorite]


def rotation_du_jour(items: list, n: int, jour=None) -> list:
    """n éléments par jour, en tournant : tout est couvert en len(items)/n jours.

    Évite qu'une longue liste de sociétés consomme tout le budget de requêtes
    (et prive les portails en rotation, ou déclenche un blocage LinkedIn).
    """
    from datetime import date
    if n <= 0 or not items:
        return []
    if len(items) <= n:
        return list(items)
    jour = jour or date.today()
    debut = (jour.toordinal() * n) % len(items)
    return [items[(debut + i) % len(items)] for i in range(n)]


def noms_secteurs(config: dict | None = None) -> list[str]:
    return [s["nom"] for s in (config or charger())["secteurs"]]


def preferences_effectives(prefs: dict, config: dict | None = None) -> dict:
    """Ajoute au profil de score les secteurs prioritaires et les sociétés « Haute »."""
    config = config or charger()
    prioritaires = [s["nom"] for s in config["secteurs"] if s["prioritaire"]]
    maisons = [n for s in societes_par_priorite("Haute", config) for n in noms_societe(s)]
    deja = (prefs or {}).get("preferred_brands", "") or ""
    return {**(prefs or {}),
            "preferred_sectors": prioritaires,
            "preferred_brands": ", ".join(x for x in [deja, *maisons] if x)}


# ----------------------------------------------------------------------------
#  Recherche booléenne LinkedIn
# ----------------------------------------------------------------------------

def _groupe(termes: list[str]) -> str:
    # LinkedIn n'accepte pas de guillemets à l'intérieur d'une expression.
    propres = [t.replace('"', "").strip() for t in termes if t.replace('"', "").strip()]
    return "(" + " OR ".join(f'"{t}"' for t in propres) + ")" if propres else ""


def requete_linkedin(config: dict | None = None, avec_signaux: bool = True) -> str:
    """Construit la requête : (postes) AND (fonctions) AND (secteurs) AND (signaux) NOT (exclure).

    Les groupes vides sont simplement ignorés. Sans signaux, la requête convient
    à la recherche d'offres (une offre ne contient pas « mandat » ou « opportunité »).
    """
    li = (config or charger())["linkedin"]
    ordre = ["postes", "fonctions", "secteurs"] + (["signaux"] if avec_signaux else [])
    blocs = [b for b in (_groupe(li.get(g, [])) for g in ordre) if b]
    requete = " AND ".join(blocs)
    exclus = _groupe(li.get("exclure", []))
    if exclus and requete:
        requete += f" NOT {exclus}"
    return requete


def lien_linkedin_posts(requete: str) -> str:
    return "https://www.linkedin.com/search/results/content/?keywords=" + quote(requete) + "&sortBy=%22date_posted%22"


def lien_linkedin_offres(requete: str) -> str:
    return "https://www.linkedin.com/jobs/search/?keywords=" + quote(requete) + "&f_TPR=r2592000"
