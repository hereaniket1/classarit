from fastapi import APIRouter, Request
from ..views import templates
from ..auth.settings import get_settings
from ..services.product_settings import all_settings
from ..services.content import terms_context

router = APIRouter()


@router.get('/')
def home(request: Request):
    product = all_settings()
    return templates.TemplateResponse('home.html', {
        'request': request,
        'google_ready': get_settings().ready,
        'signup_enabled': product['signup_enabled'],
        'invite_request_enabled': product['invite_request_enabled'],
        'email_verification_enabled': product['email_verification_enabled'],
        'invitation_pending': bool(request.session.get('pending_invitation')),
        'terms': terms_context(request),
    }, headers={'Cache-Control': 'no-store'})


@router.get('/health', include_in_schema=False)
def health():
    return {'status':'ok'}
