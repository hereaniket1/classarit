import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

INSTITUTE_STAFF_ROLES = {"ADMIN", "OPERATOR", "TEACHER"}
INDIVIDUAL_STAFF_ROLES = {"TEACHER"}
BUSINESS_FIELDS = {
    "business_legal_name",
    "business_gstin",
    "owner_aadhaar_number",
    "business_address_line1",
    "business_address_line2",
    "business_city",
    "business_state",
    "business_postal_code",
    "business_country",
}
REQUIRED_BUSINESS_FIELDS = {
    "business_legal_name",
    "business_gstin",
    "owner_aadhaar_number",
    "business_address_line1",
    "business_city",
    "business_state",
    "business_postal_code",
    "business_country",
}


def business_profile_complete(profile):
    return bool(profile) and all(str(profile.get(key) or '').strip() for key in (
        'legal_name', 'gstin', 'owner_aadhaar_number', 'address_line1', 'city', 'state', 'postal_code', 'country'))


def saved_business_summary(db, user_id):
    row = db.first("SELECT * FROM {s}.business_profiles WHERE owner_user_id=:u AND status='ACTIVE'", u=user_id)
    return {'legal_name': row['legal_name']} if business_profile_complete(row) else None


def staff_roles_for(workspace):
    return (
        INDIVIDUAL_STAFF_ROLES
        if workspace["workspace_type"] == "INDIVIDUAL"
        else INSTITUTE_STAFF_ROLES
    )


def validate_staff_roles(workspace, roles):
    roles = set(roles)
    allowed = staff_roles_for(workspace)
    invalid = roles - allowed
    if invalid:
        if workspace["workspace_type"] == "INDIVIDUAL":
            raise HTTPException(
                422,
                "Individual practices only use Teacher as an operational staff role.",
            )
        raise HTTPException(422, "Choose valid staff roles for this workspace.")
    if len(roles) != 1:
        raise HTTPException(
            422, "Choose exactly one role: Admin, Operator or Teacher."
        )


def _ensure_teacher_reassignable(a, member_id):
    if a.db.first(
        """SELECT 1 FROM {s}.program_teachers pt
        WHERE pt.workspace_id=:w AND pt.membership_id=:m
          AND EXISTS (SELECT 1 FROM {s}.teaching_programs p WHERE p.workspace_id=pt.workspace_id AND p.id=pt.program_id AND p.status='ACTIVE')
          AND NOT EXISTS (
            SELECT 1 FROM {s}.program_teachers other
            JOIN {s}.workspace_memberships om ON om.workspace_id=other.workspace_id AND om.id=other.membership_id AND om.status='ACTIVE'
            JOIN {s}.membership_roles role ON role.workspace_id=om.workspace_id AND role.membership_id=om.id AND role.role='TEACHER'
            WHERE other.workspace_id=pt.workspace_id AND other.program_id=pt.program_id AND other.membership_id<>pt.membership_id
          ) LIMIT 1""",
        w=a.id,
        m=member_id,
    ):
        raise HTTPException(
            409, "Assign another teacher to this member's active classes first."
        )
    if a.db.first(
        """SELECT 1 FROM {s}.session_teachers st
        JOIN {s}.class_sessions s ON s.workspace_id=st.workspace_id AND s.id=st.session_id
        WHERE st.workspace_id=:w AND st.membership_id=:m
          AND s.status='SCHEDULED' AND s.starts_at>CURRENT_TIMESTAMP
          AND NOT EXISTS (
            SELECT 1 FROM {s}.session_teachers other
            JOIN {s}.workspace_memberships om ON om.workspace_id=other.workspace_id AND om.id=other.membership_id AND om.status='ACTIVE'
            JOIN {s}.membership_roles role ON role.workspace_id=om.workspace_id AND role.membership_id=om.id AND role.role='TEACHER'
            WHERE other.workspace_id=st.workspace_id AND other.session_id=st.session_id AND other.membership_id<>st.membership_id
          ) LIMIT 1""",
        w=a.id,
        m=member_id,
    ):
        raise HTTPException(
            409, "Assign another teacher to this member's upcoming schedules first."
        )


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


def _business_profile(db, user_id, payload):
    existing = db.first(
        "SELECT * FROM {s}.business_profiles WHERE owner_user_id=:u AND status='ACTIVE' FOR UPDATE", u=user_id,
    )
    if business_profile_complete(existing):
        # Workspace creation reuses identity; it must never overwrite a shared profile.
        return existing
    data = payload.model_dump()
    missing = [
        field
        for field in REQUIRED_BUSINESS_FIELDS
        if not str(data.get(field) or "").strip()
    ]
    if missing:
        raise HTTPException(
            422,
            "Company setup needs a business ID, owner government ID and address.",
        )
    fields = {field: data.get(field) for field in BUSINESS_FIELDS}
    if existing:
        db.execute('''UPDATE {s}.business_profiles SET legal_name=:business_legal_name,
            gstin=:business_gstin,owner_aadhaar_number=:owner_aadhaar_number,
            address_line1=:business_address_line1,address_line2=:business_address_line2,
            city=:business_city,state=:business_state,postal_code=:business_postal_code,
            country=:business_country WHERE id=:id''', id=existing['id'], **fields)
        return existing
    return db.insert(
        "business_profiles",
        owner_user_id=user_id,
        legal_name=fields["business_legal_name"],
        gstin=fields["business_gstin"],
        owner_aadhaar_number=fields["owner_aadhaar_number"],
        address_line1=fields["business_address_line1"],
        address_line2=fields["business_address_line2"],
        city=fields["business_city"],
        state=fields["business_state"],
        postal_code=fields["business_postal_code"],
        country=fields["business_country"],
    )


def create_workspace(db, user, payload):
    account = db.first(
        "SELECT user_type,account_type FROM {s}.app_users WHERE id=:u FOR UPDATE", u=user["id"]
    )
    if account["user_type"] == "APPOWNER":
        raise HTTPException(403, "APPOWNER cannot own or join a workspace.")
    if account["user_type"] == "MEMBER" and has_active_staff_membership(db, user["id"]):
        raise HTTPException(
            409,
            "Ask the current workspace owner or admin to deactivate this staff profile before using the same email as an owner.",
        )
    data = payload.model_dump()
    requested_type = 'INDIVIDUAL' if payload.workspace_type == 'INDIVIDUAL' else 'ORGANIZATION'
    if account.get('account_type') and account['account_type'] != requested_type:
        raise HTTPException(409, 'Choose a workspace that matches your account type.')
    existing_types = db.all('SELECT DISTINCT workspace_type FROM {s}.workspaces WHERE owner_user_id=:u AND status=\'ACTIVE\'', u=user['id'])
    if any(row['workspace_type'] != payload.workspace_type for row in existing_types):
        raise HTTPException(409, 'Your existing workspaces use a different account type. Contact support before changing it.')
    business_profile_id = None
    if payload.workspace_type == "INDIVIDUAL":
        if db.first(
            """SELECT 1 FROM {s}.workspaces
            WHERE owner_user_id=:u AND workspace_type='INDIVIDUAL' AND status='ACTIVE'
            LIMIT 1""",
            u=user["id"],
        ):
            raise HTTPException(
                409,
                "Independent teachers can have one active individual workspace.",
            )
    else:
        count = db.first("SELECT count(*) AS total FROM {s}.workspaces WHERE owner_user_id=:u AND workspace_type='INSTITUTE' AND status='ACTIVE'", u=user['id'])
        if count['total'] >= 3:
            raise HTTPException(409, 'Organizations can have up to three active workspaces during early access.')
        business_profile_id = _business_profile(db, user["id"], payload)["id"]
    db.execute('UPDATE {s}.app_users SET account_type=COALESCE(account_type,:kind) WHERE id=:u', kind=requested_type, u=user['id'])
    db.execute("UPDATE {s}.app_users SET user_type='OWNER' WHERE id=:u", u=user["id"])
    workspace = db.insert(
        "workspaces",
        **{k: v for k, v in data.items() if k not in BUSINESS_FIELDS},
        created_by=user["id"],
        owner_user_id=user["id"],
        business_profile_id=business_profile_id,
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
        if new_roles - {"TEACHER"}:
            raise HTTPException(422, "An Owner may additionally be a Teacher only.")
        if a.workspace["workspace_type"] == "INDIVIDUAL" and "TEACHER" not in new_roles:
            raise HTTPException(
                409, "An individual practice owner must remain a Teacher."
            )
        new_roles.add("OWNER")
    elif not new_roles:
        raise HTTPException(422, "Choose at least one staff role.")
    else:
        validate_staff_roles(a.workspace, new_roles)
    if "TEACHER" in old_roles and "TEACHER" not in new_roles:
        _ensure_teacher_reassignable(a, member_id)
        a.db.execute(
            "DELETE FROM {s}.program_teachers WHERE workspace_id=:w AND membership_id=:m",
            w=a.id,
            m=member_id,
        )
        a.db.execute(
            """DELETE FROM {s}.session_teachers st USING {s}.class_sessions s
            WHERE st.workspace_id=:w AND st.membership_id=:m
              AND s.workspace_id=st.workspace_id AND s.id=st.session_id
              AND s.status='SCHEDULED' AND s.starts_at>CURRENT_TIMESTAMP""",
            w=a.id,
            m=member_id,
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


def remove_member(a, member_id):
    a.allow("OWNER", "ADMIN")
    member = a.db.get("workspace_memberships", a.id, member_id)
    roles = {
        row["role"]
        for row in a.db.all(
            "SELECT role FROM {s}.membership_roles WHERE workspace_id=:w AND membership_id=:m",
            w=a.id,
            m=member_id,
        )
    }
    if "OWNER" in roles:
        raise HTTPException(409, "The workspace Owner cannot be removed.")
    if member["status"] != "ACTIVE":
        raise HTTPException(409, "This member is already inactive.")
    if "TEACHER" in roles:
        _ensure_teacher_reassignable(a, member_id)
        a.db.execute(
            "DELETE FROM {s}.program_teachers WHERE workspace_id=:w AND membership_id=:m",
            w=a.id,
            m=member_id,
        )
        a.db.execute(
            """DELETE FROM {s}.session_teachers st USING {s}.class_sessions s
            WHERE st.workspace_id=:w AND st.membership_id=:m
              AND s.workspace_id=st.workspace_id AND s.id=st.session_id
              AND s.status='SCHEDULED' AND s.starts_at>CURRENT_TIMESTAMP""",
            w=a.id,
            m=member_id,
        )
    a.db.execute(
        "UPDATE {s}.workspace_memberships SET status='LEFT' WHERE workspace_id=:w AND id=:m",
        w=a.id,
        m=member_id,
    )
    return {"ok": True}


def update_workspace(a, payload):
    a.allow("OWNER")
    fields = payload.model_dump()
    a.db.execute(
        "UPDATE {s}.workspaces SET name=:name,timezone=:timezone,currency=:currency WHERE id=:w",
        w=a.id,
        **fields,
    )
    return a.db.first("SELECT * FROM {s}.workspaces WHERE id=:w", w=a.id)


def delete_workspace(a, payload):
    """Permanently remove one workspace and its tenant-scoped records."""
    a.allow("OWNER")
    if payload.confirmation.strip() != a.workspace["name"]:
        raise HTTPException(422, "Type the workspace name exactly to confirm deletion.")
    owner_id = a.workspace["owner_user_id"]
    a.db.execute(
        "UPDATE {s}.app_users SET default_workspace_id=NULL WHERE default_workspace_id=:w",
        w=a.id,
    )
    tables = [
        "makeup_bookings",
        "makeup_entitlements",
        "attendance",
        "session_participants",
        "session_teachers",
        "class_sessions",
        "recurring_session_series",
        "enrollments",
        "student_guardians",
        "guardians",
        "students",
        "program_teachers",
        "teaching_programs",
        "venue_spaces",
        "venues",
        "activities",
        "makeup_policies",
        "workspace_invitations",
        "membership_roles",
        "workspace_memberships",
    ]
    for table in tables:
        a.db.execute(f"DELETE FROM {{s}}.{table} WHERE workspace_id=:w", w=a.id)
    a.db.execute("DELETE FROM {s}.workspaces WHERE id=:w", w=a.id)
    if not a.db.first(
        "SELECT 1 FROM {s}.workspaces WHERE owner_user_id=:u", u=owner_id
    ):
        a.db.execute(
            "UPDATE {s}.app_users SET user_type='MEMBER',default_workspace_id=NULL WHERE id=:u",
            u=owner_id,
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
