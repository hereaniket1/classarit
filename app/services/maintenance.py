"""Executive reset, preserving only the designated owner's authentication."""
import re

from fastapi import HTTPException
from sqlalchemy import text

from ..auth.database import auth_engine, schema_name
from ..database import engine as legacy_engine, Base
from ..config import UPLOAD_DIR
from .product_settings import DEFAULTS

PROTECTED_EMAIL = 'aniketpathak1@gmail.com'
PRESERVED_TABLES = {'schema_migrations'}
AUTH_TABLES = ('app_users', 'user_emails', 'auth_identities', 'password_credentials',
               'auth_sessions', 'auth_challenges')


def flush_application_data():
    """Reset application data; snapshot/restore only the protected account in one transaction.

    Do not use TRUNCATE CASCADE: foreign keys outside the application schema must
    fail closed rather than erase unrelated data. Migration history is structural.
    """
    schema = schema_name()
    with auth_engine().begin() as conn:
        quote = conn.dialect.identifier_preparer.quote_identifier
        qualified = lambda name: f'{quote(schema)}.{quote(name)}'
        conn.execute(text("SET LOCAL lock_timeout='5s'"))
        tables = [row['tablename'] for row in conn.execute(text(
            'SELECT tablename FROM pg_tables WHERE schemaname=:schema ORDER BY tablename'),
            {'schema':schema}).mappings() if row['tablename'] not in PRESERVED_TABLES]
        if not set(AUTH_TABLES).issubset(tables):
            raise HTTPException(409, 'Authentication tables are incomplete. No data was deleted.')
        table_list = ', '.join(qualified(name) for name in tables)
        conn.execute(text(f'LOCK TABLE {table_list} IN ACCESS EXCLUSIVE MODE'))
        owner = conn.execute(text(f'''SELECT u.id FROM {qualified('app_users')} u
            JOIN {qualified('user_emails')} e ON e.app_user_id=u.id
            WHERE lower(e.email::text)=:email AND e.verified_at IS NOT NULL AND u.status='ACTIVE' '''),
            {'email':PROTECTED_EMAIL}).scalar_one_or_none()
        if owner is None:
            raise HTTPException(409, 'The protected executive account could not be verified. No data was deleted.')
        for table in AUTH_TABLES:
            key = 'id' if table == 'app_users' else 'app_user_id'
            conn.execute(text(f'CREATE TEMP TABLE {quote("reset_keep_"+table)} ON COMMIT DROP AS SELECT * FROM {qualified(table)} WHERE {key}=:owner'), {'owner':owner})
        # Workspaces are deleted, including the executive's default workspace.
        conn.execute(text('UPDATE pg_temp.reset_keep_app_users SET default_workspace_id=NULL'))
        conn.execute(text(f'TRUNCATE TABLE {table_list} RESTART IDENTITY'))
        for table in AUTH_TABLES:
            conn.execute(text(f'INSERT INTO {qualified(table)} SELECT * FROM pg_temp.{quote("reset_keep_"+table)}'))
        for key, value in DEFAULTS.items():
            conn.execute(text(f'INSERT INTO {qualified("app_settings")}(key,value) VALUES (:key,:value)'),
                         {'key':key,'value':'true' if value else 'false'})
        # The legacy teaching UI uses a separate local SQLite database.
        with legacy_engine.begin() as legacy:
            Base.metadata.create_all(legacy)
            for table in reversed(Base.metadata.sorted_tables):
                legacy.execute(table.delete())
    # Only app-generated material filenames, never arbitrary paths or directories.
    failed_uploads = 0
    try:
        uploads = list(UPLOAD_DIR.iterdir())
    except OSError:
        uploads = []
        failed_uploads = 1
    for path in uploads:
        if re.fullmatch(r'[0-9a-f]{32}\.(pdf|png|jpg|jpeg|mp3|wav|docx|txt)', path.name) and not path.is_symlink() and path.is_file():
            try:
                path.unlink()
            except OSError:
                failed_uploads += 1
    return {'truncated_tables':tables, 'preserved_auth_email':PROTECTED_EMAIL,
            'failed_upload_deletions':failed_uploads}
