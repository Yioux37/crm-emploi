"""Persistance du CRM independante des fichiers generes par le scanner.

SQLite sur poste local; PostgreSQL via DATABASE_URL pour deploiement sans perte.
Toutes les operations critiques utilisent des transactions SQLAlchemy.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import logging
from contextlib import closing
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import (Column, Integer, MetaData, String, Table, Text, create_engine,
                        delete, event, insert, select, update, UniqueConstraint)
from sqlalchemy.engine import Engine

from matching import (canonical_url, est_une_offre, preferred_primary, same_opportunity,
                      known_group_relation, normalize_company, SOURCE_RANK)
from scoring import DEFAULT_PREFERENCES

ROOT = Path(__file__).resolve().parent
STATUSES = [
    "A analyser", "A postuler", "Candidature envoyee", "Reseau / Approche directe",
    "Entretien 1", "Entretien final / Shortlist", "Refuse / Sans suite", "Ecarte"
]
PRIORITIES = ["Haute", "Moyenne", "Veille"]
MANUAL_SOURCES = ["Approche directe / Réseau", "LinkedIn (Post recruteur)",
                  "LinkedIn (Offres)", "Chasseur de têtes"]


def manual_source(link: str, chosen: str = "") -> str:
    """Devine l'origine d'un lien colle : post LinkedIn, offre LinkedIn ou reseau."""
    l = str(link or "").lower()
    if "linkedin.com/posts/" in l or "linkedin.com/feed/update/" in l:
        return "LinkedIn (Post recruteur)"
    if "linkedin.com/jobs/view/" in l or "linkedin.com/comm/jobs/view/" in l:
        return "LinkedIn (Offres)"
    return chosen if chosen in MANUAL_SOURCES else "Approche directe / Réseau"
STATUSES_LEGACY = {
    "🆕 À analyser": "A analyser", "🎯 À postuler": "A postuler",
    "✉️ Candidature envoyée": "Candidature envoyee",
    "🤝 Réseau / Approche directe": "Reseau / Approche directe",
    "🗣️ Entretien 1": "Entretien 1", "🔥 Entretien final / Shortlist": "Entretien final / Shortlist",
    "❌ Refusé / Sans suite": "Refuse / Sans suite", "🗄️ Écarté": "Ecarte",
}
PRIORITIES_LEGACY = {"🔴 Haute": "Haute", "🟠 Moyenne": "Moyenne", "🟢 Veille": "Veille"}
SCRAPER_COLUMNS = ["Titre", "Entreprise", "Secteur", "Pays", "Source", "Lien",
                   "Niveau estimé", "Date de détection", "Dernière détection", "Liens alternatifs"]
# États du lien (voir link_health). « Indisponible » : ancien statut, toujours lu.
LINK_STATUSES = ("Accessible", "Offre expirée", "Lien redirigé", "À vérifier", "Indisponible")
DEAD_LINK_STATUSES = ("Offre expirée", "Lien redirigé", "Indisponible")
CLOSED_STATUSES = ("Refuse / Sans suite", "Ecarte")
CRM_COLUMNS = ["Statut", "Priorité", "Contact / Chasseur", "Date dernière action",
               "Date prochaine action", "Notes"]

metadata = MetaData()
offers = Table(
    "offers", metadata,
    Column("id", String(36), primary_key=True),
    Column("title", Text, nullable=False),
    Column("company", Text, nullable=False),
    Column("sector", Text, nullable=False, default=""),
    Column("country", String(20), nullable=False),
    Column("source", Text, nullable=False, default=""),
    Column("link", Text, nullable=False, default=""),
    Column("level", Text, nullable=False, default=""),
    Column("detected_on", String(10), nullable=False),
    Column("last_seen", String(10), nullable=False),
    Column("status", Text, nullable=False, default="A analyser"),
    Column("priority", Text, nullable=False, default="Moyenne"),
    Column("contact", Text, nullable=False, default=""),
    Column("last_action", String(10), nullable=False, default=""),
    Column("next_action", String(10), nullable=False, default=""),
    Column("notes", Text, nullable=False, default=""),
    Column("is_manual", Integer, nullable=False, default=0),
    Column("link_status", String(25), nullable=False, default="Non vérifié"),
    Column("link_checked_at", String(30), nullable=False, default=""),
    Column("created_at", String(30), nullable=False),
    Column("updated_at", String(30), nullable=False),
)
links = Table(
    "offer_links", metadata,
    Column("id", String(36), primary_key=True),
    Column("offer_id", String(36), nullable=False, index=True),
    Column("url_key", Text, nullable=False, unique=True),
    Column("url", Text, nullable=False),
    Column("source", Text, nullable=False),
)
history = Table(
    "history", metadata,
    Column("id", String(36), primary_key=True),
    Column("offer_id", String(36), nullable=False, index=True),
    Column("when_at", String(30), nullable=False),
    Column("action", Text, nullable=False),
)
settings = Table(
    "settings", metadata,
    Column("key", String(120), primary_key=True),
    Column("value", Text, nullable=False),
)
notifications = Table(
    "notifications", metadata,
    Column("id", String(36), primary_key=True),
    Column("kind", String(50), nullable=False),
    Column("item_key", String(120), nullable=False),
    Column("sent_at", String(30), nullable=False),
    UniqueConstraint("kind", "item_key", name="uq_notification_kind_item"),
)

# --- Briques « pilotage actif » : réseau, sociétés cibles, préparation entretien ---
# Vocabulaires contrôlés, pour des filtres et regroupements fiables côté interface.
CONTACT_KINDS = ["Chasseur de têtes", "DRH / RH", "Opérationnel / Métier",
                 "Réseau / Ancien collègue", "Autre"]
TARGET_STATUSES = ["À approcher", "Contact établi", "En discussion", "En veille", "Écartée"]

# Réseau : chasseurs, DRH, contacts à relancer. Le moteur d'une recherche de cadre.
contacts = Table(
    "contacts", metadata,
    Column("id", String(36), primary_key=True),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False, default="Réseau / Ancien collègue"),
    Column("company", Text, nullable=False, default=""),
    Column("role", Text, nullable=False, default=""),
    Column("email", Text, nullable=False, default=""),
    Column("phone", Text, nullable=False, default=""),
    Column("country", String(20), nullable=False, default=""),
    Column("last_contact", String(10), nullable=False, default=""),
    Column("next_contact", String(10), nullable=False, default=""),
    Column("notes", Text, nullable=False, default=""),
    Column("created_at", String(30), nullable=False),
    Column("updated_at", String(30), nullable=False),
)
# Sociétés cibles : maisons visées même sans offre ouverte, suivies dans le temps.
target_companies = Table(
    "target_companies", metadata,
    Column("id", String(36), primary_key=True),
    Column("name", Text, nullable=False),
    Column("country", String(20), nullable=False, default=""),
    Column("sector", Text, nullable=False, default=""),
    Column("priority", Text, nullable=False, default="Moyenne"),
    Column("status", Text, nullable=False, default="À approcher"),
    Column("notes", Text, nullable=False, default=""),
    Column("created_at", String(30), nullable=False),
    Column("updated_at", String(30), nullable=False),
)
# Préparation entretien : une fiche par rendez-vous, reliée à une offre si besoin.
interview_prep = Table(
    "interview_prep", metadata,
    Column("id", String(36), primary_key=True),
    Column("company", Text, nullable=False),
    Column("role", Text, nullable=False, default=""),
    Column("interview_date", String(10), nullable=False, default=""),
    Column("offer_id", String(36), nullable=False, default=""),
    Column("research", Text, nullable=False, default=""),
    Column("questions", Text, nullable=False, default=""),
    Column("notes", Text, nullable=False, default=""),
    Column("created_at", String(30), nullable=False),
    Column("updated_at", String(30), nullable=False),
)


class ConcurrentEditError(RuntimeError):
    """La fiche a change depuis son affichage."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _iso_date(value: Any, fallback: str = "") -> str:
    text = _str(value)
    if not text:
        return fallback
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return fallback


def _row_values(row: dict) -> dict:
    detected = _iso_date(row.get("Date de détection"), date.today().isoformat())
    status = STATUSES_LEGACY.get(_str(row.get("Statut")), _str(row.get("Statut"))) or "A analyser"
    priority = PRIORITIES_LEGACY.get(_str(row.get("Priorité")), _str(row.get("Priorité"))) or "Moyenne"
    return {
        "title": _str(row.get("Titre")),
        "company": _str(row.get("Entreprise")),
        "sector": _str(row.get("Secteur")),
        "country": _str(row.get("Pays")),
        "source": _str(row.get("Source")),
        "link": _str(row.get("Lien")),
        "level": _str(row.get("Niveau estimé")),
        "detected_on": detected,
        "last_seen": _iso_date(row.get("Dernière détection"), detected),
        "status": status if status in STATUSES else "A analyser",
        "priority": priority if priority in PRIORITIES else "Moyenne",
        "contact": _str(row.get("Contact / Chasseur")),
        "last_action": _iso_date(row.get("Date dernière action")),
        "next_action": _iso_date(row.get("Date prochaine action")),
        "notes": _str(row.get("Notes")),
        "alternates": parse_alternate_links(row.get("Liens alternatifs", "[]")),
        "is_manual": int(_str(row.get("Source")) in ("Approche directe / Reseau", "Approche directe / Réseau")
                         or _str(row.get("Lien")).startswith("manuel://")),
    }


def parse_alternate_links(raw: Any) -> list[dict]:
    try:
        value = json.loads(_str(raw) or "[]")
        return [r for r in value if isinstance(r, dict) and r.get("url") and r.get("source")] if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


class CRMStore:
    def __init__(self, db_url: str | None = None, db_path: str | Path | None = None):
        url = db_url or os.getenv("DATABASE_URL", "").strip()
        if url:
            if url.startswith("postgres://"):
                url = "postgresql+psycopg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://"):]
        else:
            p = Path(db_path or os.getenv("CRM_DB_PATH", ROOT / "data" / "crm.sqlite3")).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{p}"
        self.is_local = url.startswith("sqlite:")
        self.backup_error = ""
        self.engine: Engine = create_engine(
            url, pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30} if self.is_local else {},
        )
        if self.is_local:
            @event.listens_for(self.engine, "connect")
            def sqlite_options(dbapi_conn, _):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()
        metadata.create_all(self.engine)

    @staticmethod
    def _get_setting(connection, key: str) -> str | None:
        return connection.execute(select(settings.c.value).where(settings.c.key == key)).scalar_one_or_none()

    @staticmethod
    def _set_setting(connection, key: str, value: str) -> None:
        if connection.execute(select(settings.c.key).where(settings.c.key == key)).first():
            connection.execute(update(settings).where(settings.c.key == key).values(value=value))
        else:
            connection.execute(insert(settings).values(key=key, value=value))

    def preferences(self) -> dict:
        with self.engine.connect() as conn:
            raw = self._get_setting(conn, "preferences")
        try:
            user = json.loads(raw) if raw else {}
            return {**DEFAULT_PREFERENCES, **user} if isinstance(user, dict) else dict(DEFAULT_PREFERENCES)
        except json.JSONDecodeError:
            return dict(DEFAULT_PREFERENCES)

    def save_preferences(self, preferences: dict) -> None:
        preferences = {**DEFAULT_PREFERENCES, **preferences}
        with self.engine.begin() as conn:
            self._set_setting(conn, "preferences", json.dumps(preferences, ensure_ascii=False))
        self.backup_local()

    @staticmethod
    def _find_offer(conn, vals: dict) -> dict | None:
        url_key = canonical_url(vals["link"])
        if url_key:
            id_found = conn.execute(select(links.c.offer_id).where(links.c.url_key == url_key)).scalar_one_or_none()
            if id_found:
                found = conn.execute(select(offers).where(offers.c.id == id_found)).mappings().first()
                if found:
                    return dict(found)
        for row in conn.execute(select(offers).where(offers.c.country == vals["country"])).mappings():
            if same_opportunity(dict(row), vals):
                return dict(row)
        return None

    @staticmethod
    def _record_event(conn, offer_id: str, action: str) -> None:
        conn.execute(insert(history).values(
            id=str(uuid.uuid4()), offer_id=offer_id, when_at=utc_now(), action=action
        ))

    @staticmethod
    def _add_link(conn, offer_id: str, link: str, source: str) -> None:
        key = canonical_url(link)
        if not key:
            return
        if conn.execute(select(links.c.id).where(links.c.url_key == key)).first():
            return
        conn.execute(insert(links).values(id=str(uuid.uuid4()), offer_id=offer_id,
                                          url_key=key, url=link, source=source))

    def _insert_or_match(self, conn, vals: dict, mode: str) -> bool:
        vals = dict(vals)
        alt_links = vals.pop("alternates", [])
        if not vals["title"] or not vals["company"] or vals["country"] not in ("France", "Suisse", "Italie"):
            return False
        # Un ajout manuel reste libre ; le flux automatique n'importe que de vraies offres.
        if mode == "feed" and not est_une_offre(vals["title"], vals["link"]):
            return False
        existing = self._find_offer(conn, vals)
        if existing:
            # Jamais remplacer les informations personnelles par des champs de scraping.
            changed = {}
            if mode == "legacy":
                # Deux fiches CSV historiques peuvent referencer le meme poste :
                # les notes et contacts distincts ne doivent pas disparaitre.
                notes = existing["notes"]
                if vals["notes"] and vals["notes"] not in notes:
                    notes = (notes + "\n\n" if notes else "") + vals["notes"]
                if vals["contact"] and vals["contact"] not in existing["contact"]:
                    changed["contact"] = (existing["contact"] + " / " if existing["contact"] else "") + vals["contact"]
                if existing["status"] == "A analyser" and vals["status"] != "A analyser":
                    changed["status"] = vals["status"]
                elif vals["status"] not in ("A analyser", existing["status"]):
                    conflict = f"[Fusion CSV - autre statut historique : {vals['status']}]"
                    if conflict not in notes:
                        notes = notes + "\n\n" + conflict if notes else conflict
                if vals["priority"] == "Haute" and existing["priority"] != "Haute":
                    changed["priority"] = "Haute"
                for key in ("last_action", "next_action"):
                    if vals[key] and (not existing[key] or (key == "last_action" and vals[key] > existing[key])
                                      or (key == "next_action" and vals[key] < existing[key])):
                        changed[key] = vals[key]
                if notes != existing["notes"]:
                    changed["notes"] = notes
            if vals["last_seen"] > existing["last_seen"]:
                changed["last_seen"] = vals["last_seen"]
            if vals["detected_on"] < existing["detected_on"]:
                changed["detected_on"] = vals["detected_on"]
            if known_group_relation(vals["company"], existing["company"]) and \
                    normalize_company(existing["company"]) in ("richemont", "lvmh", "kering"):
                changed["company"] = vals["company"]
                changed["sector"] = vals["sector"] or existing["sector"]
            if preferred_primary(vals["source"], existing["source"]) and canonical_url(vals["link"]):
                changed["link"] = vals["link"]
                changed["source"] = vals["source"]
                changed["link_status"] = "Non vérifié"
                changed["link_checked_at"] = ""
            if changed:
                conn.execute(update(offers).where(offers.c.id == existing["id"]).values(**changed))
                if mode == "legacy" and any(k in changed for k in ("notes", "contact", "status", "priority", "last_action", "next_action")):
                    self._record_event(conn, existing["id"], "Données conservées lors de la fusion d'un doublon historique")
            self._add_link(conn, existing["id"], vals["link"], vals["source"])
            for a in alt_links:
                self._add_link(conn, existing["id"], a["url"], a["source"])
            return False

        now = utc_now()
        new_id = str(uuid.uuid4())
        conn.execute(insert(offers).values(
            id=new_id, **vals, link_status="Non vérifié", link_checked_at="",
            created_at=now, updated_at=now
        ))
        self._add_link(conn, new_id, vals["link"], vals["source"])
        for a in alt_links:
            self._add_link(conn, new_id, a["url"], a["source"])
        self._record_event(conn, new_id, "Import du CRM historique" if mode == "legacy" else
                           "Ajout manuel" if mode == "manual" else "Nouvelle offre détectée")
        return True

    def import_csv(self, path: str | Path, mode: str = "feed") -> int:
        p = Path(path)
        if not p.exists():
            return 0
        raw = p.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        key = "legacy_imported" if mode == "legacy" else "feed_import_digest"
        with self.engine.begin() as conn:
            if self._get_setting(conn, key) and mode == "legacy":
                return 0
            if self._get_setting(conn, key) == digest:
                return 0
            df = pd.read_csv(p, dtype=str, keep_default_na=False)
            if not {"Titre", "Entreprise", "Pays"}.issubset(df.columns):
                raise ValueError(f"En-têtes requis absents dans {p.name}")
            added = 0
            for row in df.to_dict(orient="records"):
                added += self._insert_or_match(conn, _row_values(row), mode=mode)
            self._set_setting(conn, key, "1" if mode == "legacy" else digest)
        self.backup_local()
        return added

    def purge_non_offers(self) -> int:
        """Supprime les faux positifs deja importes (articles, profils, listes).

        Seules les fiches automatiques JAMAIS touchees sont concernees : statut
        « A analyser », aucune note, aucun contact, aucune action. Tout ce que
        l'utilisateur a modifie est conserve.
        """
        removed = 0
        with self.engine.begin() as conn:
            rows = conn.execute(select(offers).where(
                (offers.c.is_manual == 0) & (offers.c.status == "A analyser")
                & (offers.c.notes == "") & (offers.c.contact == "")
                & (offers.c.last_action == "") & (offers.c.next_action == "")
            )).mappings().all()
            for row in rows:
                if est_une_offre(row["title"], row["link"]):
                    continue
                conn.execute(delete(links).where(links.c.offer_id == row["id"]))
                conn.execute(delete(history).where(history.c.offer_id == row["id"]))
                conn.execute(delete(offers).where(offers.c.id == row["id"]))
                removed += 1
        return removed

    def bootstrap(self, root: str | Path = ROOT) -> dict:
        root = Path(root)
        self.purge_non_offers()
        return {
            "legacy": self.import_csv(root / "offres_emploi.csv", mode="legacy"),
            "feed": self.import_csv(root / "offres_detectees.csv", mode="feed"),
        }

    def add_manual(self, row: dict) -> bool:
        """Ajout a la main (reseau, chasseur, ou lien LinkedIn colle)."""
        mapped = _row_values({
            "Titre": row.get("title", ""), "Entreprise": row.get("company", ""),
            "Secteur": row.get("sector", ""), "Pays": row.get("country", ""),
            "Source": manual_source(row.get("link", ""), row.get("source", "")),
            "Lien": row.get("link", ""),
            "Niveau estimé": "Direction fonctionnelle",
            "Date de détection": date.today().isoformat(),
            "Statut": row.get("status", "A postuler"),
            "Priorité": row.get("priority", "Moyenne"),
            "Contact / Chasseur": row.get("contact", ""),
            "Date dernière action": row.get("last_action", ""),
            "Date prochaine action": row.get("next_action", ""),
            "Notes": row.get("notes", ""),
        })
        mapped["is_manual"] = 1
        with self.engine.begin() as conn:
            added = self._insert_or_match(conn, mapped, mode="manual")
        if added:
            self.backup_local()
        return added

    def list_offers(self) -> pd.DataFrame:
        with self.engine.connect() as conn:
            rows = [dict(r) for r in conn.execute(select(offers)).mappings()]
        return pd.DataFrame(rows, columns=[c.name for c in offers.c])

    def offer(self, offer_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(offers).where(offers.c.id == offer_id)).mappings().first()
        return dict(row) if row else None

    def links_for(self, offer_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(select(links).where(links.c.offer_id == offer_id)).mappings()]

    def timeline(self, offer_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(select(history).where(history.c.offer_id == offer_id)
                                                 .order_by(history.c.when_at.desc())).mappings()]

    def update_offer(self, offer_id: str, changes: dict, expected_updated_at: str | None = None) -> bool:
        allowed = {"status", "priority", "contact", "last_action", "next_action", "notes"}
        if set(changes) - allowed:
            raise ValueError("Champs CRM non autorisés")
        if "status" in changes and changes["status"] not in STATUSES:
            raise ValueError("Statut inconnu")
        if "priority" in changes and changes["priority"] not in PRIORITIES:
            raise ValueError("Priorité inconnue")
        for field in ("last_action", "next_action"):
            if field in changes and _str(changes[field]) and not _iso_date(changes[field]):
                raise ValueError("Date attendue : AAAA-MM-JJ")
        with self.engine.begin() as conn:
            current = conn.execute(select(offers).where(offers.c.id == offer_id)).mappings().first()
            if not current:
                raise KeyError("Offre introuvable")
            if expected_updated_at is not None and current["updated_at"] != expected_updated_at:
                raise ConcurrentEditError("Cette fiche a été modifiée ailleurs. Recharge-la avant d'enregistrer.")
            delta = {k: _str(v) for k, v in changes.items() if _str(v) != current[k]}
            if not delta:
                return False
            labels = {"status": "Statut", "priority": "Priorité", "contact": "Contact",
                      "last_action": "Dernière action", "next_action": "Prochaine action", "notes": "Notes"}
            message = "; ".join(
                f"{labels[k]} : {current[k]} → {v}" if k in ("status", "priority") else f"{labels[k]} modifié(e)"
                for k, v in delta.items()
            )
            conn.execute(update(offers).where(offers.c.id == offer_id).values(**delta, updated_at=utc_now()))
            self._record_event(conn, offer_id, message)
        self.backup_local()
        return True

    def record_link_check(self, offer_id: str, status: str, reason: str = "") -> None:
        """Vérification manuelle (bouton de la fiche) ou signalement « lien mort » par papa."""
        if status not in LINK_STATUSES:
            raise ValueError("Statut de lien inconnu")
        with self.engine.begin() as conn:
            conn.execute(update(offers).where(offers.c.id == offer_id).values(
                link_status=status, link_checked_at=utc_now()
            ))
            self._record_event(conn, offer_id, f"Vérification du lien : {status}" + (f" — {reason}" if reason else ""))
        self.backup_local()

    def offers_to_check(self, older_than_hours: int = 20) -> list[dict]:
        """Offres encore ouvertes à revérifier : jamais vérifiées, ou pas depuis X heures.

        Une offre écartée ou refusée n'est plus vérifiée (inutile de solliciter les sites).
        Chaque offre arrive avec TOUS ses liens (principal + alternatifs).
        """
        limite = datetime.now(timezone.utc).timestamp() - older_than_hours * 3600
        out = []
        with self.engine.connect() as conn:
            rows = conn.execute(select(offers).where(offers.c.status.notin_(CLOSED_STATUSES))).mappings()
            for r in rows:
                if not str(r["link"]).startswith(("http://", "https://")):
                    continue
                vu = r["link_checked_at"]
                try:
                    recent = vu and datetime.fromisoformat(vu).timestamp() > limite
                except ValueError:
                    recent = False
                if recent:
                    continue
                alts = [dict(a) for a in conn.execute(select(links.c.url, links.c.source)
                                                      .where(links.c.offer_id == r["id"])).mappings()]
                out.append({**dict(r), "alternates": [a for a in alts if a["url"] != r["link"]]})
        return out

    def apply_link_verdicts(self, offer_id: str, verdicts: dict) -> str:
        """Applique le résultat de la vérification à UNE offre. Renvoie ce qui s'est passé.

        Étape par étape :
          1. lien principal vivant -> on note juste le statut (« Accessible », « À vérifier ») ;
          2. lien principal mort, mais un autre lien de la même offre est ouvert
             -> il devient le lien principal : papa ne clique plus sur une annonce morte ;
          3. tous les liens connus sont morts -> statut « Offre expirée » / « Lien redirigé ».
             Si papa n'y avait pas encore touché (« A analyser »), l'offre passe en
             « Écarté » avec une note : elle quitte la liste mais reste consultable.
             Une candidature déjà en cours n'est JAMAIS déplacée : seul un bandeau prévient.
        Résultats possibles : "inchange", "ok", "remplace", "expiree", "ecartee".
        """
        with self.engine.begin() as conn:
            offer = conn.execute(select(offers).where(offers.c.id == offer_id)).mappings().first()
            if not offer:
                return "inchange"
            verdict = verdicts.get(offer["link"])
            if verdict is None:
                return "inchange"
            now = utc_now()
            if not verdict.mort:
                conn.execute(update(offers).where(offers.c.id == offer_id).values(
                    link_status=verdict.statut, link_checked_at=now))
                if verdict.statut != offer["link_status"] and offer["link_status"] in DEAD_LINK_STATUSES:
                    self._record_event(conn, offer_id, f"Lien de nouveau accessible : {verdict.statut}")
                return "ok"
            autres = [dict(a) for a in conn.execute(select(links.c.url, links.c.source)
                                                    .where(links.c.offer_id == offer_id)).mappings()
                      if a["url"] != offer["link"]]
            ouverts = [a for a in autres
                       if verdicts.get(a["url"]) is not None and verdicts[a["url"]].statut == "Accessible"]
            if ouverts:
                ouverts.sort(key=lambda a: SOURCE_RANK.get(a["source"], 0), reverse=True)
                nouveau = ouverts[0]
                conn.execute(update(offers).where(offers.c.id == offer_id).values(
                    link=nouveau["url"], source=nouveau["source"], link_status="Accessible",
                    link_checked_at=now, updated_at=now))
                self._record_event(conn, offer_id, f"Lien principal mort ({verdict.raison}) : "
                                                   f"remplacé par l'annonce {nouveau['source']}")
                return "remplace"
            changes = {"link_status": verdict.statut, "link_checked_at": now}
            resultat = "expiree"
            if offer["status"] == "A analyser":
                note = f"[Auto {date.today().strftime('%d/%m')}] {verdict.statut} : {verdict.raison}"
                changes.update(status="Ecarte", updated_at=now,
                               notes=f"{note}\n\n{offer['notes']}" if offer["notes"] else note)
                resultat = "ecartee"
            conn.execute(update(offers).where(offers.c.id == offer_id).values(**changes))
            if offer["link_status"] != verdict.statut:
                self._record_event(conn, offer_id, f"Vérification du lien : {verdict.statut} — {verdict.raison}")
            if resultat == "ecartee":
                self._record_event(conn, offer_id, "Statut : À analyser → Écarté (offre expirée, automatique)")
        return resultat

    def verify_open_offers(self, verifier=None, older_than_hours: int = 20, on_progress=None) -> dict:
        """Revérifie toutes les offres ouvertes et applique les verdicts. Renvoie le bilan."""
        from link_health import verifier_lot
        a_verifier = self.offers_to_check(older_than_hours)
        items = []
        for o in a_verifier:
            items.append((o["link"], o["title"]))
            items.extend((a["url"], o["title"]) for a in o["alternates"])
        verdicts = (verifier or verifier_lot)(items, on_progress=on_progress) if items else {}
        bilan = {"verifiees": len(a_verifier), "remplace": 0, "expiree": 0, "ecartee": 0, "ok": 0, "inchange": 0}
        for o in a_verifier:
            bilan[self.apply_link_verdicts(o["id"], verdicts)] += 1
        if a_verifier:
            self.backup_local()
        return bilan

    def is_notified(self, kind: str, item_key: str) -> bool:
        with self.engine.connect() as conn:
            return bool(conn.execute(select(notifications.c.id).where(
                (notifications.c.kind == kind) & (notifications.c.item_key == item_key))).first())

    def mark_notified(self, kind: str, item_key: str) -> None:
        with self.engine.begin() as conn:
            exists = conn.execute(select(notifications.c.id).where(
                (notifications.c.kind == kind) & (notifications.c.item_key == item_key))).first()
            if not exists:
                conn.execute(insert(notifications).values(id=str(uuid.uuid4()), kind=kind,
                                                           item_key=item_key, sent_at=utc_now()))
        self.backup_local()

    # ------------------------------------------------------------------ #
    #  Réseau, sociétés cibles, préparation entretien                     #
    #  CRUD générique : une table + un jeu de champs autorisés par entité #
    # ------------------------------------------------------------------ #
    def _list(self, table: Table) -> pd.DataFrame:
        with self.engine.connect() as conn:
            rows = [dict(r) for r in conn.execute(select(table)).mappings()]
        return pd.DataFrame(rows, columns=[c.name for c in table.c])

    def _insert_row(self, table: Table, values: dict) -> str:
        now = utc_now()
        new_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            conn.execute(insert(table).values(id=new_id, created_at=now, updated_at=now, **values))
        self.backup_local()
        return new_id

    def _update_row(self, table: Table, row_id: str, changes: dict) -> bool:
        clean = {k: _str(v) for k, v in changes.items()}
        with self.engine.begin() as conn:
            current = conn.execute(select(table).where(table.c.id == row_id)).mappings().first()
            if not current:
                raise KeyError("Élément introuvable")
            delta = {k: v for k, v in clean.items() if v != current[k]}
            if not delta:
                return False
            conn.execute(update(table).where(table.c.id == row_id).values(**delta, updated_at=utc_now()))
        self.backup_local()
        return True

    def _delete_row(self, table: Table, row_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(table).where(table.c.id == row_id))
        self.backup_local()

    # Réseau & chasseurs -------------------------------------------------
    def list_contacts(self) -> pd.DataFrame:
        return self._list(contacts)

    def add_contact(self, data: dict) -> str:
        if not _str(data.get("name")):
            raise ValueError("Le nom du contact est requis.")
        kind = data.get("kind") if data.get("kind") in CONTACT_KINDS else "Réseau / Ancien collègue"
        return self._insert_row(contacts, {
            "name": _str(data.get("name")), "kind": kind, "company": _str(data.get("company")),
            "role": _str(data.get("role")), "email": _str(data.get("email")),
            "phone": _str(data.get("phone")), "country": _str(data.get("country")),
            "last_contact": _iso_date(data.get("last_contact")),
            "next_contact": _iso_date(data.get("next_contact")),
            "notes": _str(data.get("notes")),
        })

    def update_contact(self, contact_id: str, changes: dict) -> bool:
        allowed = {"name", "kind", "company", "role", "email", "phone", "country",
                   "last_contact", "next_contact", "notes"}
        if set(changes) - allowed:
            raise ValueError("Champs contact non autorisés")
        if "kind" in changes and changes["kind"] not in CONTACT_KINDS:
            raise ValueError("Type de contact inconnu")
        for f in ("last_contact", "next_contact"):
            if f in changes and _str(changes[f]) and not _iso_date(changes[f]):
                raise ValueError("Date attendue : AAAA-MM-JJ")
        return self._update_row(contacts, contact_id, changes)

    def delete_contact(self, contact_id: str) -> None:
        self._delete_row(contacts, contact_id)

    # Sociétés cibles ----------------------------------------------------
    def list_targets(self) -> pd.DataFrame:
        return self._list(target_companies)

    def add_target(self, data: dict) -> str:
        if not _str(data.get("name")):
            raise ValueError("Le nom de la société est requis.")
        status = data.get("status") if data.get("status") in TARGET_STATUSES else "À approcher"
        priority = data.get("priority") if data.get("priority") in PRIORITIES else "Moyenne"
        return self._insert_row(target_companies, {
            "name": _str(data.get("name")), "country": _str(data.get("country")),
            "sector": _str(data.get("sector")), "priority": priority, "status": status,
            "notes": _str(data.get("notes")),
        })

    def update_target(self, target_id: str, changes: dict) -> bool:
        allowed = {"name", "country", "sector", "priority", "status", "notes"}
        if set(changes) - allowed:
            raise ValueError("Champs société non autorisés")
        if "status" in changes and changes["status"] not in TARGET_STATUSES:
            raise ValueError("Statut société inconnu")
        if "priority" in changes and changes["priority"] not in PRIORITIES:
            raise ValueError("Priorité inconnue")
        return self._update_row(target_companies, target_id, changes)

    def delete_target(self, target_id: str) -> None:
        self._delete_row(target_companies, target_id)

    # Préparation entretien ----------------------------------------------
    def list_prep(self) -> pd.DataFrame:
        return self._list(interview_prep)

    def add_prep(self, data: dict) -> str:
        if not _str(data.get("company")):
            raise ValueError("La maison est requise.")
        return self._insert_row(interview_prep, {
            "company": _str(data.get("company")), "role": _str(data.get("role")),
            "interview_date": _iso_date(data.get("interview_date")),
            "offer_id": _str(data.get("offer_id")), "research": _str(data.get("research")),
            "questions": _str(data.get("questions")), "notes": _str(data.get("notes")),
        })

    def update_prep(self, prep_id: str, changes: dict) -> bool:
        allowed = {"company", "role", "interview_date", "offer_id", "research", "questions", "notes"}
        if set(changes) - allowed:
            raise ValueError("Champs préparation non autorisés")
        if "interview_date" in changes and _str(changes["interview_date"]) and not _iso_date(changes["interview_date"]):
            raise ValueError("Date attendue : AAAA-MM-JJ")
        return self._update_row(interview_prep, prep_id, changes)

    def delete_prep(self, prep_id: str) -> None:
        self._delete_row(interview_prep, prep_id)

    def backup_local(self) -> str | None:
        """Copie SQLite coherente après écriture, dans un dossier non versionné.

        Le backup est remplacé au fil de la journée et 14 snapshots sont conservés.
        """
        if not self.is_local:
            return None
        source = Path(self.engine.url.database or "")
        target_dir = source.parent / "backups"
        temp_path = None
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            backup_path = target_dir / f"crm_{date.today().isoformat()}.sqlite3"
            temp_path = target_dir / f".{backup_path.name}.{uuid.uuid4().hex}.tmp"
            with closing(sqlite3.connect(source)) as source_connection:
                with closing(sqlite3.connect(temp_path)) as backup_connection:
                    source_connection.backup(backup_connection)
            os.replace(temp_path, backup_path)
            for expired in sorted(target_dir.glob("crm_*.sqlite3"), reverse=True)[14:]:
                expired.unlink()
            self.backup_error = ""
            return str(backup_path)
        except (OSError, sqlite3.Error) as exc:
            self.backup_error = str(exc)
            logging.warning("Sauvegarde automatique SQLite indisponible : %s", exc)
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return None

    def close(self) -> None:
        self.engine.dispose()
