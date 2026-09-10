import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException


def memberships(db, user):
    return db.all(
        """SELECT w.*,m.id AS membership_id, array_agg(r.role ORDER BY r.role) AS roles
        FROM {s}.workspaces w JOIN {s}.workspace_memberships m ON m.workspace_id=w.id
        JOIN {s}.membership_roles r ON r.membership_id=m.id AND r.workspace_id=w.id
        WHERE m.user_id=:u AND m.status='ACTIVE' AND w.status='ACTIVE'
        GROUP BY w.id,m.id ORDER BY w.created_at""",
        u=user["id"],
    )


def create_workspace(db, user, payload):
    workspace = db.insert("workspaces", **payload.model_dump(), created_by=user["id"])
    member = db.insert(
        "workspace_memberships", workspace_id=workspace["id"], user_id=user["id"]
    )
    for role in ("OWNER", "TEACHER"):
        db.execute(
            "INSERT INTO {s}.membership_roles(workspace_id,membership_id,role) VALUES (:w,:m,:r)",
            w=workspace["id"],
            m=member["id"],
            r=role,
        )
    db.execute(
        "INSERT INTO {s}.makeup_policies(workspace_id,validity_days) VALUES (:w,30)",
        w=workspace["id"],
    )
    return workspace


def invite(a, payload):
    a.allow("OWNER", "ADMIN")
    email = payload.email.lower()
    # Expire old records before the partial unique constraint is checked.
    a.db.execute(
        "UPDATE {s}.workspace_invitations SET status='EXPIRED' WHERE workspace_id=:w AND status='PENDING' AND expires_at<=CURRENT_TIMESTAMP",
        w=a.id,
    )
    if a.db.first(
        "SELECT 1 FROM {s}.workspace_memberships m JOIN {s}.user_emails e ON e.app_user_id=m.user_id WHERE m.workspace_id=:w AND lower(e.email::text)=:e AND m.status='ACTIVE'",
        w=a.id,
        e=email,
    ):
        raise HTTPException(409, "This person is already an active member.")
    token = secrets.token_urlsafe(32)
    row = a.db.insert(
        "workspace_invitations",
        workspace_id=a.id,
        email=email,
        invited_by_membership_id=a.member["id"],
        proposed_roles=sorted(set(payload.roles)),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    return {"id": row["id"], "token": token, "email": email}


def accept_invite(db, user, token):
    hashed = hashlib.sha256(token.encode()).hexdigest()
    invitation = db.first(
        "SELECT * FROM {s}.workspace_invitations WHERE token_hash=:h", h=hashed
    )
    if not invitation:
        raise HTTPException(404, "Invitation not found.")
    # Same lock order as member administration: workspace, then invitation.
    workspace = db.first(
        "SELECT * FROM {s}.workspaces WHERE id=:w AND status='ACTIVE' FOR UPDATE",
        w=invitation["workspace_id"],
    )
    invitation = db.first(
        "SELECT * FROM {s}.workspace_invitations WHERE id=:id FOR UPDATE",
        id=invitation["id"],
    )
    if (
        not workspace
        or invitation["status"] != "PENDING"
        or invitation["expires_at"] <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            409, "This invitation has expired or is no longer available."
        )
    if not db.first(
        "SELECT 1 FROM {s}.user_emails WHERE app_user_id=:u AND lower(email::text)=:e AND verified_at IS NOT NULL",
        u=user["id"],
        e=invitation["email"],
    ):
        raise HTTPException(
            403, "Sign in with the verified email address this invitation was sent to."
        )
    member = db.first(
        "SELECT * FROM {s}.workspace_memberships WHERE workspace_id=:w AND user_id=:u",
        w=workspace["id"],
        u=user["id"],
    )
    if member:
        if member["status"] != "ACTIVE":
            raise HTTPException(403, "Ask an administrator to restore your membership.")
        # A stale invitation must not overwrite or escalate an existing membership.
    else:
        member = db.insert(
            "workspace_memberships", workspace_id=workspace["id"], user_id=user["id"]
        )
        for role in invitation["proposed_roles"]:
            db.execute(
                "INSERT INTO {s}.membership_roles(workspace_id,membership_id,role) VALUES (:w,:m,:r)",
                w=workspace["id"],
                m=member["id"],
                r=role,
            )
    db.execute(
        "UPDATE {s}.workspace_invitations SET status='ACCEPTED',accepted_by=:u,accepted_at=CURRENT_TIMESTAMP WHERE id=:id",
        u=user["id"],
        id=invitation["id"],
    )
    return {"workspace_id": workspace["id"]}


def update_member(a, member_id, payload):
    a.allow("OWNER", "ADMIN")
    member = a.db.get("workspace_memberships", a.id, member_id)
    old_roles = {
        r["role"]
        for r in a.db.all(
            "SELECT role FROM {s}.membership_roles WHERE workspace_id=:w AND membership_id=:m",
            w=a.id,
            m=member_id,
        )
    }
    new_roles = set(payload.roles)
    if "OWNER" in old_roles | new_roles and "OWNER" not in a.roles:
        raise HTTPException(403, "Only an owner can change ownership.")
    if (
        "OWNER" in old_roles
        and member["status"] == "ACTIVE"
        and ("OWNER" not in new_roles or payload.status != "ACTIVE")
    ):
        owners = a.db.first(
            "SELECT count(*) AS n FROM {s}.workspace_memberships m JOIN {s}.membership_roles r ON r.membership_id=m.id AND r.workspace_id=m.workspace_id WHERE m.workspace_id=:w AND m.status='ACTIVE' AND r.role='OWNER'",
            w=a.id,
        )["n"]
        if owners <= 1:
            raise HTTPException(
                409, "Add another active owner before removing the last owner."
            )
    a.db.execute(
        "UPDATE {s}.workspace_memberships SET status=:status WHERE id=:id AND workspace_id=:w",
        status=payload.status,
        id=member_id,
        w=a.id,
    )
    a.db.execute(
        "DELETE FROM {s}.membership_roles WHERE workspace_id=:w AND membership_id=:m",
        w=a.id,
        m=member_id,
    )
    for role in new_roles:
        a.db.execute(
            "INSERT INTO {s}.membership_roles(workspace_id,membership_id,role) VALUES (:w,:m,:r)",
            w=a.id,
            m=member_id,
            r=role,
        )
    return {"ok": True}
