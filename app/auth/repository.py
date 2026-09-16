import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .database import auth_engine, schema_name
from .settings import session_signing_key
from ..services.product_settings import setting_enabled


class AccountUnavailable(Exception):
    pass


class LinkingRequired(Exception):
    pass


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(email):
    email = (email or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise AccountUnavailable("Enter a valid email address")
    return email


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_secret():
    configured = os.getenv("OTP_HMAC_SECRET", "").strip()
    return configured if len(configured) >= 32 else session_signing_key()


def challenge_digest(challenge_id, purpose, target_email, code):
    message = f"{challenge_id}:{purpose}:{target_email}:{code}".encode()
    return hmac.new(otp_secret().encode(), message, hashlib.sha256).hexdigest()


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
                    if not setting_enabled("google_new_accounts_enabled", True):
                        raise AccountUnavailable("New Google accounts are disabled")
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
        row = conn.execute(text(f'''SELECT u.id,u.full_name,u.avatar_url,u.user_type,u.default_workspace_id,e.email
            FROM {s}.auth_sessions a JOIN {s}.app_users u ON u.id=a.app_user_id
            LEFT JOIN {s}.user_emails e ON e.app_user_id=u.id AND e.is_primary=true
            WHERE a.token_hash=:hash AND a.expires_at>CURRENT_TIMESTAMP AND u.status='ACTIVE' '''),
            {"hash": digest(token)}).mappings().first()
        return dict(row, id=str(row['id']), default_workspace_id=str(row['default_workspace_id']) if row['default_workspace_id'] else None) if row else None


def revoke_session(token):
    if token:
        with auth_engine().begin() as conn:
            conn.execute(text(f'DELETE FROM {schema_name()}.auth_sessions WHERE token_hash=:hash'), {"hash": digest(token)})


def start_registration(email, full_name):
    if not setting_enabled("signup_enabled", True):
        raise AccountUnavailable("Signup is disabled right now")
    email = normalize_email(email)
    name = (full_name or email).strip()[:150] or email
    s = schema_name()
    challenge_id = uuid4()
    code = generate_otp()
    with auth_engine().begin() as conn:
        existing = conn.execute(
            text(f"""SELECT u.id,u.status,e.verified_at FROM {s}.user_emails e
            JOIN {s}.app_users u ON u.id=e.app_user_id
            WHERE lower(e.email::text)=:email FOR UPDATE OF u"""),
            {"email": email},
        ).mappings().first()
        if existing and existing["verified_at"] and existing["status"] == "ACTIVE":
            raise LinkingRequired("This email is already registered")
        if existing:
            user_id = existing["id"]
            conn.execute(
                text(f"UPDATE {s}.app_users SET full_name=:name,status='PENDING' WHERE id=:id AND status<>'ACTIVE'"),
                {"name": name, "id": user_id},
            )
        else:
            user_id = uuid4()
            conn.execute(
                text(f"INSERT INTO {s}.app_users(id,full_name,status) VALUES (:id,:name,'PENDING')"),
                {"id": user_id, "name": name},
            )
            conn.execute(
                text(f"INSERT INTO {s}.user_emails(app_user_id,email,is_primary) VALUES (:id,:email,true)"),
                {"id": user_id, "email": email},
            )
        conn.execute(
            text(f"""UPDATE {s}.auth_challenges SET consumed_at=CURRENT_TIMESTAMP
            WHERE app_user_id=:u AND target_email=:email AND purpose='REGISTRATION_EMAIL_OTP' AND consumed_at IS NULL"""),
            {"u": user_id, "email": email},
        )
        digest_value = challenge_digest(challenge_id, "REGISTRATION_EMAIL_OTP", email, code)
        conn.execute(
            text(f"""INSERT INTO {s}.auth_challenges
            (id,app_user_id,target_email,purpose,secret_digest,expires_at,max_attempts)
            VALUES (:id,:u,:email,'REGISTRATION_EMAIL_OTP',:digest,CURRENT_TIMESTAMP + interval '10 minutes',5)"""),
            {"id": challenge_id, "u": user_id, "email": email, "digest": digest_value},
        )
    return {"challenge_id": str(challenge_id), "email": email, "full_name": name, "code": code}


def verify_registration(challenge_id, code):
    try:
        challenge_uuid = UUID(str(challenge_id))
    except ValueError:
        raise AccountUnavailable("Invalid verification request")
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise AccountUnavailable("Enter the 6-digit verification code")
    s = schema_name()
    with auth_engine().begin() as conn:
        row = conn.execute(
            text(f"""SELECT c.*,u.status,u.full_name FROM {s}.auth_challenges c
            JOIN {s}.app_users u ON u.id=c.app_user_id
            WHERE c.id=:id AND c.purpose='REGISTRATION_EMAIL_OTP' FOR UPDATE OF c,u"""),
            {"id": challenge_uuid},
        ).mappings().first()
        if not row or row["consumed_at"] is not None or row["expires_at"] <= datetime.now(timezone.utc):
            raise AccountUnavailable("This verification code has expired. Please request a new one.")
        if row["attempt_count"] >= row["max_attempts"]:
            raise AccountUnavailable("Too many attempts. Please request a new code.")
        expected = challenge_digest(row["id"], row["purpose"], str(row["target_email"]).lower(), code)
        if not hmac.compare_digest(expected, row["secret_digest"]):
            conn.execute(
                text(f"UPDATE {s}.auth_challenges SET attempt_count=attempt_count+1 WHERE id=:id"),
                {"id": challenge_uuid},
            )
            raise AccountUnavailable("That code did not match. Please try again.")
        conn.execute(
            text(f"UPDATE {s}.auth_challenges SET consumed_at=CURRENT_TIMESTAMP WHERE id=:id"),
            {"id": challenge_uuid},
        )
        conn.execute(
            text(f"UPDATE {s}.app_users SET status='ACTIVE' WHERE id=:id"),
            {"id": row["app_user_id"]},
        )
        conn.execute(
            text(f"""UPDATE {s}.user_emails SET verified_at=COALESCE(verified_at,CURRENT_TIMESTAMP),is_primary=true
            WHERE app_user_id=:u AND lower(email::text)=:email"""),
            {"u": row["app_user_id"], "email": str(row["target_email"]).lower()},
        )
        return {"id": str(row["app_user_id"]), "email": str(row["target_email"]).lower(), "full_name": row["full_name"]}
