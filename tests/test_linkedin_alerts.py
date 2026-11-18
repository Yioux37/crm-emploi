"""Tests hors ligne : alertes LinkedIn lues par IMAP (aucune vraie connexion)."""
from __future__ import annotations

import os
from datetime import date
from email.message import EmailMessage
from unittest import TestCase
from unittest.mock import patch

import scraper
from linkedin_alerts import fetch_linkedin_alerts, imap_date, parse_alert_html

ALERT_HTML = """
<table>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=SECRET&refId=X">
      Directeur Supply Chain (H/F)</a>
    <p>Hermès · Paris, Île-de-France, France</p>
    <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=SECRET">Voir l'offre</a>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4099999999/">Head of Operations</a>
    <p>Rolex · Genève, Suisse</p>
  </td></tr>
  <tr><td><a href="https://www.linkedin.com/in/jean-dupont/">Jean Dupont</a></td></tr>
</table>
"""


def alert_email(html: str) -> bytes:
    msg = EmailMessage()
    msg['From'] = 'LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>'
    msg['Subject'] = 'Directeur Supply Chain : 2 nouvelles offres'
    msg.set_content('Version texte')
    msg.add_alternative(html, subtype='html')
    return msg.as_bytes()


class FakeIMAP:
    """Imite imaplib.IMAP4_SSL et enregistre les commandes recues."""
    def __init__(self, host, messages=(), fail_login=False):
        self.host, self.messages, self.fail_login = host, list(messages), fail_login
        self.selected = None
        self.search_args = None

    def login(self, user, password):
        if self.fail_login:
            import imaplib
            raise imaplib.IMAP4.error('[AUTHENTICATIONFAILED] user@example.com')

    def select(self, folder, readonly=False):
        self.selected = (folder, readonly)
        return 'OK', [b'1']

    def search(self, charset, *criteria):
        self.search_args = criteria
        ids = b' '.join(str(i + 1).encode() for i in range(len(self.messages)))
        return 'OK', [ids]

    def fetch(self, msg_id, what):
        return 'OK', [(b'1 (RFC822)', self.messages[int(msg_id) - 1])]

    def logout(self):
        return 'BYE', []


ENV = {'IMAP_USER': 'moi@gmail.com', 'IMAP_PASSWORD': 'abcd efgh ijkl mnop'}


class LinkedInAlertTests(TestCase):
    def test_parse_keeps_only_job_links_with_titles(self):
        jobs = parse_alert_html(ALERT_HTML)
        self.assertEqual([j['job_id'] for j in jobs], ['4012345678', '4099999999'])
        self.assertEqual(jobs[0]['title'], 'Directeur Supply Chain (H/F)')
        self.assertIn('Hermès', jobs[0]['context'])
        self.assertIn('France', jobs[0]['context'])

    def test_tracking_parameters_are_removed_and_mailbox_is_read_only(self):
        fake = FakeIMAP('imap.gmail.com', [alert_email(ALERT_HTML)])
        stats = {}
        with patch.dict(os.environ, ENV):
            rows = fetch_linkedin_alerts(stats=stats, imap_factory=lambda host: fake,
                                         today=date(2026, 11, 18))
        self.assertEqual(rows[0]['url'], 'https://www.linkedin.com/jobs/view/4012345678/')
        self.assertTrue(all('tracking' not in r['url'] for r in rows))
        self.assertEqual(fake.selected, ('"INBOX"', True))
        self.assertIn('15-Nov-2026', fake.search_args)
        self.assertEqual(stats['LinkedIn / Alertes e-mail']['etat'], 'ok')

    def test_duplicate_offers_across_emails_are_merged(self):
        fake = FakeIMAP('imap.gmail.com', [alert_email(ALERT_HTML), alert_email(ALERT_HTML)])
        with patch.dict(os.environ, ENV):
            rows = fetch_linkedin_alerts(imap_factory=lambda host: fake)
        self.assertEqual(len(rows), 2)

    def test_without_secrets_source_is_disabled_not_error(self):
        stats = {}
        with patch.dict(os.environ, {'IMAP_USER': '', 'IMAP_PASSWORD': ''}):
            self.assertEqual(fetch_linkedin_alerts(stats=stats), [])
        self.assertEqual(stats['LinkedIn / Alertes e-mail']['etat'], 'desactive')

    def test_login_error_never_leaks_email_address(self):
        stats = {}
        with patch.dict(os.environ, ENV):
            fetch_linkedin_alerts(stats=stats, imap_factory=lambda host: FakeIMAP(host, fail_login=True))
        detail = stats['LinkedIn / Alertes e-mail']['detail']
        self.assertEqual(stats['LinkedIn / Alertes e-mail']['etat'], 'erreur')
        self.assertNotIn('@', detail)

    def test_alerts_go_through_business_filter(self):
        raw = {'title': 'Directeur Supply Chain (H/F)', 'company': '', 'location': '',
               'url': 'https://www.linkedin.com/jobs/view/4012345678/',
               'source': 'LinkedIn (Offres)', 'country_field': '',
               'context': 'Directeur Supply Chain (H/F) Hermès · Paris, Île-de-France, France'}
        row = scraper.normaliser_source_plus(raw)
        self.assertIsNotNone(row)
        self.assertEqual(row['Pays'], 'France')
        self.assertEqual(row['Source'], 'LinkedIn (Offres)')

    def test_imap_date_is_english_whatever_the_locale(self):
        self.assertEqual(imap_date(date(2026, 2, 3)), '03-Feb-2026')


class ManualLinkTests(TestCase):
    def test_pasted_linkedin_links_get_the_right_origin(self):
        from storage import manual_source
        self.assertEqual(manual_source('https://www.linkedin.com/posts/drh-hermes_recrute-123'),
                         'LinkedIn (Post recruteur)')
        self.assertEqual(manual_source('https://ch.linkedin.com/jobs/view/4012345678/'),
                         'LinkedIn (Offres)')
        self.assertEqual(manual_source('', 'Chasseur de têtes'), 'Chasseur de têtes')
        self.assertEqual(manual_source('https://exemple.fr/offre', 'inconnu'),
                         'Approche directe / Réseau')
