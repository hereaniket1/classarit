"""Account overview, explicit workspace navigation and invitation entry pages."""

from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from ..views import templates
from ..auth.dependencies import require_user, require_dashboard_user, current_user
from ..workspaces.db import transaction
from ..workspaces.access import access, MANAGERS
from ..workspaces.services.organizations import memberships
from ..workspaces.services.overview import dashboard_data

router = APIRouter()


class DefaultWorkspaceInput(BaseModel):
    workspace_id: UUID



def context(request, user, **extra):
    return {
        "request": request,
        "user": user,
        "csrf_token": request.session.get("csrf", ""),
        "workspaces": [],
        "workspace": None,
        "invitation": None,
        **extra,
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request, user=Depends(require_dashboard_user), db=Depends(transaction)
):
    if user["user_type"] == "APPOWNER":
        return templates.TemplateResponse(
            "account_dashboard.html", context(request, user, appowner=True)
        )
    if request.session.get("pending_invitation"):
        return RedirectResponse(
            "/invitations/" + request.session["pending_invitation"], 303
        )
    # Old explicit links remain valid; a remembered workspace never selects itself.
    selected = request.query_params.get("workspace")
    if selected:
        try:
            selected = UUID(selected)
        except ValueError:
            raise HTTPException(404, "Workspace not found.")
        return RedirectResponse(f"/workspaces/{selected}", 303)
    choices = memberships(db, user)
    wants_overview = request.query_params.get("overview") in {"1", "true", "yes"}
    if not wants_overview:
        default_workspace_id = user.get("default_workspace_id")
        if default_workspace_id and any(str(choice["id"]) == str(default_workspace_id) for choice in choices):
            return RedirectResponse(f"/workspaces/{default_workspace_id}", 303)
        if default_workspace_id:
            db.execute("UPDATE {s}.app_users SET default_workspace_id=NULL WHERE id=:u", u=user["id"])
        if len(choices) == 1:
            return RedirectResponse(f"/workspaces/{choices[0]['id']}", 303)
    return templates.TemplateResponse(
        "account_dashboard.html",
        context(request, user, appowner=False, **dashboard_data(db, user)),
    )


@router.get("/workspaces/new", response_class=HTMLResponse)
def onboarding(request: Request, user=Depends(require_user), db=Depends(transaction)):
    choices = memberships(db, user)
    if user["user_type"] != "OWNER" and db.first(
        "SELECT 1 FROM {s}.workspace_memberships WHERE user_id=:u", u=user["id"]
    ):
        raise HTTPException(
            403, "Invited staff accounts can only access their assigned workspaces."
        )
    return templates.TemplateResponse(
        "workspace.html", context(request, user, teacher_only=False)
    )


@router.get("/workspaces/{workspace_id}", response_class=HTMLResponse)
def workspace_page(request: Request, a=Depends(access)):
    teacher_only = not bool(a.roles & MANAGERS)
    return templates.TemplateResponse(
        "workspace.html",
        context(
            request,
            a.user,
            workspace=a.workspace,
            workspaces=memberships(a.db, a.user),
            teacher_only=teacher_only,
            owner_view="OWNER" in a.roles,
        ),
    )


@router.get("/invitations/{token}", name="invitation_page", response_class=HTMLResponse)
def invitation_page(token: str, request: Request):
    if len(token) > 100:
        return RedirectResponse("/dashboard", 303)
    user = current_user(request)
    if not user:
        request.session["pending_invitation"] = token
        return RedirectResponse("/login", 303)
    if user["user_type"] == "APPOWNER":
        return RedirectResponse("/dashboard", 303)
    return templates.TemplateResponse(
        "workspace.html", context(request, user, invitation=token, teacher_only=True)
    )


@router.post("/api/invitations/dismiss")
def dismiss(request: Request, user=Depends(require_user)):
    request.session.pop("pending_invitation", None)
    return {"ok": True}


@router.post("/api/account/default-workspace")
def set_default_workspace(payload: DefaultWorkspaceInput, user=Depends(require_user), db=Depends(transaction)):
    row = db.first(
        """SELECT 1 FROM {s}.workspaces w
        JOIN {s}.workspace_memberships m ON m.workspace_id=w.id
        WHERE w.id=:w AND w.status='ACTIVE' AND m.user_id=:u AND m.status='ACTIVE'""",
        w=payload.workspace_id,
        u=user["id"],
    )
    if not row:
        raise HTTPException(404, "Workspace not found or access is unavailable.")
    db.execute(
        "UPDATE {s}.app_users SET default_workspace_id=:w WHERE id=:u",
        w=payload.workspace_id,
        u=user["id"],
    )
    return {"ok": True, "default_workspace_id": str(payload.workspace_id)}
