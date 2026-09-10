"""Workspace selection and onboarding pages; data APIs live in workspaces/routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from ..views import templates
from ..auth.dependencies import require_user, current_user
from ..workspaces.db import transaction
from ..workspaces.services.organizations import memberships

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db=Depends(transaction), user=Depends(require_user)):
    if request.session.get("pending_invitation"):
        return RedirectResponse(
            "/invitations/" + request.session["pending_invitation"], 303
        )
    choices = memberships(db, user)
    selected = request.query_params.get("workspace") or request.session.get(
        "workspace_id"
    )
    workspace = next(
        (w for w in choices if str(w["id"]) == selected),
        choices[0] if choices else None,
    )
    if workspace:
        request.session["workspace_id"] = str(workspace["id"])
    return templates.TemplateResponse(
        "workspace.html",
        {
            "request": request,
            "user": user,
            "csrf_token": request.session.get("csrf", ""),
            "workspaces": choices,
            "workspace": workspace,
            "invitation": None,
        },
    )


@router.get("/workspaces/new", response_class=HTMLResponse)
def onboarding(request: Request, user=Depends(require_user)):
    return templates.TemplateResponse(
        "workspace.html",
        {
            "request": request,
            "user": user,
            "csrf_token": request.session.get("csrf", ""),
            "workspaces": [],
            "workspace": None,
            "invitation": None,
        },
    )


@router.get("/invitations/{token}", name="invitation_page", response_class=HTMLResponse)
def invitation_page(token: str, request: Request):
    if len(token) > 100:
        return RedirectResponse("/dashboard", 303)
    user = current_user(request)
    if not user:
        request.session["pending_invitation"] = token
        return RedirectResponse("/login", 303)
    return templates.TemplateResponse(
        "workspace.html",
        {
            "request": request,
            "user": user,
            "csrf_token": request.session.get("csrf", ""),
            "workspaces": [],
            "workspace": None,
            "invitation": token,
        },
    )


@router.post("/api/invitations/dismiss")
def dismiss(request: Request, user=Depends(require_user)):
    request.session.pop("pending_invitation", None)
    return {"ok": True}
