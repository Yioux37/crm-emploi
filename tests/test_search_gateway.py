import unittest
from unittest.mock import patch
from search_gateway import BraveWebSearch, default_search_client


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {'web': {'results': [{'title': 'Directeur supply chain',
                                     'url': 'https://jobs.example.com/123',
                                     'description': 'Paris, France'}]}}


class FakeSession:
    def __init__(self):
        self.url = None
        self.params = None
        self.headers = None

    def get(self, url, params, headers, timeout):
        self.url, self.params, self.headers = url, params, headers
        return FakeResponse()

    def close(self):
        pass


class SearchGatewayTests(unittest.TestCase):
    def test_brave_maps_to_ddgs_schema_without_exposing_api_key(self):
        session = FakeSession()
        with BraveWebSearch('secret-private-key', session) as client:
            rows = client.text('supply chain director luxury', 10)
        self.assertEqual(rows[0]['href'], 'https://jobs.example.com/123')
        self.assertEqual(session.params['count'], 10)
        self.assertEqual(session.headers['X-Subscription-Token'], 'secret-private-key')
        self.assertNotIn('secret-private-key', session.url)

    def test_key_enables_brave_only_when_configured(self):
        with patch.dict('os.environ', {'BRAVE_SEARCH_API_KEY': 'some-key'}):
            factory = default_search_client()
            self.assertIsInstance(factory(), BraveWebSearch)


if __name__ == '__main__':
    unittest.main()
