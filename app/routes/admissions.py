from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import RedirectResponse
from ..auth.dependencies import current_user
from pydantic import BaseModel, ConfigDict, Field

from ..services import admissions
from .executive import require_executive

router = APIRouter()


class InterestInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    country: str = Field(pattern=r'^[A-Z]{2}$')
    usage_type: Literal['INDIVIDUAL', 'ORGANIZATION']


class ReviewInput(BaseModel):
    status: Literal['APPROVED', 'REJECTED']


class InvitationVerifyInput(BaseModel):
    challenge_id: UUID
    code: str = Field(pattern=r'^\d{6}$')


@router.post('/auth/invitation-requests')
def submit_request(payload: InterestInput, request: Request):
    return admissions.request_invitation(payload, str(request.base_url))


@router.post('/auth/invitation-requests/verify')
def verify_request(payload: InvitationVerifyInput, request: Request):
    return admissions.verify_request(payload.challenge_id, payload.code, str(request.base_url))


@router.get('/api/executive/invitation-requests')
def requests(request: Request, status: Literal['PENDING', 'APPROVED', 'REJECTED', 'ALL']='PENDING',
             offset: int=Query(default=0, ge=0), request_id: UUID | None=None, user=Depends(require_executive)):
    admissions.queue_owner_notifications(str(request.base_url))
    return admissions.list_requests(status, offset, request_id)


@router.get('/invitation-review/{request_id}/{decision}')
def review_link(request_id: UUID, decision: Literal['APPROVED', 'REJECTED'], request: Request):
    destination = f'/executive#request={request_id}&decision={decision}'
    request.session['invitation_review_next'] = destination
    return RedirectResponse(destination if current_user(request) else '/login', status_code=303)


@router.patch('/api/executive/invitation-requests/{request_id}')
def review(request_id: UUID, payload: ReviewInput, request: Request, user=Depends(require_executive)):
    return admissions.review_request(request_id, payload.status, user['id'], str(request.url_for('login_page')))


@router.post('/api/executive/invitation-requests/{request_id}/email')
def send_invitation(request_id: UUID, request: Request, user=Depends(require_executive)):
    return admissions.email_approval(request_id, str(request.url_for('login_page')))
