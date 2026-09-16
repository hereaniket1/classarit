from uuid import UUID
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from ...auth.dependencies import require_user
from ..db import transaction
from ..access import access
from ..schemas import WorkspaceInput, InviteInput, MemberInput, PolicyInput
from ..services import organizations, queries, makeups, overview

router = APIRouter(prefix="/api")


@router.get("/workspaces")
def listing(db=Depends(transaction), user=Depends(require_user)):
    return organizations.memberships(db, user)


@router.post("/workspaces", status_code=201)
def create(p: WorkspaceInput, db=Depends(transaction), user=Depends(require_user)):
    return organizations.create_workspace(db, user, p)


@router.post("/invitations/{token}/accept")
def accept(
    token: str, request: Request, db=Depends(transaction), user=Depends(require_user)
):
    result = organizations.accept_invite(db, user, token)
    request.session.pop("pending_invitation", None)
    return result


@router.get("/workspaces/{workspace_id}/snapshot")
def snapshot(a=Depends(access)):
    return queries.snapshot(a)


@router.get("/workspaces/{workspace_id}/calendar")
def calendar(month: str = Query(pattern=r"^\d{4}-\d{2}$"), a=Depends(access)):
    return queries.calendar_month(a, month)


@router.get("/workspaces/{workspace_id}/section/{section}")
def workspace_section(
    section: str,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    history: bool = False,
    a=Depends(access),
):
    return queries.section(a, section, month, history=history)


@router.post("/workspaces/{workspace_id}/invitations", status_code=201)
def invite(p: InviteInput, request: Request, a=Depends(access)):
    result = organizations.invite(a, p)
    result["url"] = str(request.url_for("invitation_page", token=result.pop("token")))
    return result


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}")
def revoke(invitation_id: UUID, a=Depends(access)):
    a.allow("OWNER", "ADMIN")
    a.db.get("workspace_invitations", a.id, invitation_id)
    a.db.execute(
        "UPDATE {s}.workspace_invitations SET status='REVOKED' WHERE workspace_id=:w AND id=:id AND status='PENDING'",
        w=a.id,
        id=invitation_id,
    )
    return {"ok": True}


@router.patch("/workspaces/{workspace_id}/members/{member_id}")
def member(member_id: UUID, p: MemberInput, a=Depends(access)):
    return organizations.update_member(a, member_id, p)


@router.put("/workspaces/{workspace_id}/makeup-policy")
def policy(p: PolicyInput, a=Depends(access)):
    return makeups.policy(a, p)


@router.get("/dashboard/overview")
def account_overview(user=Depends(require_user), db=Depends(transaction)):
    return overview.dashboard_data(db, user)
