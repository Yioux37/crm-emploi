"""Tests hors reseau : dedup, pays, CRM, historique et notifications."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matching import canonical_url, country_from_location, same_opportunity
from merge_feed import merge_feed
from scoring import calculate_score
from storage import CRMStore, ConcurrentEditError, SCRAPER_COLUMNS
from notifications import collect_alerts, compose


def job(company="Hermès", title="Directeur Supply Chain", country="France", link="https://jobs.example.com/job/123"):
    return {
        "Titre": title, "Entreprise": company, "Secteur": "Textile / Couture, Luxe",
        "Pays": country, "Source": "LinkedIn (Offres)", "Lien": link,
        "Niveau estimé": "Direction fonctionnelle", "Date de détection": "2026-11-16",
    }


class MatchingTests(unittest.TestCase):
    def test_linkedin_search_switzerland_does_not_override_paris(self):
        self.assertEqual(country_from_location("Paris, France"), "France")
        self.assertEqual(country_from_location("Geneva, Switzerland"), "Suisse")
        self.assertEqual(country_from_location("Milano, Italia"), "Italie")

    def test_ambiguity_not_guessed(self):
        self.assertIsNone(country_from_location("France et Suisse"))
        self.assertIsNone(country_from_location("Poste remote"))
        self.assertIsNone(country_from_location("Paris, France", "CH"))

    def test_country_not_from_link(self):
        from scraper import verifier_pays_strict
        self.assertEqual(verifier_pays_strict("Paris", lien="https://ch.linkedin.com/jobs/view/123"), "France")

    def test_url_normalization(self):
        a = "https://fr.linkedin.com/jobs/view/assistant-director-at-x-1234567890?utm_source=mail"
        b = "https://ch.linkedin.com/jobs/view/different-job-at-y-1234567890"
        self.assertEqual(canonical_url(a), canonical_url(b))

    def test_group_child_specific_identifier_deduplicated(self):
        a = {"title": "Responsable Logistique VDJ", "company": "Richemont", "country": "Suisse", "link": "https://ats.example.org/job/JR567"}
        b = {"title": "Responsable Logistique VDJ", "company": "Vacheron Constantin", "country": "Suisse", "link": "https://linkedin.com/jobs/view/role-1234567891"}
        self.assertTrue(same_opportunity(a, b))

    def test_generic_roles_at_different_brands_are_distinct(self):
        a = {"title": "Head of Supply Chain", "company": "Richemont", "country": "Suisse", "link": "https://jobs.example.org/a"}
        b = {"title": "Head of Supply Chain", "company": "Vacheron Constantin", "country": "Suisse", "link": "https://jobs.example.org/b"}
        self.assertFalse(same_opportunity(a, b))

    def test_score_has_explanation_and_preferences(self):
        o = {"title": "Directeur Supply Chain", "company": "Hermès", "sector": "Textile / Couture, Luxe",
             "country": "France", "level": "Direction fonctionnelle", "detected_on": "2026-11-16"}
        score, reasons = calculate_score(o, today=date(2026, 11, 17))
        self.assertGreaterEqual(score, 85)
        self.assertTrue(any("Métier" in r for r in reasons))
        changed, _ = calculate_score(o, {"preferred_countries": [], "preferred_sectors": []}, today=date(2026, 11, 17))
        self.assertLess(changed, score)


class FeedAndStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.store = CRMStore(db_path=self.root / "crm.sqlite3")
        self.addCleanup(self.store.close)

    def csv(self, filename: str, records: list[dict]) -> Path:
        path = self.root / filename
        pd.DataFrame(records).to_csv(path, index=False)
        return path

    def test_merge_feed_preserves_alternate_link(self):
        a = job("Richemont", "Responsable Logistique VDJ", "Suisse", "https://ats.example.com/jobs/VDJ")
        b = job("Vacheron Constantin", "Responsable Logistique VDJ", "Suisse", "https://linkedin.com/jobs/view/role-1234567891")
        merged = merge_feed([], [a, b], "2026-11-17")
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["Entreprise"], "Vacheron Constantin")
        self.assertEqual(len(json.loads(merged[0]["Liens alternatifs"])), 1)

    def test_import_preserves_notes_status_and_action_dates(self):
        legacy = job()
        legacy.update({"Statut": "🗣️ Entretien 1", "Priorité": "🔴 Haute", "Notes": "Ne pas perdre cette note",
                       "Contact / Chasseur": "Recruteur X", "Date dernière action": "2026-11-15"})
        self.csv("offres_emploi.csv", [legacy])
        self.assertEqual(self.store.import_csv(self.root / "offres_emploi.csv", mode="legacy"), 1)
        row = self.store.list_offers().iloc[0]
        self.assertEqual(row["status"], "Entretien 1")
        self.assertEqual(row["contact"], "Recruteur X")
        self.assertEqual(row["notes"], "Ne pas perdre cette note")
        self.store.update_offer(row["id"], {"next_action": "2026-11-22", "notes": "Notes personnelles modifiées"}, row["updated_at"])
        scan = job(link="https://jobs.example.com/job/123?utm_campaign=tracker")
        self.csv("offres_detectees.csv", [scan])
        self.assertEqual(self.store.import_csv(self.root / "offres_detectees.csv"), 0)
        newer = self.store.list_offers().iloc[0]
        self.assertEqual(newer["notes"], "Notes personnelles modifiées")
        self.assertEqual(newer["next_action"], "2026-11-22")
        self.assertEqual(newer["status"], "Entretien 1")
        self.assertEqual(len(self.store.timeline(row["id"])), 2)

    def test_reimport_idempotence(self):
        self.csv("offres_detectees.csv", [job()])
        self.assertEqual(self.store.import_csv(self.root / "offres_detectees.csv"), 1)
        self.assertEqual(self.store.import_csv(self.root / "offres_detectees.csv"), 0)
        self.assertEqual(len(self.store.list_offers()), 1)

    def test_source_links_preserved(self):
        a = job(link="https://jobs.example.com/job/123")
        a["Liens alternatifs"] = json.dumps([{"url": "https://linkedin.com/jobs/view/abc-1234567891", "source": "LinkedIn (Offres)"}])
        self.csv("offres_detectees.csv", [a])
        self.store.import_csv(self.root / "offres_detectees.csv")
        self.assertEqual(len(self.store.links_for(self.store.list_offers().iloc[0]["id"])), 2)

    def test_prevent_concurrent_edit_and_invalid_dates(self):
        self.csv("offres_detectees.csv", [job()])
        self.store.import_csv(self.root / "offres_detectees.csv")
        row = self.store.list_offers().iloc[0]
        self.store.update_offer(row["id"], {"status": "A postuler"}, row["updated_at"])
        with self.assertRaises(ConcurrentEditError):
            self.store.update_offer(row["id"], {"status": "Ecarte"}, row["updated_at"])
        with self.assertRaises(ValueError):
            self.store.update_offer(row["id"], {"next_action": "demain"})

    def test_manual_relaunch_is_due(self):
        self.assertTrue(self.store.add_manual({
            "title": "Directeur Operations", "company": "Prada",
            "country": "Italie", "sector": "Luxe", "status": "A postuler",
            "next_action": "2026-11-17", "priority": "Haute",
        }))
        self.assertEqual(len(collect_alerts(self.store, date(2026, 11, 17))["due"]), 1)
        subject, message, _ = compose(self.store, "daily", date(2026, 11, 17))
        self.assertIn("Prada", message)
        self.assertIn("2026-11-17", subject)


if __name__ == "__main__":
    unittest.main()


class SafetyAndScanTests(unittest.TestCase):
    def test_import_merges_two_legacy_notes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            s = CRMStore(db_path=root / "my.sqlite3")
            left = job("Richemont", "Responsable Logistique VDJ", "Suisse", "https://ats.example.com/job/123")
            left.update({"Notes": "Note ATS", "Contact / Chasseur": "Contact 1", "Statut": "🆕 À analyser"})
            right = job("Vacheron Constantin", "Responsable Logistique VDJ", "Suisse", "https://linkedin.com/jobs/view/role-1234567891")
            right.update({"Notes": "Note LinkedIn", "Contact / Chasseur": "Contact 2", "Statut": "🗣️ Entretien 1"})
            pd.DataFrame([left, right]).to_csv(root / "offres_emploi.csv", index=False)
            self.assertEqual(s.import_csv(root / "offres_emploi.csv", mode="legacy"), 1)
            result = s.list_offers().iloc[0]
            self.assertIn("Note ATS", result["notes"])
            self.assertIn("Note LinkedIn", result["notes"])
            self.assertIn("Contact 1", result["contact"])
            self.assertIn("Contact 2", result["contact"])
            self.assertEqual(result["status"], "Entretien 1")
            s.close()

    def test_scan_does_not_touch_private_legacy_file(self):
        from unittest.mock import patch
        import scraper
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            legacy = root / "offres_emploi.csv"
            legacy.write_text("ma note personnelle ne doit pas changer\n", encoding="utf-8")
            original = legacy.read_bytes()
            with patch.object(scraper, "fetch_portails_directs", return_value=[job()]), \
                 patch.object(scraper, "fetch_ats_complementaires", return_value=[]), \
                 patch.object(scraper, "fetch_portails_specialises", return_value=[]):
                scan = scraper.executer_tout(str(root / "offres_detectees.csv"), str(root / "report.json"))
            self.assertEqual(legacy.read_bytes(), original)
            self.assertEqual(scan["annonces_nouvelles"], 1)
            self.assertNotIn("Notes", pd.read_csv(root / "offres_detectees.csv").columns)

    def test_failed_scan_keeps_previous_feed(self):
        from unittest.mock import patch
        import scraper
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            feed = root / "offres_detectees.csv"
            feed.write_text("Titre,Entreprise\nancien,intact\n", encoding="utf-8")
            before = feed.read_bytes()
            with patch.object(scraper, "fetch_portails_directs", return_value=[]), \
                 patch.object(scraper, "fetch_ats_complementaires", return_value=[]), \
                 patch.object(scraper, "fetch_portails_specialises", return_value=[]):
                result = scraper.executer_tout(str(feed), str(root / "report.json"))
            self.assertEqual(feed.read_bytes(), before)
            self.assertEqual(result["statut"], "aucune_offre_cible")
            self.assertEqual(result["annonces_nouvelles"], 0)
