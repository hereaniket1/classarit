"""Explicit integration check: real schema, rolled-back test data, mocked email.

Run manually after migration 017: python tests/invitation_db_check.py
"""
from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from sqlalchemy import text
from app.auth.database import auth_engine, schema_name
from app.auth import repository
from app.routes.admissions import InterestInput
from app.services import admissions


def check():
    schema = schema_name()
    with auth_engine().connect() as conn:
        transaction = conn.begin()

        class RollbackEngine:
            @contextmanager
            def begin(self):
                yield conn

            connect = begin

        try:
            reviewer = conn.execute(text(f"SELECT app_user_id FROM {schema}.user_emails WHERE lower(email::text)=:email"),
                                    {'email':'aniketpathak1@gmail.com'}).scalar_one()
            email = f'invitation-test-{uuid4().hex}@example.com'
            payload = InterestInput(full_name='Invitation integration test', email=email, country='IN', usage_type='INDIVIDUAL')
            with patch.object(admissions, 'auth_engine', return_value=RollbackEngine()), patch.object(repository, 'auth_engine', return_value=RollbackEngine()), patch.object(repository, 'setting_enabled', side_effect=lambda key, default: key == 'invite_request_enabled'), patch.object(admissions, 'setting_enabled', return_value=True), patch.object(admissions, 'send_email', return_value={'id':'mock-provider-accepted'}) as mail, patch.object(repository, 'generate_otp', return_value='123456'):
                claims = {'sub':uuid4().hex, 'email':email, 'email_verified':True, 'name':'Invitation test'}
                response = admissions.request_invitation(payload, 'https://classarit.test')
                challenge = UUID(response['challenge_id'])
                row = conn.execute(text(f'SELECT * FROM {schema}.interest WHERE verification_id=:id'), {'id':challenge}).mappings().one()
                assert mail.call_count == 1  # Applicant OTP only; owner must wait for verification.
                admissions.retry_owner_notifications()
                assert mail.call_count == 1
                assert row['email_verified_at'] is None
                try:
                    repository.google_account(claims)
                    raise AssertionError('Unverified Google signup accepted')
                except repository.AccountUnavailable:
                    pass
                try:
                    admissions.review_request(row['id'], 'APPROVED', reviewer, 'https://classarit.test/login#signup')
                    raise AssertionError('Unverified request was approved')
                except HTTPException as error:
                    assert error.status_code == 409
                try:
                    admissions.verify_request(challenge, '000000', 'https://classarit.test')
                    raise AssertionError('Incorrect OTP accepted')
                except HTTPException as error:
                    assert error.status_code == 400
                assert conn.execute(text(f'SELECT verification_attempts FROM {schema}.interest WHERE id=:id'), {'id':row['id']}).scalar_one() == 1
                admissions.verify_request(challenge, '123456', 'https://classarit.test')
                admissions.verify_request(challenge, '123456', 'https://classarit.test')
                assert mail.call_count == 3  # Only one receipt, including replay.
                assert 'Continue with Google' in mail.call_args.args[2]
                try:
                    repository.google_account(claims)
                    raise AssertionError('Unapproved Google signup accepted')
                except repository.AccountUnavailable:
                    pass
                approved = admissions.review_request(row['id'], 'APPROVED', reviewer, 'https://classarit.test/login#signup')
                assert approved['email_sent'] and mail.call_count == 4
                assert admissions.admission_type(conn, email) == 'INDIVIDUAL'
                assert admissions.list_requests('APPROVED', request_id=row['id'])['requests'][0]['email_verified_at']
                assert conn.execute(text(f'SELECT count(*) FROM {schema}.user_emails WHERE email=:email'), {'email':email}).scalar_one() == 0
                new_user = repository.google_account(claims)
                assert new_user['is_new_user']
                assert conn.execute(text(f'SELECT account_type FROM {schema}.app_users WHERE id=:id'), {'id':UUID(new_user['id'])}).scalar_one() == 'INDIVIDUAL'
                assert not repository.google_account(claims)['is_new_user']
            print('Passed: real DB request, OTP, approval, Google account creation and repeat login, account type and delivery markers. All email mocked; test data rolled back.')
        finally:
            transaction.rollback()


if __name__ == '__main__':
    try:
        check()
    except Exception as error:
        print(f'Integration check failed: {type(error).__name__}; no credentials printed.', file=sys.stderr)
        diagnostic = getattr(getattr(error, 'orig', None), 'diag', None)
        if diagnostic:
            print(diagnostic.message_primary, file=sys.stderr)
        sys.exit(1)
