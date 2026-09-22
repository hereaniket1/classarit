"""CTO/CEO executive dashboard for product controls and performance."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import SQLAlchemyError

from ..auth.dependencies import require_dashboard_user
from ..services import maintenance, telemetry
from ..services.product_settings import all_settings, set_settings
from ..views import templates

router = APIRouter()
EXECUTIVE_EMAILS = {"aniketpathak1@gmail.com"}


class ExecutiveSettingsInput(BaseModel):
    google_new_accounts_enabled: bool | None = None
    signup_enabled: bool | None = None
    email_verification_enabled: bool | None = None
    notification_emails_enabled: bool | None = None


class ExecutiveFlushInput(BaseModel):
    confirmation: str


def require_executive(user=Depends(require_dashboard_user)):
    if (user.get("email") or "").lower() not in EXECUTIVE_EMAILS:
        raise HTTPException(403, "This dashboard is restricted.")
    return user


def context(request, user, **extra):
    return {"request": request, "user": user, "csrf_token": request.session.get("csrf", ""), **extra}


@router.get("/executive", response_class=HTMLResponse)
def executive_page(request: Request, user=Depends(require_executive)):
    return templates.TemplateResponse("executive_dashboard.html", context(request, user))


@router.get("/api/executive/dashboard")
def executive_data(user=Depends(require_executive)):
    try:
        return {
            "settings": all_settings(),
            "registrations": telemetry.registration_stats(),
            "api": telemetry.executive_metrics(),
        }
    except SQLAlchemyError:
        raise HTTPException(503, "Executive tables are not ready. Apply migration 008.") from None


@router.patch("/api/executive/settings")
def executive_settings(payload: ExecutiveSettingsInput, user=Depends(require_executive)):
    try:
        updates = {key: value for key, value in payload.model_dump().items() if value is not None}
        return {"settings": set_settings(updates, user["id"])}
    except SQLAlchemyError:
        raise HTTPException(503, "Executive settings are not ready. Apply migration 008.") from None


@router.post("/api/executive/flush-data")
def executive_flush_data(
    payload: ExecutiveFlushInput,
    request: Request,
    user=Depends(require_executive),
):
    if payload.confirmation != "DELETE ALL DATA":
        raise HTTPException(422, "Type DELETE ALL DATA to confirm.")
    try:
        result = maintenance.flush_application_data()
        request.session.clear()
        return {"ok": True, **result}
    except SQLAlchemyError:
        raise HTTPException(503, "Could not flush data. Check database readiness.") from None


@router.delete("/api/executive/terms-acceptances")
def executive_delete_terms_acceptances(
    payload: ExecutiveFlushInput,
    user=Depends(require_executive),
):
    if payload.confirmation != "DELETE TERMS AUDIT":
        raise HTTPException(422, "Type DELETE TERMS AUDIT to confirm.")
    try:
        return {"ok": True, **maintenance.delete_terms_acceptance_audit()}
    except SQLAlchemyError:
        raise HTTPException(503, "Could not delete terms audit records.") from None
