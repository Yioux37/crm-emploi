import os
import time
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from collections import Counter
from datetime import date
import argparse
import json
from matching import country_from_location, canonical_url
from merge_feed import merge_feed
from storage import SCRAPER_COLUMNS
from sources_plus import fetch_public_ats, fetch_indexed_jobs
from search_gateway import default_search_client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from ddgs import DDGS
    DDGS_DISPONIBLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_DISPONIBLE = True
    except ImportError:
        DDGS_DISPONIBLE = False
        print("⚠️ Moteur web manquant. Lance dans le terminal : pip install ddgs duckduckgo-search")

# ==============================================================================
# 1. RÉFÉRENTIEL COMPLET (TOUTES LES MAISONS, GROUPES & MANUFACTURES)
# ==============================================================================

MAISONS_ET_MANUFACTURES = [
    # Groupes & Maisons Couture, Textile, Maroquinerie
    "hermès", "hermes", "karl lagerfeld", "lvmh", "louis vuitton", "christian dior", "dior",
    "chanel", "kering", "gucci", "saint laurent", "yves saint laurent", "bottega veneta",
    "balenciaga", "celine", "loewe", "givenchy", "guerlain", "fendi", "loro piana",
    "berluti", "moynat", "goyard", "delvaux", "longchamp", "prada", "miu miu",
    "moncler", "brunello cucinelli", "zegna", "ermenegildo zegna", "giorgio armani",
    "armani", "valentino", "salvatore ferragamo", "ferragamo", "tod's", "tods",
    "lanvin", "chloé", "chloe", "alaïa", "alaia", "isabel marant", "jacquemus",
    "maison margiela", "richemont", "puig", "kenzo", "emilio pucci", "marc jacobs",
    "patou", "rimowa", "brioni", "alexander mcqueen", "stella mccartney",
    "gruppo florence", "minerva hub", "maroquinerie thomas", "simone", "tolomei",
    # Horlogerie & Manufactures
    "rolex", "tudor", "patek philippe", "audemars piguet", "richard mille",
    "cartier", "omega", "swatch group", "breguet", "blancpain", "longines",
    "tissot", "breitling", "tag heuer", "hublot", "zenith", "vacheron constantin",
    "jaeger-lecoultre", "jaeger lecoultre", "iwc", "panerai", "piaget",
    "chopard", "girard-perregaux", "ulysse nardin", "parmigiani", "h. moser",
    "roger dubuis", "baume & mercier", "franck muller", "frederique constant",
    "montblanc", "van cleef & arpels", "glashütte original", "rado", "mido", "hamilton",
    "acrotec", "sellita", "soprod", "la joux-perret", "vaucher manufacture",
    "kenissi", "etasa", "nivarox", "universo", "rubattel",
    # Joaillerie & Bijouterie
    "van cleef", "boucheron", "chaumet", "bulgari", "bvlgari", "tiffany",
    "fred", "messika", "pomellato", "dinh van", "mauboussin", "buccellati",
    "damiani", "repossi", "qeelin", "graff", "harry winston", "de beers"
]

MOTS_TITRE_DIRECTION = [
    "directeur", "directrice", "director", "head of", "vp ", "vice president",
    "responsabile", "direttore", "managing director",
    "vice-president", "coo", "chief operating", "direttore"
]

MOTS_METIER_OPERATIONS = [
    "opérations", "operations", "supply chain", "supply", "manufacture", "manufacturing",
    "atelier", "industriel", "industrial", "production", "produzione", "s&op",
    "excellence opérationnelle", "operational excellence",
    "transformation industrielle", "industrial transformation", "trasformazione industriale",
    "logistique", "logistics", "sourcing", "achats", "procurement", "planning",
    "plant", "usine", "factory", "industrializzazione", "lean manufacturing",
    "continuous improvement", "amélioration continue", "miglioramento continuo"
]

MOTS_INTENTION_RECRUTEMENT = [
    "recrute", "recrutons", "recrutement", "rejoignez", "rejoindre",
    "opportunité", "opportunite", "poste à pourvoir", "poste a pourvoir",
    "candidature", "cv", "hiring", "we are hiring", "looking for",
    "join our team", "join us", "open role", "job opening", "apply",
    "cercasi", "ricerca", "offerta di lavoro", "candidati"
]

MOTS_EXCLUSION_POSTS = [
    "interview", "accueille", "nomination", "félicitations", "felicitations",
    "bienvenue", "welcome", "ravi d'annoncer", "pleased to announce",
    "retour sur", "conférence", "conference", "webinar", "podcast", "article",
    "découvrez l'interview", "decouvrez l'interview"
]

MOTS_EXCLUSION_TITRE = [
    "stage", "stagiaire", "intern", "alternance", "apprentissage", "assistant",
    "adjoint", "junior", "technicien", "opérateur", "operateur", "chef de projet",
    "project manager", "coordinateur", "coordinator", "analyste", "analyst",
    "vendeur", "conseiller", "boutique", "store", "retail", "visual merchandiser",
    "chargé de", "charge de", "gestionnaire", "planificateur",
    "hotel", "hôtel", "hotellerie", "hôtellerie", "resort", "hospitality",
    "hr ", "human resources", "ressources humaines", "payroll", "paie",
    "crm", "loyalty", "fidélité", "sûreté", "surete", "sécurité", "securite", "hse",
    "marketing", "communication", "digital", "e-commerce", "ecommerce",
    "finance", "financial", "comptab", "legal", "juridique", "it ",
    "customer service", "client service", "offres d'emploi", "offres d’emploi",
    "toutes les offres", "ricerca lavoro", "jobs in "
]

ENTREPRISES_EXCLUES = [
    "hotel", "hôtel", "resorts", "hospitality", "visilab", "randstad",
    "adecco", "manpower", "synergie", "kritter", "proman"
]


# ==============================================================================
# 2. VÉRIFICATION DU PAYS, DES LIENS & CLASSIFICATION DU NIVEAU
# ==============================================================================

def verifier_pays_strict(texte, pays_api=None, lien=""):
    """Detecte depuis la localisation de l'annonce, jamais depuis l'URL ou le filtre.

    pays_api n'est pris en compte que si c'est un champ du poste (API de l'ATS).
    En cas d'ambiguite, on laisse l'offre de cote plutot que de l'etiqueter a tort.
    """
    return country_from_location(texte, country_field=pays_api)


def classer_niveau(titre):
    t = str(titre).lower()
    if any(x in t for x in [
        "coo", "chief operating officer", "vp ", "vice president",
        "vice-president", "chief operations", "chief supply chain"
    ]):
        return "Direction exécutive"
    if any(x in t for x in [
        "directeur des opérations", "director of operations",
        "directeur supply chain", "director supply chain",
        "head of operations", "head of supply chain",
        "directeur de manufacture", "directeur d'atelier",
        "plant director", "manufacturing director",
        "industrial director", "direttore di stabilimento"
    ]):
        return "Direction fonctionnelle"
    if any(x in t for x in [
        "senior manager", "manager", "responsable", "responsabile",
        "directeur", "director", "head of", "direttore"
    ]):
        return "Management senior"
    return "Hors cible"


def est_lien_post_direct(lien):
    """Vérifie que le lien mène directement vers un post LinkedIn, et JAMAIS vers un profil (/in/)."""
    l = str(lien).lower()
    if "/in/" in l or "/company/" in l or "/jobs/" in l or "/pulse/" in l:
        return False
    return ("linkedin.com/posts/" in l) or ("linkedin.com/feed/update/" in l)


# ==============================================================================
# 3. VALIDATION STRICTE & DÉTECTION AUTOMATIQUE DE TOUTES LES MAISONS
# ==============================================================================

def detecter_maison_exacte(texte_complet, lien="", fallback="Maison de Luxe"):
    """Identifie la Maison exacte parmi tout le référentiel ou depuis le nom de domaine."""
    tout = f"{texte_complet} {lien}".lower()

    groupes_generiques = {"lvmh", "kering", "richemont", "swatch group", "puig"}
    for maison in MAISONS_ET_MANUFACTURES:
        if maison not in groupes_generiques and re.search(rf"\b{re.escape(maison)}\b", tout):
            return maison.title()

    for groupe in groupes_generiques:
        if re.search(rf"\b{re.escape(groupe)}\b", tout):
            return groupe.upper() if groupe in {"lvmh"} else groupe.title()

    match_domaine = re.search(r"https?://(?:www\.|careers\.|jobs\.|talents\.|join\.)?([a-z0-9-]+)\.", str(lien).lower())
    if match_domaine:
        nom_dom = match_domaine.group(1)
        if nom_dom not in {"linkedin", "myworkdayjobs", "smartrecruiters", "greenhouse", "lever", "michaelpage", "robertwalters", "hays", "luxetalent", "fedsupply"}:
            return nom_dom.replace("-", " ").title()

    return fallback


def valider_et_classer_offre(titre, entreprise, contexte="", est_post=False, lien=""):
    titre_low = str(titre).lower()
    ent_low = str(entreprise).lower()
    tout_low = f"{titre} {entreprise} {contexte}".lower()

    if any(ex in ent_low for ex in ENTREPRISES_EXCLUES):
        return None

    if any(ex in titre_low for ex in MOTS_EXCLUSION_TITRE):
        return None

    if est_post:
        if lien and not est_lien_post_direct(lien):
            return None
        if any(ex in tout_low for ex in MOTS_EXCLUSION_POSTS):
            return None
        if not any(rec in tout_low for rec in MOTS_INTENTION_RECRUTEMENT):
            return None

    zone_analyse = tout_low if est_post else titre_low
    niveau = classer_niveau(tout_low if est_post else titre)

    if est_post:
        a_niveau_direction = niveau != "Hors cible"
    else:
        a_niveau_direction = niveau in ["Direction exécutive", "Direction fonctionnelle", "Management senior"]

    a_metier_cible = any(m in zone_analyse for m in MOTS_METIER_OPERATIONS)

    if not (a_niveau_direction and a_metier_cible):
        return None

    secteurs = []

    if any(m in tout_low for m in [
        "horloger", "watchmaking", "orolog", "rolex", "tudor", "patek", "audemars",
        "omega", "swatch", "breitling", "tag heuer", "hublot", "zenith",
        "vacheron", "jaeger", "iwc", "panerai", "richard mille", "breguet",
        "blancpain", "longines", "parmigiani", "acrotec", "sellita", "soprod",
        "kenissi", "vaucher", "glashütte", "rado", "mido", "hamilton", "tissot"
    ]):
        secteurs.append("Horlogerie")

    if any(m in tout_low for m in [
        "joaill", "bijou", "jewelry", "jewellery", "gioiell", "haute joaillerie",
        "van cleef", "boucheron", "chaumet", "bulgari", "bvlgari", "tiffany",
        "fred", "messika", "pomellato", "dinh van", "mauboussin", "buccellati",
        "damiani", "repossi", "qeelin", "graff", "harry winston"
    ]):
        secteurs.append("Joaillerie / Bijouterie")

    if any(m in tout_low for m in [
        "textile", "couture", "haute couture", "maroquinerie", "pelletteria",
        "leather goods", "prêt-à-porter", "pret-a-porter", "soie", "cachemire",
        "hermès", "hermes", "chanel", "dior", "louis vuitton", "gucci", "prada",
        "moncler", "saint laurent", "bottega veneta", "balenciaga", "celine",
        "loewe", "loro piana", "brunello cucinelli", "zegna", "armani", "valentino", "karl lagerfeld",
        "fendi", "longchamp", "gruppo florence", "minerva hub", "maroquinerie thomas",
        "delvaux", "goyard", "moynat", "berluti", "jacquemus", "isabel marant", "chloé", "alaïa"
    ]):
        secteurs.append("Textile / Couture")

    if any(m in tout_low for m in [
        "luxe", "luxury", "lusso", "artisanat d'art", "artisanat d'exception",
        "lvmh", "kering", "richemont", "cartier", "chopard", "piaget", "guerlain", "puig"
    ]) or any(maison in ent_low for maison in MAISONS_ET_MANUFACTURES):
        if "Luxe" not in secteurs:
            secteurs.append("Luxe")

    if not secteurs:
        return None

    return ", ".join(secteurs)


def deduire_source(lien, source_actuelle=""):
    s = str(source_actuelle)
    if s in ["LinkedIn (Offres)", "LinkedIn (Posts)", "Sites Maisons de Luxe", "Cabinets de Recrutement", "Portails spécialisés", "Portails cadres", "Approche directe / Réseau"]:
        return s
    l = str(lien).lower()
    if "linkedin.com/posts" in l or "linkedin.com/feed/update" in l:
        return "LinkedIn (Posts)"
    if "linkedin.com/jobs" in l:
        return "LinkedIn (Offres)"
    cabinets = ["michaelpage", "robertwalters", "luxetalent", "hays", "fedsupply", "pagepersonnel"]
    if any(c in l for c in cabinets):
        return "Cabinets de Recrutement"
    return "Sites Maisons de Luxe"


# ==============================================================================
# 4A. SOURCE 1 : LINKEDIN OFFRES DIRECT (SANS RAPIDAPI NI CLÉ API)
# ==============================================================================

def fetch_linkedin_jobs():
    """Offres LinkedIn publiques (page invitee, sans compte). Voir linkedin_guest.py.

    Lancee uniquement avec `python3 scraper.py --linkedin`, a la main.
    """
    from linkedin_guest import fetch_linkedin_guest_jobs
    statistiques = {}
    raw = fetch_linkedin_guest_jobs(stats=statistiques)
    retained = []
    for item in raw:
        normalized = normaliser_source_plus(item)  # filtre metier / luxe / pays commun
        if normalized:
            retained.append(normalized)
            key = item.get('_origine_diagnostic')
            if key in statistiques:
                statistiques[key]['retenues'] += 1
    EXTRA_SOURCE_STATS.update(statistiques)
    print(f"[LinkedIn direct] {len(raw)} offres lues, {len(retained)} retenues")
    return retained


# ==============================================================================
# 4B. SOURCE 1B : ACCÈS DIRECT API WORKDAY & ATS (GROUPES + MAISONS INDÉPENDANTES)
# ==============================================================================

def fetch_portails_directs():
    """Interroge en direct les API Workday, SmartRecruiters et Greenhouse des groupes et Maisons."""
    offres = []

    tenants_workday = [
        ("Richemont", "https://richemont.wd3.myworkdayjobs.com/wday/cxs/richemont/Richemont/jobs", "https://richemont.wd3.myworkdayjobs.com/fr-FR/Richemont"),
        ("Kering", "https://kering.wd3.myworkdayjobs.com/wday/cxs/kering/Kering/jobs", "https://kering.wd3.myworkdayjobs.com/fr-FR/Kering"),
        ("LVMH", "https://lvmh.wd3.myworkdayjobs.com/wday/cxs/lvmh/LVMH/jobs", "https://lvmh.wd3.myworkdayjobs.com/fr-FR/LVMH"),
        ("Louis Vuitton", "https://louisvuitton.wd3.myworkdayjobs.com/wday/cxs/louisvuitton/LouisVuitton/jobs", "https://louisvuitton.wd3.myworkdayjobs.com/fr-FR/LouisVuitton"),
        ("Christian Dior", "https://christiandior.wd3.myworkdayjobs.com/wday/cxs/christiandior/ChristianDiorCouture/jobs", "https://christiandior.wd3.myworkdayjobs.com/fr-FR/ChristianDiorCouture"),
        ("Loro Piana", "https://loropiana.wd3.myworkdayjobs.com/wday/cxs/loropiana/LoroPiana/jobs", "https://loropiana.wd3.myworkdayjobs.com/en-US/LoroPiana"),
        ("Bulgari", "https://bulgari.wd3.myworkdayjobs.com/wday/cxs/bulgari/Bulgari/jobs", "https://bulgari.wd3.myworkdayjobs.com/en-US/Bulgari"),
        ("TAG Heuer", "https://tagheuer.wd3.myworkdayjobs.com/wday/cxs/tagheuer/TAGHeuer/jobs", "https://tagheuer.wd3.myworkdayjobs.com/fr-FR/TAGHeuer"),
        ("Hublot", "https://hublot.wd3.myworkdayjobs.com/wday/cxs/hublot/Hublot/jobs", "https://hublot.wd3.myworkdayjobs.com/fr-FR/Hublot"),
        ("Zenith", "https://zenith.wd3.myworkdayjobs.com/wday/cxs/zenith/Zenith/jobs", "https://zenith.wd3.myworkdayjobs.com/fr-FR/Zenith"),
        ("Guerlain", "https://guerlain.wd3.myworkdayjobs.com/wday/cxs/guerlain/Guerlain/jobs", "https://guerlain.wd3.myworkdayjobs.com/fr-FR/Guerlain"),
        ("Tiffany & Co.", "https://tiffany.wd5.myworkdayjobs.com/wday/cxs/tiffany/TiffanyCareers/jobs", "https://tiffany.wd5.myworkdayjobs.com/en-US/TiffanyCareers"),
        ("Salvatore Ferragamo", "https://ferragamo.wd3.myworkdayjobs.com/wday/cxs/ferragamo/Ferragamo/jobs", "https://ferragamo.wd3.myworkdayjobs.com/en-US/Ferragamo"),
        ("Puig", "https://puig.wd3.myworkdayjobs.com/wday/cxs/puig/PuigCareers/jobs", "https://puig.wd3.myworkdayjobs.com/en-US/PuigCareers")
    ]

    # Mots-clés larges pour capter tous les intitulés exacts des portails Workday
    mots_cles = [
        "Director",
        "Directeur",
        "Head of",
        "Direttore"
    ]

    # Une seule session HTTP (cookies conserves) et des en-tetes de navigateur
    # complets : Workday renvoie 429 aux requetes "nues" venant de datacenters.
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    })
    pause_workday = float(os.getenv("WORKDAY_PAUSE_SECONDS", "3"))

    def post_workday(api_url, base_url, payload):
        """POST avec un seul nouvel essai si Workday repond 429 (limite de debit)."""
        origin = base_url.split("/", 3)
        extra = {"Origin": "/".join(origin[:3]), "Referer": base_url}
        resp = session.post(api_url, json=payload, headers=extra, timeout=15)
        if resp.status_code == 429:
            try:
                wait = min(30.0, float(resp.headers.get("Retry-After", 10)))
            except ValueError:
                wait = 10.0
            time.sleep(wait)
            resp = session.post(api_url, json=payload, headers=extra, timeout=15)
        return resp

    for numero, (groupe_nom, api_url, base_url) in enumerate(tenants_workday):
        if numero and pause_workday:
            time.sleep(pause_workday)  # espace les tenants au lieu de les enchainer
        print(f"⏳ [Workday public] {groupe_nom}...")
        liens_vus = set()
        ok_requests = 0
        errors = []
        raw_count = 0
        accepted = 0
        for kw in mots_cles:
            try:
                resp = post_workday(api_url, base_url, {
                    'appliedFacets': {}, 'limit': 20, 'offset': 0, 'searchText': kw,
                })
                if resp.status_code != 200:
                    errors.append(f'HTTP {resp.status_code}')
                    # Ne pas multiplier les requetes apres un refus.
                    if resp.status_code in (401, 403, 404, 429):
                        break
                    continue
                ok_requests += 1
                posts = resp.json().get('jobPostings', [])
                raw_count += len(posts)
                for job in posts:
                    titre = job.get('title') or ''
                    loc = job.get('locationsText') or ''
                    path = job.get('externalPath') or ''
                    bullets = ' '.join(job.get('bulletFields', []) or [])
                    if not path:
                        continue
                    lien = f'{base_url}{path}'
                    if lien in liens_vus:
                        continue
                    liens_vus.add(lien)
                    contexte = f'{titre} {loc} {bullets} {path}'
                    entreprise = detecter_maison_exacte(contexte, lien=lien, fallback=groupe_nom)
                    secteur = valider_et_classer_offre(titre, entreprise, contexte, lien=lien)
                    pays = verifier_pays_strict(loc)
                    if not (secteur and pays):
                        continue
                    offres.append({
                        'Titre': titre, 'Entreprise': entreprise, 'Secteur': secteur,
                        'Pays': pays, 'Source': 'Sites Maisons de Luxe', 'Lien': lien,
                        'Niveau estimé': classer_niveau(titre),
                        'Date de détection': pd.Timestamp.today().strftime('%Y-%m-%d'),
                    })
                    accepted += 1
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                errors.append(type(exc).__name__)
        label = f'Workday / {groupe_nom}'
        EXTRA_SOURCE_STATS[label] = {
            'brutes': raw_count, 'retenues': accepted,
            'etat': ('ok' if accepted else 'vide') if ok_requests else 'erreur',
            'detail': ', '.join(dict.fromkeys(errors))[:100] if not ok_requests else '',
        }

    return offres


# ==============================================================================
# 5. SOURCES 2, 3 & 4 : SCAN UNIVERSEL DE TOUTES LES MAISONS, POSTS & CABINETS
# ==============================================================================

def fetch_web_et_posts():
    search_client = default_search_client()
    if search_client is None:
        return []

    offres = []

    maisons_uniques = sorted(list(set(MAISONS_ET_MANUFACTURES)))
    paquets_maisons = [maisons_uniques[i:i + 15] for i in range(0, len(maisons_uniques), 15)]

    requetes = [
        # --- SOURCE A : LINKEDIN POSTS ---
        ("LinkedIn (Posts)", 'site:linkedin.com/posts "recrute" "Directeur" "Supply Chain" Luxe'),
        ("LinkedIn (Posts)", 'site:linkedin.com/posts "recrute" "Directeur" "Opérations" Luxe OR Horlogerie OR Maroquinerie'),
        ("LinkedIn (Posts)", 'site:linkedin.com/posts "hiring" "Head of" "Supply Chain" Luxury OR Watchmaking'),
        ("LinkedIn (Posts)", 'site:linkedin.com/posts "hiring" "Director of Operations" Luxury OR Jewelry OR Fashion'),
        ("LinkedIn (Posts)", 'site:linkedin.com/posts "opportunité" "Directeur" Horlogerie OR Joaillerie OR Couture'),
        ("LinkedIn (Posts)", 'site:linkedin.com/posts "cercasi" OR "ricerca" "Direttore" "Supply Chain" OR "Operations" Lusso OR Moda'),

        # --- SOURCE B : PORTAILS NON-WORKDAY ---
        ("Sites Maisons de Luxe", '(site:talents.hermes.com OR site:careers.chanel.com OR site:careers.rolex.com OR site:careers.swatchgroup.com OR site:careers.pradagroup.com) ("Directeur" OR "Director" OR "Head of" OR "Direttore") ("Operations" OR "Opérations" OR "Supply Chain" OR "Manufacture" OR "Production" OR "Atelier")'),
        ("Sites Maisons de Luxe", '(site:patek.com OR site:monclergroup.com OR site:brunellocucinelli.com OR site:zegna.com OR site:longchamp.com OR site:chopard.com) ("Directeur" OR "Director" OR "Head of" OR "Direttore") ("Operations" OR "Supply Chain" OR "Production" OR "Manufacture" OR "Produzione")'),

        # --- SOURCE C : CABINETS DE RECRUTEMENT ---
        ("Cabinets de Recrutement", '(site:michaelpage.fr/job-detail OR site:michaelpage.ch/job-detail OR site:michaelpage.it/job-detail) ("Directeur" OR "Director" OR "Head of" OR "Direttore") ("Supply Chain" OR "Operations" OR "Opérations" OR "Production")'),
        ("Cabinets de Recrutement", '(site:robertwalters.fr OR site:robertwalters.ch OR site:robertwalters.it OR site:luxetalent.fr OR site:luxetalent.it) ("Directeur" OR "Director" OR "Head of" OR "Direttore") ("Supply Chain" OR "Operations" OR "Luxe" OR "Luxury" OR "Lusso")'),
        ("Cabinets de Recrutement", '(site:hays.fr OR site:hays.ch OR site:hays.it OR site:fedsupply.fr) ("Directeur" OR "Director" OR "Head of") ("Supply Chain" OR "Industriel" OR "Manufacture" OR "Logistique")')
    ]

    for paquet in paquets_maisons:
        or_maisons = " OR ".join([f'"{m}"' for m in paquet])
        q_universelle = f'({or_maisons}) ("Directeur" OR "Director" OR "Head of" OR "Direttore") ("Operations" OR "Opérations" OR "Supply Chain" OR "Manufacture" OR "Production") (careers OR jobs OR recrutement OR offerte)'
        requetes.append(("Sites Maisons de Luxe", q_universelle))

    try:
        with search_client() as ddgs:
            for source_nom, query in requetes:
                print(f"⏳ [{source_nom}] Scan : {query[:65]}...")
                try:
                    resultats = list(ddgs.text(query, max_results=20))
                    for r in resultats:
                        titre_web = r.get("title", "")
                        lien_web = r.get("href", "")
                        if not canonical_url(lien_web):
                            continue
                        extrait = r.get("body", "")
                        est_post = (source_nom == "LinkedIn (Posts)")

                        if est_post and not est_lien_post_direct(lien_web):
                            continue

                        if est_post and "linkedin.com/posts/" in lien_web.lower():
                            try:
                                slug = lien_web.split("linkedin.com/posts/")[1].split("_")[0]
                                entreprise = slug.replace("-", " ").title()
                            except Exception:
                                entreprise = "Auteur LinkedIn"
                        else:
                            entreprise = detecter_maison_exacte(f"{titre_web} {extrait}", lien=lien_web, fallback=source_nom)

                        secteur_valide = valider_et_classer_offre(
                            titre_web, entreprise, extrait, est_post=est_post, lien=lien_web
                        )
                        if not secteur_valide:
                            continue

                        pays_valide = verifier_pays_strict(f"{titre_web} {extrait}")
                        if not pays_valide:
                            continue

                        extrait_propre = " ".join(extrait.split())
                        titre_affiche = f"📢 {extrait_propre[:125]}..." if (est_post and len(extrait_propre) > 20) else titre_web
                        niveau_detecte = classer_niveau(f"{titre_web} {extrait}" if est_post else titre_web)

                        offres.append({
                            "Titre": titre_affiche,
                            "Entreprise": entreprise,
                            "Secteur": secteur_valide,
                            "Pays": pays_valide,
                            "Source": deduire_source(lien_web, source_nom),
                            "Lien": lien_web,
                            "Niveau estimé": niveau_detecte,
                            "Date de détection": pd.Timestamp.today().strftime("%Y-%m-%d")
                        })
                    time.sleep(1.5)
                except Exception as e:
                    print(f"⚠️ Erreur sur {source_nom} : {e}")
    except Exception as e:
        print(f"⚠️ Erreur moteur web : {e}")

    return offres


# ==============================================================================
# 5B. NOUVEAUX CANAUX : LEVER, ASHBY, RSS ET INDEX SPECIALISES
# ==============================================================================


def normaliser_source_plus(raw):
    """N'importe jamais de donnee personnelle : uniquement poste, pays et lien public."""
    titre = str(raw.get("title") or "").strip()
    lien = str(raw.get("url") or "").strip()
    if not titre or not canonical_url(lien):
        return None
    source = str(raw.get("source") or "Portails spécialisés")
    localisation = str(raw.get("location") or "").strip()
    contexte = str(raw.get("context") or "")
    employeur = str(raw.get("company") or "").strip()
    if not employeur:
        # Ne jamais attribuer le nom du portail a l'entreprise.
        employeur = detecter_maison_exacte(f"{titre} {contexte}", lien="",
                                           fallback="Employeur non précisé")
    if localisation:
        pays = verifier_pays_strict(localisation, pays_api=raw.get("country_field"))
    else:
        # Moteurs indexes: pays UNIQUEMENT si le titre ou l'extrait le mentionnent.
        pays = verifier_pays_strict(f"{titre} {contexte}", pays_api=raw.get("country_field"))
    if not pays:
        return None
    secteur = valider_et_classer_offre(titre, employeur, f"{contexte} {localisation}", lien=lien)
    if not secteur:
        return None
    return {
        "Titre": titre, "Entreprise": employeur, "Secteur": secteur, "Pays": pays,
        "Source": source, "Lien": lien, "Niveau estimé": classer_niveau(titre),
        "Date de détection": pd.Timestamp.today().strftime("%Y-%m-%d")
    }


EXTRA_SOURCE_STATS = {}


def fetch_ats_complementaires():
    statistiques = {}
    raw = fetch_public_ats(stats=statistiques)
    retained = []
    for item in raw:
        normalized = normaliser_source_plus(item)
        if normalized:
            retained.append(normalized)
            key = item.get('_origine_diagnostic')
            if key in statistiques:
                statistiques[key]['retenues'] += 1
    EXTRA_SOURCE_STATS.update(statistiques)
    for source, detail in statistiques.items():
        print(f"[ATS public] {source}: {detail['brutes']} brutes, "
              f"{detail['retenues']} retenues, {detail['etat']}")
    return retained


def fetch_portails_specialises():
    statistiques = {}
    raw = fetch_indexed_jobs(stats=statistiques)
    retained = []
    for item in raw:
        normalized = normaliser_source_plus(item)
        if normalized:
            retained.append(normalized)
            key = item.get('_origine_diagnostic')
            if key in statistiques:
                statistiques[key]['retenues'] += 1
    EXTRA_SOURCE_STATS.update(statistiques)
    print(f"[Index gratuit] {len(raw)} resultats indexes, {len(retained)} offres retenues")
    return retained


def fetch_alertes_linkedin():
    """Offres envoyees par LinkedIn dans les alertes e-mail (lecture seule IMAP)."""
    from linkedin_alerts import fetch_linkedin_alerts
    statistiques = {}
    raw = fetch_linkedin_alerts(stats=statistiques)
    retained = []
    for item in raw:
        # Meme filtre metier / luxe / pays que les autres sources.
        normalized = normaliser_source_plus(item)
        if normalized:
            retained.append(normalized)
            for stat in statistiques.values():
                stat['retenues'] += 1
    EXTRA_SOURCE_STATS.update(statistiques)
    print(f"[Alertes LinkedIn] {len(raw)} offres lues, {len(retained)} retenues")
    return retained


# ==============================================================================
# 6. SAUVEGARDE, PURGE & PRÉSERVATION DES DONNÉES CRM
# ==============================================================================

def executer_tout(output="offres_detectees.csv", report="scan_rapport.json", signals_output=None,
                  linkedin=False):
    """Ne modifie jamais la base personnelle: conserve le flux en cas de panne.

    V6: les sites d'emploi indexables restent surveilles en mode gratuit,
    les annonces directes proviennent d'ATS publics configures. Les appels
    LinkedIn non autorises et la recherche complexe historique sont desactives.
    """
    collected = []
    counts = {}
    EXTRA_SOURCE_STATS.clear()
    if not linkedin:
        EXTRA_SOURCE_STATS['LinkedIn direct'] = {
            'brutes': 0, 'retenues': 0, 'etat': 'manuel',
            'detail': 'Non lance : python3 scraper.py --linkedin (a la main, depuis le Mac)',
        }
    EXTRA_SOURCE_STATS['Recherche web historique'] = {
        'brutes': 0, 'retenues': 0, 'etat': 'desactive',
        'detail': 'Requetes anciennes trop complexes et peu fiables',
    }
    for name, provider in (
        ('Workday publics', fetch_portails_directs),
        ('ATS publics configures', fetch_ats_complementaires),
        ('Index gratuit', fetch_portails_specialises),
        ('Alertes LinkedIn', fetch_alertes_linkedin),
    ) + ((('LinkedIn direct', fetch_linkedin_jobs),) if linkedin else ()):
        try:
            rows = provider()
        except Exception as exc:
            print(f'⚠️ ERREUR [{name}] : {type(exc).__name__}')
            EXTRA_SOURCE_STATS[name] = {'brutes': 0, 'retenues': 0,
                                        'etat': 'erreur', 'detail': type(exc).__name__}
            rows = []
        counts[name] = len(rows)
        collected.extend(rows)

    current_day = date.today().isoformat()
    output_path = os.path.abspath(output)
    report_path = os.path.abspath(report)
    previous = []
    if os.path.isfile(output_path):
        previous = pd.read_csv(output_path, dtype=str, keep_default_na=False).to_dict('records')
    merged_old = merge_feed(previous, [], current_day)
    errors = sum(1 for d in EXTRA_SOURCE_STATS.values()
                 if d.get('etat') in ('erreur', 'indisponible', 'non_interroge'))
    successes = sum(1 for d in EXTRA_SOURCE_STATS.values()
                    if d.get('etat') in ('ok', 'vide'))
    if collected:
        merged = merge_feed(merged_old, collected, current_day)
        status = 'partiel' if errors else 'ok'
    else:
        merged = merged_old
        status = 'degrade' if errors else 'aucune_offre_cible'
    result = {
        'version': 6, 'date_scan': current_day, 'statut': status,
        'par_source': counts,
        'annonces_brutes': len(collected),  # historiques: signifie annonces retenues AVANT fusion
        'resultats_sources': sum(int(x.get('brutes', 0)) for x in EXTRA_SOURCE_STATS.values()),
        'annonces_retenues': len(collected),
        'annonces_nouvelles': max(0, len(merged) - len(merged_old)),
        'total_historique': len(merged),
        'sources_en_erreur': errors, 'sources_repondant': successes,
        'etat_sources': EXTRA_SOURCE_STATS.copy(),
        'avertissement': ('Des sources ont echoue. Les anciennes offres restent conservees.'
                          if errors else ''),
    }
    if collected:
        temp = output_path + '.tmp'
        pd.DataFrame(merged, columns=SCRAPER_COLUMNS).to_csv(temp, index=False, encoding='utf-8')
        os.replace(temp, output_path)
    else:
        # Important : aucune re-ecriture du flux public si 0 offre retenue.
        print('⚠️ Aucune nouvelle offre exploitable. Le flux precedent est conserve.')
    if signals_output is not None:
        try:
            from market_signals import update_signals
            result.update(update_signals(signals_output, MAISONS_ET_MANUFACTURES))
        except Exception as exc:
            print(f'⚠️ [Signaux marche] {type(exc).__name__}')
            result['signaux_erreur'] = type(exc).__name__
    # Ecriture atomique du diagnostic, meme lorsque la collecte est degradee.
    os.makedirs(os.path.dirname(report_path) or '.', exist_ok=True)
    report_temp = report_path + '.tmp'
    with open(report_temp, 'w', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    os.replace(report_temp, report_path)
    if errors:
        print(f'::warning::Radar partiellement indisponible : {errors} sources en erreur.')
    print(f"Fin du scan V6 : {result['annonces_nouvelles']} nouvelles offres, "
          f"{len(merged)} conservees, {errors} sources en erreur. Donnees CRM intactes.")
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Veille publique - sans ecriture du CRM")
    cli.add_argument("--output", default="offres_detectees.csv")
    cli.add_argument("--report", default="scan_rapport.json")
    cli.add_argument("--signals-output", default="signaux_marche.csv")
    cli.add_argument("--linkedin", action="store_true",
                     help="Ajoute les offres LinkedIn publiques (a lancer a la main, pas sur GitHub)")
    args = cli.parse_args()
    executer_tout(args.output, args.report, args.signals_output, linkedin=args.linkedin)
