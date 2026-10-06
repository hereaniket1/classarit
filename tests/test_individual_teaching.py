"""Individual accounts are single-teacher workspaces; offline service checks."""
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.workspaces.services import catalog, organizations

class IndividualTests(unittest.TestCase):
    def setUp(self):
        self.owner = uuid4()
        self.a = SimpleNamespace(id=uuid4(), workspace={'workspace_type':'INDIVIDUAL','owner_user_id':uuid4()}, member={'id':self.owner}, roles={'OWNER','TEACHER'}, db=MagicMock(), allow=MagicMock())
        self.a.db.first.side_effect = [{'id':self.owner}, {'valid':True}]

    def test_missing_teacher_defaults_to_owner(self):
        self.assertEqual(catalog.teachers(self.a, []), [self.owner])

    def test_other_teacher_is_rejected(self):
        with self.assertRaises(HTTPException):
            catalog.teachers(self.a, [uuid4()])

    def test_create_class_assigns_owner(self):
        self.a.db.insert.return_value = {'id':uuid4()}
        with patch.object(catalog, '_program_fields', return_value={}), patch.object(catalog, '_replace_program_teachers') as save:
            catalog.program(self.a, SimpleNamespace(teacher_ids=[]))
        self.assertEqual(save.call_args.args[2], [self.owner])

    def test_individual_invite_rejected_before_writes(self):
        with self.assertRaises(HTTPException):
            organizations.invite(self.a, SimpleNamespace(email='new@example.com', roles=['TEACHER']))
        self.a.db.insert.assert_not_called()
        self.a.db.execute.assert_not_called()

    def test_old_individual_invite_cannot_be_accepted(self):
        invitation={'id':uuid4(),'workspace_id':self.a.id,'status':'PENDING','expires_at':datetime.now(timezone.utc)+timedelta(hours=1)}
        self.a.db.first.side_effect=[invitation,self.a.workspace,invitation]
        with self.assertRaises(HTTPException):
            organizations.accept_invite(self.a.db, {'id':uuid4()}, 'old-token')
        self.a.db.insert.assert_not_called()

    def test_organization_retains_multiple_teachers(self):
        self.a.workspace['workspace_type']='INSTITUTE'
        first,second=uuid4(),uuid4()
        self.assertEqual(catalog.teachers(self.a,[first,second]),[first,second])

if __name__ == '__main__':
    unittest.main()
