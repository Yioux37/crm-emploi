"""Rapprochement prudent des offres et reconnaissance de localisation.

Aucun lien/nom de domaine LinkedIn n'est utilise pour deduire le pays du poste.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit


def simplify(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


CITIES = {
    "France": [
        "paris", "lyon", "bordeaux", "besancon", "annecy", "marseille",
        "ile de france", "neuilly", "boulogne", "nantes", "lille",
        "clermont ferrand", "pantin", "romans sur isere", "saint etienne",
        "val de reuil", "issoudun", "orleans", "tours", "angers", "nice",
        "grenoble", "cholet", "strasbourg", "montpellier", "versailles"
    ],
    "Suisse": [
        "geneve", "geneva", "zurich", "lausanne", "neuchatel", "bienne",
        "biel", "schaffhausen", "le brassus", "plan les ouates",
        "la chaux de fonds", "le locle", "nyon", "meyrin", "zug",
        "basel", "bale", "val de travers", "jura bernois", "fribourg",
        "vaud", "carouge", "versoix", "saint imier", "grenchen",
        "solothurn", "soleure", "mendrisio", "lucerne", "lugano"
    ],
    "Italie": [
        "milan", "milano", "florence", "firenze", "rome", "roma", "turin",
        "torino", "vicenza", "valenza", "bologna", "padova", "venezia",
        "scandicci", "novara", "biella", "varese", "como", "arezzo",
        "napoli", "naples", "venise", "bologne", "treviso", "prato"
    ],
}
COUNTRY_WORDS = {
    "France": ["france", "fr", "french"],
    "Suisse": ["suisse", "switzerland", "schweiz", "svizzera", "ch", "swiss"],
    "Italie": ["italie", "italia", "italy", "it", "italian"],
}


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text))


def country_from_location(location: object, country_field: object = "") -> str | None:
    """Le vrai lieu de l'annonce prime sur le pays filtre de la recherche.

    Si deux pays sont clairement presents dans la localisation, on ne devine pas.
    country_field doit venir de la fiche de poste (jamais du filtre de recherche).
    """
    t = simplify(location)
    if not t and not country_field:
        return None
    found = {
        c for c in CITIES
        if any(_contains_phrase(t, x) for x in COUNTRY_WORDS[c] + CITIES[c])
    }
    explicit = simplify(country_field)
    field_matches = {
        c for c in CITIES if explicit and (
            explicit in [simplify(x) for x in COUNTRY_WORDS[c]]
            or any(_contains_phrase(explicit, x) for x in COUNTRY_WORDS[c] if len(x) > 2)
        )
    }
    if len(found) > 1 or len(field_matches) > 1:
        return None
    if found and field_matches and found != field_matches:
        return None
    return next(iter(found or field_matches), None)


# Marqueurs de genre et de contrat, dans toutes les langues des annonces :
# (H/F), (F/H/X), (m/w/d), (w/m/d), (m/f/d), Directeur.rice, Directeur/trice...
_TITLE_NOISE = re.compile(
    r"\b(cdi|cdd|full time|temps plein|job|poste"
    r"|h f x|f h x|h f d|h f|f h|m f d|f m d|m w d|w m d|m f x|m f|f m|hfx|hf|mwd|wmd|mfd"
    r"|e|rice|trice)\b")
# Lieux souvent accolés au titre (« Directeur Supply Chain - Paris ») : retirés en fin de titre.
_LIEUX_FIN = sorted({c for villes in CITIES.values() for c in villes}
                    | {w for mots in COUNTRY_WORDS.values() for w in mots if len(w) > 2},
                    key=len, reverse=True)


def normalize_title(title: object) -> str:
    s = _TITLE_NOISE.sub(" ", simplify(title))
    s = re.sub(r"\s+", " ", s).strip()
    retire = True
    while retire:  # « ... paris france » : on retire les deux
        retire = False
        for lieu in _LIEUX_FIN:
            if s.endswith(" " + lieu):
                s, retire = s[: -len(lieu) - 1].strip(), True
                break
    return s


# Formes juridiques et mots d'enseigne qui ne changent pas l'employeur.
_COMPANY_NOISE = re.compile(
    r"\b(sa|sas|sasu|sarl|snc|spa|s p a|srl|s r l|ag|gmbh|ltd|limited|inc|llc|bv|nv"
    r"|international|holding|france|suisse|switzerland|italia|italy)\b")
_COMPANY_SUBSTITUTIONS = {
    "hermes international": "hermes", "christian dior couture": "dior", "christian dior": "dior",
    "dior couture": "dior", "prada group": "prada", "the swatch group": "swatch group",
    "swatch": "swatch group", "lvmh group": "lvmh", "lvmh moet hennessy louis vuitton": "lvmh",
    "bvlgari": "bulgari", "van cleef": "van cleef arpels",
}


def _company_core(s: str) -> str:
    s = _COMPANY_NOISE.sub(" ", s)
    s = re.sub(r"^(maison|groupe|group|gruppo|the)\s+", "", re.sub(r"\s+", " ", s).strip())
    return re.sub(r"\s+", " ", s).strip()


_KNOWN_CACHE: dict = {"cle": None, "valeur": []}


def _known_companies() -> list[tuple[str, "re.Pattern", str]]:
    """(forme, motif mot entier, forme canonique) : sociétés du Ciblage + groupes connus.

    Mis en cache tant que ciblage.json ne change pas (la fusion du flux compare
    chaque offre à toutes les autres : des milliers d'appels par scan).
    """
    try:
        import ciblage
        config = ciblage.charger()
    except Exception:
        config = None
    if _KNOWN_CACHE["cle"] is not None and _KNOWN_CACHE["cle"] is config:
        return _KNOWN_CACHE["valeur"]
    pairs = []
    try:
        import ciblage
        for soc in (config or {"societes": []})["societes"]:
            canon = simplify(soc["nom"])
            canon = _COMPANY_SUBSTITUTIONS.get(canon, canon)
            for nom in ciblage.noms_societe(soc):
                if len(simplify(nom)) >= 4:  # « SIS » trop court pour un rapprochement
                    pairs.append((simplify(nom), canon))
    except Exception:
        pass
    for groupe, maisons in GROUP_CHILDREN.items():
        pairs += [(groupe, groupe)] + [(m, m) for m in maisons]
    valeur = [(forme, re.compile(r"(?<![a-z0-9])" + re.escape(forme) + r"(?![a-z0-9])"), canon)
              for forme, canon in sorted(set(pairs), key=lambda p: -len(p[0]))]
    _KNOWN_CACHE.update(cle=config if config is not None else None, valeur=valeur)
    return valeur


def normalize_company(company: object) -> str:
    """« ROLEX SA », « Rolex » et « Maison Rolex » -> « rolex ». « Louis Vuitton Malletier »
    -> « louis vuitton » (nom connu contenu dans le nom complet)."""
    s = simplify(company)
    if s in _COMPANY_SUBSTITUTIONS:
        return _COMPANY_SUBSTITUTIONS[s]
    s = _company_core(s) or s
    if s in _COMPANY_SUBSTITUTIONS:
        return _COMPANY_SUBSTITUTIONS[s]
    for forme, motif, canon in _known_companies():
        if s == forme or motif.search(s):
            return canon
    return s


GROUP_CHILDREN = {
    "richemont": {"vacheron constantin", "cartier", "jaeger lecoultre", "iwc", "panerai", "piaget", "van cleef arpels", "montblanc", "roger dubuis"},
    "lvmh": {"dior", "louis vuitton", "fendi", "guerlain", "bulgari", "tag heuer", "hublot", "zenith", "loro piana"},
    "kering": {"gucci", "saint laurent", "bottega veneta", "balenciaga", "boucheron"},
}


def known_group_relation(company_a: object, company_b: object) -> bool:
    a, b = normalize_company(company_a), normalize_company(company_b)
    return any((a == group and b in children) or (b == group and a in children)
               for group, children in GROUP_CHILDREN.items())


def canonical_url(url: object) -> str:
    """Supprime les trackers, unifie les variantes LinkedIn pour la meme annonce."""
    u = str(url or "").strip()
    if not u.startswith(("https://", "http://")):
        return ""
    try:
        parts = urlsplit(u)
        host = (parts.hostname or "").casefold().removeprefix("www.")
        path = unquote(parts.path).rstrip("/")
        if "linkedin.com" in host and "/jobs/view/" in path:
            match = re.search(r"-(\d{8,})$", path)
            if match:
                return "linkedin:job:" + match.group(1)
        if "linkedin.com" in host:
            host = "linkedin.com"
        allowed = {"id", "jobid", "gh_jid", "jid", "reqid"}
        query = "&".join(f"{k.lower()}={v}" for k, v in parse_qsl(parts.query)
                         if k.lower() in allowed)
        return urlunsplit(("https", host, path.casefold(), query, ""))
    except ValueError:
        return ""


def _specific_role_code(title: object) -> bool:
    """Ne rapproche pas deux postes generiques de maisons d'un meme groupe."""
    stop = {"CDI", "CDD", "H", "F", "HF", "COO", "CEO", "VP", "SAP", "SOP", "IT", "FR",
            "HEAD", "OF", "SUPPLY", "CHAIN", "TEAM", "LEAD", "MANAGER", "SENIOR", "THE",
            "DE", "DU", "DES", "EN", "PAP", "HOMME", "FEMME", "LUXE", "LUXURY", "GROUP",
            "REGION", "SA", "FRANCE", "SUISSE", "ITALIE", "PARIS", "EMEA", "APAC"}
    return any(3 <= len(s) <= 6 and s not in stop and any(ch.isalpha() for ch in s)
               for s in re.findall(r"\b[A-Z0-9]{2,6}\b", str(title or "")))


def same_opportunity(a: dict, b: dict) -> bool:
    au, bu = canonical_url(a.get("link", "")), canonical_url(b.get("link", ""))
    if au and au == bu:
        return True
    if a.get("country") != b.get("country"):
        return False
    title_a, title_b = normalize_title(a.get("title")), normalize_title(b.get("title"))
    if not title_a or not title_b:
        return False
    similarity = SequenceMatcher(None, title_a, title_b).ratio()
    comp_a, comp_b = normalize_company(a.get("company")), normalize_company(b.get("company"))
    if comp_a == comp_b and comp_a:
        return similarity >= 0.94
    if known_group_relation(comp_a, comp_b):
        return title_a == title_b and (_specific_role_code(a.get("title")) or _specific_role_code(b.get("title")))
    return False


SOURCE_RANK = {"Sites Maisons de Luxe": 5, "Cabinets de Recrutement": 4,
               "Portails spécialisés": 3, "Portails cadres": 3,
               "LinkedIn (Offres)": 3, "LinkedIn (Posts)": 2,
               "Approche directe / Reseau": 1, "Approche directe / Réseau": 1}


def preferred_primary(new_source: str, old_source: str) -> bool:
    return SOURCE_RANK.get(new_source, 0) > SOURCE_RANK.get(old_source, 0)


# --- Filtre « ce n'est pas une offre » -------------------------------------
# La recherche ouverte par maison remonte aussi des articles de presse
# (« LVMH nomme X directeur industriel »), des fiches de personnes (The Org,
# RocketReach...) et des pages de resultats de jobboards. Ce filtre les ecarte
# AVANT le CRM. Il renvoie la raison, pour pouvoir l'expliquer dans les tests.

# Sites qui ne publient jamais d'offres : presse, bourse, annuaires de personnes.
NON_JOB_HOSTS = (
    # Organigrammes et annuaires de personnes (donnees personnelles)
    "theorg.com", "rocketreach.co", "zoominfo.com", "signalhire.com", "lusha.com",
    "contactout.com", "crunchbase.com", "apollo.io", "cbinsights.com",
    # Bourse et finance
    "zonebourse.com", "marketscreener.com", "boursorama.com", "investing.com",
    "boursier.com", "abcbourse.com", "finance.yahoo.com",
    # Presse generale, economique et luxe
    "lefigaro.fr", "lemonde.fr", "lesechos.fr", "challenges.fr", "bfmtv.com",
    "latribune.fr", "capital.fr", "lexpress.fr", "lepoint.fr", "usinenouvelle.com",
    "reuters.com", "bloomberg.com", "ft.com", "forbes.com", "forbes.fr", "wwd.com",
    "businessoffashion.com", "fashionnetwork.com", "fashionunited.com",
    "journalduluxe.fr", "luxus-plus.com", "bilan.ch", "letemps.ch", "agefi.com",
    "pambianconews.com", "ilsole24ore.com", "milanofinanza.it", "corriere.it",
    "europastar.com", "worldtempus.com", "watchpro.com", "watchonista.com",
    # Communiques
    "prnewswire.com", "globenewswire.com", "businesswire.com",
    # Encyclopedies et reseaux sociaux
    "wikipedia.org", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com",
)

# Morceaux d'URL typiques d'un article, d'un organigramme ou d'une liste de resultats.
_NON_JOB_PATH = re.compile(
    r"/(actualites?|news|article|articles|communiques?|press|org-chart|people|profil|profile)/"
    r"|/s/emploi/|/(search|recherche|resultats)/?$"
)

# Titres d'annonces de nomination, de fiches de personnes et de pages de resultats.
# Compare sur le titre simplifie (minuscules, sans accents ni ponctuation).
_NON_JOB_TITLE = re.compile(
    r"\b(nomme|nommee|nomination|nominato|nominata|appoints?|appointed|appointment"
    r"|rejoint|joins|promu|promue|succede a|prend la tete|new ceo|nouveau directeur general"
    r"|the org|org chart|organigramme"
    r"|offres? s d emploi|offres d emploi|toutes les offres|emplois? et recrutement"
    r"|jobs in|ricerca lavoro|offerte di lavoro)\b"
)


def raison_non_offre(title: object, url: object) -> str | None:
    """Renvoie pourquoi ce resultat n'est PAS une offre, ou None si c'en est une."""
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in NON_JOB_HOSTS):
        return f"site sans offres ({host})"
    if _NON_JOB_PATH.search((parts.path or "").lower()):
        return "page d'article, de profil ou de resultats"
    if _NON_JOB_TITLE.search(simplify(title)):
        return "titre d'article, de profil ou de liste"
    return None


def est_une_offre(title: object, url: object) -> bool:
    return raison_non_offre(title, url) is None
