"""Offline admission/security regressions; never connects to the configured DB."""
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.auth import repository
from app.main import app
from app.routes.admissions import InterestInput
from app.services import admissions, content, product_settings
from app.workspaces.schemas import WorkspaceInput
from app.workspaces.services import organizations


def result(row):
    response = MagicMock()
    response.first.return_value = row
    response.mappings.return_value.first.return_value = row
    return response


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.engine = MagicMock()
        self.engine.begin.return_value.__enter__.return_value = self.conn
        self.engine.connect.return_value.__enter__.return_value = self.conn

    def test_unapproved_email_is_blocked(self):
        self.conn.execute.return_value = result(None)
        with patch.object(admissions, 'setting_enabled', return_value=True):
            with self.assertRaises(repository.AccountUnavailable):
                admissions.admission_type(self.conn, 'new@example.com')

    def test_approved_type_is_returned(self):
        self.conn.execute.return_value = result({'usage_type': 'ORGANIZATION'})
        with patch.object(admissions, 'setting_enabled', return_value=True):
            self.assertEqual(admissions.admission_type(self.conn, 'new@example.com'), 'ORGANIZATION')

    def test_open_signup_does_not_need_interest_row(self):
        with patch.object(admissions, 'setting_enabled', return_value=False):
            self.assertIsNone(admissions.admission_type(self.conn, 'new@example.com'))
        self.conn.execute.assert_not_called()

    def test_staff_invite_checks_email_hash_expiry_and_workspace(self):
        self.conn.execute.return_value = result((1,))
        with patch.object(admissions, 'setting_enabled', return_value=True):
            self.assertIsNone(admissions.admission_type(self.conn, 'staff@example.com', 'secret-token'))
        statement, params = self.conn.execute.call_args.args
        sql = str(statement)
        self.assertEqual(params['email'], 'staff@example.com')
        self.assertNotEqual(params['token'], 'secret-token')
        self.assertIn('expires_at>CURRENT_TIMESTAMP', sql)
        self.assertIn("w.status='ACTIVE'", sql)
        self.assertIn("i.status='PENDING'", sql)

    def test_invalid_staff_invite_does_not_bypass_approval(self):
        self.conn.execute.return_value = result(None)
        with patch.object(admissions, 'setting_enabled', return_value=True):
            with self.assertRaises(repository.AccountUnavailable):
                admissions.admission_type(self.conn, 'different@example.com', 'invalid')

    def test_mode_query_failure_does_not_open_signup(self):
        self.conn.execute.side_effect = OperationalError('SELECT', {}, Exception())
        with patch.object(product_settings, 'auth_engine', return_value=self.engine):
            with self.assertRaises(OperationalError):
                product_settings.setting_enabled('invite_request_enabled', False)

    def test_disabling_invitation_mode_enables_signup_atomically(self):
        with patch.object(product_settings, 'auth_engine', return_value=self.engine), patch.object(product_settings, 'all_settings', return_value={}):
            product_settings.set_settings({'invite_request_enabled': False, 'signup_enabled': False}, uuid4())
        saved = {call.args[1]['key']: call.args[1]['value'] for call in self.conn.execute.call_args_list}
        self.assertEqual(saved, {'invite_request_enabled': 'false', 'signup_enabled': 'true'})
        self.engine.begin.assert_called_once()

    def test_enabling_invitation_mode_preserves_signup_control(self):
        with patch.object(product_settings, 'auth_engine', return_value=self.engine), patch.object(product_settings, 'all_settings', return_value={}):
            product_settings.set_settings({'invite_request_enabled': True}, uuid4())
        saved = {call.args[1]['key']: call.args[1]['value'] for call in self.conn.execute.call_args_list}
        self.assertEqual(saved, {'invite_request_enabled': 'true'})

    def test_duplicate_request_does_not_reset_approval_or_send_email(self):
        self.conn.execute.side_effect = [result(None), result(None), result({'id': uuid4()})]
        payload = InterestInput(full_name='Applicant', email='TEST@example.com', country='IN', usage_type='INDIVIDUAL')
        with patch.object(admissions, 'auth_engine', return_value=self.engine), patch.object(admissions, 'setting_enabled', return_value=True), patch.object(admissions, 'send_email') as send:
            self.assertTrue(admissions.request_invitation(payload)['ok'])
        self.assertFalse(any('UPDATE' in str(c.args[0]) or 'INSERT' in str(c.args[0]) for c in self.conn.execute.call_args_list))
        send.assert_not_called()

    def test_existing_account_cannot_request_invitation(self):
        self.conn.execute.side_effect = [result(None), result((1,))]
        payload = InterestInput(full_name='Existing', email='existing@example.com', country='IN', usage_type='INDIVIDUAL')
        with patch.object(admissions, 'auth_engine', return_value=self.engine), patch.object(admissions, 'setting_enabled', return_value=True):
            with self.assertRaises(HTTPException) as error:
                admissions.request_invitation(payload)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(error.exception.detail, repository.ACCOUNT_EXISTS_MESSAGE)
        self.assertEqual(self.conn.execute.call_count, 2)

    def test_signup_existing_account_message_is_consistent(self):
        client = TestClient(app)
        with patch('app.auth.routes.repository.start_password_registration', side_effect=repository.LinkingRequired()):
            response = client.post('/auth/password/register', json={
                'full_name': 'Existing', 'phone': '5551234567',
                'email': 'existing@example.com', 'password': 'a sufficiently long password',
                'account_type': 'INDIVIDUAL', 'accepted_terms': True,
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], repository.ACCOUNT_EXISTS_MESSAGE)

    def test_request_closed_when_mode_off(self):
        with patch.object(admissions, 'setting_enabled', return_value=False):
            with self.assertRaises(HTTPException) as error:
                admissions.request_invitation(MagicMock())
        self.assertEqual(error.exception.status_code, 409)

    def test_approval_never_automatically_sends_email(self):
        self.conn.execute.return_value = result({'id': uuid4(), 'status': 'APPROVED'})
        with patch.object(admissions, 'auth_engine', return_value=self.engine), patch.object(admissions, 'send_email') as send:
            admissions.review_request(uuid4(), 'APPROVED', uuid4())
        send.assert_not_called()

    def test_failed_email_does_not_record_delivery(self):
        self.conn.execute.return_value = result({'status': 'APPROVED', 'email': 'a@example.com', 'full_name': 'A', 'recently_sent': False})
        with patch.object(admissions, 'auth_engine', return_value=self.engine), patch.object(admissions, 'setting_enabled', return_value=True), patch.object(admissions, 'send_email', return_value={'skipped': True}):
            with self.assertRaises(HTTPException):
                admissions.email_approval(uuid4(), 'http://localhost/login')
        self.assertEqual(self.conn.execute.call_count, 1)

    def test_provider_success_records_delivery(self):
        self.conn.execute.return_value = result({'status': 'APPROVED', 'email': 'a@example.com', 'full_name': '<script>', 'recently_sent': False})
        with patch.object(admissions, 'auth_engine', return_value=self.engine), patch.object(admissions, 'setting_enabled', return_value=True), patch.object(admissions, 'send_email', return_value={'id': 'accepted'}) as send:
            self.assertTrue(admissions.email_approval(uuid4(), 'http://localhost/login')['ok'])
        self.assertIn('&lt;script&gt;', send.call_args.args[2])
        self.assertIn('last_email_sent_at=CURRENT_TIMESTAMP', str(self.conn.execute.call_args.args[0]))

    def test_revoked_request_blocks_otp_activation(self):
        with patch.object(repository, 'auth_engine', return_value=self.engine), patch.object(repository, '_verified_challenge', return_value={'target_email': 'a@example.com', 'account_type': 'INDIVIDUAL'}), patch.object(repository, 'setting_enabled', return_value=True), patch.object(repository, 'admission_type', side_effect=repository.AccountUnavailable('Revoked')):
            with self.assertRaises(repository.AccountUnavailable):
                repository.verify_registration(str(uuid4()), '123456')
        self.conn.execute.assert_not_called()

    def test_all_registration_paths_use_admission_gate(self):
        self.conn.execute.return_value = result(None)
        with patch.object(repository, 'auth_engine', return_value=self.engine), patch.object(repository, 'setting_enabled', return_value=True), patch.object(repository, 'admission_type', side_effect=repository.AccountUnavailable('Not approved')) as gate:
            for method, args in [
                (repository.start_registration, ('a@example.com', 'A', 'INDIVIDUAL')),
                (repository.start_password_registration, ('a@example.com', 'A', '1234567', 'long-enough-password', 'INDIVIDUAL')),
                (repository.google_account, ({'sub': 'google-sub', 'email': 'a@example.com', 'email_verified': True},)),
            ]:
                with self.subTest(method=method.__name__), self.assertRaises(repository.AccountUnavailable):
                    method(*args)
            self.assertEqual(gate.call_count, 3)
        self.assertFalse(any('INSERT' in str(c.args[0]) for c in self.conn.execute.call_args_list))

    def test_existing_google_account_does_not_require_new_approval(self):
        self.conn.execute.return_value = result({'id': uuid4(), 'full_name': 'Existing', 'status': 'ACTIVE'})
        with patch.object(repository, 'auth_engine', return_value=self.engine), patch.object(repository, 'admission_type') as gate, patch.object(repository, '_link_verified_contacts'):
            row = repository.google_account({'sub': 'existing', 'email': 'a@example.com', 'email_verified': True})
        self.assertFalse(row['is_new_user'])
        gate.assert_not_called()

    def test_signup_account_type_must_match_approved_request(self):
        self.assertEqual(repository.resolve_account_type('INDIVIDUAL'), 'INDIVIDUAL')
        self.assertEqual(repository.resolve_account_type('ORGANIZATION', 'ORGANIZATION'), 'ORGANIZATION')
        with self.assertRaises(repository.AccountUnavailable):
            repository.resolve_account_type('INDIVIDUAL', 'ORGANIZATION')
        with self.assertRaises(repository.AccountUnavailable):
            repository.resolve_account_type('UNKNOWN')

    def test_complete_business_profile_is_reused_without_overwrite(self):
        db = MagicMock()
        profile = {k: 'saved' for k in ('id','legal_name','gstin','owner_aadhaar_number','address_line1','city','state','postal_code','country')}
        profile['status'] = 'ACTIVE'
        db.first.return_value = profile
        payload = WorkspaceInput(name='Second branch', workspace_type='INSTITUTE')
        self.assertEqual(organizations._business_profile(db, uuid4(), payload), profile)
        db.execute.assert_not_called()
        db.insert.assert_not_called()

    def test_incomplete_legacy_profile_still_needs_identity(self):
        db = MagicMock()
        db.first.return_value = {'id': uuid4(), 'legal_name': 'Legacy', 'status': 'ACTIVE'}
        with self.assertRaises(HTTPException) as error:
            organizations._business_profile(db, uuid4(), WorkspaceInput(name='Branch', workspace_type='INSTITUTE'))
        self.assertEqual(error.exception.status_code, 422)

    def test_account_type_cannot_be_changed_through_workspace_creation(self):
        db = MagicMock()
        db.first.return_value = {'user_type': 'OWNER', 'account_type': 'INDIVIDUAL'}
        with self.assertRaises(HTTPException):
            organizations.create_workspace(db, {'id': uuid4()}, WorkspaceInput(name='Company', workspace_type='INSTITUTE'))
        db.insert.assert_not_called()

    def test_fourth_organization_workspace_is_rejected_before_insert(self):
        db = MagicMock()
        db.first.side_effect = [{'user_type': 'OWNER', 'account_type': 'ORGANIZATION'}, {'total': 3}]
        db.all.return_value = [{'workspace_type': 'INSTITUTE'}]
        with self.assertRaises(HTTPException) as error:
            organizations.create_workspace(db, {'id': uuid4()}, WorkspaceInput(name='Fourth', workspace_type='INSTITUTE'))
        self.assertIn('three', error.exception.detail)
        db.insert.assert_not_called()

    def test_terms_version_changes_with_content(self):
        self.conn.execute.side_effect = [result({'title': 'Terms', 'body': 'One'}), result({'title': 'Terms', 'body': 'Two'})]
        with patch.object(content, 'auth_engine', return_value=self.engine):
            self.assertNotEqual(content.terms()['version'], content.terms()['version'])

    def test_executive_api_requires_identity_and_csrf(self):
        async def no_metrics(*args):
            pass
        client = TestClient(app)
        with patch('app.main.record_api_metric', no_metrics), patch('app.auth.dependencies.current_user', return_value=None):
            self.assertEqual(client.get('/api/executive/invitation-requests').status_code, 401)
        with patch('app.main.record_api_metric', no_metrics), patch('app.auth.dependencies.current_user', return_value={'id': str(uuid4()), 'email': 'other@example.com'}):
            self.assertEqual(client.get('/api/executive/invitation-requests').status_code, 403)
        with patch('app.main.record_api_metric', no_metrics), patch('app.auth.dependencies.current_user', return_value={'id': str(uuid4()), 'email': 'aniketpathak1@gmail.com'}):
            self.assertEqual(client.patch('/api/executive/invitation-requests/'+str(uuid4()), json={'status':'APPROVED'}).status_code, 403)
            self.assertEqual(client.put('/api/executive/terms', json={'title':'T','body':'B'}).status_code, 403)

    def test_signup_api_requires_account_type(self):
        client = TestClient(app)
        response = client.post('/auth/password/register', json={
            'full_name': 'Applicant', 'phone': '5551234567',
            'email': 'applicant@example.com', 'password': 'a sufficiently long password',
            'accepted_terms': True,
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn('account_type', response.text)


if __name__ == '__main__':
    unittest.main()
