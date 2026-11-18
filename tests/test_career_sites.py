"""Tests hors ligne des connecteurs SuccessFactors et Oracle Recruiting."""
from __future__ import annotations

import json
from unittest import TestCase

import scraper
from sources_plus import (fetch_oracle_recruiting, fetch_public_ats, fetch_successfactors,
                          parse_successfactors_search, read_sources_config)

SF_HTML = """
<table><tbody>
<tr class="data-row">
  <td><span class="jobTitle hidden-phone">
    <a class="jobTitle-link" href="/job/Milano-Supply-Chain-Director/1293231601/">Supply Chain Director</a></span></td>
  <td><span class="jobLocation">Milano, IT</span></td>
  <td><span class="jobDate">18 nov. 2026</span></td>
</tr>
<tr class="data-row">
  <td><a class="jobTitle-link" href="/job/Paris-Client-Advisor/1293231602/">Client Advisor</a></td>
  <td><span class="jobLocation">Paris, FR</span></td>
</tr>
</tbody></table>
"""

ORACLE_JSON = {"items": [{"TotalJobsCount": 2, "requisitionList": [
    {"Id": "102345", "Title": "Directeur Supply Chain Maroquinerie (H/F)",
     "PrimaryLocation": "Pantin, Île-de-France, France", "PrimaryLocationCountry": "FR",
     "PostedDate": "2026-11-15", "ShortDescriptionStr": "Pilotage des flux"},
    {"Id": "102346", "Title": "Head of Operations", "PrimaryLocation": "Genève, Suisse",
     "PrimaryLocationCountry": "CH"},
]}]}


class Resp:
    def __init__(self, text='', payload=None, code=200):
        self.text, self._payload, self.status_code = text, payload, code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)


class Session:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        return self.resp


class CareerSiteTests(TestCase):
    def test_successfactors_page_is_parsed(self):
        rows = parse_successfactors_search(SF_HTML, 'jobs.pradagroup.com')
        self.assertEqual(rows[0]['title'], 'Supply Chain Director')
        self.assertEqual(rows[0]['url'],
                         'https://jobs.pradagroup.com/job/Milano-Supply-Chain-Director/1293231601/')
        self.assertEqual(rows[0]['location'], 'Milano, IT')

    def test_successfactors_queries_senior_keywords_and_dedupes(self):
        session = Session(Resp(SF_HTML))
        rows = fetch_successfactors(session, {'company': 'Prada Group', 'host': 'jobs.pradagroup.com'})
        self.assertEqual(len(rows), 2)  # 2 offres, meme si 5 mots-cles renvoient la meme page
        self.assertEqual(session.calls[0][1]['q'], 'director')
        self.assertTrue(all(r['company'] == 'Prada Group' for r in rows))

    def test_oracle_builds_public_job_links(self):
        session = Session(Resp(payload=ORACLE_JSON))
        rows = fetch_oracle_recruiting(session, {'company': 'Hermès', 'host': 'talents.hermes.com',
                                                 'site': 'CX', 'keywords': ['directeur']})
        self.assertEqual(rows[0]['url'], 'https://talents.hermes.com/fr/sites/CX/job/102345')
        self.assertEqual(rows[0]['country_field'], 'FR')
        url, params = session.calls[0]
        self.assertIn('/hcmRestApi/resources/latest/recruitingCEJobRequisitions', url)
        self.assertIn('siteNumber=CX', params['finder'])

    def test_offers_pass_the_business_filter(self):
        session = Session(Resp(payload=ORACLE_JSON))
        rows = fetch_oracle_recruiting(session, {'company': 'Hermès', 'host': 'talents.hermes.com',
                                                 'keywords': ['directeur']})
        kept = [r for r in (scraper.normaliser_source_plus(x) for x in rows) if r]
        self.assertTrue(any(r['Pays'] == 'France' for r in kept))

    def test_invalid_host_is_rejected(self):
        with self.assertRaises(ValueError):
            fetch_successfactors(Session(Resp('')), {'company': 'X', 'host': 'evil.com/../x'})

    def test_one_failing_site_does_not_break_the_others(self):
        class Mixed(Session):
            def get(self, url, params=None, headers=None, timeout=None):
                if 'moncler' in url:
                    return Resp(code=404)
                return Resp(SF_HTML)
        stats = {}
        config = {'successfactors': [{'company': 'Moncler', 'host': 'jobs.moncler.com'},
                                     {'company': 'Valentino', 'host': 'jobs.valentino.com'}]}
        rows = fetch_public_ats(config, session=Mixed(None), stats=stats)
        self.assertEqual(stats['SuccessFactors / Moncler']['etat'], 'erreur')
        self.assertEqual(stats['SuccessFactors / Valentino']['etat'], 'ok')
        self.assertTrue(rows)

    def test_shipped_config_declares_the_new_houses(self):
        config = read_sources_config()
        self.assertEqual({b['company'] for b in config['successfactors']},
                         {'Prada Group', 'Moncler', 'Valentino'})
        self.assertEqual(config['oracle'][0]['host'], 'talents.hermes.com')
        self.assertEqual(config['greenhouse'], [])
