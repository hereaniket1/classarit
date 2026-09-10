from uuid import UUID
from fastapi import APIRouter, Depends, Request, HTTPException
from ...auth.dependencies import require_user
from ..db import transaction
from ..access import access
from ..schemas import WorkspaceInput, InviteInput, MemberInput, PolicyInput
from ..services import organizations, queries, makeups

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
