"""Recherche web via API contractuelle Brave (facultative), ou DDGS de secours.

Aucune cle n'est stockee dans le depot. La recherche renvoie des LIENS indexes,
pas le contenu integral des pages.
"""
from __future__ import annotations

import os
import requests

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None


class BraveWebSearch:
    URL = 'https://api.search.brave.com/res/v1/web/search'

    def __init__(self, api_key: str, session=None):
        self.key = api_key
        self.session = session or requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    def text(self, query: str, max_results: int = 10):
        response = self.session.get(
            self.URL,
            params={'q': query[:600], 'count': max(1, min(20, max_results))},
            headers={'X-Subscription-Token': self.key, 'Accept': 'application/json'},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json().get('web', {}).get('results', [])
        return [dict(title=r.get('title', ''), href=r.get('url', ''),
                     body=r.get('description', '')) for r in data]


def default_search_client():
    key = os.getenv('BRAVE_SEARCH_API_KEY', '').strip()
    if key:
        return lambda: BraveWebSearch(key)
    return DDGS
