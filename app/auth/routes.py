import logging
import secrets

from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from ..views import templates
from ..services import notifications
from ..services.product_settings import setting_enabled
from .settings import get_settings, google_callback_url
from .dependencies import current_user
from . import repository

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()
oauth = OAuth()


class RegistrationStart(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=254)


class RegistrationVerify(BaseModel):
    challenge_id: str
    code: str = Field(min_length=6, max_length=6)


oauth.register('google', client_id=settings.client_id, client_secret=settings.client_secret,
               server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
               client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256'})


def result(request, success=False, message=''):
    return templates.TemplateResponse('auth/callback.html', {'request': request, 'success': success, 'message': message},
                                      status_code=200 if success else 400,
                                      headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


@router.get('/login')
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse('/dashboard', status_code=303)
    return templates.TemplateResponse('login.html', {'request':request, 'google_ready':settings.ready, 'signup_enabled':setting_enabled('signup_enabled', True), 'invitation_pending':bool(request.session.get('pending_invitation'))})


@router.get('/auth/google/login')
async def google_login(request: Request):
    if not settings.ready:
        return result(request, message='Google login is not available yet. Please try again later.')
    try:
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
        user = await run_in_threadpool(repository.google_account, claims)
        await run_in_threadpool(repository.revoke_session, request.session.get('sid'))
        sid = await run_in_threadpool(repository.create_session, user['id'])
        # Keep only the invitation intent while rotating authentication state.
        pending_invitation = request.session.get('pending_invitation')
        request.session.clear()
        request.session.update(sid=sid, csrf=secrets.token_urlsafe(32))
        if pending_invitation:
            request.session['pending_invitation'] = pending_invitation
        return result(request, success=True)
    except repository.LinkingRequired:
        return result(request, message='This email is already registered with another login method. Account linking is coming soon.')
    except repository.AccountUnavailable:
        return result(request, message='This account cannot sign in. Please contact support.')
    except Exception:
        # Do not log OAuth codes, tokens, DB connection details or provider claims.
        logger.warning('Google callback could not be completed')
        return result(request, message='Sign-in could not be completed. Please try again or contact support.')


@router.post('/auth/register/start')
def register_start(payload: RegistrationStart, background_tasks: BackgroundTasks):
    try:
        challenge = repository.start_registration(payload.email, payload.full_name)
        notifications.send_registration_otp(
            background_tasks,
            challenge['email'],
            challenge['full_name'],
            challenge['code'],
        )
        return {'ok': True, 'challenge_id': challenge['challenge_id'], 'email': challenge['email']}
    except repository.LinkingRequired:
        return JSONResponse({'detail':'This email is already registered. Please log in with an existing method.'}, status_code=409)
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=403)


@router.post('/auth/register/verify')
def register_verify(payload: RegistrationVerify, request: Request):
    try:
        user = repository.verify_registration(payload.challenge_id, payload.code)
        repository.revoke_session(request.session.get('sid'))
        sid = repository.create_session(user['id'])
        request.session.clear()
        request.session.update(sid=sid, csrf=secrets.token_urlsafe(32))
        return {'ok': True}
    except repository.AccountUnavailable as error:
        return JSONResponse({'detail':str(error)}, status_code=400)


@router.get('/auth/me')
def me(request: Request):
    user = current_user(request)
    return JSONResponse({'authenticated':bool(user)}, headers={'Cache-Control':'no-store'})


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
