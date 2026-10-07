import logging
import secrets
from datetime import date
from typing import Literal

from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from ..views import templates
from ..services import notifications
from ..services.content import terms_context
from ..services.product_settings import setting_enabled, all_settings
from .settings import get_settings, google_callback_url
from .dependencies import current_user, require_dashboard_user
from . import repository

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()
oauth = OAuth()


class RegistrationStart(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=254)
    account_type: Literal['INDIVIDUAL', 'ORGANIZATION']
    accepted_terms: bool = False


class RegistrationVerify(BaseModel):
    challenge_id: str
    code: str = Field(min_length=6, max_length=6)


class PasswordRegistration(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=5, max_length=30)
    email: str = Field(min_length=3, max_length=254)
    account_type: Literal['INDIVIDUAL', 'ORGANIZATION']
    password: str = Field(min_length=10, max_length=128)
    accepted_terms: bool = False


class TermsAcceptance(BaseModel):
    accepted_terms: bool = False


class GoogleProfileCompletion(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    account_type: Literal['INDIVIDUAL', 'ORGANIZATION']
    accepted_terms: bool = False


class PasswordLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=5, max_length=30)
    date_of_birth: date | None = None
    country: str | None = Field(default=None, max_length=100)


oauth.register('google', client_id=settings.client_id, client_secret=settings.client_secret,
               server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
               client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256'})


def result(request, success=False, message=''):
    return templates.TemplateResponse('auth/callback.html', {'request': request, 'success': success, 'message': message},
                                      status_code=200 if success else 400,
                                      headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


def sign_in(request, user):
    repository.revoke_session(request.session.get('sid'))
    sid = repository.create_session(user['id'])
    pending_invitation = request.session.get('pending_invitation')
    invitation_review_next = request.session.get('invitation_review_next')
    request.session.clear()
    request.session.update(sid=sid, csrf=secrets.token_urlsafe(32))
    if pending_invitation:
        request.session['pending_invitation'] = pending_invitation
    if invitation_review_next:
        request.session['invitation_review_next'] = invitation_review_next


def request_ip(request):
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else "")


def record_terms(request, user, source):
    try:
        repository.record_terms_acceptance(
            user["id"],
            user.get("email"),
            user.get("full_name"),
            source,
            request_ip(request),
            request.headers.get("user-agent", ""),
            version=request.session.get('terms_version'),
        )
    except Exception:
        # Terms audit is important, but a stale local schema or duplicate historical
        # row must not break a successful authentication. The executive audit table
        # migration can be applied independently to resume durable event capture.
        logger.warning('Terms acceptance audit could not be saved', exc_info=True)


@router.get('/login')
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse('/dashboard', status_code=303)
    product = all_settings()
    return templates.TemplateResponse('login.html', {
        'request':request,
        'google_ready':settings.ready,
        'signup_enabled':product['signup_enabled'],
        'invite_request_enabled':product['invite_request_enabled'],
        'email_verification_enabled':product['email_verification_enabled'],
        'invitation_pending':bool(request.session.get('pending_invitation')),
        'terms': terms_context(request),
    })


@router.get('/auth/google/login')
async def google_login(request: Request):
    if not settings.ready:
        return result(request, message='Google login is not available yet. Please try again later.')
    try:
        request.session['google_login_started'] = True
        return await oauth.google.authorize_redirect(request, google_callback_url(request), prompt='select_account')
    except Exception:
        logger.warning('Could not start Google authorization')
        return result(request, message='Unable to reach Google. Please try again.')


@router.get('/auth/google/callback')
async def google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        # Authlib validates ID-token signature, issuer, audience, expiry and nonce.
        claims = token.get('userinfo')
        if not token.get('id_token') or not claims:
            raise repository.AccountUnavailable('Missing verified ID token')
        started_from_login = bool(request.session.get('google_login_started'))
        user = await run_in_threadpool(repository.google_account, claims, request.session.get('pending_invitation'))
        await run_in_threadpool(record_terms, request, user, 'GOOGLE_LOGIN')
        await run_in_threadpool(sign_in, request, user)
        if started_from_login and user.get('is_new_user'):
            request.session['google_profile_required'] = True
        return result(request, success=True)
    except repository.LinkingRequired:
        return result(request, message='Verify this account by email before connecting Google.')
    except repository.AccountUnavailable as error:
        return result(request, message=str(error))
    except Exception:
        # Do not log OAuth codes, tokens, DB connection details or provider claims.
        logger.warning('Google callback could not be completed', exc_info=True)
        return result(request, message='Sign-in could not be completed. Please try again or contact support.')


@router.post('/auth/register/start')
def register_start(payload: RegistrationStart, request: Request, background_tasks: BackgroundTasks):
    if not payload.accepted_terms:
        return JSONResponse({'detail':'Accept the terms and conditions to continue.'}, status_code=422)
    try:
        challenge = repository.start_registration(payload.email, payload.full_name, payload.account_type, request.session.get('pending_invitation'))
        record_terms(request, challenge, 'EMAIL_OTP_SIGNUP')
        notifications.send_registration_otp(
            background_tasks,
            challenge['email'],
            challenge['full_name'],
            challenge['code'],
        )
        return {'ok': True, 'challenge_id': challenge['challenge_id'], 'email': challenge['email']}
    except repository.LinkingRequired:
        return JSONResponse({'detail':repository.ACCOUNT_EXISTS_MESSAGE}, status_code=409)
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=403)


@router.post('/auth/register/verify')
def register_verify(payload: RegistrationVerify, request: Request):
    try:
        user = repository.verify_registration(payload.challenge_id, payload.code, request.session.get('pending_invitation'))
        sign_in(request, user)
        return {'ok': True}
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.post('/auth/password/register')
def password_register(payload: PasswordRegistration, request: Request, background_tasks: BackgroundTasks):
    if not payload.accepted_terms:
        return JSONResponse({'detail':'Accept the terms and conditions to continue.'}, status_code=422)
    try:
        user = repository.start_password_registration(
            payload.email, payload.full_name, payload.phone, payload.password,
            payload.account_type, request.session.get('pending_invitation')
        )
        record_terms(request, user, 'PASSWORD_SIGNUP')
        if user['verification_required']:
            notifications.send_registration_otp(
                background_tasks, user['email'], user['full_name'], user['code']
            )
            return {
                'ok': True,
                'verification_required': True,
                'challenge_id': user['challenge_id'],
                'email': user['email'],
            }
        sign_in(request, user)
        return {'ok': True, 'verification_required': False}
    except repository.LinkingRequired:
        return JSONResponse({'detail':repository.ACCOUNT_EXISTS_MESSAGE}, status_code=409)
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.post('/auth/terms/accept')
def terms_accept(payload: TermsAcceptance, request: Request):
    if not payload.accepted_terms:
        return JSONResponse({'detail':'Accept the terms and conditions to continue.'}, status_code=422)
    request.session['terms_accepted'] = True
    return {'ok': True}


@router.get('/auth/google/profile')
def google_profile_page(request: Request, user=Depends(require_dashboard_user)):
    if not request.session.get('google_profile_required'):
        return RedirectResponse('/dashboard', status_code=303)
    return templates.TemplateResponse('auth/google_profile.html', {
        'request': request,
        'user': user,
        'csrf_token': request.session.get('csrf', ''),
        'terms': terms_context(request),
        'invite_request_enabled': setting_enabled('invite_request_enabled', False),
    })


@router.post('/auth/google/profile')
def google_profile_complete(payload: GoogleProfileCompletion, request: Request, user=Depends(require_dashboard_user)):
    if not request.session.get('google_profile_required'):
        return {'ok': True}
    if not payload.accepted_terms:
        return JSONResponse({'detail':'Accept the terms and conditions to continue.'}, status_code=422)
    try:
        updated = repository.complete_google_profile(
            user['id'], payload.full_name, payload.phone, payload.account_type
        )
        record_terms(request, updated, 'GOOGLE_PROFILE')
        request.session.pop('google_profile_required', None)
        return {'ok': True}
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.post('/auth/password/register/verify')
def password_register_verify(payload: RegistrationVerify, request: Request):
    try:
        user = repository.verify_registration(payload.challenge_id, payload.code, request.session.get('pending_invitation'))
        sign_in(request, user)
        return {'ok': True}
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.post('/auth/password/login')
def password_login(payload: PasswordLogin, request: Request):
    try:
        user = repository.password_account(payload.email, payload.password)
        sign_in(request, user)
        return {'ok': True}
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=401)


@router.patch('/api/account/profile')
def profile_update(payload: ProfileUpdate, user=Depends(require_dashboard_user)):
    try:
        return repository.update_profile(
            user['id'], payload.full_name, payload.phone,
            payload.date_of_birth, payload.country,
        )
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.post('/auth/email/verify/start')
def email_verify_start(background_tasks: BackgroundTasks, user=Depends(require_dashboard_user)):
    try:
        challenge = repository.start_email_verification(user['id'])
        notifications.send_registration_otp(
            background_tasks,
            challenge['email'],
            challenge['full_name'],
            challenge['code'],
        )
        return {
            'ok': True,
            'challenge_id': challenge['challenge_id'],
            'email': challenge['email'],
        }
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.post('/auth/email/verify/complete')
def email_verify_complete(
    payload: RegistrationVerify, user=Depends(require_dashboard_user)
):
    try:
        repository.verify_email(payload.challenge_id, payload.code, user['id'])
        return {'ok': True}
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.get('/auth/me')
def me(request: Request):
    user = current_user(request)
    payload = {'authenticated': bool(user)}
    if user and request.session.get('google_profile_required'):
        payload['next_url'] = '/auth/google/profile'
    elif user and request.session.get('invitation_review_next'):
        payload['next_url'] = request.session['invitation_review_next']
    return JSONResponse(payload, headers={'Cache-Control':'no-store'})


@router.post('/auth/logout')
async def logout(request: Request):
    form = await request.form()
    expected = request.session.get('csrf','')
    supplied = str(form.get('csrf_token',''))
    if not expected or not secrets.compare_digest(expected,supplied):
        return JSONResponse({'detail':'Invalid request'},status_code=403)
    try:
        await run_in_threadpool(repository.revoke_session, request.session.get('sid'))
    except Exception:
        return JSONResponse({'detail':'Could not log out. Please retry.'},status_code=503)
    request.session.clear()
    return RedirectResponse('/',status_code=303)
