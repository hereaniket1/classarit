from dataclasses import dataclass
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from ..auth.dependencies import require_user
from .db import Store, transaction

MANAGERS = {"OWNER", "ADMIN", "OPERATOR"}


@dataclass
class Access:
    db: Store
    workspace: dict
    member: dict
    roles: set
    user: dict

    @property
    def id(self):
        return self.workspace["id"]

    def allow(self, *roles):
        if not self.roles.intersection(roles):
            raise HTTPException(403, "Your role does not allow this action.")

    def program(self, program_id):
        program = self.db.get("teaching_programs", self.id, program_id)
        if not self.roles.intersection(MANAGERS) and not self.db.first(
            "SELECT 1 FROM {s}.program_teachers WHERE workspace_id=:w AND program_id=:p AND membership_id=:m",
            w=self.id,
            p=program_id,
            m=self.member["id"],
        ):
            raise HTTPException(403, "This class is not assigned to you.")
        return program

    def session(self, session_id):
        session = self.db.get("class_sessions", self.id, session_id)
        if not self.roles.intersection(MANAGERS) and not self.db.first(
            "SELECT 1 FROM {s}.session_teachers WHERE workspace_id=:w AND session_id=:s AND membership_id=:m",
            w=self.id,
            s=session_id,
            m=self.member["id"],
        ):
            raise HTTPException(403, "This session is not assigned to you.")
        return session


def access(
    workspace_id: UUID,
    request: Request,
    db: Store = Depends(transaction),
    user=Depends(require_user),
):
    # Serialize mutations within one workspace to protect capacity, conflicts and owners.
    lock = " FOR UPDATE" if request.method not in ("GET", "HEAD", "OPTIONS") else ""
    workspace = db.first(
        "SELECT * FROM {s}.workspaces WHERE id=:w" + lock, w=workspace_id
    )
    member = db.first(
        "SELECT * FROM {s}.workspace_memberships WHERE workspace_id=:w AND user_id=:u AND status='ACTIVE'",
        w=workspace_id,
        u=user["id"],
    )
    if not workspace or workspace["status"] != "ACTIVE" or not member:
        raise HTTPException(404, "Workspace not found or access is unavailable.")
    roles = {
        r["role"]
        for r in db.all(
            "SELECT role FROM {s}.membership_roles WHERE workspace_id=:w AND membership_id=:m",
            w=workspace_id,
            m=member["id"],
        )
    }
    return Access(db, workspace, member, roles, user)
