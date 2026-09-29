"""Invitation requests and admission checks shared by every registration path."""
import hashlib
from html import escape
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from ..auth.database import auth_engine, schema_name
from .product_settings import setting_enabled
from .emailer import send_email


def admission_type(conn, email, invitation_token=None):
    """Return an approved account type, or allow a matching active staff invite.

    Called inside the account-creation transaction. Missing schema fails closed.
    Existing authenticated users never pass through this gate.
    """
    s = schema_name()
    if not setting_enabled('invite_request_enabled', False):
        return None
    if invitation_token and len(invitation_token) <= 100:
        invitation = conn.execute(text(f"""SELECT 1 FROM {s}.workspace_invitations i
            JOIN {s}.workspaces w ON w.id=i.workspace_id
            WHERE i.token_hash=:token AND lower(i.email::text)=:email
              AND i.status='PENDING' AND i.expires_at>CURRENT_TIMESTAMP
              AND w.status='ACTIVE'"""),
            {'token': hashlib.sha256(invitation_token.encode()).hexdigest(), 'email': email}).first()
        if invitation:
            return None
    row = conn.execute(text(f"""SELECT usage_type FROM {s}.interest
        WHERE lower(email::text)=:email AND status='APPROVED'
        ORDER BY approved_at DESC LIMIT 1 FOR SHARE"""), {'email': email}).mappings().first()
    if not row:
        # Import here avoids a module cycle with the registration repository.
        from ..auth.repository import AccountUnavailable
        raise AccountUnavailable('Request an invitation and wait for approval before creating an account.')
    return row['usage_type']


def request_invitation(payload):
    from ..auth.repository import (
        ACCOUNT_EXISTS_MESSAGE, AccountUnavailable, normalize_email,
    )
    if not setting_enabled('invite_request_enabled', False):
        raise HTTPException(409, 'Invitation requests are closed. You can use the signup form.')
    try:
        email = normalize_email(payload.email)
    except AccountUnavailable as error:
        raise HTTPException(422, str(error)) from None
    with auth_engine().begin() as conn:
        # Serialize duplicate requests without relying on an unknown historical index.
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:email, 814))'), {'email': email})
        account = conn.execute(text(f"""SELECT 1 FROM {schema_name()}.user_emails
            WHERE lower(email::text)=:email LIMIT 1"""), {'email': email}).first()
        if account:
            raise HTTPException(409, ACCOUNT_EXISTS_MESSAGE)
        existing = conn.execute(text(f'SELECT id FROM {schema_name()}.interest WHERE lower(email::text)=:email LIMIT 1'), {'email': email}).first()
        if not existing:
            conn.execute(text(f"""INSERT INTO {schema_name()}.interest(full_name,email,country,usage_type)
                VALUES (:name,:email,:country,:kind)"""),
                {'name': payload.full_name, 'email': email, 'country': payload.country, 'kind': payload.usage_type})
    # Same response for duplicates; public callers cannot inspect approval state.
    return {'ok': True, 'message': 'Your request has been received. We will email you if it is approved.'}


def list_requests(status='PENDING', offset=0):
    with auth_engine().connect() as conn:
        rows = conn.execute(text(f"""SELECT id,full_name,email,country,usage_type,status,
            requested_at,approved_at,last_email_sent_at FROM {schema_name()}.interest
            WHERE (:status='ALL' OR status=:status)
            ORDER BY requested_at DESC,id LIMIT 51 OFFSET :offset"""), {'status': status, 'offset': offset}).mappings().all()
    return {'requests': [dict(row) for row in rows[:50]], 'has_more': len(rows)>50}


def review_request(request_id, status, reviewer):
    with auth_engine().begin() as conn:
        row = conn.execute(text(f"""UPDATE {schema_name()}.interest SET status=:status,
            approved_at=CASE WHEN :status='APPROVED' THEN CURRENT_TIMESTAMP ELSE NULL END,
            approved_by=CASE WHEN :status='APPROVED' THEN :reviewer ELSE NULL END
            WHERE id=:id RETURNING id,status"""),
            {'id': request_id, 'status': status, 'reviewer': UUID(str(reviewer))}).mappings().first()
        if not row:
            raise HTTPException(404, 'Request not found.')
    return dict(row)


def email_approval(request_id, signup_url):
    """Explicit executive action; report actual provider success, never fake delivery."""
    if not setting_enabled('notification_emails_enabled', True):
        raise HTTPException(409, 'Enable operational emails before sending an invitation.')
    with auth_engine().begin() as conn:
        row = conn.execute(text(f"""SELECT email,full_name,status,last_email_sent_at,
            last_email_sent_at > CURRENT_TIMESTAMP - interval '1 minute' AS recently_sent
            FROM {schema_name()}.interest WHERE id=:id FOR UPDATE"""), {'id': request_id}).mappings().first()
        if not row or row['status'] != 'APPROVED':
            raise HTTPException(409, 'Approve this request before sending an invitation.')
        if row['recently_sent']:
            raise HTTPException(429, 'Wait one minute before sending another invitation.')
        try:
            result = send_email(str(row['email']), 'Your Classarit invitation is ready',
                f'<h2>Welcome to Classarit</h2><p>Hi {escape(row["full_name"])}, your request is approved.</p>'
                f'<p><a href="{escape(signup_url, quote=True)}">Create your account</a> using this email address.</p>',
                f'Your Classarit request is approved. Create your account using this email address: {signup_url}')
        except Exception:
            raise HTTPException(502, 'The email provider could not send the invitation. Approval is saved; try again.') from None
        if not result or not result.get('id'):
            raise HTTPException(503, 'Email is not configured or delivery was not accepted. Approval is saved.')
        conn.execute(text(f'UPDATE {schema_name()}.interest SET last_email_sent_at=CURRENT_TIMESTAMP WHERE id=:id'), {'id': request_id})
    return {'ok': True}
