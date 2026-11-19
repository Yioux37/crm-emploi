"""Fusion incrémentale du flux d'annonces, sans données personnelles CRM."""
from __future__ import annotations

import json
from datetime import date
from matching import (est_une_offre, known_group_relation, preferred_primary, same_opportunity,
                      normalize_company, source_depuis_lien)
from storage import SCRAPER_COLUMNS


def _alts(record: dict) -> list[dict]:
    raw = record.get("Liens alternatifs") or "[]"
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return [{**a, "source": source_depuis_lien(a["url"], a["source"])}
                for a in value if isinstance(a, dict) and a.get("url") and a.get("source")]
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
        row["Source"] = source_depuis_lien(row["Lien"], row["Source"])
        if not row["Titre"] or not row["Entreprise"] or row["Pays"] not in ("France", "Suisse", "Italie"):
            continue
        # Articles, fiches de personnes, pages de resultats : retires du flux, meme anciens.
        if not est_une_offre(row["Titre"], row["Lien"]):
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


def liens_a_verifier(rows: list[dict], scanned_on: str | None = None, maximum: int = 150) -> list[tuple[str, str]]:
    """(url, titre) de tous les liens du flux, offres du jour en premier, plafonnés.

    Le plafond protège la durée du scan quand l'historique grossit : ce qui
    n'est pas vérifié aujourd'hui le sera à un prochain passage.
    """
    today = scanned_on or date.today().isoformat()
    ordre = sorted(rows, key=lambda r: (r.get("Dernière détection") != today,
                                        r.get("Dernière détection", "")), reverse=False)
    liens, vus = [], set()
    for row in ordre:
        for url in [row.get("Lien", "")] + [a["url"] for a in _alts(row)]:
            if url and url.startswith(("http://", "https://")) and url not in vus:
                vus.add(url)
                liens.append((url, row.get("Titre", "")))
    return liens[:maximum]


def appliquer_verdicts_flux(rows: list[dict], verdicts: dict) -> tuple[list[dict], dict]:
    """Retire les liens morts du flux public, sans jamais perdre une offre encore vivante.

    Etape par etape, pour chaque offre :
      1. on classe ses liens (principal + alternatifs) : morts / vivants / non vérifiés ;
      2. un lien non vérifié ou « À vérifier » est gardé : un blocage n'est pas une preuve ;
      3. si le lien principal est mort mais qu'un alternatif vit, il prend sa place
         (ex. : copie trabajo.org expirée -> vraie fiche LinkedIn encore ouverte) ;
      4. si TOUS les liens sont morts, l'offre sort du flux.
    """
    from link_health import ACCESSIBLE  # import local : merge_feed reste léger

    def mort(url):
        v = verdicts.get(url)
        return bool(v and v.mort)

    kept, stats = [], {"offres_retirees": 0, "liens_morts": 0, "liens_remplaces": 0, "retirees": []}
    for row in rows:
        liens = [(row["Lien"], row["Source"])] + [(a["url"], a["source"]) for a in _alts(row)]
        vivants = [(u, s) for u, s in liens if u and not mort(u)]
        stats["liens_morts"] += sum(1 for u, _ in liens if u and mort(u))
        if not vivants:
            stats["offres_retirees"] += 1
            v = verdicts.get(row["Lien"])
            stats["retirees"].append({"titre": row["Titre"], "entreprise": row["Entreprise"],
                                      "raison": v.raison if v else ""})
            continue
        if mort(row["Lien"]):
            # Le meilleur survivant : d'abord une page vérifiée ouverte, puis la source la plus fiable.
            from matching import SOURCE_RANK
            vivants.sort(key=lambda us: (verdicts.get(us[0]) is not None
                                         and verdicts[us[0]].statut == ACCESSIBLE,
                                         SOURCE_RANK.get(us[1], 0)), reverse=True)
            row = {**row, "Lien": vivants[0][0], "Source": vivants[0][1]}
            stats["liens_remplaces"] += 1
        row["Liens alternatifs"] = json.dumps(
            [{"url": u, "source": s} for u, s in vivants if u != row["Lien"]], ensure_ascii=False)
        kept.append(row)
    return kept, stats
