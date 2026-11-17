"""Focused v4 tests: source coverage, public ATS, and practical market guidance."""
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from source_catalog import SEARCH_SITES, NEWS_SITES, catalog_totals
from sources_plus import fetch_greenhouse, fetch_smartrecruiters, select_search_sites
from market_signals import signal_guidance


class Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


class Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.payload)


class V4Sources(unittest.TestCase):
    def test_catalog_covers_three_countries_and_many_channels(self):
        counts = catalog_totals()
        self.assertEqual(counts['index_targets'], len(SEARCH_SITES))
        self.assertGreaterEqual(counts['index_targets'], 100)
        self.assertGreaterEqual(counts['news_targets'], 15)
        self.assertEqual(counts['priority_daily'], 12)
        self.assertEqual(len({site[1] for site in SEARCH_SITES}), len(SEARCH_SITES))
        self.assertTrue(any(x[1] == 'ceruleanjobs.ch' for x in SEARCH_SITES))
        self.assertTrue(any(x[1] == 'luxurytalents.com' for x in SEARCH_SITES))
        self.assertTrue(any(x[1] == 'pambianconews.com' for x in NEWS_SITES))

    def test_rotation_covers_whole_catalog_over_time(self):
        seen = set()
        for offset in range(20):
            chosen = select_search_sites(date(2026, 11, 17) + timedelta(days=offset), budget=20)
            self.assertEqual(len(chosen), 20)
            seen.update(site[1] for site in chosen)
        self.assertEqual(len(seen), len(SEARCH_SITES))

    def test_greenhouse_only_public_posts(self):
        session = Session({'jobs': [
            {'title': 'Directeur Supply Chain', 'absolute_url':
             'https://job-boards.greenhouse.io/jacquemus/jobs/123',
             'location': {'name': 'Paris, France'}, 'departments': [{'name': 'Operations'}]}
        ]})
        rows = fetch_greenhouse(session, {'company': 'Jacquemus', 'board': 'jacquemus'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['company'], 'Jacquemus')
        self.assertEqual(rows[0]['location'], 'Paris, France')
        self.assertIn('boards-api.greenhouse.io', session.calls[0][0])

    def test_smartrecruiters_public_fields_and_url(self):
        session = Session({'content': [
            {'name': 'Director Operations', 'id': 'post123',
             'location': {'city': 'Milano', 'country': 'IT'}}
        ]})
        rows = fetch_smartrecruiters(session,
                {'company': 'Breitling', 'company_id': 'Breitling'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['country_field'], 'IT')
        self.assertEqual(rows[0]['url'],
                         'https://jobs.smartrecruiters.com/Breitling/post123')

    def test_smartrecruiters_ignores_bad_job_id(self):
        session = Session({'content': [
            {'id': '../admin', 'name': 'Director', 'location': {'city': 'Paris', 'country': 'FR'}}
        ]})
        self.assertEqual(fetch_smartrecruiters(session,
                         {'company': 'Test', 'company_id': 'Test'}), [])

    def test_market_signal_guidance_is_hypothesis_not_vacancy(self):
        for label in ('Investissement / expansion', 'Recrutement / reorganisation',
                      'Acquisition / rapprochement', 'Transformation industrielle'):
            title, action = signal_guidance(label)
            self.assertTrue(title)
            self.assertTrue('verifier' in action.lower() or 'confirmer' in action.lower())

    def test_father_guide_and_source_page_exist(self):
        app_code = (Path(__file__).resolve().parents[1] / 'app.py').read_text()
        self.assertIn('elif page == "Guide simple":', app_code)
        self.assertIn('elif page == "Sources surveill', app_code)
        self.assertIn('aucun poste ouvert', app_code.lower())


if __name__ == '__main__':
    unittest.main()
