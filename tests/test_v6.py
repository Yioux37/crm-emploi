"""Tests offline v6: collecteurs libres, erreurs DDGS, rapports et confidentialité."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import requests

import scraper
from sources_plus import (fetch_indexed_jobs, fetch_workable, fetch_recruitee,
                          fetch_public_ats)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class Session:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return Response(self.payload)


class FailingDDGS:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def text(self, query, max_results):
        self.calls.append(query)
        raise requests.ConnectionError('Network unavailable (test only)')


class NoHitsDDGS(FailingDDGS):
    def text(self, query, max_results):
        self.calls.append(query)
        return []


class V6PublicFeedTests(TestCase):
    def test_workable_public_feed(self):
        session = Session({'jobs': [{
            'title': 'Directeur Supply Chain', 'shortcode': 'ABC987',
            'location': {'city': 'Paris', 'country': 'France'},
        }]})
        items = fetch_workable(session, {'company': 'Hermès', 'account': 'hermes'})
        self.assertEqual(items[0]['url'], 'https://apply.workable.com/hermes/j/ABC987/')
        self.assertIsNotNone(scraper.normaliser_source_plus(items[0]))

    def test_recruitee_public_feed(self):
        session = Session({'offers': [{
            'title': 'Directeur des Operations', 'location': 'Genève, Suisse',
            'careers_url': 'https://maison.recruitee.com/o/directeur-operations',
        }]})
        items = fetch_recruitee(session, {'company': 'Rolex', 'account': 'maison'})
        self.assertEqual(len(items), 1)
        self.assertEqual(scraper.normaliser_source_plus(items[0])['Pays'], 'Suisse')

    def test_ats_diagnostic_is_specific_per_board(self):
        config = {'workable': [{'company': 'Hermès', 'account': 'hermes'}]}
        stats = {}
        items = fetch_public_ats(config=config, session=Session({'jobs': []}), stats=stats)
        self.assertEqual(items, [])
        self.assertEqual(stats['Workable / Hermès']['etat'], 'vide')
        self.assertEqual(stats['Workable / Hermès']['brutes'], 0)

    def test_ddgs_aborts_after_three_failures_and_reports_unchecked(self):
        engine = FailingDDGS()
        stats = {}
        rows = fetch_indexed_jobs(day=date(2026, 11, 17), budget=30,
                                  ddgs_factory=lambda: engine, sleep_seconds=0,
                                  stats=stats)
        self.assertEqual(rows, [])
        self.assertEqual(len(engine.calls), 3)
        self.assertEqual(sum(x['etat']=='erreur' for x in stats.values()), 3)
        self.assertEqual(sum(x['etat']=='non_interroge' for x in stats.values()), 27)
        self.assertIn('site:', engine.calls[0])
        self.assertNotIn(' OR ', engine.calls[0])

    def test_no_results_is_not_search_error(self):
        engine = NoHitsDDGS()
        stats = {}
        fetch_indexed_jobs(day=date(2026, 11, 17), budget=4,
                           ddgs_factory=lambda: engine, sleep_seconds=0, stats=stats)
        self.assertEqual(len(engine.calls), 4)
        self.assertEqual({s['etat'] for s in stats.values()}, {'vide'})

    def test_failures_preserve_feed_and_make_diagnostic_without_secrets(self):
        with TemporaryDirectory() as folder:
            feed = Path(folder) / 'offres_detectees.csv'
            report = Path(folder) / 'scan_rapport.json'
            feed.write_text('Titre,Entreprise\nOriginal,Hermès\n')
            before = feed.read_bytes()
            with patch.object(scraper, 'fetch_portails_directs', side_effect=RuntimeError('test error')), \
                 patch.object(scraper, 'fetch_ats_complementaires', return_value=[]), \
                 patch.object(scraper, 'fetch_portails_specialises', return_value=[]):
                result = scraper.executer_tout(str(feed), str(report))
            self.assertEqual(feed.read_bytes(), before)
            self.assertEqual(result['statut'], 'degrade')
            self.assertGreaterEqual(result['sources_en_erreur'], 1)
            self.assertNotIn('APP_PASSWORD', report.read_text())
            self.assertNotIn('DATABASE_URL', report.read_text())
            self.assertIn('etat_sources', json.loads(report.read_text()))


if __name__ == '__main__':
    import unittest
    unittest.main()
