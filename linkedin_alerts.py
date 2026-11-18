"""Lecture des alertes emploi LinkedIn recues par e-mail (Gmail ou toute boite IMAP).

Pourquoi ce module ?
    LinkedIn interdit la collecte automatique de son site. En revanche, quand on
    cree une "alerte emploi", LinkedIn ENVOIE lui-meme les offres par e-mail.
    On lit donc sa propre boite mail : c'est gratuit, autorise et fiable.

Pourquoi imaplib + email (bibliotheque standard) plutot que l'API Gmail ?
    - L'API Gmail exige un projet Google Cloud, un ecran de consentement OAuth et
      un jeton a renouveler : lourd pour un scan quotidien sur GitHub Actions.
    - IMAP fonctionne avec un simple "mot de passe d'application" Gmail, et
      marche aussi avec Outlook, iCloud, etc.
    - imaplib/email sont fournis avec Python : aucune dependance a installer.
    BeautifulSoup (deja utilise par le projet) sert a lire le HTML des e-mails.

Confidentialite :
    - La boite est ouverte en LECTURE SEULE (aucun message marque lu ou supprime).
    - On ne garde que : intitule, extrait court (entreprise / lieu), lien d'offre.
    - Les liens sont reecrits en https://www.linkedin.com/jobs/view/<id>/ : les
      parametres de suivi personnels (trackingId, refId...) sont supprimes.
    - Identifiants lus dans les variables d'environnement (Secrets GitHub),
      jamais dans le depot.
"""
from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import date, timedelta
from email import policy

from bs4 import BeautifulSoup

# /jobs/view/123456 ou /comm/jobs/view/123456 : l'identifiant numerique suffit.
JOB_ID = re.compile(r'linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#]*-)?(\d{6,})', re.I)
# Textes de boutons a ignorer quand on cherche l'intitule du poste.
BUTTON_WORDS = {'voir', 'voir l’offre', "voir l'offre", 'view job', 'apply', 'postuler',
                'candidature simplifiée', 'easy apply', 'see all jobs', 'voir toutes les offres'}
# imaplib attend des mois en anglais (ex. 15-Nov-2026), quelle que soit la langue du systeme.
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def imap_date(day: date) -> str:
    return f'{day.day:02d}-{MONTHS[day.month - 1]}-{day.year}'


def canonical_job_url(job_id: str) -> str:
    return f'https://www.linkedin.com/jobs/view/{job_id}/'


def _html_of(message) -> str:
    """Renvoie la partie HTML d'un e-mail (les alertes LinkedIn sont en HTML)."""
    part = message.get_body(preferencelist=('html', 'plain'))
    if part is None:
        return ''
    try:
        return part.get_content()
    except (LookupError, ValueError):
        return ''


def parse_alert_html(html: str) -> list[dict]:
    """Extrait les offres d'un e-mail d'alerte : une entree par identifiant d'offre."""
    soup = BeautifulSoup(html or '', 'html.parser')
    jobs: dict[str, dict] = {}
    for link in soup.find_all('a', href=True):
        match = JOB_ID.search(link['href'])
        if not match:
            continue
        job_id = match.group(1)
        text = ' '.join(link.get_text(' ', strip=True).split())
        entry = jobs.setdefault(job_id, {'title': '', 'context': ''})
        # 1) Intitule : le premier texte de lien qui n'est pas un bouton.
        if text and not entry['title'] and text.lower() not in BUTTON_WORDS and len(text) > 4:
            entry['title'] = text[:200]
            # 2) Contexte : le plus petit bloc parent qui contient aussi
            #    "Entreprise · Lieu" (sert a detecter maison et pays).
            parent = link.parent
            for _ in range(6):
                if parent is None:
                    break
                block = ' '.join(parent.get_text(' ', strip=True).split())
                if len(block) > len(text) + 5:
                    entry['context'] = block[:400]
                    break
                parent = parent.parent
    return [dict(job_id=k, **v) for k, v in jobs.items() if v['title']]


def fetch_linkedin_alerts(days: int = 3, stats: dict | None = None,
                          imap_factory=imaplib.IMAP4_SSL, today: date | None = None) -> list[dict]:
    """Lit les alertes des `days` derniers jours. Renvoie des lignes "brutes".

    Format de sortie identique aux autres collecteurs (title, company, location,
    url, source, context) pour reutiliser normaliser_source_plus() du scraper.
    """
    label = 'LinkedIn / Alertes e-mail'
    user = os.getenv('IMAP_USER', '').strip()
    password = os.getenv('IMAP_PASSWORD', '').strip()
    if not (user and password):
        if stats is not None:
            stats[label] = {'brutes': 0, 'retenues': 0, 'etat': 'desactive',
                            'detail': 'Ajouter IMAP_USER et IMAP_PASSWORD dans les Secrets GitHub'}
        return []
    host = os.getenv('IMAP_HOST', 'imap.gmail.com').strip()
    folder = os.getenv('LINKEDIN_ALERTS_FOLDER', 'INBOX').strip()
    since = imap_date((today or date.today()) - timedelta(days=days))
    rows, seen = [], set()
    try:
        box = imap_factory(host)
        try:
            box.login(user, password)
            # readonly=True : on ne marque rien comme lu, on ne deplace rien.
            box.select(f'"{folder}"', readonly=True)
            status, data = box.search(None, 'FROM', '"linkedin.com"', 'SINCE', since)
            ids = data[0].split() if status == 'OK' and data and data[0] else []
            for msg_id in ids[-200:]:  # garde-fou : 200 e-mails maximum par scan
                status, parts = box.fetch(msg_id, '(RFC822)')
                if status != 'OK' or not parts or not isinstance(parts[0], tuple):
                    continue
                message = email.message_from_bytes(parts[0][1], policy=policy.default)
                for job in parse_alert_html(_html_of(message)):
                    if job['job_id'] in seen:
                        continue
                    seen.add(job['job_id'])
                    rows.append({
                        'title': job['title'], 'company': '', 'location': '',
                        'url': canonical_job_url(job['job_id']),
                        'source': 'LinkedIn (Offres)', 'country_field': '',
                        'context': job['context'], '_origine_diagnostic': label,
                    })
        finally:
            try:
                box.logout()
            except Exception:  # la connexion peut deja etre fermee
                pass
    except (imaplib.IMAP4.error, OSError) as exc:
        if stats is not None:
            # On n'affiche jamais le message brut : il peut contenir l'adresse e-mail.
            stats[label] = {'brutes': 0, 'retenues': 0, 'etat': 'erreur',
                            'detail': f'{type(exc).__name__} (verifier le mot de passe d application)'}
        return []
    if stats is not None:
        stats[label] = {'brutes': len(rows), 'retenues': 0, 'etat': 'ok' if rows else 'vide'}
    return rows
