"""Account overview, explicit workspace navigation and invitation entry pages."""

from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from ..views import templates
from ..auth.dependencies import require_user, require_dashboard_user, current_user
from ..workspaces.db import transaction
from ..workspaces.access import access, MANAGERS
from ..workspaces.services.organizations import memberships, saved_business_summary
from ..workspaces.services.overview import dashboard_data
from ..services.product_settings import setting_enabled

router = APIRouter()


class DefaultWorkspaceInput(BaseModel):
    workspace_id: UUID


ROLE_PRIORITY = ("OWNER", "ADMIN", "OPERATOR", "TEACHER", "STUDENT")


def role_label(db, user, choices=None):
    choices = choices if choices is not None else memberships(db, user)
    roles = {role for choice in choices for role in (choice.get("roles") or [])}
    if not roles.intersection(ROLE_PRIORITY[:4]) and db.first(
        "SELECT 1 FROM {s}.students WHERE linked_user_id=:u AND status='ACTIVE' LIMIT 1",
        u=user["id"],
    ):
        roles.add("STUDENT")
    return next(
        (role for role in ROLE_PRIORITY if role in roles),
        user.get("user_type") or "MEMBER",
    )



def context(request, user, **extra):
    return {
        "request": request,
        "user": user,
        "csrf_token": request.session.get("csrf", ""),
        "workspaces": [],
        "workspace": None,
        "invitation": None,
        "display_role": user.get("user_type") or "MEMBER",
        "executive_access": (user.get("email") or "").lower()
        == "aniketpathak1@gmail.com",
        **extra,
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request, user=Depends(require_dashboard_user), db=Depends(transaction)
):
    if request.session.get("google_profile_required"):
        return RedirectResponse("/auth/google/profile", 303)
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
        context(
            request,
            user,
            appowner=False,
            display_role=role_label(db, user, choices),
            **dashboard_data(db, user, choices=choices),
        ),
    )


@router.get("/profile", response_class=HTMLResponse)
def profile(
    request: Request,
    user=Depends(require_dashboard_user),
    db=Depends(transaction),
):
    choices = [] if user.get("user_type") == "APPOWNER" else memberships(db, user)
    return templates.TemplateResponse(
        "profile.html",
        context(
            request,
            user,
            display_role=role_label(db, user, choices),
            email_verification_enabled=setting_enabled(
                "email_verification_enabled", True
            ),
        ),
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
        "workspace.html",
        context(
            request,
            user,
            teacher_only=False,
            business_profile=saved_business_summary(db, user['id']),
            account_type=user.get('account_type') or next(('INDIVIDUAL' if item['workspace_type']=='INDIVIDUAL' else 'ORGANIZATION' for item in choices if item.get('owner_user_id') and str(item['owner_user_id']) == str(user['id'])), None),
            display_role=role_label(db, user, choices),
        ),
    )


@router.get("/workspaces/{workspace_id}", response_class=HTMLResponse)
def workspace_page(request: Request, a=Depends(access)):
    teacher_only = not bool(a.roles & MANAGERS)
    account_type = a.user.get("account_type") or (
        "INDIVIDUAL"
        if a.workspace.get("workspace_type") == "INDIVIDUAL"
        else "ORGANIZATION"
    )
    return templates.TemplateResponse(
        "workspace.html",
        context(
            request,
            a.user,
            workspace=a.workspace,
            workspaces=memberships(a.db, a.user),
            organization_account=account_type == "ORGANIZATION",
            teacher_only=teacher_only,
            owner_view="OWNER" in a.roles,
            display_role=next(
                (role for role in ROLE_PRIORITY if role in a.roles), "MEMBER"
            ),
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
