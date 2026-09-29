from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query
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


@router.post('/auth/invitation-requests')
def submit_request(payload: InterestInput):
    return admissions.request_invitation(payload)


@router.get('/api/executive/invitation-requests')
def requests(status: Literal['PENDING', 'APPROVED', 'REJECTED', 'ALL']='PENDING',
             offset: int=Query(default=0, ge=0), user=Depends(require_executive)):
    return admissions.list_requests(status, offset)


@router.patch('/api/executive/invitation-requests/{request_id}')
def review(request_id: UUID, payload: ReviewInput, user=Depends(require_executive)):
    return admissions.review_request(request_id, payload.status, user['id'])


@router.post('/api/executive/invitation-requests/{request_id}/email')
def send_invitation(request_id: UUID, request: Request, user=Depends(require_executive)):
    return admissions.email_approval(request_id, str(request.url_for('login_page')))
