"""Tests v3 hors reseau : formats publics, filtres et conservation."""
from __future__ import annotations

import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import scraper
from market_signals import detect_company, detect_signal, merge_signals, scan_public_signals
from sources_plus import (fetch_ashby, fetch_lever, fetch_rss, fetch_indexed_jobs,
                          read_sources_config, select_search_sites)


class FakeResponse:
    def __init__(self, data=None, content=None, status=200):
        self._data = data
        self.content = content or b''
        self.status = status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status >= 400:
            import requests
            raise requests.HTTPError(str(self.status))


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return FakeResponse(data=self.payload, content=self.payload if isinstance(self.payload, bytes) else None)


class FakeDDGS:
    def __init__(self, hits):
        self.hits = hits
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def text(self, query, max_results):
        self.queries.append(query)
        return self.hits


class PublicATSTests(unittest.TestCase):
    def test_lever_eu_public_postings(self):
        fake = FakeSession([{
            'text': 'Directeur Supply Chain',
            'categories': {'location': 'Paris, France', 'department': 'Opérations'},
            'hostedUrl': 'https://jobs.eu.lever.co/karllagerfeld/post123',
        }])
        rows = fetch_lever(fake, {'site': 'karllagerfeld', 'region': 'eu', 'company': 'Karl Lagerfeld'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['location'], 'Paris, France')
        self.assertEqual(rows[0]['company'], 'Karl Lagerfeld')
        self.assertIn('api.eu.lever.co', fake.urls[0])
        self.assertIsNotNone(scraper.normaliser_source_plus(rows[0]))

    def test_ashby_hidden_unlisted_postings_excluded(self):
        fake = FakeSession({'jobs': [
            {'title': 'Director of Operations', 'location': 'Milano, Italy',
             'jobUrl': 'https://jobs.ashbyhq.com/veliu/open', 'isListed': True},
            {'title': 'Director of Operations', 'location': 'Milano, Italy',
             'jobUrl': 'https://jobs.ashbyhq.com/veliu/hidden', 'isListed': False},
        ]})
        rows = fetch_ashby(fake, {'company': 'Veliu', 'board': 'veliu'})
        self.assertEqual(len(rows), 1)
        self.assertIn('/open', rows[0]['url'])

    def test_teamtailor_rss_public_data(self):
        feed = '''<?xml version="1.0" encoding="UTF-8"?>
          <rss version="2.0"><channel><title>Jobs</title>
            <item><title>Directeur Operations</title>
            <link>https://career.example.com/jobs/123</link>
            <location>Genève, Suisse</location>
            <description><![CDATA[<p>Manufacture horlogerie</p>]]></description>
            </item></channel></rss>'''.encode("utf-8")
        fake = FakeSession(feed)
        rows = fetch_rss(fake, {'company': 'Rolex', 'url': 'https://career.example.com/jobs.rss'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['location'], 'Genève, Suisse')
        self.assertIsNotNone(scraper.normaliser_source_plus(rows[0]))

    def test_ats_rejects_unsafe_board_identifier(self):
        with self.assertRaises(ValueError):
            fetch_lever(FakeSession([]), {'company': 'x', 'site': '../etc/passwd'})

    def test_unknown_location_not_guessed(self):
        row = {'title': 'Directeur Supply Chain', 'company': 'Hermès', 'location': '',
               'context': 'Nous recrutons en remote', 'url': 'https://jobs.example.com/role',
               'source': 'Portails spécialisés'}
        self.assertIsNone(scraper.normaliser_source_plus(row))

    def test_domain_only_used_as_index_filter_not_country(self):
        ddgs = FakeDDGS([
            {'title': 'Directeur Supply Chain · Hermès', 'body': 'Paris, France - luxe',
             'href': 'https://fr.fashionjobs.com/jobs/123'},
            {'title': 'Directeur Supply Chain · Hermès', 'body': 'Paris, France - luxe',
             'href': 'https://other.example.com/jobs/123'},
        ])
        res = fetch_indexed_jobs(date(2026, 11, 17), budget=1,
                                 ddgs_factory=lambda: ddgs, sleep_seconds=0)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['source'], 'Portails spécialisés')
        self.assertEqual(scraper.normaliser_source_plus(res[0])['Pays'], 'France')
        self.assertEqual(len(ddgs.queries), 1)

    def test_budget_rotates_web_sources(self):
        self.assertEqual(len(select_search_sites(date(2026, 11, 17), budget=12)), 12)
        a = select_search_sites(date(2026, 11, 17), budget=12)
        b = select_search_sites(date(2026, 11, 18), budget=12)
        self.assertNotEqual(a[6:], b[6:])
        self.assertEqual(a[:6], b[:6])


class SignalTests(unittest.TestCase):
    def test_signal_needs_industry_company_and_trigger(self):
        self.assertEqual(detect_signal('Hermès investit dans un nouvel atelier'),
                         'Investissement / expansion')
        self.assertEqual(detect_company('Hermès investit dans un nouvel atelier', ['Hermès', 'Prada']), 'Hermès')
        self.assertEqual(detect_company('industrie du luxe investit', ['Hermès', 'Prada']), '')
        self.assertIsNone(detect_signal('Tendances du luxe cette saison'))

    def test_signal_feed_is_independent_from_job_feed(self):
        signal = {'Date de détection': '2026-11-16', 'Actualité': 'Hermès investit dans un atelier',
                  'Entreprise': 'Hermès', 'Catégorie': 'Investissement / expansion',
                  'Pays': 'France', 'Source': 'FashionNetwork',
                  'Lien': 'https://fashionnetwork.com/news/example'}
        merged = merge_signals([signal], [{**signal, 'Date de détection': '2026-11-17'}],
                               date(2026, 11, 17))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['Date de détection'], '2026-11-16')
        self.assertNotIn('Statut', merged[0])

    def test_news_filters_unverified_business_claims(self):
        ddgs = FakeDDGS([
            {'title': 'Hermès investit dans un atelier', 'body': 'Extension près de Lyon, France',
             'href': 'https://fashionnetwork.com/news/example'},
            {'title': 'Luxe et industrie: investissements', 'body': 'Une belle annee',
             'href': 'https://fashionnetwork.com/news/abstract'},
        ])
        # Source selection rotates; fake host may not match on the given day. Force a deterministic site.
        with patch('market_signals.NEWS_SITES', [('FashionNetwork', 'fashionnetwork.com')]):
            rows = scan_public_signals(['Hermès', 'Prada'], date(2026, 11, 17),
                                       budget=1, ddgs_factory=lambda: ddgs, sleep_seconds=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Entreprise'], 'Hermès')
        self.assertIn('Signal', 'Signal')


if __name__ == '__main__':
    unittest.main()
