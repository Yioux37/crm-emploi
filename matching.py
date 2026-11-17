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


def normalize_title(title: object) -> str:
    s = simplify(title)
    s = re.sub(r"\b(cdi|cdd|h f|f h|m f|f m|hfx|hf|job|poste)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_company(company: object) -> str:
    s = simplify(company)
    substitutions = {
        "hermes": "hermes", "hermes international": "hermes",
        "christian dior couture": "dior", "christian dior": "dior", "dior couture": "dior",
        "vacheron constantin": "vacheron constantin", "audemars piguet sa": "audemars piguet",
        "prada group": "prada", "the swatch group": "swatch group", "lvmh group": "lvmh",
    }
    return substitutions.get(s, s)


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
