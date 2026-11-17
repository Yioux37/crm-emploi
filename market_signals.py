"""Radar de signaux publics du secteur luxe (PAS des offres d'emploi).

Recherche indexee d'articles de presse sur capacite, croissance,
reorganisations et acquisitions. Ne collecte ni profils ni contacts.
"""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import pandas as pd
import re
import time
from urllib.parse import urlsplit

from matching import canonical_url, simplify, country_from_location

from search_gateway import default_search_client

SIGNAL_COLUMNS = ['Date de détection', 'Actualité', 'Entreprise', 'Catégorie',
                  'Pays', 'Source', 'Lien']
from source_catalog import NEWS_SITES

SIGNAL_TERMS = {
    'Investissement / expansion': ['investissement', 'investit', 'investissement', 'agrandit',
                                    'extension', 'nouvelle usine', 'nouvel atelier',
                                    'expansion', 'investment', 'new factory', 'new plant',
                                    'opening', 'apertura', 'ampliamento', 'nuovo stabilimento'],
    'Recrutement / réorganisation': ['recrutement', 'recrute', 'nomination', 'nommé',
                                     'nouveau dirigeant', 'nouvelle direction', 'reorganisation',
                                     'reorganization', 'appointed', 'appoints', 'hiring',
                                     'direzione', 'assume la guida', 'nomina'],
    'Transformation industrielle': ['modernisation', 'automatisation', 'automation',
                                     'digitalisation', 'digital transformation',
                                     'transformation industrielle', 'excellence operationnelle',
                                     'operational excellence', 'industria 4.0', 'automazione'],
    'Acquisition / rapprochement': ['rachat', 'acquisition', 'fusion', 'partenariat', 'acquires',
                                     'merger', 'joint venture', 'acquisizione', 'fusione'],
}


# Evidence-aware actions. A market signal is a lead, never a confirmed vacancy.
GUIDANCE = {
    'Investissement / expansion': (
        'Capacite industrielle / supply chain potentiellement en mouvement',
        'Lire la source et sa date; verifier le projet; identifier le bon service; proposer un echange reseau.'),
    'Recrutement / reorganisation': (
        'Organisation ou priorites de direction potentiellement en evolution',
        'Confirmer les nominations et leur date; comprendre les enjeux; preparer une prise de contact ciblee.'),
    'Acquisition / rapprochement': (
        'Integration industrielle, flux et gouvernance a surveiller',
        'Verifier le perimetre et l etat de l operation; proposer une conversation sur les enjeux.'),
    'Transformation industrielle': (
        'Chantiers de performance et de transformation a approfondir',
        'Chercher les besoins documentes en operations; preparer une approche liee a un enjeu precis.'),
}


def signal_guidance(category: str) -> tuple[str, str]:
    title, action = GUIDANCE.get(category, (
        'Actualite a verifier', 'Lire la source originale avant toute conclusion ou prise de contact.'))
    return title, 'Verifier la source et sa date avant toute demarche. ' + action


def detect_signal(text: object) -> str | None:
    plain = simplify(text)
    for label, words in SIGNAL_TERMS.items():
        if any(re.search(r'(?<![a-z0-9])' + re.escape(simplify(w)) + r'(?![a-z0-9])', plain)
               for w in words):
            return label
    return None


def detect_company(text: str, companies: list[str]) -> str:
    """Marque identifiable uniquement dans le titre ou l'extrait public."""
    plain = simplify(text)
    # Prefere une maison identifiable et specifique aux noms de groupes.
    groups = {'lvmh', 'kering', 'richemont', 'swatch group', 'puig'}
    for company in sorted(set(companies), key=lambda s: -len(s)):
        key = simplify(company)
        if key and len(key) > 4 and key not in groups and re.search(r'(?<![a-z0-9])' + re.escape(key) + r'(?![a-z0-9])', plain):
            return company.title()
    for company in groups:
        if re.search(r'(?<![a-z0-9])' + re.escape(company) + r'(?![a-z0-9])', plain):
            return company.upper() if company == 'lvmh' else company.title()
    return ''


def scan_public_signals(companies: list[str], day: date | None = None,
                        budget: int = 4, ddgs_factory=None,
                        sleep_seconds: float = 1.0) -> list[dict]:
    day = day or date.today()
    budget = max(0, min(len(NEWS_SITES), budget))
    if ddgs_factory is None:
        ddgs_factory = default_search_client()
    if not ddgs_factory or not budget:
        return []
    start = (day.toordinal() * budget) % len(NEWS_SITES)
    selected = [NEWS_SITES[(start + i) % len(NEWS_SITES)] for i in range(budget)]
    terms = [
        '("nouvelle usine" OR investissement OR expansion OR "new factory") luxe horlogerie',
        '(acquisition OR nomination OR "nouvelle direction" OR recrutement) luxe horlogerie',
        '(investimento OR acquisizione OR "nuovo stabilimento" OR "production capacity") luxury fashion',
    ][day.toordinal() % 3]
    found, urls = [], set()
    consecutive_errors = 0
    try:
        with ddgs_factory() as ddgs:
            for source, domain in selected:
                try:
                    results = list(ddgs.text(f'site:{domain} {terms}', max_results=10) or [])
                    consecutive_errors = 0
                    for hit in results:
                        title, excerpt = str(hit.get('title') or '').strip(), str(hit.get('body') or '')
                        url = str(hit.get('href') or '')
                        parsed = urlsplit(url)
                        host = (parsed.hostname or '').lower()
                        if parsed.scheme != 'https' or not (host == domain or host.endswith('.' + domain)):
                            continue
                        url_key = canonical_url(url)
                        if not url_key or url_key in urls:
                            continue
                        cat = detect_signal(title + ' ' + excerpt)
                        company = detect_company(title + ' ' + excerpt, companies)
                        if not cat or not company:
                            continue
                        urls.add(url_key)
                        found.append({'Date de détection': day.isoformat(), 'Actualité': title[:280],
                                      'Entreprise': company, 'Catégorie': cat,
                                      'Pays': country_from_location(title + ' ' + excerpt) or 'Non précisé',
                                      'Source': source, 'Lien': url})
                except Exception as exc:
                    consecutive_errors += 1
                    print(f'⚠️ [Actualites / {source}] {type(exc).__name__}')
                    if consecutive_errors >= 3:
                        print('⚠️ [Actualites] Moteur indisponible; arret anticipe des recherches.')
                        break
                if sleep_seconds:
                    time.sleep(sleep_seconds)
    except Exception as exc:
        print(f'⚠️ [Actualites] {type(exc).__name__}: {str(exc)[:150]}')
    return found


def merge_signals(previous: list[dict], incoming: list[dict], day: date | None = None) -> list[dict]:
    """Garde les 180 derniers jours, sans perdre la date initiale de detection."""
    today = pd.Timestamp(day or date.today())
    result = {}
    for row in previous + incoming:
        url = canonical_url(row.get('Lien'))
        if not url:
            continue
        try:
            detected = pd.Timestamp(row.get('Date de détection'))
        except (ValueError, TypeError):
            continue
        if detected.tz is not None:
            detected = detected.tz_localize(None)
        if detected > today or (today - detected).days > 180:
            continue
        normalized = {c: str(row.get(c, '') or '') for c in SIGNAL_COLUMNS}
        if not normalized['Entreprise'] or not normalized['Actualité']:
            continue
        if url in result:
            old = result[url]
            normalized['Date de détection'] = min(old['Date de détection'], normalized['Date de détection'])
        result[url] = normalized
    return sorted(result.values(), key=lambda r: r['Date de détection'], reverse=True)


def update_signals(output: str | Path, companies: list[str], day: date | None = None,
                   ddgs_factory=None, budget: int | None = None) -> dict:
    output = Path(output)
    if budget is None:
        try:
            budget = int(os.getenv('NEWS_MAX_QUERIES', '5'))
        except ValueError:
            budget = 4
    rows = scan_public_signals(companies, day=day, budget=budget, ddgs_factory=ddgs_factory)
    old = pd.read_csv(output, dtype=str, keep_default_na=False).to_dict('records') if output.exists() else []
    merged = merge_signals(old, rows, day=day)
    if rows or not output.exists():
        temp = output.with_suffix('.csv.tmp')
        pd.DataFrame(merged, columns=SIGNAL_COLUMNS).to_csv(temp, index=False, encoding='utf-8')
        os.replace(temp, output)
    return {'signaux_detectes': len(rows), 'signaux_total': len(merged),
            'signaux_nouveaux': max(0, len(merged) - len(merge_signals(old, [], day=day)))}
