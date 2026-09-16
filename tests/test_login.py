"""Integration tests use a disposable PostgreSQL cluster, never the configured DB.
Run: .venv/bin/python -B -m unittest discover -s tests -v
Requires local initdb/pg_ctl (PostgreSQL 14+).
"""
import os
import sys
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


from workspace_cases import WorkspaceCases
from owner_cases import OwnerCases


class LoginTests(OwnerCases, WorkspaceCases, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='classarit-tests-',dir='/tmp')
        cls.root=Path(cls.temp.name)
        (cls.root/'socket').mkdir()
        subprocess.run(['initdb','-D',str(cls.root/'pg'),'-A','trust','--no-locale','--encoding=UTF8'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['pg_ctl','-D',str(cls.root/'pg'),'-l',str(cls.root/'pg.log'),'-o',f"-k {cls.root/'socket'} -h '' -p 55441",'-w','start'],check=True,stdout=subprocess.DEVNULL)
        cls.addClassCleanup(cls.stop_cluster)
        cls.env=patch.dict(os.environ, {'CLASSARIT_DATA_DIR':str(cls.root/'data'),
            'DB_HOST':str(cls.root/'socket'),'DB_PORT':'55441','DB_NAME':'postgres',
            'DB_USER':os.getenv('USER','aniketpathak'),'DB_PASSWORD':'test','DB_SCHEMA':'classarit','DB_SSLMODE':'disable',
            'GOOGLE_CLIENT_ID':'test-client','GOOGLE_CLIENT_SECRET':'test-secret',
            'GOOGLE_REDIRECT_URI':'http://127.0.0.1:8000/auth/google/callback',
            'RESEND_API_KEY':'','RESEND_FROM_EMAIL':'','OTP_HMAC_SECRET':'test-otp-secret-with-at-least-32-chars',
            'SESSION_SECRET_KEY':'test-session-secret-with-at-least-32-chars','RENDER':'false'})
        cls.env.start();cls.addClassCleanup(cls.env.stop)
        cmd=['psql','-h',str(cls.root/'socket'),'-p','55441','-d','postgres','-v','ON_ERROR_STOP=1']
        # Match hosted installations where citext already lives in public.
        subprocess.run(cmd+['-c','CREATE EXTENSION citext WITH SCHEMA public'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(cmd+['-f',str(ROOT/'setup/auth_schema.sql')],check=True,stdout=subprocess.DEVNULL)
        for migration in ('001_workspaces_and_teaching.sql','002_account_types_and_single_owner.sql','003_owner_staff_separation.sql','004_recurring_session_series.sql','005_workspace_type_role_policy.sql','006_direct_scheduled_participants.sql','007_default_workspace.sql','008_notifications_otp_executive.sql'):
            for _ in range(2):
                subprocess.run([sys.executable,str(ROOT/'setup/apply_migration.py'),migration],check=True,stdout=subprocess.DEVNULL)
        from app.main import app
        from fastapi.testclient import TestClient
        cls.app=app; cls.client_type=TestClient

    @classmethod
    def stop_cluster(cls):
        subprocess.run(['pg_ctl','-D',str(cls.root/'pg'),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)
        from app.database import engine
        engine.dispose()
        cls.temp.cleanup()

    def setUp(self):
        from app.auth.database import auth_engine
        from sqlalchemy import text
        with auth_engine().begin() as conn:
            conn.execute(text('TRUNCATE classarit.app_users CASCADE'))
            conn.execute(text("UPDATE classarit.app_settings SET value='true', updated_by=NULL"))
            conn.execute(text('TRUNCATE classarit.api_request_metrics'))
        self.client=self.client_type(self.app,base_url='http://127.0.0.1:8000')
        self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)

    def login(self, client=None, subject='alice', email='alice@example.com'):
        client=client or self.client
        with patch('app.auth.routes.oauth.google.authorize_access_token',new=AsyncMock(return_value={
            'id_token':'verified-by-mocked-provider','userinfo':{'sub':subject,'email':email,'email_verified':True,'name':subject}})):
            result=client.get('/auth/google/callback')
        self.assertEqual(result.status_code,200,result.text)
        html=client.get('/dashboard').text
        return re.search(r'name="csrf-token" content="([^"]+)"',html).group(1)


    def test_email_otp_registration_and_executive_controls(self):
        sent = []
        with patch('app.services.emailer.send_email', side_effect=lambda *args, **kwargs: sent.append((args, kwargs)) or {'id':'test'}), \
             patch('app.auth.repository.generate_otp', return_value='123456'):
            started = self.client.post('/auth/register/start', json={'full_name':'New Owner','email':'new-owner@example.com'})
            self.assertEqual(started.status_code, 200, started.text)
            self.assertEqual(len(sent), 1)
            verify = self.client.post('/auth/register/verify', json={'challenge_id':started.json()['challenge_id'],'code':'123456'})
            self.assertEqual(verify.status_code, 200, verify.text)
            self.assertTrue(self.client.get('/auth/me').json()['authenticated'])

        self.assertEqual(self.client.get('/executive').status_code, 403)
        existing = self.client_type(self.app, base_url='http://127.0.0.1:8000')
        existing.__enter__(); self.addCleanup(existing.__exit__, None, None, None)
        self.login(existing, 'existing-google', 'existing@example.com')

        exec_client = self.client_type(self.app, base_url='http://127.0.0.1:8000')
        exec_client.__enter__(); self.addCleanup(exec_client.__exit__, None, None, None)
        exec_csrf = self.login(exec_client, 'aniket-exec', 'aniketpathak1@gmail.com')
        self.assertEqual(exec_client.get('/executive').status_code, 200)
        data = exec_client.get('/api/executive/dashboard')
        self.assertEqual(data.status_code, 200, data.text)
        self.assertIn('api', data.json())
        changed = exec_client.patch('/api/executive/settings', headers={'X-CSRF-Token':exec_csrf}, json={'google_new_accounts_enabled':False,'signup_enabled':False,'notification_emails_enabled':False})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertFalse(changed.json()['settings']['google_new_accounts_enabled'])
        self.assertEqual(self.client.post('/auth/register/start', json={'full_name':'Blocked','email':'blocked@example.com'}).status_code, 403)
        self.login(existing, 'existing-google', 'existing@example.com')
        newcomer = self.client_type(self.app, base_url='http://127.0.0.1:8000')
        newcomer.__enter__(); self.addCleanup(newcomer.__exit__, None, None, None)
        with patch('app.auth.routes.oauth.google.authorize_access_token',new=AsyncMock(return_value={
            'id_token':'verified-by-mocked-provider','userinfo':{'sub':'brand-new','email':'brand-new@example.com','email_verified':True,'name':'Brand New'}})):
            blocked = newcomer.get('/auth/google/callback')
        self.assertEqual(blocked.status_code, 400)

    def test_automatic_callback_urls(self):
        from urllib.parse import parse_qs,urlsplit
        from app.auth.routes import oauth
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
        metadata={'authorization_endpoint':'https://accounts.google.com/o/oauth2/v2/auth'}
        with patch.object(oauth.google,'load_server_metadata',new=AsyncMock(return_value=metadata)):
            for origin in ['http://127.0.0.1:8000','http://localhost:8000','https://myremote.example.com']:
                with self.client_type(self.app,base_url=origin) as client:
                    response=client.get('/auth/google/login',follow_redirects=False)
                    query=parse_qs(urlsplit(response.headers['location']).query)
                    self.assertEqual(query['redirect_uri'],[origin+'/auth/google/callback'])
                    self.assertEqual('; secure' in response.headers['set-cookie'].lower(),origin.startswith('https'))
            # Render terminates TLS before forwarding to Uvicorn.
            proxied=ProxyHeadersMiddleware(self.app,trusted_hosts=['testclient'])
            with self.client_type(proxied,base_url='http://myremote.example.com') as client:
                response=client.get('/auth/google/login',headers={'X-Forwarded-Proto':'https'},follow_redirects=False)
                query=parse_qs(urlsplit(response.headers['location']).query)
                self.assertEqual(query['redirect_uri'],['https://myremote.example.com/auth/google/callback'])
                self.assertIn('; secure',response.headers['set-cookie'].lower())
            with self.client_type(self.app,base_url='http://myremote.example.com') as client:
                self.assertEqual(client.get('/auth/google/login').status_code,400)

    def test_generated_key_persists_without_required_environment(self):
        from app.auth.settings import get_settings
        with tempfile.TemporaryDirectory() as directory, patch('app.auth.settings.DATA_DIR',Path(directory)), patch.dict(os.environ,{'SESSION_SECRET_KEY':'','RENDER':'true','GOOGLE_REDIRECT_URI':'obsolete-value'}):
            first=get_settings()
            second=get_settings()
            self.assertTrue(first.ready)
            self.assertEqual(first.session_secret,second.session_secret)
            self.assertGreaterEqual(len(first.session_secret),32)
            self.assertEqual((Path(directory)/'.session_secret').stat().st_mode & 0o077,0)
            with patch.dict(os.environ,{'SESSION_SECRET_KEY':'explicit-shared-key-of-at-least-32-characters'}):
                self.assertEqual(get_settings().session_secret,'explicit-shared-key-of-at-least-32-characters')

    def test_public_routes_and_no_demo_bypass(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertIn('data-signup',self.client.get('/').text)
        self.assertIn('Continue with Google',self.client.get('/login').text)
        self.assertEqual(self.client.get('/dashboard',follow_redirects=False).headers['location'],'/login')
        self.assertEqual(self.client.get('/api/students').status_code,401)
        self.assertEqual(self.client.post('/login',follow_redirects=False).status_code,405)
        self.assertNotIn('Teacher Dashboard',self.client.get('/?demo=1').text)
        self.assertEqual(self.client.get('/uploads/private.pdf').status_code,401)

    def test_callback_state_rejected(self):
        # Real Authlib code: missing state cannot issue a session.
        self.assertEqual(self.client.get('/auth/google/callback?code=forged&state=invalid').status_code,400)
        self.assertFalse(self.client.get('/auth/me').json()['authenticated'])

    def test_google_login_logout_and_replay(self):
        csrf=self.login()
        cookie=self.client.cookies.get('classarit_session')
        self.assertEqual(self.client.post('/auth/logout',data={'csrf_token':'wrong'}).status_code,403)
        self.client.post('/auth/logout',data={'csrf_token':csrf})
        self.assertFalse(self.client.get('/auth/me').json()['authenticated'])
        replay=self.client_type(self.app,base_url='http://127.0.0.1:8000')
        replay.cookies.set('classarit_session',cookie)
        self.assertFalse(replay.get('/auth/me').json()['authenticated'])
        replay.close()

    def test_real_oidc_validation_and_nonce(self):
        import time
        from urllib.parse import parse_qs,urlsplit
        from joserfc import jwt
        from joserfc.jwk import RSAKey
        from app.auth.routes import oauth
        key=RSAKey.generate_key(2048)
        key.ensure_kid()
        metadata={'issuer':'https://accounts.google.com',
            'authorization_endpoint':'https://accounts.google.com/o/oauth2/v2/auth',
            'token_endpoint':'https://oauth2.googleapis.com/token',
            'jwks_uri':'https://www.googleapis.com/oauth2/v3/certs',
            'id_token_signing_alg_values_supported':['RS256']}
        with patch.object(oauth.google,'load_server_metadata',new=AsyncMock(return_value=metadata)):
            response=self.client.get('/auth/google/login',follow_redirects=False)
            query=parse_qs(urlsplit(response.headers['location']).query)
            self.assertIn('nonce',query)
            self.assertIn('code_challenge',query)
            claims={'iss':metadata['issuer'],'aud':'test-client','sub':'signed-user',
                'iat':int(time.time()),'exp':int(time.time())+300,'nonce':query['nonce'][0],
                'email':'signed@example.com','email_verified':True,'name':'Signed user'}
            encoded=jwt.encode({'alg':'RS256','kid':key.kid},claims,key)
            with patch.object(oauth.google,'fetch_access_token',new=AsyncMock(return_value={'id_token':encoded,'access_token':'test'})), patch.object(oauth.google,'fetch_jwk_set',new=AsyncMock(return_value={'keys':[key.as_dict(private=False)]})):
                callback=self.client.get('/auth/google/callback',params={'state':query['state'][0],'code':'test-code'})
                self.assertEqual(callback.status_code,200,callback.text)
                self.assertTrue(self.client.get('/auth/me').json()['authenticated'])
                # Replayed state must fail, even with a valid token.
                replay=self.client.get('/auth/google/callback',params={'state':query['state'][0],'code':'test-code'})
                self.assertEqual(replay.status_code,400)
            response=self.client.get('/auth/google/login',follow_redirects=False)
            query=parse_qs(urlsplit(response.headers['location']).query)
            wrong=jwt.encode({'alg':'RS256','kid':key.kid},{**claims,'nonce':'wrong'},key)
            with patch.object(oauth.google,'fetch_access_token',new=AsyncMock(return_value={'id_token':wrong,'access_token':'test'})), patch.object(oauth.google,'fetch_jwk_set',new=AsyncMock(return_value={'keys':[key.as_dict(private=False)]})):
                self.assertEqual(self.client.get('/auth/google/callback',params={'state':query['state'][0],'code':'test-code'}).status_code,400)

    def test_duplicate_identity_and_email_collision(self):
        from app.auth.repository import google_account,LinkingRequired,AccountUnavailable
        claims={'sub':'one','email':'same@example.com','email_verified':True}
        first=google_account(claims)
        self.assertEqual(first['id'],google_account(claims)['id'])
        with self.assertRaises(LinkingRequired):
            google_account({**claims,'sub':'two'})
        with self.assertRaises(AccountUnavailable):
            google_account({**claims,'email_verified':False})
        with self.assertRaises(AccountUnavailable):
            google_account({**claims,'sub':None})

    def test_blocked_and_expired_sessions(self):
        from app.auth.database import auth_engine
        from sqlalchemy import text
        self.login()
        with auth_engine().begin() as conn:
            conn.execute(text("UPDATE classarit.app_users SET status='BLOCKED'"))
        self.assertFalse(self.client.get('/auth/me').json()['authenticated'])
        with auth_engine().begin() as conn:
            conn.execute(text("UPDATE classarit.app_users SET status='ACTIVE'"))
            conn.execute(text("UPDATE classarit.auth_sessions SET expires_at=now()-interval '1 second'"))
        self.assertFalse(self.client.get('/auth/me').json()['authenticated'])

    def test_account_isolation_and_csrf(self):
        csrf=self.login()
        payload={'name':'Student A','subject':'Piano','start_date':'2026-09-09','teacher_id':999}
        self.assertEqual(self.client.post('/api/students',json=payload).status_code,403)
        headers={'X-CSRF-Token':csrf}
        created=self.client.post('/api/students',json=payload,headers=headers)
        self.assertEqual(created.status_code,200,created.text)
        student_id=created.json()['id']
        session=self.client.post('/api/classes',json={'student_id':student_id,'subject':'Piano','date':'2026-09-09','start_time':'10:00'},headers=headers)
        self.assertEqual(session.status_code,200,session.text)
        class_id=session.json()['id']
        upload=self.client.post('/api/materials',data={'title':'Private','subject':'Piano'},files={'file':('notes.txt',b'private notes','text/plain')},headers=headers)
        self.assertEqual(upload.status_code,200,upload.text)
        from app.database import SessionLocal
        from app.models import Material
        with SessionLocal() as db: path=db.get(Material,upload.json()['id']).file_path
        self.assertEqual(self.client.get(path).status_code,200)
        with self.client_type(self.app,base_url='http://127.0.0.1:8000') as other:
            other_csrf=self.login(other,'bob','bob@example.com'); other_headers={'X-CSRF-Token':other_csrf}
            self.assertEqual(other.get('/api/students').json(),[])
            self.assertEqual(other.get('/api/classes').json(),[])
            self.assertEqual(other.put(f'/api/students/{student_id}',json=payload,headers=other_headers).status_code,404)
            self.assertEqual(other.post('/api/payments',json={'student_id':student_id,'billing_month':'September','amount_due':5,'amount_paid':0},headers=other_headers).status_code,404)
            self.assertEqual(other.post(f'/api/classes/{class_id}/attendance',data={'status':'Present'},headers=other_headers).status_code,404)
            self.assertEqual(other.get(path).status_code,404)


if __name__=='__main__':
    unittest.main()
