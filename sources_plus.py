"""Connecteurs gratuits de veille emploi (v6).

Sources non authentifiees et PUBLIQUES uniquement : Lever, Ashby, flux RSS/Atom
publies, ainsi que decouverte de liens indexes par un moteur de recherche.
Aucun contournement de login, robots.txt, CAPTCHA, limitation ou API privee.
Les enregistrements retournés sont des candidats bruts : scraper.py les valide.
"""
from __future__ import annotations

from datetime import date
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import requests

import progress
from bs4 import BeautifulSoup

from matching import est_une_offre
from search_gateway import default_search_client

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / 'sources_plus.json'
HEADERS = {'User-Agent': 'CRM-Carriere/6.0 (lecture annonces publiques)',
           'Accept': 'application/json, application/xml, text/xml;q=0.9, */*;q=0.5'}
IDENTIFIER = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,90}$')

# Sites classes par type. La rotation limite les quotas du moteur web :
# les sites non prioritaires alternent chaque jour plutot qu'etre tous interroges.
from source_catalog import NEWS_SITES, SEARCH_SITES

SEARCH_TERMS = {
    'fr': [
        '("directeur supply chain" OR "directeur operations" OR "directeur des operations") (luxe OR horlogerie OR mode OR maroquinerie)',
        '("directeur industriel" OR "directeur de production" OR "directeur manufacture") (luxe OR joaillerie OR textile)',
        '("responsable excellence operationnelle" OR "head of supply chain" OR "plant director") (luxe OR luxury OR horlogerie)',
    ],
    'en': [
        '("head of supply chain" OR "operations director" OR "supply chain director") (luxury OR watches OR fashion)',
        '("manufacturing director" OR "plant director" OR "head of manufacturing") (luxury OR watchmaking OR jewelry)',
        '("head of operations" OR "industrial director" OR "procurement director") (luxury OR watch OR couture)',
    ],
    'it': [
        '("direttore produzione" OR "direttore operations" OR "direttore supply chain") (lusso OR moda OR pelletteria)',
        '("direttore industriale" OR "responsabile produzione" OR "direttore stabilimento") (lusso OR orologeria)',
        '("head of operations" OR "supply chain director" OR "manufacturing director") (luxury OR fashion OR Italy)',
    ],
}


def read_sources_config(path: str | Path = CONFIG_FILE) -> dict:
    """Configuration versionnee sans cle API ou donnee de candidature."""
    try:
        content = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(content, dict):
            raise ValueError('La configuration doit etre un objet JSON.')
        return content
    except FileNotFoundError:
        return {}


def _safe_slug(value: object) -> str:
    v = str(value or '').strip()
    if not IDENTIFIER.fullmatch(v):
        raise ValueError(f'Identifiant de site invalide: {v!r}')
    return v


def _safe_url(url: object) -> str:
    v = str(url or '').strip()
    try:
        parsed = urlsplit(v)
    except ValueError:
        return ''
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not host or host in {'localhost', '127.0.0.1', '::1'} or host.endswith('.local'):
        return ''
    if parsed.username or parsed.password:
        return ''
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            return ''
    except ValueError:
        if host.endswith(('.internal', '.localhost', '.test')):
            return ''
    return v


def _get_json(session, url: str, params=None) -> object:
    response = session.get(url, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def _raw(title, company, location, url, source, country_field='', context='') -> dict:
    return dict(title=str(title or '').strip(), company=str(company or '').strip(),
                location=str(location or '').strip(), url=_safe_url(url),
                source=source, country_field=str(country_field or '').strip(),
                context=str(context or '').strip())


def fetch_lever(session, board: dict) -> list[dict]:
    company = str(board['company']).strip()
    slug = _safe_slug(board['site'])
    region = str(board.get('region', 'global')).lower()
    if region not in {'eu', 'global'}:
        raise ValueError('Lever: region doit etre eu ou global')
    base = 'https://api.eu.lever.co' if region == 'eu' else 'https://api.lever.co'
    jobs = []
    for page in range(3):  # Maximum 300 offres par maison/scan
        batch = _get_json(session, f'{base}/v0/postings/{slug}',
                          params={'skip': page * 100, 'limit': 100, 'mode': 'json'})
        if not isinstance(batch, list):
            break
        for p in batch:
            categories = p.get('categories') or {}
            location = categories.get('location') or p.get('workplaceType') or ''
            jobs.append(_raw(p.get('text'), company, location,
                             p.get('hostedUrl') or p.get('applyUrl'), 'Sites Maisons de Luxe',
                             context=' '.join(str(x or '') for x in
                                              [categories.get('department'), categories.get('team'),
                                               categories.get('commitment')])))
        if len(batch) < 100:
            break
    return jobs


def fetch_ashby(session, board: dict) -> list[dict]:
    company = str(board['company']).strip()
    slug = _safe_slug(board['board'])
    raw = _get_json(session, f'https://api.ashbyhq.com/posting-api/job-board/{slug}')
    jobs = []
    for p in raw.get('jobs', []) if isinstance(raw, dict) else []:
        if not p.get('isListed', True):  # Ne jamais publier de poste non liste.
            continue
        address = (p.get('address') or {}).get('postalAddress') or {}
        country = address.get('addressCountry') or ''
        location = p.get('location') or address.get('addressLocality') or ''
        jobs.append(_raw(p.get('title'), company, location,
                         p.get('jobUrl') or p.get('applyUrl'), 'Sites Maisons de Luxe',
                         country_field=country,
                         context=' '.join(str(x or '') for x in [p.get('department'), p.get('team')])))
    return jobs


def fetch_greenhouse(session, board: dict) -> list[dict]:
    """Public Greenhouse Job Board GET endpoint; no login or application POST."""
    company = str(board['company']).strip()
    slug = _safe_slug(board['board'])
    response = _get_json(session,
                         f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs')
    jobs = []
    for post in response.get('jobs', []) if isinstance(response, dict) else []:
        location = (post.get('location') or {}).get('name') or ''
        jobs.append(_raw(post.get('title'), company, location,
                         post.get('absolute_url'), 'Sites Maisons de Luxe',
                         context=' '.join(str(d.get('name', '')) for d in post.get('departments') or [])))
    return jobs


def fetch_smartrecruiters(session, board: dict) -> list[dict]:
    """Only publicly advertised posts of an explicitly configured company."""
    company = str(board['company']).strip()
    slug = _safe_slug(board['company_id'])
    rows = []
    for offset in (0, 100, 200):
        batch = _get_json(session,
                          f'https://api.smartrecruiters.com/v1/companies/{slug}/postings',
                          params={'limit': 100, 'offset': offset})
        posts = batch.get('content', []) if isinstance(batch, dict) else []
        for post in posts:
            job_id = post.get('id') or ''
            if not IDENTIFIER.fullmatch(str(job_id)):
                continue
            location = post.get('location') or {}
            city = location.get('city') or ''
            region = location.get('region') or ''
            country = location.get('country') or ''
            rows.append(_raw(post.get('name'), company, ' '.join((city, region)).strip(),
                             f'https://jobs.smartrecruiters.com/{slug}/{job_id}',
                             'Sites Maisons de Luxe', country_field=country,
                             context=str(post.get('department') or '')))
        if len(posts) < 100:
            break
    return rows


def fetch_workable(session, board: dict) -> list[dict]:
    """Flux public d'un compte Workable connu, sans cle ni connexion."""
    company = str(board['company']).strip()
    slug = _safe_slug(board['account'])
    data = _get_json(session, f'https://apply.workable.com/api/v1/widget/accounts/{slug}',
                     params={'details': 'true'})
    results = []
    for post in data.get('jobs', []) if isinstance(data, dict) else []:
        loc = post.get('location') or {}
        if isinstance(loc, str):
            location, country = loc, ''
        else:
            location = ', '.join(str(loc.get(k)) for k in ('city', 'region', 'country') if loc.get(k))
            country = loc.get('country') or ''
        link = post.get('url') or post.get('application_url') or ''
        code = post.get('shortcode') or ''
        if not link and IDENTIFIER.fullmatch(str(code)):
            link = f'https://apply.workable.com/{slug}/j/{code}/'
        results.append(_raw(post.get('title'), company, location, link,
                            'Sites Maisons de Luxe', country_field=country,
                            context=str(post.get('department') or '')))
    return results


def fetch_recruitee(session, board: dict) -> list[dict]:
    """Flux public Recruitee d'une entreprise explicitement configuree."""
    company = str(board['company']).strip()
    slug = _safe_slug(board['account'])
    data = _get_json(session, f'https://{slug}.recruitee.com/api/offers/')
    results = []
    for post in data.get('offers', []) if isinstance(data, dict) else []:
        loc = post.get('location') or ''
        country = post.get('country_code') or ''
        if isinstance(loc, dict):
            location = ', '.join(str(loc.get(k)) for k in ('city', 'country') if loc.get(k))
        else:
            location = str(loc)
        results.append(_raw(post.get('title'), company, location,
                            post.get('careers_url') or post.get('url') or '',
                            'Sites Maisons de Luxe', country_field=country,
                            context=str(post.get('department') or '')))
    return results


def _xml_txt(element, name: str) -> str:
    for child in element:
        if child.tag.rsplit('}', 1)[-1].lower() == name.lower():
            return ''.join(child.itertext()).strip()
    return ''


def fetch_rss(session, board: dict) -> list[dict]:
    company = str(board['company']).strip()
    url = _safe_url(board['url'])
    if not url:
        raise ValueError('RSS: URL HTTPS valide necessaire')
    response = session.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    # XML standard, sans entity expansion externe.
    root = ET.fromstring(response.content)
    jobs = []
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1].lower() not in {'item', 'entry'}:
            continue
        title = _xml_txt(element, 'title')
        location = (_xml_txt(element, 'location') or _xml_txt(element, 'jobLocation')
                    or _xml_txt(element, 'city'))
        link = _xml_txt(element, 'link')
        if not link:
            link = next((node.get('href', '') for node in element
                         if node.tag.rsplit('}', 1)[-1].lower() == 'link'), '')
        description = _xml_txt(element, 'description') or _xml_txt(element, 'summary') or ''
        description = BeautifulSoup(description, 'html.parser').get_text(' ', strip=True)
        jobs.append(_raw(title, company, location, link, 'Sites Maisons de Luxe',
                         context=description[:700]))
    return jobs


# ------------------------------------------------------------------------------
# Connecteurs "page carrieres officielle" : on lit la meme source que le site
# carrieres de la maison. Toutes les offres d'un mot-cle, filtre ensuite chez nous.
# ------------------------------------------------------------------------------

# Mots-cles de niveau Direction : un site SuccessFactors / Oracle d'une grande
# maison compte des milliers d'offres boutique ; on ne rapatrie que le haut.
SENIOR_KEYWORDS = ('director', 'directeur', 'direttore', 'head of', 'responsable')
HOST = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')


def _safe_host(value: object) -> str:
    host = str(value or '').strip().lower()
    if not HOST.fullmatch(host):
        raise ValueError(f'Nom de domaine invalide : {host!r}')
    return host


def parse_successfactors_search(html: str, host: str) -> list[dict]:
    """Lit une page /search/ d'un site carrieres SAP SuccessFactors (RMK).

    Structure : <tr class="data-row"> avec a.jobTitle-link et span.jobLocation.
    """
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    for row in soup.select('tr.data-row, li.job-tile'):
        link = row.select_one('a.jobTitle-link') or row.find('a', href=re.compile(r'^/job/'))
        if not link:
            continue
        title = ' '.join(link.get_text(' ', strip=True).split())
        href = link.get('href', '')
        location = row.select_one('.jobLocation')
        rows.append({'title': title, 'url': f'https://{host}{href}' if href.startswith('/') else href,
                     'location': ' '.join(location.get_text(' ', strip=True).split()) if location else ''})
    return [r for r in rows if r['title'] and r['url']]


def fetch_successfactors(session, board: dict) -> list[dict]:
    """Sites carrieres SAP SuccessFactors (ex. jobs.pradagroup.com, jobs.moncler.com).

    Page publique /search/?q=... : 25 offres par page, 2 pages par mot-cle maximum.
    """
    company = str(board['company']).strip()
    host = _safe_host(board['host'])
    rows, seen = [], set()
    for keyword in board.get('keywords') or SENIOR_KEYWORDS:
        for startrow in (0, 25):
            resp = session.get(f'https://{host}/search/', headers=HEADERS, timeout=15,
                               params={'q': keyword, 'locale': board.get('locale', 'en_US'),
                                       'sortColumn': 'referencedate', 'sortDirection': 'desc',
                                       'startrow': startrow})
            resp.raise_for_status()
            page = parse_successfactors_search(resp.text, host)
            for job in page:
                if job['url'] in seen:
                    continue
                seen.add(job['url'])
                rows.append(_raw(job['title'], company, job['location'], job['url'],
                                 'Sites Maisons de Luxe', context=f"{company} {job['location']}"))
            if len(page) < 25:
                break  # derniere page atteinte
    return rows


def fetch_oracle_recruiting(session, board: dict) -> list[dict]:
    """Oracle Recruiting Cloud (ex. Hermes : talents.hermes.com, site CX).

    API publique utilisee par la page carrieres elle-meme (sans compte) :
    /hcmRestApi/resources/latest/recruitingCEJobRequisitions
    """
    company = str(board['company']).strip()
    host = _safe_host(board['host'])
    site = _safe_slug(board.get('site', 'CX'))
    language = _safe_slug(board.get('language', 'fr'))
    rows, seen = [], set()
    for keyword in board.get('keywords') or SENIOR_KEYWORDS:
        finder = (f'findReqs;siteNumber={site},keyword="{keyword}",limit=100,offset=0,'
                  'sortBy=POSTING_DATES_DESC')
        data = _get_json(session, f'https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions',
                         params={'onlyData': 'true', 'expand': 'requisitionList.secondaryLocations',
                                 'finder': finder})
        for block in data.get('items', []) if isinstance(data, dict) else []:
            for req in block.get('requisitionList') or []:
                job_id = str(req.get('Id') or '')
                if not IDENTIFIER.fullmatch(job_id) or job_id in seen:
                    continue
                seen.add(job_id)
                location = str(req.get('PrimaryLocation') or '')
                rows.append(_raw(req.get('Title'), company, location,
                                 f'https://{host}/{language}/sites/{site}/job/{job_id}',
                                 'Sites Maisons de Luxe',
                                 country_field=str(req.get('PrimaryLocationCountry') or ''),
                                 context=f"{company} {location} {req.get('ShortDescriptionStr') or ''}"[:750]))
    return rows


def fetch_public_ats(config: dict | None = None, session=None, stats: dict | None = None) -> list[dict]:
    """Interroge seulement des interfaces publiques explicitement configurees.

    Une erreur sur un site n'annule pas le resultat des autres fournisseurs.
    """
    config = config if config is not None else read_sources_config()
    session = session or requests.Session()
    jobs = []
    providers = [('Lever', config.get('lever', []), fetch_lever),
                 ('Ashby', config.get('ashby', []), fetch_ashby),
                 ('Greenhouse', config.get('greenhouse', []), fetch_greenhouse),
                 ('SmartRecruiters', config.get('smartrecruiters', []), fetch_smartrecruiters),
                 ('Workable', config.get('workable', []), fetch_workable),
                 ('Recruitee', config.get('recruitee', []), fetch_recruitee),
                 ('RSS/Atom', config.get('rss', []), fetch_rss),
                 ('SuccessFactors', config.get('successfactors', []), fetch_successfactors),
                 ('Oracle Recruiting', config.get('oracle', []), fetch_oracle_recruiting)]
    total_boards = sum(len(boards) for _, boards, _ in providers)
    board_number = 0
    for provider, boards, fn in providers:
        for board in boards:
            name = str(board.get('company', '?'))
            progress.tick(board_number, total_boards, f'{provider} / {name}')
            board_number += 1
            label = f'{provider} / {name}'
            try:
                batch = [x for x in fn(session, board) if x['url'] and x['title']]
                for row in batch:
                    row['_origine_diagnostic'] = label
                jobs.extend(batch)
                if stats is not None:
                    stats[label] = {'brutes': len(batch), 'retenues': 0,
                                    'etat': 'ok' if batch else 'vide'}
            except (requests.RequestException, ValueError, KeyError, ET.ParseError, TypeError) as exc:
                print(f'⚠️ [{label}] {exc}')
                detail = type(exc).__name__
                code = getattr(getattr(exc, 'response', None), 'status_code', None)
                if code == 404:
                    detail = 'HTTP 404 : identifiant de flux introuvable, a verifier'
                elif code:
                    detail = f'HTTP {code}'
                if stats is not None:
                    stats[label] = {'brutes': 0, 'retenues': 0,
                                    'etat': 'erreur', 'detail': detail}
    return jobs


def _cibles_prioritaires(day: date | None = None) -> list[tuple]:
    """Sociétés « Haute » de la page Ciblage absentes du catalogue, en rotation quotidienne.

    Recherche ouverte sur leur nom (toutes plateformes), comme les grandes maisons.
    CIBLAGE_MAX_QUERIES (8 par défaut) requêtes par jour : 24 sociétés sont donc
    toutes cherchées en 3 jours, sans priver les portails en rotation.
    Un nom de 3 lettres ou moins (« SIS », « BFL ») est trop ambigu pour un moteur :
    il reste reconnu dans les annonces, mais ne déclenche pas de recherche dédiée.
    """
    try:
        import ciblage
        societes = ciblage.societes_par_priorite('Haute')
        quota = int(os.getenv('CIBLAGE_MAX_QUERIES', '8'))
    except Exception:
        return []
    connus = {_fold(_GROUP_SUFFIX.sub('', name)).strip() for name, *_ in SEARCH_SITES}
    extra = []
    for soc in societes:
        cles = {_fold(n).strip() for n in ciblage.noms_societe(soc)}
        cle = _fold(soc['nom']).strip()
        if len(cle) <= 3 or cles & connus:
            continue
        connus.add(cle)
        pseudo_domaine = re.sub(r'[^a-z0-9]+', '-', cle).strip('-') + '.ciblage'
        extra.append((soc['nom'], pseudo_domaine, 'Sites Maisons de Luxe', 'fr', True))
    return ciblage.rotation_du_jour(extra, quota, day)


def select_search_sites(day: date | None = None, budget: int | None = None) -> list[tuple]:
    """Interroge les sites incontournables chaque jour, puis fait tourner les autres."""
    day = day or date.today()
    if budget is None:
        try:
            budget = int(os.getenv('INDEX_MAX_QUERIES', '60'))
        except ValueError:
            budget = 60
    # 39 sites quotidiens (12 portails + 3 LinkedIn Jobs + 24 maisons) + une part tournante.
    budget = max(0, min(80, budget))
    always = [s for s in SEARCH_SITES if s[4]] + _cibles_prioritaires(day)
    rotating = [s for s in SEARCH_SITES if not s[4]]
    if budget <= len(always):
        return always[:budget]
    slots = budget - len(always)
    start = ((day.toordinal() // 1) * slots) % len(rotating)
    chosen = [rotating[(start + i) % len(rotating)] for i in range(slots)]
    return always + chosen


# V7 : mots-cles SANS guillemets. Avec guillemets, le moteur exigeait l'expression
# exacte et renvoyait 0 resultat sur 30 sites. On garde une requete par site
# (pas de OR) et on fait tourner les intitules d'un jour a l'autre.
LIGHT_TERMS = {
    'fr': ['directeur supply chain', 'directeur industriel', 'directeur production',
           'directeur des operations', 'directeur logistique', 'responsable supply chain'],
    'en': ['operations director', 'head of supply chain', 'manufacturing director',
           'supply chain director', 'head of operations', 'logistics director'],
    'it': ['direttore produzione', 'direttore operations', 'direttore supply chain',
           'direttore logistica', 'responsabile supply chain', 'direttore industriale'],
}

# Plateformes ATS qui hebergent plusieurs employeurs : on garde site:domaine.
_ATS_HOSTS = ('greenhouse.io', 'lever.co', 'ashbyhq.com', 'smartrecruiters.com',
              'myworkdayjobs.com', 'teamtailor.com', 'recruitee.com')
_GROUP_SUFFIX = re.compile(r'\s+(group|groupe)$', re.I)


def _fold(text: str) -> str:
    """Minuscules sans accents : 'Hermès' et 'Hermes' deviennent identiques."""
    text = unicodedata.normalize('NFKD', str(text or ''))
    return ''.join(c for c in text if not unicodedata.combining(c)).lower()


def is_open_brand_search(source: str, domain: str) -> bool:
    """Maison de luxe : recherche ouverte sur son nom, toutes plateformes."""
    return source == 'Sites Maisons de Luxe' and not any(h in domain for h in _ATS_HOSTS)


# Pages qui ne sont JAMAIS des offres : profils de personnes, reseaux sociaux,
# encyclopedies et articles de presse. Un profil LinkedIn est une donnee
# personnelle : il ne doit ni entrer dans le CRM ni etre publie dans le depot.
_NEWS_HOSTS = tuple(domain for _, domain in NEWS_SITES)
_NON_JOB_HOSTS = ('facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'youtube.com',
                  'tiktok.com', 'wikipedia.org', 'pinterest.com') + _NEWS_HOSTS


def looks_like_job_page(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    path = (parts.path or '').lower()
    if host == 'linkedin.com' or host.endswith('.linkedin.com'):
        # Seules les fiches d'offre publiques sont acceptees (pas /in/, /posts/, /company/).
        return path.startswith('/jobs/view/')
    if any(host == h or host.endswith('.' + h) for h in _NON_JOB_HOSTS):
        return False
    # Presse, bourse, organigrammes (The Org...), pages de resultats.
    return est_une_offre('', url)


def build_index_query(name: str, domain: str, source: str, term: str) -> str:
    if is_open_brand_search(source, domain):
        brand = _GROUP_SUFFIX.sub('', name).strip()
        # Ex. : "Hermes" directeur supply chain  -> offres Hermes sur tous les jobboards
        return f'"{brand}" {term}'
    if domain.endswith('linkedin.com'):
        # Restreint aux fiches d'offre : evite de remonter des profils de personnes.
        return f'site:{domain}/jobs/view {term}'
    return f'site:{domain} {term}'


def fetch_indexed_jobs(day: date | None = None, budget: int | None = None,
                       ddgs_factory=None, sleep_seconds: float = 1.0,
                       stats: dict | None = None, max_consecutive_errors: int = 3) -> list[dict]:
    """Index gratuit: statuts 'vide' et 'erreur' distincts, arret si moteur bloque.

    Les sites ne sont pas crawles directement. La limite budget represente le nombre
    maximal de requetes, pas le nombre de sites garantis comme accessibles.
    """
    day = day or date.today()
    sites = select_search_sites(day, budget)
    if ddgs_factory is None:
        ddgs_factory = default_search_client()
    if not ddgs_factory:
        if stats is not None:
            stats['Moteur web'] = {'brutes': 0, 'retenues': 0, 'etat': 'indisponible',
                                  'detail': 'Moteur DDGS non installe'}
        return []
    if not sites:
        return []
    rows, seen, consecutive_errors = [], set(), 0
    try:
        with ddgs_factory() as engine:
            for index, (name, domain, source, language, _) in enumerate(sites):
                progress.tick(index, len(sites), name)
                label = f'Index / {name}'
                terms = LIGHT_TERMS[language]
                # Intitule different chaque jour pour un meme site (6 intitules par langue).
                term = terms[(day.toordinal() + sum(map(ord, domain))) % len(terms)]
                query = build_index_query(name, domain, source, term)
                open_brand = is_open_brand_search(source, domain)
                brand_key = _fold(_GROUP_SUFFIX.sub('', name))
                try:
                    hits = list(engine.text(query, max_results=12) or [])
                    consecutive_errors = 0
                    brutes = 0
                    for hit in hits:
                        url = _safe_url(hit.get('href') or hit.get('url'))
                        if not url or not looks_like_job_page(url):
                            continue
                        # Ex. « LVMH nomme X directeur industriel » : un article, pas une offre.
                        if not est_une_offre(hit.get('title'), url):
                            continue
                        host = (urlsplit(url).hostname or '').lower()
                        if open_brand:
                            # Tout site accepte, mais la maison doit etre citee.
                            texte = _fold(f"{hit.get('title', '')} {hit.get('body', '')}")
                            if brand_key not in texte:
                                continue
                        elif not (host == domain or host.endswith('.' + domain)):
                            continue
                        brutes += 1
                        if url in seen:
                            continue
                        seen.add(url)
                        raw = _raw(hit.get('title'), '', '', url, source,
                                   context=str(hit.get('body') or '')[:750])
                        raw['_origine_diagnostic'] = label
                        rows.append(raw)
                    if stats is not None:
                        stats[label] = {'brutes': brutes, 'retenues': 0,
                                        'etat': 'ok' if brutes else 'vide'}
                except Exception as exc:
                    # ddgs leve DDGSException("No results found.") quand une requete
                    # ne renvoie RIEN : ce n'est pas une panne du moteur, juste un site
                    # sans annonce correspondante. On le note 'vide' sans activer le
                    # coupe-circuit (sinon 3 sites vides de suite bloquaient 27 sites).
                    if 'no results found' in str(exc).lower():
                        consecutive_errors = 0
                        if stats is not None:
                            stats[label] = {'brutes': 0, 'retenues': 0, 'etat': 'vide'}
                        if sleep_seconds:
                            time.sleep(sleep_seconds)
                        continue
                    consecutive_errors += 1
                    kind = type(exc).__name__
                    print(f'⚠️ [{label}] Erreur du moteur de recherche : {kind}')
                    if stats is not None:
                        stats[label] = {'brutes': 0, 'retenues': 0,
                                        'etat': 'erreur', 'detail': kind}
                    if consecutive_errors >= max_consecutive_errors:
                        remaining = sites[index + 1:]
                        if stats is not None:
                            for remaining_name, _, _, _, _ in remaining:
                                stats[f'Index / {remaining_name}'] = {
                                    'brutes': 0, 'retenues': 0, 'etat': 'non_interroge',
                                    'detail': 'Moteur indisponible apres erreurs repetees'}
                        print(f'⚠️ Moteur de recherche indisponible : {len(remaining)} sites reportes. '
                              'Les flux ATS continuent normalement.')
                        break
                if sleep_seconds:
                    time.sleep(sleep_seconds)
    except Exception as exc:
        print(f'⚠️ [Index] Moteur inaccessible : {type(exc).__name__}')
        if stats is not None:
            stats['Moteur web'] = {'brutes': 0, 'retenues': 0,
                                  'etat': 'indisponible', 'detail': type(exc).__name__}
    return rows
