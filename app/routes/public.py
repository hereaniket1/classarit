from fastapi import APIRouter, Request
from ..views import templates
from ..auth.settings import get_settings
from ..services.product_settings import setting_enabled
from ..services.content import terms_context

router = APIRouter()


@router.get('/')
def home(request: Request):
    return templates.TemplateResponse('home.html', {
        'request': request,
        'google_ready': get_settings().ready,
        'signup_enabled': setting_enabled('signup_enabled', True),
        'invite_request_enabled': setting_enabled('invite_request_enabled', False),
        'email_verification_enabled': setting_enabled('email_verification_enabled', True),
        'invitation_pending': bool(request.session.get('pending_invitation')),
        'terms': terms_context(request),
    }, headers={'Cache-Control': 'no-store'})


@router.get('/health', include_in_schema=False)
def health():
    return {'status':'ok'}
