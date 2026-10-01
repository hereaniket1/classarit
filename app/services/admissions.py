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
          AND (NOT verification_required OR email_verified_at IS NOT NULL)
        ORDER BY approved_at DESC LIMIT 1 FOR SHARE"""), {'email': email}).mappings().first()
    if not row:
        # Import here avoids a module cycle with the registration repository.
        from ..auth.repository import AccountUnavailable
        raise AccountUnavailable('Request an invitation and wait for approval before creating an account.')
    return row['usage_type']


def _deliver(to, subject, body):
    try:
        result = send_email(to, subject, body, None)
    except Exception:
        raise HTTPException(502, 'Email delivery failed. Please retry.') from None
    if not result or not result.get('id'):
        raise HTTPException(503, 'Email delivery is unavailable. Please retry.')


def _details(row, internal=True):
    details = dict(row)
    details['usage_type'] = {'INDIVIDUAL':'Individual', 'ORGANIZATION':'Organization'}.get(row.get('usage_type'), 'Not selected')
    when = row.get('requested_at')
    if hasattr(when, 'strftime'):
        details['requested_at'] = when.strftime('%d %b %Y, %H:%M %Z')
    fields = [('Name','full_name'), ('Email','email'), ('Country','country'), ('Account type','usage_type'), ('Requested on','requested_at')]
    if internal:
        fields.append(('Request ID','id'))
    return '<table style="border-collapse:collapse;width:100%;max-width:560px">' + ''.join(
        f'<tr><th style="text-align:left;padding:10px;border-bottom:1px solid #e5e7eb">{label}</th>'
        f'<td style="padding:10px;border-bottom:1px solid #e5e7eb">{escape(str(details.get(key) or "Not supplied"))}</td></tr>'
        for label, key in fields) + '</table>'


def retry_owner_notifications():
    """Pending deliveries survive restarts; row locking prevents concurrent sends."""
    with auth_engine().connect() as conn:
        pending = conn.execute(text(f'''SELECT id,notification_base_url FROM {schema_name()}.interest
            WHERE owner_notified_at IS NULL AND email_verified_at IS NOT NULL AND notification_base_url IS NOT NULL
            ORDER BY requested_at LIMIT 50''')).mappings().all()
    for row in pending:
        try:
            _notify_owner(row['id'], row['notification_base_url'])
        except HTTPException:
            continue


def queue_owner_notifications(base_url):
    """Include older requests whose owner notification never succeeded."""
    with auth_engine().begin() as conn:
        conn.execute(text(f'''UPDATE {schema_name()}.interest SET notification_base_url=:url
            WHERE owner_notified_at IS NULL AND email_verified_at IS NOT NULL AND notification_base_url IS NULL'''), {'url':base_url})


def _notify_owner(request_id, base_url):
    with auth_engine().begin() as conn:
        row = conn.execute(text(f'SELECT * FROM {schema_name()}.interest WHERE id=:id FOR UPDATE'),
                           {'id': request_id}).mappings().first()
        if not row or row['owner_notified_at'] or not row.get('email_verified_at'):
            return
        link = escape(base_url.rstrip('/') + '/invitation-review/' + str(row['id']), quote=True)
        _deliver('aniketpathak1@gmail.com', 'Verified Classarit access request',
                 '<h2>Verified access request</h2>' + _details(row) +
                 '<p>The applicant has completed email OTP verification. Sign in with your executive account to approve or decline this request.</p>' +
                 f'<p><a href="{link}/APPROVED">Review and approve access</a></p>' +
                 f'<p><a href="{link}/REJECTED">Review and decline access</a></p>')
        conn.execute(text(f'UPDATE {schema_name()}.interest SET owner_notified_at=CURRENT_TIMESTAMP WHERE id=:id'), {'id': request_id})


def request_invitation(payload, base_url=''):
    from uuid import uuid4
    from ..auth.repository import ACCOUNT_EXISTS_MESSAGE, AccountUnavailable, normalize_email, generate_otp, challenge_digest
    if not setting_enabled('invite_request_enabled', False):
        raise HTTPException(409, 'Invitation requests are closed. You can use the signup form.')
    try:
        email = normalize_email(payload.email)
    except AccountUnavailable as error:
        raise HTTPException(422, str(error)) from None
    with auth_engine().begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:email, 814))'), {'email': email})
        if conn.execute(text(f'SELECT 1 FROM {schema_name()}.user_emails WHERE lower(email::text)=:email LIMIT 1'), {'email':email}).first():
            raise HTTPException(409, ACCOUNT_EXISTS_MESSAGE)
        row = conn.execute(text(f"""SELECT *, verification_sent_at > CURRENT_TIMESTAMP - interval '1 minute' AS recent
            FROM {schema_name()}.interest WHERE lower(email::text)=:email ORDER BY requested_at DESC LIMIT 1 FOR UPDATE"""), {'email':email}).mappings().first()
        if row and (not row.get('verification_required') or
                    (row.get('email_verified_at') and row.get('receipt_sent_at') and row.get('owner_notified_at'))):
            return {'ok':True, 'message':'Your request is already recorded. Wait for the access decision or log in if you have an account.'}
        if row and row['recent']:
            raise HTTPException(429, 'Wait one minute before requesting another verification code.')
        if not row:
            row = conn.execute(text(f"""INSERT INTO {schema_name()}.interest(full_name,email,country,usage_type,verification_required)
                VALUES (:name,:email,:country,:kind,true) RETURNING *"""),
                {'name':payload.full_name,'email':email,'country':payload.country,'kind':payload.usage_type}).mappings().first()
        request_id, challenge_id, code = row['id'], uuid4(), generate_otp()
        conn.execute(text(f"""UPDATE {schema_name()}.interest SET verification_id=:challenge,
            verification_digest=:digest,verification_expires_at=CURRENT_TIMESTAMP+interval '10 minutes',
            verification_attempts=0,verification_sent_at=CURRENT_TIMESTAMP,notification_base_url=:base_url WHERE id=:id"""),
            {'id':request_id,'challenge':challenge_id,'base_url':base_url,'digest':challenge_digest(challenge_id,'INVITATION_REQUEST_OTP',email,code)})
        _deliver(email, 'Verify your Classarit access request',
                 f'<h2>Verify your email</h2><p>Your access-request verification code is <strong>{code}</strong>.</p>'
                 '<p>Expires in 10 minutes. This verifies an invitation request only; it does not create an account or grant access.</p>')
    return {'ok':True,'verification_required':True,'challenge_id':str(challenge_id),
            'message':'Check your email for the access-request verification code.'}


def verify_request(challenge_id, code, base_url):
    import hmac
    from ..auth.repository import challenge_digest
    invalid = False
    with auth_engine().begin() as conn:
        row = conn.execute(text(f"""SELECT *, verification_expires_at>CURRENT_TIMESTAMP AS unexpired
            FROM {schema_name()}.interest WHERE verification_id=:id FOR UPDATE"""), {'id':challenge_id}).mappings().first()
        if not row or not row['unexpired'] or row['verification_attempts'] >= 5:
            raise HTTPException(400, 'Code expired or unavailable. Request a new code.')
        expected = challenge_digest(challenge_id,'INVITATION_REQUEST_OTP',str(row['email']).lower(),code)
        if not hmac.compare_digest(expected,row['verification_digest'] or ''):
            conn.execute(text(f'UPDATE {schema_name()}.interest SET verification_attempts=verification_attempts+1 WHERE id=:id'), {'id':row['id']})
            invalid = True
        else:
            conn.execute(text(f'UPDATE {schema_name()}.interest SET email_verified_at=COALESCE(email_verified_at,CURRENT_TIMESTAMP) WHERE id=:id'), {'id':row['id']})
    if invalid:
        raise HTTPException(400, 'Incorrect verification code.')
    # Verification stays committed even if delivery fails; the same code can retry delivery until expiry.
    try:
        _notify_owner(row['id'], base_url)
    except HTTPException:
        pass  # The durable pending notification is retried by the application worker.
    with auth_engine().begin() as conn:
        current = conn.execute(text(f'SELECT * FROM {schema_name()}.interest WHERE id=:id FOR UPDATE'), {'id':row['id']}).mappings().first()
        if not current['receipt_sent_at']:
            login_url = escape(base_url.rstrip('/') + '/login', quote=True)
            next_step = ('Your access is approved. You can log in now.' if current['status'] == 'APPROVED' else
                         'Your request was declined. Access is not enabled.' if current['status'] == 'REJECTED' else
                         'Your email is verified and your request is awaiting approval. We will email you when access is granted.')
            _deliver(str(current['email']), 'Your Classarit access request is verified',
                     f'<h2>Thank you, {escape(current["full_name"])}</h2><p>{next_step}</p>' +
                     _details(current, internal=False) +
                     f'<p>Once approved, open <a href="{login_url}">Classarit login</a> and choose <strong>Continue with Google</strong>. '
                     f'Use your verified Google account for <strong>{escape(str(current["email"]))}</strong>.</p>')
            conn.execute(text(f'UPDATE {schema_name()}.interest SET receipt_sent_at=CURRENT_TIMESTAMP WHERE id=:id'), {'id':row['id']})
    return {'ok':True,'message':'Email verified. Your request details have been emailed to you. We will email you when access is granted.'}


def list_requests(status='PENDING', offset=0, request_id=None):
    with auth_engine().connect() as conn:
        rows = conn.execute(text(f"""SELECT id,full_name,email,country,usage_type,status,
            requested_at,approved_at,last_email_sent_at,email_verified_at,verification_required FROM {schema_name()}.interest
            WHERE (:status='ALL' OR status=:status) AND (CAST(:request_id AS uuid) IS NULL OR id=CAST(:request_id AS uuid))
            ORDER BY requested_at DESC,id LIMIT 51 OFFSET :offset"""), {'status': status, 'offset': offset, 'request_id': request_id}).mappings().all()
    return {'requests': [dict(row) for row in rows[:50]], 'has_more': len(rows)>50}


def review_request(request_id, status, reviewer, signup_url=None):
    with auth_engine().begin() as conn:
        row = conn.execute(text(f"""UPDATE {schema_name()}.interest SET status=:status,
            approved_at=CASE WHEN :status='APPROVED' THEN CURRENT_TIMESTAMP ELSE NULL END,
            approved_by=CASE WHEN :status='APPROVED' THEN :reviewer ELSE NULL END
            WHERE id=:id AND (:status!='APPROVED' OR NOT verification_required OR email_verified_at IS NOT NULL) RETURNING id,status"""),
            {'id': request_id, 'status': status, 'reviewer': UUID(str(reviewer))}).mappings().first()
        if not row:
            raise HTTPException(409, 'Request not found or applicant email is not verified.')
    result = dict(row)
    if status == 'APPROVED' and signup_url:
        try:
            email_approval(request_id, signup_url)
            result['email_sent'] = True
        except HTTPException as error:
            result.update(email_sent=False, email_error=error.detail)
    return result


def email_approval(request_id, signup_url):
    """Send after approval or explicit executive retry; record provider acceptance."""
    # Access decisions are transactional emails, independent of schedule notifications.
    signup_url = signup_url.split('#', 1)[0]
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
                f'<p><a href="{escape(signup_url, quote=True)}">Log in to Classarit</a> and choose <strong>Continue with Google</strong> '
                f'using <strong>{escape(str(row["email"]))}</strong>.</p>',
                f'Your Classarit request is approved. Log in with Google using {row["email"]}: {signup_url}')
        except Exception:
            raise HTTPException(502, 'The email provider could not send the invitation. Approval is saved; try again.') from None
        if not result or not result.get('id'):
            raise HTTPException(503, 'Email is not configured or delivery was not accepted. Approval is saved.')
        conn.execute(text(f'UPDATE {schema_name()}.interest SET last_email_sent_at=CURRENT_TIMESTAMP WHERE id=:id'), {'id': request_id})
    return {'ok': True}
