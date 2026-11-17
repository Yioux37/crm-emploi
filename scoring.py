"""Scoring explicable, deterministe, sans service externe ni CV requis."""
from __future__ import annotations

from datetime import date
from matching import simplify

DEFAULT_PREFERENCES = {
    "preferred_countries": ["France", "Suisse", "Italie"],
    "preferred_sectors": ["Horlogerie", "Joaillerie / Bijouterie", "Textile / Couture", "Luxe"],
    "preferred_brands": "",
    "priority_keywords": "operations, opérations, excellence opérationnelle, supply chain, manufacture, manufacturing, production, atelier, industriel, planning, logistique, procurement, achats",
    "alert_threshold": 85,
}


def _tokens(value: str) -> list[str]:
    return [simplify(part) for part in (value or "").split(",") if simplify(part)]


def calculate_score(offer: dict, preferences: dict | None = None, today: date | None = None) -> tuple[int, list[str]]:
    """Retourne la note 0-100 et les facteurs (pas une probabilite d'embauche)."""
    prefs = {**DEFAULT_PREFERENCES, **(preferences or {})}
    t = simplify(offer.get("title", ""))
    company = simplify(offer.get("company", ""))
    sectors = simplify(offer.get("sector", ""))
    level = simplify(offer.get("level", ""))
    country = str(offer.get("country", ""))
    reasons = []
    score = 0

    if any(x in t for x in ("coo", "chief operating", "vice president", "vp ")) or "executive" in level:
        score += 35
        reasons.append("Niveau direction exécutive (+35)")
    elif any(x in t for x in ("directeur", "directrice", "director", "direttore", "head of")):
        score += 30
        reasons.append("Responsabilité de direction (+30)")
    elif any(x in t for x in ("responsable", "manager", "lead")):
        score += 17
        reasons.append("Management / responsable (+17)")
    else:
        score += 7
        reasons.append("Intitulé à examiner (+7)")

    keywords = _tokens(prefs.get("priority_keywords", ""))
    hits = [k for k in keywords if k and k in t]
    if hits:
        score += 25
        reasons.append(f"Métier prioritaire : {', '.join(hits[:2])} (+25)")
    elif any(x in t for x in ("operations", "supply", "industrial", "logistic", "sourcing", "procurement", "planning", "production")):
        score += 15
        reasons.append("Fonction voisine des opérations (+15)")
    else:
        score += 3
        reasons.append("Métier peu explicite dans le titre (+3)")

    if any(simplify(s) in sectors for s in prefs.get("preferred_sectors", []) if s):
        score += 15
        reasons.append("Secteur recherché (+15)")
    elif sectors:
        score += 6
        reasons.append("Secteur secondaire (+6)")

    if country in prefs.get("preferred_countries", []):
        score += 10
        reasons.append(f"Pays souhaité : {country} (+10)")
    elif country in ("France", "Suisse", "Italie"):
        score += 4
        reasons.append("Pays hors préférences (+4)")

    brands = _tokens(prefs.get("preferred_brands", ""))
    if any(b in company for b in brands):
        score += 10
        reasons.append("Maison favorite (+10)")
    elif company and company not in ("sites maisons de luxe", "cabinets de recrutement", "maison de luxe"):
        score += 5
        reasons.append("Employeur identifié (+5)")

    seen = offer.get("detected_on", "")
    today = today or date.today()
    try:
        age = (today - date.fromisoformat(str(seen)[:10])).days
    except (ValueError, TypeError):
        age = 365
    if 0 <= age <= 7:
        score += 5
        reasons.append("Détectée ces 7 derniers jours (+5)")
    elif 7 < age <= 30:
        score += 3
        reasons.append("Détectée ces 30 derniers jours (+3)")
    return min(100, score), reasons
