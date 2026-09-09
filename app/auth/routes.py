import logging
import secrets

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from ..views import templates
from .settings import get_settings
from .dependencies import current_user
from . import repository

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()
oauth = OAuth()
oauth.register('google', client_id=settings.client_id, client_secret=settings.client_secret,
               server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
               client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256'})


def result(request, success=False, message=''):
    return templates.TemplateResponse('auth/callback.html', {'request': request, 'success': success, 'message': message},
                                      status_code=200 if success else 400,
                                      headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


@router.get('/login')
def login_page(request: Request):
    if settings.ready and str(request.base_url).rstrip('/') != settings.origin:
        return RedirectResponse(settings.origin + '/login', status_code=303)
    if current_user(request):
        return RedirectResponse('/dashboard', status_code=303)
    return templates.TemplateResponse('login.html', {'request':request, 'google_ready':settings.ready})


@router.get('/auth/google/login')
async def google_login(request: Request):
    if not settings.ready:
        return result(request, message='Google login is not available yet. Please try again later.')
    # Keep the entire popup flow on the configured origin, including its state cookie.
    if str(request.base_url).rstrip('/') != settings.origin:
        return RedirectResponse(settings.origin + '/auth/google/login', status_code=303)
    try:
        return await oauth.google.authorize_redirect(request, settings.redirect_uri, prompt='select_account')
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
        request.session.clear()
        request.session.update(sid=sid, csrf=secrets.token_urlsafe(32))
        return result(request, success=True)
    except repository.LinkingRequired:
        return result(request, message='This email is already registered with another login method. Account linking is coming soon.')
    except repository.AccountUnavailable:
        return result(request, message='This account cannot sign in. Please contact support.')
    except Exception:
        # Do not log OAuth codes, tokens, DB connection details or provider claims.
        logger.warning('Google callback could not be completed')
        return result(request, message='Sign-in could not be completed. Please try again or contact support.')


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
