"""Fusion incrémentale du flux d'annonces, sans données personnelles CRM."""
from __future__ import annotations

import json
from datetime import date
from matching import known_group_relation, preferred_primary, same_opportunity, normalize_company
from storage import SCRAPER_COLUMNS


def _alts(record: dict) -> list[dict]:
    raw = record.get("Liens alternatifs") or "[]"
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return [a for a in value if isinstance(a, dict) and a.get("url") and a.get("source")]
    except (ValueError, TypeError):
        return []


def _to_match(record: dict) -> dict:
    return {"title": record.get("Titre", ""), "company": record.get("Entreprise", ""),
            "country": record.get("Pays", ""), "link": record.get("Lien", "")}


def merge_feed(old: list[dict], new: list[dict], scanned_on: str | None = None) -> list[dict]:
    """Conserve l'historique, actualise les derniers passages et les liens alternatifs."""
    today = scanned_on or date.today().isoformat()
    merged: list[dict] = []
    for raw in [(r, False) for r in old] + [(r, True) for r in new]:
        record, is_new = raw
        row = {c: str(record.get(c, "") or "") for c in SCRAPER_COLUMNS}
        if not row["Titre"] or not row["Entreprise"] or row["Pays"] not in ("France", "Suisse", "Italie"):
            continue
        if not row["Date de détection"]:
            row["Date de détection"] = today
        if is_new:
            row["Dernière détection"] = today
        elif not row["Dernière détection"]:
            row["Dernière détection"] = row["Date de détection"]
        row["Liens alternatifs"] = json.dumps(_alts(record), ensure_ascii=False)
        position = next((idx for idx, existing in enumerate(merged)
                         if same_opportunity(_to_match(existing), _to_match(row))), None)
        if position is None:
            merged.append(row)
            continue
        target = merged[position]
        target["Date de détection"] = min(target["Date de détection"], row["Date de détection"])
        target["Dernière détection"] = max(target["Dernière détection"], row["Dernière détection"])
        alt = _alts(target)
        urls = {a["url"] for a in alt}
        if row["Lien"] and row["Lien"] != target["Lien"] and row["Lien"] not in urls:
            alt.append({"url": row["Lien"], "source": row["Source"]})
        for a in _alts(row):
            if a["url"] != target["Lien"] and a["url"] not in urls:
                alt.append(a)
                urls.add(a["url"])
        if preferred_primary(row["Source"], target["Source"]):
            if target["Lien"] and target["Lien"] != row["Lien"] and target["Lien"] not in {a["url"] for a in alt}:
                alt.append({"url": target["Lien"], "source": target["Source"]})
            target["Lien"], target["Source"] = row["Lien"], row["Source"]
        # Le nom de la Maison est plus precis que celui de sa holding.
        if known_group_relation(target["Entreprise"], row["Entreprise"]):
            if normalize_company(target["Entreprise"]) in ("richemont", "lvmh", "kering"):
                target["Entreprise"] = row["Entreprise"]
                target["Secteur"] = row["Secteur"] or target["Secteur"]
        target["Liens alternatifs"] = json.dumps(
            [a for a in alt if a["url"] != target["Lien"]], ensure_ascii=False
        )
    return merged
