"""Teste en direct chaque source "page carrieres officielle" et affiche un tableau.

Usage, depuis le Mac (IP perso) :
    python3 verifier_sources.py

Pour chaque maison : une seule requete legere, puis un verdict :
    OK      la source repond et renvoie des offres
    VIDE    la source repond mais 0 offre pour le test (normal si peu d'offres)
    KO      erreur (404 = identifiant faux, 429 = trop de requetes, etc.)

Rien n'est enregistre : ce script ne modifie ni le flux ni le CRM.
"""
from __future__ import annotations

import time

import requests

from sources_plus import (HEADERS, fetch_oracle_recruiting, fetch_smartrecruiters,
                          fetch_successfactors, read_sources_config)

# Portails Workday : les 2 verifies + les anciens tenants devines, pour confirmer.
WORKDAY = [
    ('Richemont (Cartier, VCA, IWC…)', 'richemont.wd3', 'richemont', 'Richemont', True),
    ('Kering (Gucci, Saint Laurent…)', 'kering.wd3', 'kering', 'Kering', True),
    ('LVMH (ancien, devine)', 'lvmh.wd3', 'lvmh', 'LVMH', False),
    ('Louis Vuitton (ancien, devine)', 'louisvuitton.wd3', 'louisvuitton', 'LouisVuitton', False),
    ('Dior (ancien, devine)', 'christiandior.wd3', 'christiandior', 'ChristianDiorCouture', False),
    ('TAG Heuer (ancien, devine)', 'tagheuer.wd3', 'tagheuer', 'TAGHeuer', False),
    ('Tiffany (ancien, devine)', 'tiffany.wd5', 'tiffany', 'TiffanyCareers', False),
]


def check_workday(session, host, tenant, site):
    url = f'https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs'
    resp = session.post(url, json={'appliedFacets': {}, 'limit': 20, 'offset': 0,
                                   'searchText': 'Director'},
                        headers={**HEADERS, 'Content-Type': 'application/json',
                                 'Accept': 'application/json'}, timeout=15)
    if resp.status_code != 200:
        return 'KO', f'HTTP {resp.status_code}', 0, ''
    data = resp.json()
    posts = data.get('jobPostings') or []
    sample = posts[0].get('title', '') if posts else ''
    return ('OK' if posts else 'VIDE'), f"{data.get('total', len(posts))} au total", len(posts), sample


def run(label, fn):
    try:
        return fn()
    except requests.HTTPError as exc:
        code = getattr(exc.response, 'status_code', '?')
        return 'KO', f'HTTP {code}', 0, ''
    except Exception as exc:  # on veut un verdict par ligne, jamais un plantage
        return 'KO', type(exc).__name__, 0, ''


def one_keyword(board, keyword='director'):
    return {**board, 'keywords': [keyword]}


def main():
    session = requests.Session()
    config = read_sources_config()
    results = []

    for label, host, tenant, site, verified in WORKDAY:
        results.append((f'Workday / {label}', *run(label, lambda: check_workday(session, host, tenant, site))))
        time.sleep(1)

    for board in config.get('successfactors', []):
        def sf(board=board):
            rows = fetch_successfactors(session, one_keyword(board))
            return ('OK' if rows else 'VIDE'), board['host'], len(rows), rows[0]['title'] if rows else ''
        results.append((f"SuccessFactors / {board['company']}", *run(board['company'], sf)))
        time.sleep(1)

    for board in config.get('oracle', []):
        def orc(board=board):
            rows = fetch_oracle_recruiting(session, one_keyword(board))
            return ('OK' if rows else 'VIDE'), board['host'], len(rows), rows[0]['title'] if rows else ''
        results.append((f"Oracle / {board['company']}", *run(board['company'], orc)))
        time.sleep(1)

    for board in config.get('smartrecruiters', []):
        def sr(board=board):
            rows = fetch_smartrecruiters(session, board)
            return ('OK' if rows else 'VIDE'), board['company_id'], len(rows), rows[0]['title'] if rows else ''
        results.append((f"SmartRecruiters / {board['company']}", *run(board['company'], sr)))
        time.sleep(1)

    width = max(len(r[0]) for r in results) + 2
    print(f"\n{'Source'.ljust(width)}Verdict  Offres  Detail / exemple")
    print('-' * (width + 70))
    for name, verdict, detail, count, sample in results:
        mark = {'OK': '✅', 'VIDE': '⚪', 'KO': '❌'}[verdict]
        print(f"{name.ljust(width)}{mark} {verdict:<5} {count:>5}   {detail}  {sample[:50]}")
    ok = sum(1 for r in results if r[1] == 'OK')
    print(f'\n{ok}/{len(results)} sources renvoient des offres. Copie ce tableau a Claude pour ajuster.')


if __name__ == '__main__':
    main()
