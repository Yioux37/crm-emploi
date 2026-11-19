"""Collecte des OFFRES LinkedIn publiques via la page invitee (sans compte).

A lancer a la main, depuis son ordinateur :  python3 scraper.py --linkedin
(jamais depuis GitHub Actions : les IP de datacenter sont bloquees d'office).

Ce que fait ce module, etape par etape :
  1. Il interroge la page publique "jobs-guest" de LinkedIn : la meme liste
     d'offres qu'un visiteur NON connecte voit sur linkedin.com/jobs.
  2. Deux familles de recherches :
       - par FONCTION (directeur supply chain, operations...) x 3 pays ;
       - par MAISON (Hermes, Chanel, Rolex...) filtree niveau Direction,
         ce qui capte les intitules que l'on n'aurait pas devines.
  3. Il lit les cartes d'offre (intitule, entreprise, lieu, lien) et c'est tout.
     Aucun profil, aucun contact, aucune connexion a un compte LinkedIn.
  4. Les lignes passent ensuite par le meme filtre metier / luxe / pays que
     toutes les autres sources (normaliser_source_plus dans scraper.py).

Garde-fous :
  - 3 a 5 s de pause aleatoire entre deux requetes, 45 requetes maximum ;
  - arret IMMEDIAT au premier refus (429 = trop de requetes, 999 = blocage
    LinkedIn, 403) : les recherches restantes sont notees "non interrogees" ;
  - liens reecrits en https://www.linkedin.com/jobs/view/<id>/ (sans suivi).

Pourquoi requests + BeautifulSoup et pas Selenium / Playwright ?
  La page invitee renvoie du HTML deja rempli : pas besoin de navigateur.
  requests est leger, deja installe, et ne pilote pas un faux navigateur pour
  contourner quoi que ce soit. BeautifulSoup lit ce HTML de facon tolerante.
"""
from __future__ import annotations

import random
import re
import time

import requests
from bs4 import BeautifulSoup

import progress
from linkedin_alerts import JOB_ID, canonical_job_url

SEARCH_URL = 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'),
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8,it;q=0.7',
}
# Codes LinkedIn "niveau d'experience" : 4 = confirme / senior, 5 = directeur, 6 = executif.
SENIOR_LEVELS = '4,5,6'
DIRECTION_LEVELS = '5,6'
LAST_30_DAYS = 'r2592000'
BLOCKING_CODES = {403, 429, 999}

# Recherches par fonction : intitules REELS, sans le mot "luxe" (absent des titres).
FUNCTION_QUERIES = {
    'France': ['directeur supply chain', 'directeur des opérations', 'directeur industriel',
               'directeur de production', 'head of supply chain', 'directeur logistique'],
    'Switzerland': ['directeur supply chain', 'directeur des opérations', 'head of operations',
                    'directeur industriel', 'directeur de production horlogère'],
    'Italy': ['direttore supply chain', 'direttore operations', 'direttore produzione',
              'direttore industriale', 'head of supply chain'],
}
# Recherches par maison : toutes leurs offres de niveau Direction en Europe.
HOUSE_QUERIES = ['Hermès', 'Chanel', 'Louis Vuitton', 'Dior', 'Cartier', 'Rolex',
                 'Patek Philippe', 'Audemars Piguet', 'Richemont', 'Kering', 'LVMH', 'Gucci',
                 'Prada', 'Bulgari', 'Moncler', 'Loro Piana', 'Chopard', 'Breitling',
                 'TAG Heuer', 'Swatch Group', 'Vacheron Constantin', 'Van Cleef & Arpels',
                 'Zegna', 'Valentino']

CIBLAGE_HOUSES_PER_RUN = 4


def build_queries() -> list[tuple[str, dict]]:
    """Liste (libelle de diagnostic, parametres) dans l'ordre d'execution."""
    queries = []
    for country, keywords in FUNCTION_QUERIES.items():
        for kw in keywords:
            queries.append((f'LinkedIn direct / {kw} ({country})',
                            {'keywords': kw, 'location': country, 'f_TPR': LAST_30_DAYS,
                             'f_E': SENIOR_LEVELS, 'start': 0}))
    houses = list(HOUSE_QUERIES)
    try:
        # Sociétés « Haute » de la page Ciblage : 4 par lancement, en rotation, pour
        # rester sous la limite de requêtes (au-delà, LinkedIn bloque l'accès invité).
        import ciblage
        known = {ciblage.fold(h) for h in houses}
        extra = []
        for soc in ciblage.societes_par_priorite('Haute'):
            noms = {ciblage.fold(n) for n in ciblage.noms_societe(soc)}
            if len(ciblage.fold(soc['nom'])) > 3 and not noms & known:
                known |= noms
                extra.append(soc['nom'])
        houses += ciblage.rotation_du_jour(extra, CIBLAGE_HOUSES_PER_RUN)
    except Exception:
        pass
    for house in houses:
        queries.append((f'LinkedIn direct / {house}',
                        {'keywords': house, 'location': 'Europe', 'f_TPR': LAST_30_DAYS,
                         'f_E': DIRECTION_LEVELS, 'start': 0}))
    return queries


def _text(node) -> str:
    return ' '.join(node.get_text(' ', strip=True).split()) if node else ''


def parse_cards(html: str) -> list[dict]:
    """Lit les cartes d'offre de la page invitee (structure 'base-card')."""
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    for card in soup.select('div.base-card, li div.job-search-card'):
        link = card.select_one('a.base-card__full-link') or card.find('a', href=JOB_ID)
        if not link:
            continue
        match = JOB_ID.search(link.get('href', ''))
        title = _text(card.select_one('.base-search-card__title'))
        if not (match and title):
            continue
        company = _text(card.select_one('.base-search-card__subtitle'))
        location = _text(card.select_one('.job-search-card__location'))
        posted = card.find('time')
        rows.append({
            'title': title, 'company': company, 'location': location,
            'url': canonical_job_url(match.group(1)), 'source': 'LinkedIn (Offres)',
            'country_field': '', 'context': f'{title} {company} {location}',
            'posted_on': posted.get('datetime', '') if posted else '',
        })
    return rows


def fetch_linkedin_guest_jobs(stats: dict | None = None, session=None,
                              pause=(3.0, 5.0), max_requests: int = 45,
                              sleep=time.sleep) -> list[dict]:
    session = session or requests.Session()
    queries = build_queries()[:max_requests]
    rows, seen = [], set()
    for index, (label, params) in enumerate(queries):
        progress.tick(index, len(queries), label.replace('LinkedIn direct / ', ''))
        if index:
            sleep(random.uniform(*pause))  # rythme humain, jamais en rafale
        try:
            resp = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
        except requests.RequestException as exc:
            if stats is not None:
                stats[label] = {'brutes': 0, 'retenues': 0, 'etat': 'erreur',
                                'detail': type(exc).__name__}
            continue
        if resp.status_code in BLOCKING_CODES:
            # LinkedIn freine : on s'arrete net au lieu d'insister.
            if stats is not None:
                stats[label] = {'brutes': 0, 'retenues': 0, 'etat': 'erreur',
                                'detail': f'HTTP {resp.status_code} : LinkedIn limite, arret de la serie'}
                for later, _ in queries[index + 1:]:
                    stats[later] = {'brutes': 0, 'retenues': 0, 'etat': 'non_interroge',
                                    'detail': 'Serie arretee apres un refus LinkedIn'}
            print(f'⚠️ [LinkedIn direct] HTTP {resp.status_code} : arret. '
                  'Reessaie plus tard (quelques heures).')
            break
        if resp.status_code != 200:
            if stats is not None:
                stats[label] = {'brutes': 0, 'retenues': 0, 'etat': 'erreur',
                                'detail': f'HTTP {resp.status_code}'}
            continue
        cards = parse_cards(resp.text)
        for card in cards:
            if card['url'] in seen:
                continue
            seen.add(card['url'])
            card['_origine_diagnostic'] = label
            rows.append(card)
        if stats is not None:
            stats[label] = {'brutes': len(cards), 'retenues': 0,
                            'etat': 'ok' if cards else 'vide'}
        print(f'⏳ [{label}] {len(cards)} offres')
    return rows
