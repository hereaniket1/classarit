import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.workspaces.routes.teaching import search_students


class StudentLookupTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.access = SimpleNamespace(id=uuid4(), db=self.db)

    def test_short_queries_do_not_hit_database(self):
        self.assertEqual(search_students('a', self.access), {'students': []})
        self.db.all.assert_not_called()

    def test_search_returns_minimal_name_and_email_matches(self):
        self.db.all.return_value = [{'id': 'student-1', 'full_name': 'Asha Rao', 'email': 'asha@example.com', 'phone': '+91 99999'}]
        result = search_students('Asha', self.access)
        self.assertEqual(result['students'][0]['full_name'], 'Asha Rao')
        query = self.db.all.call_args.args[0]
        self.assertIn("status='ACTIVE'", query)
        self.assertIn('full_name ILIKE :q', query)
        self.assertIn("COALESCE(email,'') ILIKE :q", query)
        self.assertEqual(self.db.all.call_args.kwargs['w'], self.access.id)
        self.assertEqual(self.db.all.call_args.kwargs['q'], '%Asha%')

    def test_search_is_limited(self):
        self.db.all.return_value = []
        search_students('student', self.access)
        self.assertIn('LIMIT 20', self.db.all.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
