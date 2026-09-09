import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .database import auth_engine, schema_name


class AccountUnavailable(Exception):
    pass


class LinkingRequired(Exception):
    pass


def google_account(claims):
    """Resolve a validated Google subject; never attach by email alone."""
    subject = claims.get("sub")
    email = (claims.get("email") or "").strip().lower()
    if not isinstance(subject, str) or not subject or not email or claims.get("email_verified") is not True:
        raise AccountUnavailable("Google did not provide a verified identity")
    s = schema_name()
    # Unique constraints plus a retry resolve simultaneous first logins safely.
    for attempt in range(2):
        try:
            with auth_engine().begin() as conn:
                row = conn.execute(text(f'''SELECT u.id, u.full_name, u.status FROM {s}.app_users u
                    JOIN {s}.auth_identities i ON i.app_user_id=u.id
                    WHERE i.provider='GOOGLE' AND i.provider_subject=:sub FOR UPDATE OF u'''),
                    {"sub": subject}).mappings().first()
                if row:
                    if row['status'] != 'ACTIVE':
                        raise AccountUnavailable("Account is not active")
                    user_id = row['id']
                    conn.execute(text(f'''UPDATE {s}.auth_identities SET provider_email=:email,
                        provider_email_verified=true WHERE provider='GOOGLE' AND provider_subject=:sub'''),
                        {"email": email, "sub": subject})
                    conn.execute(text(f'''UPDATE {s}.app_users SET full_name=:name, avatar_url=:picture
                        WHERE id=:id'''), {"id": user_id, "name": claims.get('name') or email,
                                          "picture": claims.get('picture')})
                else:
                    existing = conn.execute(text(f'SELECT app_user_id FROM {s}.user_emails WHERE lower(email::text)=:email'),
                                            {"email": email}).first()
                    if existing:
                        raise LinkingRequired("This email belongs to an existing account")
                    user_id = uuid4()
                    conn.execute(text(f'''INSERT INTO {s}.app_users(id,full_name,avatar_url,status)
                        VALUES (:id,:name,:picture,'ACTIVE')'''),
                        {"id": user_id, "name": claims.get('name') or email, "picture": claims.get('picture')})
                    # Verification here is Google's reported claim; not used for automatic linking.
                    conn.execute(text(f'''INSERT INTO {s}.user_emails(app_user_id,email,is_primary,verified_at)
                        VALUES (:id,:email,true,CURRENT_TIMESTAMP)'''), {"id": user_id, "email": email})
                    conn.execute(text(f'''INSERT INTO {s}.auth_identities
                        (app_user_id,provider,provider_subject,provider_email,provider_email_verified)
                        VALUES (:id,'GOOGLE',:sub,:email,true)'''), {"id": user_id,"sub": subject,"email": email})
                return {"id": str(user_id), "full_name": claims.get('name') or email, "email": email}
        except IntegrityError:
            if attempt:
                raise LinkingRequired("Account identity conflict") from None


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    with auth_engine().begin() as conn:
        s = schema_name()
        conn.execute(text(f'DELETE FROM {s}.auth_sessions WHERE expires_at < CURRENT_TIMESTAMP'))
        conn.execute(text(f'''INSERT INTO {s}.auth_sessions(token_hash,app_user_id,expires_at)
            VALUES (:hash,:id,:expires)'''),
            {"hash": digest(token), "id": UUID(user_id), "expires": datetime.now(timezone.utc)+timedelta(hours=12)})
        conn.execute(text(f'UPDATE {s}.app_users SET last_login_at=CURRENT_TIMESTAMP WHERE id=:id'),
                     {"id": UUID(user_id)})
    return token


def session_user(token):
    if not token or len(token) > 200:
        return None
    s = schema_name()
    with auth_engine().connect() as conn:
        row = conn.execute(text(f'''SELECT u.id,u.full_name,u.avatar_url,e.email
            FROM {s}.auth_sessions a JOIN {s}.app_users u ON u.id=a.app_user_id
            LEFT JOIN {s}.user_emails e ON e.app_user_id=u.id AND e.is_primary=true
            WHERE a.token_hash=:hash AND a.expires_at>CURRENT_TIMESTAMP AND u.status='ACTIVE' '''),
            {"hash": digest(token)}).mappings().first()
        return dict(row, id=str(row['id'])) if row else None


def revoke_session(token):
    if token:
        with auth_engine().begin() as conn:
            conn.execute(text(f'DELETE FROM {schema_name()}.auth_sessions WHERE token_hash=:hash'), {"hash": digest(token)})
