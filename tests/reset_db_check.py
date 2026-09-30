"""Manual reset integration check in a NEW synthetic schema, always rolled back.

Never calls reset against the configured application schema. No real emails/data
are read or copied. SQLite and uploaded files also use disposable storage.
"""
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from fastapi import HTTPException
from app.auth.database import auth_engine
from app.services import maintenance
from app import models
from app.database import Base


def check():
    schema = 'reset_test_' + uuid4().hex
    assert schema.startswith('reset_test_') and len(schema) == 43
    with tempfile.TemporaryDirectory() as directory, auth_engine().connect() as conn:
        transaction = conn.begin()
        local = create_engine('sqlite://')
        Base.metadata.create_all(local)
        uploads = Path(directory)
        upload = uploads / (uuid4().hex + '.pdf')
        upload.write_bytes(b'synthetic material')
        untouched = uploads / 'unrelated.txt'
        untouched.write_text('not an app-generated upload')
        class TestEngine:
            @contextmanager
            def begin(self):
                with conn.begin_nested():
                    yield conn
        try:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(text(f'''CREATE TABLE {schema}.app_users (id uuid PRIMARY KEY, status text, default_workspace_id uuid);
                CREATE TABLE {schema}.workspaces (id uuid PRIMARY KEY, owner_user_id uuid REFERENCES {schema}.app_users(id));
                ALTER TABLE {schema}.app_users ADD FOREIGN KEY(default_workspace_id) REFERENCES {schema}.workspaces(id);
                CREATE TABLE {schema}.user_emails (id uuid PRIMARY KEY, app_user_id uuid REFERENCES {schema}.app_users(id), email text, verified_at timestamptz);
                CREATE TABLE {schema}.app_settings (key text PRIMARY KEY, value text);
                CREATE TABLE {schema}.schema_migrations (filename text PRIMARY KEY);
                CREATE TABLE {schema}.user_terms_acceptances (app_user_id uuid REFERENCES {schema}.app_users(id), audit text);
                CREATE TABLE {schema}.api_request_metrics (user_id uuid REFERENCES {schema}.app_users(id), audit text);
                INSERT INTO {schema}.schema_migrations VALUES ('synthetic');'''))
            for table in maintenance.AUTH_TABLES[2:]:
                conn.execute(text(f'CREATE TABLE {schema}.{table} (app_user_id uuid REFERENCES {schema}.app_users(id), credential text)'))
            owner, other, workspace = uuid4(), uuid4(), uuid4()
            for user, email in [(owner, maintenance.PROTECTED_EMAIL), (other, 'other@example.com')]:
                conn.execute(text(f"INSERT INTO {schema}.app_users VALUES (:id,'ACTIVE',NULL)"), {'id':user})
                conn.execute(text(f'INSERT INTO {schema}.user_emails VALUES (:id,:user,:email,now())'), {'id':uuid4(),'user':user,'email':email})
                for table in maintenance.AUTH_TABLES[2:]:
                    conn.execute(text(f'INSERT INTO {schema}.{table} VALUES (:user,:credential)'), {'user':user,'credential':str(user)})
                for table, key in [('user_terms_acceptances','app_user_id'), ('api_request_metrics','user_id')]:
                    conn.execute(text(f"INSERT INTO {schema}.{table} VALUES (:user,'synthetic audit')"), {'user':user})
            conn.execute(text(f'INSERT INTO {schema}.workspaces VALUES (:id,:owner)'), {'id':workspace,'owner':owner})
            conn.execute(text(f'UPDATE {schema}.app_users SET default_workspace_id=:workspace WHERE id=:owner'), {'workspace':workspace,'owner':owner})
            with local.begin() as legacy:
                legacy.execute(models.Teacher.__table__.insert().values(name='Synthetic teacher', email='test@example.com'))
            with patch.object(maintenance,'schema_name',return_value=schema), patch.object(maintenance,'auth_engine',return_value=TestEngine()), patch.object(maintenance,'legacy_engine',local), patch.object(maintenance,'UPLOAD_DIR',uploads):
                # Missing protected identity must abort BEFORE deleting any data.
                with patch.object(maintenance,'PROTECTED_EMAIL','missing@example.com'):
                    try:
                        maintenance.flush_application_data()
                        raise AssertionError('Reset did not abort')
                    except HTTPException as error:
                        assert error.status_code == 409
                assert conn.execute(text(f'SELECT count(*) FROM {schema}.app_users')).scalar_one() == 2
                response = maintenance.flush_application_data()
                assert response['failed_upload_deletions'] == 0
            assert conn.execute(text(f'SELECT id FROM {schema}.app_users')).scalar_one() == owner
            assert conn.execute(text(f'SELECT default_workspace_id FROM {schema}.app_users')).scalar_one() is None
            for table in maintenance.AUTH_TABLES[2:]:
                assert conn.execute(text(f'SELECT credential FROM {schema}.{table}')).scalar_one() == str(owner)
            for table in ['workspaces', 'user_terms_acceptances', 'api_request_metrics']:
                assert conn.execute(text(f'SELECT count(*) FROM {schema}.{table}')).scalar_one() == 0
            assert conn.execute(text(f'SELECT count(*) FROM {schema}.app_settings')).scalar_one() == len(maintenance.DEFAULTS)
            assert conn.execute(text(f'SELECT filename FROM {schema}.schema_migrations')).scalar_one() == 'synthetic'
            with local.connect() as legacy:
                for table in Base.metadata.sorted_tables:
                    assert legacy.execute(text(f'SELECT count(*) FROM "{table.name}"')).scalar_one() == 0
            assert not upload.exists() and untouched.exists()
            print('Passed: reset removes other auth, application data, all audits, legacy rows and uploads; preserves only owner auth and migration history; missing owner fails closed.')
        finally:
            transaction.rollback()
            local.dispose()


if __name__ == '__main__':
    try:
        check()
    except Exception as error:
        print(f'Isolated reset check failed: {type(error).__name__}', file=sys.stderr)
        diagnostic = getattr(getattr(error, 'orig', None), 'diag', None)
        if diagnostic:
            print(diagnostic.message_primary, file=sys.stderr)
        sys.exit(1)
