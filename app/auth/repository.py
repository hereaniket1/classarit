import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .database import auth_engine, schema_name
from .settings import session_signing_key
from ..services.product_settings import setting_enabled
from ..services.admissions import admission_type


class AccountUnavailable(Exception):
    pass


class LinkingRequired(Exception):
    pass


class InvalidVerificationCode(AccountUnavailable):
    """Internal signal used so a failed-attempt increment can commit."""


ACCOUNT_EXISTS_MESSAGE = 'An account already exists for this email. Please log in.'
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)
# Always verify a real hash when an address is unknown to reduce account enumeration
# through timing differences.
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("classarit-dummy-password-never-used")
TERMS_VERSION = "demo-2026-09-20"
ACCOUNT_TYPES = {'INDIVIDUAL', 'ORGANIZATION'}


def resolve_account_type(selected, admitted=None):
    if selected not in ACCOUNT_TYPES:
        raise AccountUnavailable('Choose an Individual or Organization account.')
    if admitted and selected != admitted:
        raise AccountUnavailable('Choose the account type approved for this invitation request.')
    return admitted or selected


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


def _metadata_hash(value):
    value = (value or "").strip()
    if not value:
        return None
    return hmac.new(session_signing_key().encode(), value.encode(), hashlib.sha256).hexdigest()


def record_terms_acceptance(user_id, email=None, full_name=None, source="PASSWORD_SIGNUP", ip=None, user_agent=None, version=None):
    s = schema_name()
    with auth_engine().begin() as conn:
        conn.execute(
            text(
                f"""INSERT INTO {s}.user_terms_acceptances
                (app_user_id,email,full_name,terms_version,acceptance_source,ip_hash,user_agent_hash)
                VALUES (:u,:email,:name,:version,:source,:ip_hash,:user_agent_hash)
                """
            ),
            {
                "u": UUID(str(user_id)),
                "email": normalize_email(email) if email else None,
                "name": (full_name or None),
                "version": version or TERMS_VERSION,
                "source": source,
                "ip_hash": _metadata_hash(ip),
                "user_agent_hash": _metadata_hash(user_agent),
            },
        )


def _link_verified_contacts(conn, user_id, email):
    """Mark matching workspace contacts as belonging to this verified email owner.

    Linking supplies verification context only. Workspace access still requires an
    invitation or membership and is never granted from an email match.
    """
    s = schema_name()
    conn.execute(
        text(
            f"""WITH candidates AS (
                SELECT DISTINCT ON (workspace_id) id
                FROM {s}.students st
                WHERE st.linked_user_id IS NULL
                  AND lower(btrim(st.email))=:email
                  AND NOT EXISTS (
                    SELECT 1 FROM {s}.students linked
                    WHERE linked.workspace_id=st.workspace_id
                      AND linked.linked_user_id=:user_id
                  )
                ORDER BY workspace_id,created_at,id
            )
            UPDATE {s}.students st SET linked_user_id=:user_id
            FROM candidates c WHERE st.id=c.id"""
        ),
        {"user_id": user_id, "email": email},
    )
    conn.execute(
        text(
            f"""UPDATE {s}.guardians SET linked_user_id=:user_id
            WHERE linked_user_id IS NULL AND lower(btrim(email))=:email"""
        ),
        {"user_id": user_id, "email": email},
    )


def google_account(claims, invitation_token=None):
    """Resolve Google identity; link only to an already verified email account."""
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
                is_new_user = False
                if row:
                    if row['status'] != 'ACTIVE':
                        raise AccountUnavailable("Account is not active")
                    user_id = row['id']
                    conn.execute(text(f'''UPDATE {s}.auth_identities SET provider_email=:email,
                        provider_email_verified=true WHERE provider='GOOGLE' AND provider_subject=:sub'''),
                        {"email": email, "sub": subject})
                    conn.execute(text(f'''UPDATE {s}.app_users SET full_name=COALESCE(NULLIF(full_name,''),:name), avatar_url=:picture
                        WHERE id=:id'''), {"id": user_id, "name": claims.get('name') or email,
                                          "picture": claims.get('picture')})
                else:
                    existing = conn.execute(
                        text(f'''SELECT e.app_user_id,e.verified_at,u.status
                        FROM {s}.user_emails e JOIN {s}.app_users u ON u.id=e.app_user_id
                        WHERE lower(e.email::text)=:email FOR UPDATE OF u'''),
                        {"email": email},
                    ).mappings().first()
                    if existing:
                        if not existing["verified_at"] or existing["status"] != "ACTIVE":
                            raise LinkingRequired("Verify the existing account before linking Google")
                        user_id = existing["app_user_id"]
                        conn.execute(
                            text(f'''UPDATE {s}.app_users
                            SET full_name=COALESCE(NULLIF(full_name,''),:name),avatar_url=COALESCE(avatar_url,:picture)
                            WHERE id=:id'''),
                            {"id": user_id,"name": claims.get("name") or email,"picture": claims.get("picture")},
                        )
                    else:
                        invitation_mode = setting_enabled('invite_request_enabled', False)
                        account_type = admission_type(conn, email, invitation_token)
                        if not invitation_mode and not setting_enabled("google_new_accounts_enabled", True):
                            raise AccountUnavailable("New Google accounts are disabled")
                        user_id = uuid4()
                        is_new_user = True
                        conn.execute(text(f'''INSERT INTO {s}.app_users(id,full_name,avatar_url,status)
                            VALUES (:id,:name,:picture,'ACTIVE')'''),
                            {"id": user_id, "name": claims.get('name') or email, "picture": claims.get('picture')})
                        conn.execute(text(f'''INSERT INTO {s}.user_emails(app_user_id,email,is_primary,verified_at)
                            VALUES (:id,:email,true,CURRENT_TIMESTAMP)'''), {"id": user_id, "email": email})
                        conn.execute(text(f'UPDATE {s}.app_users SET account_type=:kind WHERE id=:id'),
                                     {'kind': account_type, 'id': user_id})
                    if existing:
                        conn.execute(
                            text(f'''UPDATE {s}.user_emails
                            SET verified_at=COALESCE(verified_at,CURRENT_TIMESTAMP)
                            WHERE app_user_id=:id AND lower(email::text)=:email'''),
                            {"id": user_id,"email": email},
                        )
                    conn.execute(text(f'''INSERT INTO {s}.auth_identities
                        (app_user_id,provider,provider_subject,provider_email,provider_email_verified)
                        VALUES (:id,'GOOGLE',:sub,:email,true)
                        ON CONFLICT (provider,provider_subject) DO NOTHING'''), {"id": user_id,"sub": subject,"email": email})
                _link_verified_contacts(conn, user_id, email)
                return {"id": str(user_id), "full_name": claims.get('name') or email, "email": email, "is_new_user": is_new_user}
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
        row = conn.execute(text(f'''SELECT u.id,u.full_name,u.phone,u.date_of_birth,u.country,
                u.avatar_url,u.user_type,u.account_type,u.default_workspace_id,e.email,
                (e.verified_at IS NOT NULL) AS email_verified
            FROM {s}.auth_sessions a JOIN {s}.app_users u ON u.id=a.app_user_id
            LEFT JOIN {s}.user_emails e ON e.app_user_id=u.id AND e.is_primary=true
            WHERE a.token_hash=:hash AND a.expires_at>CURRENT_TIMESTAMP AND u.status='ACTIVE' '''),
            {"hash": digest(token)}).mappings().first()
        return dict(row, id=str(row['id']), default_workspace_id=str(row['default_workspace_id']) if row['default_workspace_id'] else None) if row else None


def revoke_session(token):
    if token:
        with auth_engine().begin() as conn:
            conn.execute(text(f'DELETE FROM {schema_name()}.auth_sessions WHERE token_hash=:hash'), {"hash": digest(token)})


def validate_password(password):
    if not isinstance(password, str) or len(password) < 10:
        raise AccountUnavailable("Use at least 10 characters for your password")
    if len(password) > 128:
        raise AccountUnavailable("Password must be 128 characters or fewer")
    return password


def password_account(email, password):
    """Authenticate by primary email while keeping unknown-account timing similar."""
    email = normalize_email(email)
    password = password if isinstance(password, str) else ""
    s = schema_name()
    with auth_engine().begin() as conn:
        row = conn.execute(
            text(
                f"""SELECT u.id,u.status,p.password_hash
                FROM {s}.user_emails e
                JOIN {s}.app_users u ON u.id=e.app_user_id
                JOIN {s}.password_credentials p ON p.app_user_id=u.id
                WHERE lower(e.email::text)=:email AND e.is_primary=true
                FOR UPDATE OF u,p"""
            ),
            {"email": email},
        ).mappings().first()
        encoded = row["password_hash"] if row else DUMMY_PASSWORD_HASH
        try:
            valid = PASSWORD_HASHER.verify(encoded, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
        if not row or not valid:
            raise AccountUnavailable("Email or password is incorrect")
        if row["status"] == "PENDING":
            raise AccountUnavailable("Verify your email before logging in")
        if row["status"] != "ACTIVE":
            raise AccountUnavailable("This account cannot sign in")
        if PASSWORD_HASHER.check_needs_rehash(encoded):
            conn.execute(
                text(
                    f"UPDATE {s}.password_credentials SET password_hash=:hash,password_changed_at=CURRENT_TIMESTAMP WHERE app_user_id=:id"
                ),
                {"hash": PASSWORD_HASHER.hash(password), "id": row["id"]},
            )
        return {"id": str(row["id"]), "email": email}


def _new_challenge(conn, user_id, email, purpose):
    s = schema_name()
    challenge_id = uuid4()
    code = generate_otp()
    conn.execute(
        text(
            f"""UPDATE {s}.auth_challenges SET consumed_at=CURRENT_TIMESTAMP
            WHERE app_user_id=:u AND target_email=:email AND purpose=:purpose
              AND consumed_at IS NULL"""
        ),
        {"u": user_id, "email": email, "purpose": purpose},
    )
    conn.execute(
        text(
            f"""INSERT INTO {s}.auth_challenges
            (id,app_user_id,target_email,purpose,secret_digest,expires_at,max_attempts)
            VALUES (:id,:u,:email,:purpose,:digest,CURRENT_TIMESTAMP + interval '10 minutes',5)"""
        ),
        {
            "id": challenge_id,
            "u": user_id,
            "email": email,
            "purpose": purpose,
            "digest": challenge_digest(challenge_id, purpose, email, code),
        },
    )
    return {"challenge_id": str(challenge_id), "code": code}


def start_password_registration(email, full_name, phone, password, account_type, invitation_token=None):
    if not setting_enabled("signup_enabled", True):
        raise AccountUnavailable("Signup is disabled right now")
    email = normalize_email(email)
    name = (full_name or "").strip()
    phone = (phone or "").strip()
    if not name:
        raise AccountUnavailable("Enter your full name")
    if not 5 <= len(phone) <= 30:
        raise AccountUnavailable("Enter a valid phone number")
    password = validate_password(password)
    password_hash = PASSWORD_HASHER.hash(password)
    verification_required = setting_enabled("email_verification_enabled", True)
    s = schema_name()
    try:
        with auth_engine().begin() as conn:
            approved_type = admission_type(conn, email, invitation_token)
            account_type = resolve_account_type(account_type, approved_type)
            existing = conn.execute(
                text(
                    f"""SELECT u.id,u.status,e.verified_at
                    FROM {s}.user_emails e JOIN {s}.app_users u ON u.id=e.app_user_id
                    WHERE lower(e.email::text)=:email FOR UPDATE OF u"""
                ),
                {"email": email},
            ).mappings().first()
            if existing and (existing["verified_at"] or existing["status"] != "PENDING"):
                raise LinkingRequired("This email is already registered")
            user_id = existing["id"] if existing else uuid4()
            status = "PENDING" if verification_required else "ACTIVE"
            if existing:
                # A retry can recover a pending signup after a lost email. It still
                # cannot activate while verification is required without the new OTP.
                conn.execute(
                    text(
                        f"""UPDATE {s}.app_users
                        SET full_name=:name,phone=:phone,status=:status WHERE id=:id"""
                    ),
                    {"id": user_id, "name": name[:150], "phone": phone, "status": status},
                )
            else:
                conn.execute(
                    text(
                        f"""INSERT INTO {s}.app_users(id,full_name,phone,status)
                        VALUES (:id,:name,:phone,:status)"""
                    ),
                    {"id": user_id, "name": name[:150], "phone": phone, "status": status},
                )
                conn.execute(
                    text(
                        f"INSERT INTO {s}.user_emails(app_user_id,email,is_primary) VALUES (:id,:email,true)"
                    ),
                    {"id": user_id, "email": email},
                )
            conn.execute(
                text(
                    f"""INSERT INTO {s}.password_credentials(app_user_id,password_hash)
                    VALUES (:id,:hash) ON CONFLICT (app_user_id) DO UPDATE
                    SET password_hash=EXCLUDED.password_hash,password_changed_at=CURRENT_TIMESTAMP"""
                ),
                {"id": user_id, "hash": password_hash},
            )
            conn.execute(text(f'UPDATE {s}.app_users SET account_type=COALESCE(account_type,:kind) WHERE id=:id'),
                         {'kind': account_type, 'id': user_id})
            challenge = (
                _new_challenge(conn, user_id, email, "REGISTRATION_EMAIL_OTP")
                if verification_required
                else None
            )
            return {
                "id": str(user_id),
                "email": email,
                "full_name": name[:150],
                "verification_required": verification_required,
                **(challenge or {}),
            }
    except IntegrityError:
        raise LinkingRequired("This email is already registered") from None


def start_email_verification(user_id):
    if not setting_enabled("email_verification_enabled", True):
        raise AccountUnavailable("Email verification is currently disabled")
    s = schema_name()
    with auth_engine().begin() as conn:
        row = conn.execute(
            text(
                f"""SELECT u.id,u.full_name,e.email,e.verified_at
                FROM {s}.app_users u JOIN {s}.user_emails e ON e.app_user_id=u.id
                WHERE u.id=:id AND e.is_primary=true FOR UPDATE OF u,e"""
            ),
            {"id": UUID(str(user_id))},
        ).mappings().first()
        if not row:
            raise AccountUnavailable("Primary email is unavailable")
        if row["verified_at"]:
            raise AccountUnavailable("Your email is already verified")
        challenge = _new_challenge(conn, row["id"], str(row["email"]).lower(), "EMAIL_VERIFY")
        return {
            **challenge,
            "email": str(row["email"]).lower(),
            "full_name": row["full_name"],
        }


def _verified_challenge(conn, challenge_id, code, purpose, user_id=None):
    try:
        challenge_uuid = UUID(str(challenge_id))
    except ValueError:
        raise AccountUnavailable("Invalid verification request")
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise AccountUnavailable("Enter the 6-digit verification code")
    s = schema_name()
    row = conn.execute(
        text(
            f"""SELECT c.*,u.status,u.full_name,u.account_type FROM {s}.auth_challenges c
            JOIN {s}.app_users u ON u.id=c.app_user_id
            WHERE c.id=:id AND c.purpose=:purpose
              AND (CAST(:user_id AS uuid) IS NULL OR c.app_user_id=CAST(:user_id AS uuid))
            FOR UPDATE OF c,u"""
        ),
        {
            "id": challenge_uuid,
            "purpose": purpose,
            "user_id": str(user_id) if user_id else None,
        },
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
        raise InvalidVerificationCode("That code did not match. Please try again.")
    return row


def verify_email(challenge_id, code, user_id=None, invitation_token=None):
    s = schema_name()
    purpose = "EMAIL_VERIFY" if user_id else "REGISTRATION_EMAIL_OTP"
    invalid_error = None
    with auth_engine().begin() as conn:
        try:
            row = _verified_challenge(conn, challenge_id, code, purpose, user_id)
        except InvalidVerificationCode as error:
            invalid_error = error
        else:
            if not user_id:
                if not setting_enabled('signup_enabled', True):
                    raise AccountUnavailable('Signup is disabled right now')
                approved_type = admission_type(conn, str(row['target_email']).lower(), invitation_token)
                resolve_account_type(row['account_type'], approved_type)
            conn.execute(
                text(f"UPDATE {s}.auth_challenges SET consumed_at=CURRENT_TIMESTAMP WHERE id=:id"),
                {"id": row["id"]},
            )
            conn.execute(
                text(f"UPDATE {s}.app_users SET status='ACTIVE' WHERE id=:id AND status='PENDING'"),
                {"id": row["app_user_id"]},
            )
            email = str(row["target_email"]).lower()
            conn.execute(
                text(
                    f"""UPDATE {s}.user_emails
                    SET verified_at=COALESCE(verified_at,CURRENT_TIMESTAMP),is_primary=true
                    WHERE app_user_id=:u AND lower(email::text)=:email"""
                ),
                {"u": row["app_user_id"], "email": email},
            )
            _link_verified_contacts(conn, row["app_user_id"], email)
            result = {
                "id": str(row["app_user_id"]),
                "email": email,
                "full_name": row["full_name"],
            }
    if invalid_error:
        raise invalid_error
    return result


def complete_google_profile(user_id, full_name, phone=None, account_type=None):
    name = (full_name or "").strip()
    phone = (phone or "").strip() or None
    if not name:
        raise AccountUnavailable("Enter your full name")
    if phone and not 5 <= len(phone) <= 30:
        raise AccountUnavailable("Enter a valid phone number")
    s = schema_name()
    with auth_engine().begin() as conn:
        current = conn.execute(
            text(f'SELECT account_type FROM {s}.app_users WHERE id=:id FOR UPDATE'),
            {'id': UUID(str(user_id))},
        ).mappings().first()
        if not current:
            raise AccountUnavailable('Profile is unavailable')
        account_type = resolve_account_type(account_type, current['account_type'])
        conn.execute(
            text(f"""UPDATE {s}.app_users SET full_name=:name,phone=:phone,
                account_type=:account_type WHERE id=:id"""),
            {"id": UUID(str(user_id)), "name": name[:150], "phone": phone,
             'account_type': account_type},
        )
    return session_profile(user_id)


def update_profile(user_id, full_name, phone, date_of_birth=None, country=None):
    name = (full_name or "").strip()
    phone = (phone or "").strip()
    country = (country or "").strip() or None
    if not name:
        raise AccountUnavailable("Enter your full name")
    if not 5 <= len(phone) <= 30:
        raise AccountUnavailable("Enter a valid phone number")
    if country and not 2 <= len(country) <= 100:
        raise AccountUnavailable("Enter a valid country")
    if date_of_birth and date_of_birth > datetime.now(timezone.utc).date():
        raise AccountUnavailable("Date of birth cannot be in the future")
    s = schema_name()
    with auth_engine().begin() as conn:
        conn.execute(
            text(
                f"""UPDATE {s}.app_users SET full_name=:name,phone=:phone,
                date_of_birth=:dob,country=:country WHERE id=:id"""
            ),
            {
                "id": UUID(str(user_id)),
                "name": name[:150],
                "phone": phone,
                "dob": date_of_birth,
                "country": country,
            },
        )
    return session_profile(user_id)


def session_profile(user_id):
    s = schema_name()
    with auth_engine().connect() as conn:
        row = conn.execute(
            text(
                f"""SELECT u.id,u.full_name,u.phone,u.date_of_birth,u.country,
                u.avatar_url,u.user_type,e.email,(e.verified_at IS NOT NULL) email_verified
                FROM {s}.app_users u LEFT JOIN {s}.user_emails e
                  ON e.app_user_id=u.id AND e.is_primary=true
                WHERE u.id=:id"""
            ),
            {"id": UUID(str(user_id))},
        ).mappings().first()
        if not row:
            raise AccountUnavailable("Profile is unavailable")
        return dict(row, id=str(row["id"]))


def start_registration(email, full_name, account_type, invitation_token=None):
    if not setting_enabled("signup_enabled", True):
        raise AccountUnavailable("Signup is disabled right now")
    email = normalize_email(email)
    name = (full_name or email).strip()[:150] or email
    s = schema_name()
    challenge_id = uuid4()
    code = generate_otp()
    with auth_engine().begin() as conn:
        approved_type = admission_type(conn, email, invitation_token)
        account_type = resolve_account_type(account_type, approved_type)
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
        conn.execute(text(f'UPDATE {s}.app_users SET account_type=COALESCE(account_type,:kind) WHERE id=:id'),
                     {'kind': account_type, 'id': user_id})
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
    return {"id": str(user_id), "challenge_id": str(challenge_id), "email": email, "full_name": name, "code": code}


def verify_registration(challenge_id, code, invitation_token=None):
    return verify_email(challenge_id, code, invitation_token=invitation_token)
