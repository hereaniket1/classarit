import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

INSTITUTE_STAFF_ROLES = {"ADMIN", "OPERATOR", "TEACHER"}
INDIVIDUAL_STAFF_ROLES = {"TEACHER"}


def staff_roles_for(workspace):
    return (
        INDIVIDUAL_STAFF_ROLES
        if workspace["workspace_type"] == "INDIVIDUAL"
        else INSTITUTE_STAFF_ROLES
    )


def validate_staff_roles(workspace, roles):
    allowed = staff_roles_for(workspace)
    invalid = set(roles) - allowed
    if invalid:
        if workspace["workspace_type"] == "INDIVIDUAL":
            raise HTTPException(
                422,
                "Individual practices only use Teacher as an operational staff role.",
            )
        raise HTTPException(422, "Choose valid staff roles for this workspace.")


def memberships(db, user):
    return db.all(
        """SELECT w.*,m.id AS membership_id, array_agg(r.role ORDER BY r.role) AS roles,
            bool_or(w.id=u.default_workspace_id) AS is_default
        FROM {s}.workspaces w JOIN {s}.workspace_memberships m ON m.workspace_id=w.id
        JOIN {s}.membership_roles r ON r.membership_id=m.id AND r.workspace_id=w.id
        JOIN {s}.app_users u ON u.id=m.user_id
        WHERE m.user_id=:u AND m.status='ACTIVE' AND w.status='ACTIVE'
        GROUP BY w.id,m.id ORDER BY w.created_at""",
        u=user["id"],
    )


def has_active_staff_membership(db, user_id):
    return db.first(
        """SELECT 1 FROM {s}.workspace_memberships m
        WHERE m.user_id=:u AND m.status='ACTIVE'
        AND NOT EXISTS (
            SELECT 1 FROM {s}.membership_roles r
            WHERE r.workspace_id=m.workspace_id AND r.membership_id=m.id AND r.role='OWNER'
        )
        LIMIT 1""",
        u=user_id,
    )


def create_workspace(db, user, payload):
    account = db.first(
        "SELECT user_type FROM {s}.app_users WHERE id=:u FOR UPDATE", u=user["id"]
    )
    if account["user_type"] == "APPOWNER":
        raise HTTPException(403, "APPOWNER cannot own or join a workspace.")
    if account["user_type"] == "MEMBER" and has_active_staff_membership(db, user["id"]):
        raise HTTPException(
            409,
            "Ask the current workspace owner or admin to deactivate this staff profile before using the same email as an owner.",
        )
    db.execute("UPDATE {s}.app_users SET user_type='OWNER' WHERE id=:u", u=user["id"])
    workspace = db.insert(
        "workspaces",
        **payload.model_dump(),
        created_by=user["id"],
        owner_user_id=user["id"]
    )
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
    db.execute(
        "UPDATE {s}.app_users SET default_workspace_id=COALESCE(default_workspace_id,:w) WHERE id=:u",
        w=workspace["id"],
        u=user["id"],
    )
    return workspace


def invite(a, payload):
    a.allow("OWNER", "ADMIN")
    validate_staff_roles(a.workspace, payload.roles)
    email = payload.email.lower()
    account = a.db.first(
        "SELECT u.user_type FROM {s}.user_emails e JOIN {s}.app_users u ON u.id=e.app_user_id WHERE lower(e.email::text)=:e",
        e=email,
    )
    if account and account["user_type"] in {"APPOWNER", "OWNER"}:
        raise HTTPException(
            409,
            "Use a different email for staff access. OWNER and APPOWNER accounts cannot receive staff invitations.",
        )
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
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
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
    account = db.first(
        "SELECT user_type FROM {s}.app_users WHERE id=:u FOR UPDATE", u=user["id"]
    )
    if account["user_type"] in {"OWNER", "APPOWNER"}:
        raise HTTPException(
            409,
            "Use a separate email for staff access. Owner and product-owner accounts cannot accept staff invitations.",
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
    db.execute(
        "UPDATE {s}.app_users SET default_workspace_id=COALESCE(default_workspace_id,:w) WHERE id=:u",
        w=workspace["id"],
        u=user["id"],
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
    if not old_roles:
        raise HTTPException(404, "Record not found in this workspace.")
    if "OWNER" in new_roles:
        raise HTTPException(
            409,
            "OWNER is managed by the workspace ownership flow, not staff-role editing.",
        )
    if "OWNER" in old_roles:
        if "OWNER" not in a.roles:
            raise HTTPException(
                403, "Only the owner can change their operational roles."
            )
        if payload.status != "ACTIVE":
            raise HTTPException(
                409, "The subscription owner cannot be removed or suspended."
            )
        validate_staff_roles(a.workspace, new_roles)
        if a.workspace["workspace_type"] == "INDIVIDUAL" and "TEACHER" not in new_roles:
            raise HTTPException(
                409, "An individual practice owner must remain a Teacher."
            )
        new_roles.add("OWNER")
    elif not new_roles:
        raise HTTPException(422, "Choose at least one staff role.")
    else:
        validate_staff_roles(a.workspace, new_roles)
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


def member_contact(a, member_id):
    return a.db.first(
        """SELECT m.id,m.status,u.full_name,e.email,array_agg(r.role ORDER BY r.role) AS roles
        FROM {s}.workspace_memberships m
        JOIN {s}.app_users u ON u.id=m.user_id
        LEFT JOIN {s}.user_emails e ON e.app_user_id=u.id AND e.is_primary=true
        LEFT JOIN {s}.membership_roles r ON r.workspace_id=m.workspace_id AND r.membership_id=m.id
        WHERE m.workspace_id=:w AND m.id=:m
        GROUP BY m.id,u.full_name,e.email""",
        w=a.id,
        m=member_id,
    )
