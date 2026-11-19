"""Tests hors ligne de la collecte LinkedIn invitee (aucune requete reelle)."""
from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import scraper
from linkedin_guest import build_queries, fetch_linkedin_guest_jobs, parse_cards

# Extrait fidele a la structure de la page invitee LinkedIn.
GUEST_HTML = """
<li><div class="base-card base-search-card job-search-card">
  <a class="base-card__full-link"
     href="https://fr.linkedin.com/jobs/view/directeur-supply-chain-h-f-at-herm%C3%A8s-4012345678?position=1&refId=abc&trackingId=XYZ">
     <span class="sr-only">Directeur Supply Chain (H/F)</span></a>
  <div class="base-search-card__info">
    <h3 class="base-search-card__title">Directeur Supply Chain (H/F)</h3>
    <h4 class="base-search-card__subtitle"><a href="https://fr.linkedin.com/company/hermes">Hermès</a></h4>
    <span class="job-search-card__location">Paris, Île-de-France, France</span>
    <time class="job-search-card__listdate" datetime="2026-11-15">il y a 3 jours</time>
  </div>
</div></li>
<li><div class="base-card base-search-card job-search-card">
  <a class="base-card__full-link" href="https://ch.linkedin.com/jobs/view/head-of-operations-at-rolex-4099999999?position=2">x</a>
  <h3 class="base-search-card__title">Head of Operations</h3>
  <h4 class="base-search-card__subtitle">Rolex</h4>
  <span class="job-search-card__location">Genève, Suisse</span>
</div></li>
"""


class Resp:
    def __init__(self, code, text=''):
        self.status_code, self.text = code, text


class FakeSession:
    def __init__(self, codes):
        self.codes, self.calls = list(codes), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        code = self.codes.pop(0) if self.codes else 200
        return Resp(code, GUEST_HTML if code == 200 else '')


class LinkedInGuestTests(TestCase):
    def test_cards_are_parsed_and_tracking_removed(self):
        cards = parse_cards(GUEST_HTML)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]['title'], 'Directeur Supply Chain (H/F)')
        self.assertEqual(cards[0]['company'], 'Hermès')
        self.assertEqual(cards[0]['url'], 'https://www.linkedin.com/jobs/view/4012345678/')
        self.assertEqual(cards[0]['posted_on'], '2026-11-15')

    def test_queries_never_contain_the_word_luxe_and_target_houses(self):
        queries = build_queries()
        self.assertLessEqual(len(queries), 45)
        self.assertTrue(all('luxe' not in p['keywords'].lower() for _, p in queries))
        # La requete Ciblage tourne a chaque scan, pas dans la serie --linkedin.
        self.assertFalse(any(label.startswith('LinkedIn Ciblage') for label, _ in queries))
        self.assertIn('LinkedIn direct / Hermès', [label for label, _ in queries])

    def test_stops_immediately_when_linkedin_throttles(self):
        session = FakeSession([200, 429])
        stats = {}
        rows = fetch_linkedin_guest_jobs(stats=stats, session=session, sleep=lambda s: None)
        self.assertEqual(len(session.calls), 2)          # aucune 3e requete
        self.assertEqual(len(rows), 2)
        states = [s['etat'] for s in stats.values()]
        self.assertEqual(states.count('erreur'), 1)
        self.assertEqual(states.count('non_interroge'), len(build_queries()) - 2)

    def test_duplicates_across_queries_are_merged(self):
        session = FakeSession([200, 200, 200])
        rows = fetch_linkedin_guest_jobs(session=session, sleep=lambda s: None, max_requests=3)
        self.assertEqual(len(rows), 2)

    def test_offers_go_through_business_filter(self):
        rows = [scraper.normaliser_source_plus(c) for c in parse_cards(GUEST_HTML)]
        kept = [r for r in rows if r]
        self.assertTrue(kept)
        self.assertTrue(all(r['Source'] == 'LinkedIn (Offres)' for r in kept))
        self.assertEqual(kept[0]['Pays'], 'France')

    def test_linkedin_is_off_unless_explicitly_requested(self):
        with patch.object(scraper, 'fetch_linkedin_jobs') as guest, \
             patch.object(scraper, 'fetch_portails_directs', return_value=[]), \
             patch.object(scraper, 'fetch_ats_complementaires', return_value=[]), \
             patch.object(scraper, 'fetch_portails_specialises', return_value=[]), \
             patch.object(scraper, 'fetch_alertes_linkedin', return_value=[]):
            import tempfile, os
            with tempfile.TemporaryDirectory() as d:
                scraper.executer_tout(os.path.join(d, 'f.csv'), os.path.join(d, 'r.json'))
                guest.assert_not_called()
                scraper.executer_tout(os.path.join(d, 'f.csv'), os.path.join(d, 'r.json'),
                                      linkedin=True)
                guest.assert_called_once()


class CiblageFetchTests(TestCase):
    """Requete booleenne de la page Ciblage, lancee depuis l'appli."""

    def test_429_isole_saute_la_page_sans_tout_arreter(self):
        from linkedin_guest import fetch_ciblage_jobs
        # France : 429 puis 429 (sautee) ; Suisse : 200 ; Italie : 200.
        session = FakeSession([429, 429, 200, 200])
        rows, bilan = fetch_ciblage_jobs('("Directeur") AND ("Luxe")', pages=1,
                                         session=session, sleep=lambda s: None)
        self.assertEqual(bilan['sautees'], 1)
        self.assertFalse(bilan['bloque'])
        self.assertEqual({r['search_country'] for r in rows}, {'Suisse'})  # doublons fusionnes

    def test_blocage_999_arrete_net(self):
        from linkedin_guest import fetch_ciblage_jobs
        session = FakeSession([999, 200, 200])
        rows, bilan = fetch_ciblage_jobs('("Directeur")', pages=1, session=session,
                                         sleep=lambda s: None)
        self.assertTrue(bilan['bloque'])
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(rows, [])
