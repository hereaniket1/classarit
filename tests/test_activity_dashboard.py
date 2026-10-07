"""Dashboard date boundaries and teacher visibility, without a live database."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from app.workspaces.services import queries


class ActivityDashboardTests(unittest.TestCase):
    def test_two_day_window_uses_workspace_timezone_and_teacher_scope(self):
        for roles in ({'TEACHER'}, {'OWNER'}):
            access = SimpleNamespace(id='workspace', member={'id': 'teacher'},
                                     roles=roles, workspace={'timezone': 'Asia/Kolkata'}, db=MagicMock())
            access.db.all.return_value = [{'id': 'session'}]
            # UTC Jan 31 is already Feb 1 in this workspace.
            with patch.object(queries, 'datetime') as clock, \
                 patch.object(queries, '_blank', return_value={}), \
                 patch.object(queries, '_action_refs'), \
                 patch.object(queries, '_load_business_profile'):
                clock.now.return_value = datetime(2026, 1, 31, 20, tzinfo=timezone.utc)
                result = queries.section(access, 'dashboard')
            statement = access.db.all.call_args.args[0]
            values = access.db.all.call_args.kwargs
            self.assertEqual(values['until'].isoformat(), '2026-02-03T00:00:00+05:30')
            self.assertEqual('st.membership_id=:m' in statement, roles == {'TEACHER'})
            self.assertIn("s.status='SCHEDULED'", statement)
            self.assertIn('s.ends_at>:now', statement)
            self.assertEqual(result['sessions'], [{'id': 'session'}])


if __name__ == '__main__':
    unittest.main()
