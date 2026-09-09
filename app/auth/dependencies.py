import secrets
from fastapi import HTTPException, Request
from .repository import session_user


def current_user(request: Request):
    if hasattr(request.state, 'user'):
        return request.state.user
    try:
        user = session_user(request.session.get('sid'))
    except Exception:
        raise HTTPException(503, 'Sign-in is temporarily unavailable. Please try again.') from None
    request.state.user = user
    return user


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, 'Please log in to continue.')
    if request.method not in ('GET','HEAD','OPTIONS'):
        expected = request.session.get('csrf', '')
        supplied = request.headers.get('X-CSRF-Token', '')
        if not expected or not secrets.compare_digest(expected, supplied):
            raise HTTPException(403, 'Invalid request. Refresh and try again.')
    return user
