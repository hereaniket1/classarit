import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4
from app.routes import dashboard
from app.views import templates
from fastapi import HTTPException


class WorkspaceControlTests(unittest.TestCase):
    def test_default_requires_active_membership_and_saves_for_current_user(self):
        user={'id':uuid4()}
        payload=dashboard.DefaultWorkspaceInput(workspace_id=uuid4())
        db=MagicMock()
        db.first.return_value=None
        with self.assertRaises(HTTPException):
            dashboard.set_default_workspace(payload,user,db)
        db.execute.assert_not_called()
        db.first.return_value={'exists':True}
        result=dashboard.set_default_workspace(payload,user,db)
        self.assertEqual(result['default_workspace_id'],str(payload.workspace_id))
        self.assertEqual(db.execute.call_args.kwargs,{'w':payload.workspace_id,'u':user['id']})

    def test_organization_add_button_stops_at_three_workspaces(self):
        user = {'id': uuid4(), 'user_type':'OWNER', 'account_type':'ORGANIZATION', 'full_name':'Owner', 'email':'owner@example.com'}
        for count in [1,2,3]:
            choices = [{'id':uuid4(), 'owner_user_id':user['id'], 'workspace_type':'INSTITUTE', 'name':f'Workspace {i}'} for i in range(count)]
            a = SimpleNamespace(user=user, workspace=choices[0], roles={'OWNER'}, db=MagicMock())
            with patch.object(dashboard, 'memberships', return_value=choices), \
                 patch.object(dashboard.templates, 'TemplateResponse', side_effect=lambda name, context: context):
                context = dashboard.workspace_page(SimpleNamespace(session={}), a)
            self.assertEqual(context['can_add_workspace'], count < 3)
            html = templates.get_template('workspace.html').render(**context)
            self.assertEqual('>Add workspace</a>' in html, count < 3)
            self.assertIn('id="make-default-workspace"', html)
            self.assertIn('Manage workspaces', html)

    def test_individual_has_no_extra_workspace_controls(self):
        user = {'id':uuid4(), 'user_type':'OWNER', 'account_type':'INDIVIDUAL', 'full_name':'Teacher'}
        workspace = {'id':uuid4(), 'owner_user_id':user['id'], 'workspace_type':'INDIVIDUAL', 'name':'Teaching'}
        a = SimpleNamespace(user=user, workspace=workspace, roles={'OWNER'}, db=MagicMock())
        with patch.object(dashboard, 'memberships', return_value=[workspace]), \
             patch.object(dashboard.templates, 'TemplateResponse', side_effect=lambda name, context: context):
            context = dashboard.workspace_page(SimpleNamespace(session={}), a)
        html = templates.get_template('workspace.html').render(**context)
        self.assertNotIn('>Add workspace</a>', html)
        self.assertNotIn('id="make-default-workspace"', html)


if __name__ == '__main__':
    unittest.main()
