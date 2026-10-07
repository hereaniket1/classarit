"""Asset delivery regressions; no live database or application startup."""
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


class PagePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_static_files_revalidate_without_redownloading(self):
        response = self.client.get('/static/styles.css')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('no-store', response.headers['cache-control'])
        cached = self.client.get('/static/styles.css', headers={'If-None-Match': response.headers['etag']})
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.content, b'')

    def test_bootstrap_is_local_and_compressed(self):
        response = self.client.get('/static/vendor/bootstrap/bootstrap.min.css', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('v5.3.3', response.text[:200])
        self.assertEqual(response.headers['content-encoding'], 'gzip')
        for path in Path('app/templates').rglob('*.html'):
            self.assertNotIn('https://cdn.jsdelivr.net', path.read_text(encoding='utf-8'))

    def test_private_pages_still_cannot_be_cached(self):
        response = self.client.get('/profile', follow_redirects=False)
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertIn('app;dur=', response.headers['server-timing'])


if __name__ == '__main__':
    unittest.main()
