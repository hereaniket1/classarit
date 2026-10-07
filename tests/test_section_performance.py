"""Verify lightweight projections and request-scoped authorization."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app.workspaces.access import access
from app.workspaces.services import queries
from app.services import telemetry


class SectionPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.a = SimpleNamespace(id='w', member={'id':'m'}, user={'id':'u'},
                                 roles={'OWNER'}, workspace={'id':'w','timezone':'UTC'}, db=MagicMock())
        self.a.db.all.return_value = []
        self.a.db.first.return_value = {}

    def test_tabs_never_load_quick_add_references(self):
        with patch.object(queries, '_action_refs') as refs:
            for tab in ['dashboard','calendar','classes','students','sessions','venues','settings','reporting']:
                with self.subTest(tab=tab):
                    queries.section(self.a, tab)
            refs.assert_not_called()
            queries.section(self.a, 'action-refs')
            refs.assert_called_once()

    def test_reporting_counts_use_one_statement(self):
        queries.section(self.a, 'reporting')
        self.a.db.first.assert_called_once()
        self.a.db.all.assert_not_called()

    def test_related_records_are_filtered_in_database(self):
        queries._related(self.a, 'session_participants', 'session_id', {'session'})
        sql = self.a.db.all.call_args.args[0]
        self.assertIn('workspace_id=:w', sql)
        self.assertIn('session_id=ANY(:ids)', sql)
        self.a.db.all.reset_mock()
        self.assertEqual(queries._related(self.a, 'session_participants', 'session_id', set()), [])
        self.a.db.all.assert_not_called()

    def test_membership_roles_share_lookup_and_mutations_keep_lock(self):
        for method in ['GET','POST']:
            db = MagicMock()
            db.first.side_effect = [{'id':'w','status':'ACTIVE'}, {'id':'m','access_roles':['TEACHER']}]
            result = access('w', SimpleNamespace(method=method), db, {'id':'u'})
            self.assertEqual(result.roles, {'TEACHER'})
            self.assertEqual('FOR UPDATE' in db.first.call_args_list[0].args[0], method == 'POST')
            db.all.assert_not_called()

    def test_missing_membership_is_rejected(self):
        db = MagicMock()
        db.first.side_effect = [{'id':'w','status':'ACTIVE'}, None]
        with self.assertRaises(HTTPException) as error:
            access('w', SimpleNamespace(method='GET'), db, {'id':'u'})
        self.assertEqual(error.exception.status_code, 404)

    def test_telemetry_does_not_prune_for_every_request(self):
        engine = MagicMock()
        conn = engine.begin.return_value.__enter__.return_value
        with patch.object(telemetry, 'auth_engine', return_value=engine), \
             patch.object(telemetry, '_next_cleanup', 0):
            for _ in range(3):
                telemetry._insert_metric('GET','/api/test','/api/test',200,10,None)
        statements = [str(call.args[0]) for call in conn.execute.call_args_list]
        self.assertEqual(sum('DELETE' in sql for sql in statements), 1)
        self.assertEqual(sum('INSERT' in sql for sql in statements), 3)


if __name__ == '__main__':
    unittest.main()
