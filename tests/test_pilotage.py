"""Tests des briques de pilotage actif : réseau, sociétés cibles, préparation entretien."""
from __future__ import annotations

import os
import tempfile
from unittest import TestCase

from storage import CONTACT_KINDS, PRIORITIES, TARGET_STATUSES, CRMStore


class PilotageTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = CRMStore(db_path=os.path.join(self.dir, "crm.sqlite3"))

    # Réseau & chasseurs ------------------------------------------------
    def test_contact_crud(self):
        cid = self.store.add_contact({
            "name": "Claire Chasseuse", "kind": "Chasseur de têtes",
            "company": "Egon Zehnder", "next_contact": "2026-11-28"})
        df = self.store.list_contacts()
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["company"], "Egon Zehnder")
        self.assertTrue(self.store.update_contact(cid, {"last_contact": "2026-11-20"}))
        self.assertFalse(self.store.update_contact(cid, {"last_contact": "2026-11-20"}))
        self.store.delete_contact(cid)
        self.assertEqual(len(self.store.list_contacts()), 0)

    def test_contact_requires_name_and_valid_kind(self):
        with self.assertRaises(ValueError):
            self.store.add_contact({"name": "  "})
        cid = self.store.add_contact({"name": "X"})
        with self.assertRaises(ValueError):
            self.store.update_contact(cid, {"kind": "Inexistant"})
        with self.assertRaises(ValueError):
            self.store.update_contact(cid, {"next_contact": "demain"})

    def test_contact_default_kind_is_valid(self):
        cid = self.store.add_contact({"name": "Sans type"})
        self.assertIn(self.store.list_contacts().iloc[0]["kind"], CONTACT_KINDS)

    # Sociétés cibles ----------------------------------------------------
    def test_target_crud_and_validation(self):
        tid = self.store.add_target({"name": "Patek Philippe", "country": "Suisse",
                                     "priority": "Haute", "status": "À approcher"})
        self.assertEqual(self.store.list_targets().iloc[0]["priority"], "Haute")
        self.assertTrue(self.store.update_target(tid, {"status": "En discussion"}))
        self.assertEqual(self.store.list_targets().iloc[0]["status"], "En discussion")
        with self.assertRaises(ValueError):
            self.store.update_target(tid, {"status": "Pas un statut"})
        self.store.delete_target(tid)
        self.assertEqual(len(self.store.list_targets()), 0)

    def test_target_coerces_unknown_values_on_add(self):
        self.store.add_target({"name": "Maison X", "status": "n'importe quoi", "priority": "zzz"})
        row = self.store.list_targets().iloc[0]
        self.assertIn(row["status"], TARGET_STATUSES)
        self.assertIn(row["priority"], PRIORITIES)

    # Préparation entretien ----------------------------------------------
    def test_prep_crud(self):
        pid = self.store.add_prep({"company": "Cartier", "role": "Directeur Industriel",
                                   "interview_date": "2026-12-03", "questions": "Organisation des ateliers ?"})
        df = self.store.list_prep()
        self.assertEqual(df.iloc[0]["company"], "Cartier")
        self.assertEqual(df.iloc[0]["interview_date"], "2026-12-03")
        self.assertTrue(self.store.update_prep(pid, {"research": "Manufacture à La Chaux-de-Fonds"}))
        self.store.delete_prep(pid)
        self.assertEqual(len(self.store.list_prep()), 0)

    def test_prep_requires_company(self):
        with self.assertRaises(ValueError):
            self.store.add_prep({"company": "", "role": "X"})

    def test_tables_isolated_from_offers(self):
        # Les nouvelles tables ne perturbent pas la table des offres.
        self.store.add_contact({"name": "A"})
        self.store.add_target({"name": "B"})
        self.store.add_prep({"company": "C"})
        self.assertTrue(self.store.list_offers().empty)
