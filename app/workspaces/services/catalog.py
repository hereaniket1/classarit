"""Workspace catalog and enrollment rules, independent of HTTP routing."""

from urllib.parse import urlsplit
from fastapi import HTTPException
from ..access import MANAGERS


def web_url(value):
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and not any(c.isspace() for c in value)
        )
        parsed.port  # Validate malformed ports as part of URL parsing.
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "Enter a complete http or https URL.")
    return value


def location(a, mode, url, venue, space):
    url = web_url(url)
    if venue:
        a.db.get("venues", a.id, venue)
    if space:
        room = a.db.get("venue_spaces", a.id, space)
        if str(room["venue_id"]) != str(venue):
            raise HTTPException(422, "Select a space belonging to the venue.")
    if mode == "ONLINE":
        if not url:
            raise HTTPException(422, "Online sessions need a meeting URL.")
        venue = space = None
    elif mode == "IN_PERSON":
        if not venue:
            raise HTTPException(422, "In-person sessions need a venue.")
        url = None
    elif not venue or not url:
        raise HTTPException(422, "Hybrid sessions need both a venue and meeting URL.")
    return url, venue, space


def teachers(a, ids):
    if a.workspace['workspace_type'] == 'INDIVIDUAL':
        owner = a.db.first(
            "SELECT id FROM {s}.workspace_memberships WHERE workspace_id=:w AND user_id=:u AND status='ACTIVE'",
            w=a.id, u=a.workspace['owner_user_id'],
        )
        if not owner:
            raise HTTPException(409, 'The individual workspace owner is unavailable.')
        if ids and any(str(mid) != str(owner['id']) for mid in ids):
            raise HTTPException(422, 'The owner is the only teacher for an individual account.')
        ids = [owner['id']]
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise HTTPException(422, "Assign at least one teacher.")
    for mid in ids:
        if not a.db.first(
            "SELECT 1 FROM {s}.workspace_memberships m JOIN {s}.membership_roles r ON r.workspace_id=m.workspace_id AND r.membership_id=m.id WHERE m.workspace_id=:w AND m.id=:m AND m.status='ACTIVE' AND r.role='TEACHER'",
            w=a.id,
            m=mid,
        ):
            raise HTTPException(
                422, "Teachers must be active teaching members of this workspace."
            )
    return ids


def _activity_id(a, p):
    if p.activity_id:
        a.db.get("activities", a.id, p.activity_id)
        return p.activity_id
    name = (p.activity_name or "").strip()
    if not name:
        raise HTTPException(422, "Choose or name an activity.")
    row = a.db.first(
        "SELECT id FROM {s}.activities WHERE workspace_id=:w AND lower(btrim(name))=lower(:n)",
        w=a.id,
        n=name,
    )
    return (
        row
        or a.db.insert(
            "activities", workspace_id=a.id, name=name, category=p.category
        )
    )["id"]


def _program_fields(a, p):
    url, venue_id, space_id = location(
        a,
        p.default_delivery_mode,
        p.default_meeting_url,
        p.default_venue_id,
        p.default_space_id,
    )
    fields = p.model_dump(
        exclude={"teacher_ids", "activity_id", "activity_name", "category"}
    )
    fields.update(
        activity_id=_activity_id(a, p),
        default_meeting_url=url,
        default_venue_id=venue_id,
        default_space_id=space_id,
    )
    if p.teaching_format == "ONE_TO_ONE":
        fields["capacity"] = 1
    return fields


def _replace_program_teachers(a, program_id, teacher_ids):
    a.db.execute(
        "DELETE FROM {s}.program_teachers WHERE workspace_id=:w AND program_id=:p",
        w=a.id,
        p=program_id,
    )
    for index, membership_id in enumerate(teacher_ids):
        a.db.execute(
            "INSERT INTO {s}.program_teachers(workspace_id,program_id,membership_id,assignment_type) VALUES (:w,:p,:m,:kind)",
            w=a.id,
            p=program_id,
            m=membership_id,
            kind="LEAD" if index == 0 else "ASSISTANT",
        )


def activity(a, p):
    a.allow(*MANAGERS)
    return a.db.insert("activities", workspace_id=a.id, **p.model_dump())


def venue(a, p):
    a.allow(*MANAGERS)
    names = list(dict.fromkeys(n.strip() for n in p.space_names if n.strip()))
    row = a.db.insert(
        "venues",
        workspace_id=a.id,
        name=p.name,
        address=p.address,
        directions=p.directions,
        map_url=web_url(p.map_url),
    )
    for name in names:
        a.db.insert("venue_spaces", workspace_id=a.id, venue_id=row["id"], name=name)
    return row


def _verified_user_id(a, email):
    email = (email or "").strip().lower()
    if not email:
        return None
    row = a.db.first(
        """SELECT e.app_user_id FROM {s}.user_emails e
        JOIN {s}.app_users u ON u.id=e.app_user_id
        WHERE lower(e.email::text)=:email AND e.verified_at IS NOT NULL
          AND u.status='ACTIVE' ORDER BY e.is_primary DESC LIMIT 1""",
        email=email,
    )
    return row["app_user_id"] if row else None


def _student_link_id(a, email, student_id=None):
    user_id = _verified_user_id(a, email)
    if not user_id:
        return None
    existing = a.db.first(
        """SELECT id FROM {s}.students
        WHERE workspace_id=:w AND linked_user_id=:u
          AND (CAST(:student_id AS uuid) IS NULL OR id<>CAST(:student_id AS uuid))
        LIMIT 1""",
        w=a.id,
        u=user_id,
        student_id=str(student_id) if student_id else None,
    )
    return None if existing else user_id


def student(a, p):
    a.allow(*MANAGERS)
    fields = p.model_dump(
        exclude={"guardian_name", "guardian_email", "guardian_phone"}
    )
    fields["linked_user_id"] = _student_link_id(a, p.email)
    row = a.db.insert(
        "students",
        workspace_id=a.id,
        **fields,
    )
    if p.guardian_name:
        guardian = a.db.insert(
            "guardians",
            workspace_id=a.id,
            full_name=p.guardian_name,
            email=p.guardian_email,
            phone=p.guardian_phone,
            linked_user_id=_verified_user_id(a, p.guardian_email),
        )
        a.db.execute(
            "INSERT INTO {s}.student_guardians(workspace_id,student_id,guardian_id,relationship,is_primary) VALUES (:w,:s,:g,'GUARDIAN',true)",
            w=a.id,
            s=row["id"],
            g=guardian["id"],
        )
    return row


def program(a, p):
    a.allow(*MANAGERS)
    ids = teachers(
        a, p.teacher_ids or ([a.member["id"]] if "TEACHER" in a.roles else [])
    )
    fields = _program_fields(a, p)
    row = a.db.insert("teaching_programs", workspace_id=a.id, status="ACTIVE", **fields)
    _replace_program_teachers(a, row["id"], ids)
    return row


def update_program(a, program_id, p):
    """Update future class defaults without rewriting existing session history."""
    a.allow(*MANAGERS)
    a.program(program_id)
    current_teachers = [
        row["membership_id"]
        for row in a.db.all(
            "SELECT membership_id FROM {s}.program_teachers WHERE workspace_id=:w AND program_id=:p ORDER BY assignment_type DESC,created_at",
            w=a.id,
            p=program_id,
        )
    ]
    teacher_ids = teachers(a, p.teacher_ids if a.workspace['workspace_type'] == 'INDIVIDUAL' else (p.teacher_ids or current_teachers))
    fields = _program_fields(a, p)
    active_enrollments = a.db.first(
        "SELECT count(*) n FROM {s}.enrollments WHERE workspace_id=:w AND program_id=:p AND status IN ('ACTIVE','PAUSED')",
        w=a.id,
        p=program_id,
    )["n"]
    if p.program_kind == "EVENT" and active_enrollments:
        raise HTTPException(
            409, "End active enrollments before changing this class to an event."
        )
    if fields["capacity"] < active_enrollments:
        raise HTTPException(
            409,
            f"Capacity cannot be below the {active_enrollments} active enrollments.",
        )
    a.db.execute(
        "UPDATE {s}.teaching_programs SET "
        + ",".join(f"{key}=:{key}" for key in fields)
        + " WHERE workspace_id=:w AND id=:id",
        w=a.id,
        id=program_id,
        **fields,
    )
    _replace_program_teachers(a, program_id, teacher_ids)
    return a.db.get("teaching_programs", a.id, program_id)


def archive_program(a, program_id):
    program = a.program(program_id)
    if not (
        a.roles.intersection({"OWNER", "ADMIN"})
        or "TEACHER" in a.roles
    ):
        raise HTTPException(403, "Only an Owner, Admin or assigned Teacher can delete a class.")
    if program["status"] == "ARCHIVED":
        raise HTTPException(409, "This class has already been deleted.")
    a.db.execute(
        "UPDATE {s}.teaching_programs SET status='ARCHIVED' WHERE workspace_id=:w AND id=:p",
        w=a.id,
        p=program_id,
    )
    a.db.execute(
        "UPDATE {s}.enrollments SET status='CANCELLED' WHERE workspace_id=:w AND program_id=:p AND status IN ('ACTIVE','PAUSED')",
        w=a.id,
        p=program_id,
    )
    cancelled = a.db.execute(
        """UPDATE {s}.class_sessions
        SET status='CANCELLED',cancelled_at=CURRENT_TIMESTAMP,cancellation_reason='Class deleted'
        WHERE workspace_id=:w AND program_id=:p AND status='SCHEDULED' AND starts_at>CURRENT_TIMESTAMP
        RETURNING id""",
        w=a.id,
        p=program_id,
    ).fetchall()
    a.db.execute(
        "UPDATE {s}.recurring_session_series SET status='ARCHIVED' WHERE workspace_id=:w AND program_id=:p AND status='ACTIVE'",
        w=a.id,
        p=program_id,
    )
    return {"ok": True, "cancelled_session_ids": [str(row[0]) for row in cancelled]}


def archive_venue(a, venue_id):
    a.allow("OWNER", "ADMIN")
    venue = a.db.get("venues", a.id, venue_id)
    if venue.get("archived_at"):
        raise HTTPException(409, "This venue has already been deleted.")
    if a.db.first(
        "SELECT 1 FROM {s}.teaching_programs WHERE workspace_id=:w AND default_venue_id=:v AND status='ACTIVE' LIMIT 1",
        w=a.id,
        v=venue_id,
    ):
        raise HTTPException(409, "Change the venue on active classes before deleting it.")
    if a.db.first(
        "SELECT 1 FROM {s}.class_sessions WHERE workspace_id=:w AND venue_id=:v AND status='SCHEDULED' AND starts_at>CURRENT_TIMESTAMP LIMIT 1",
        w=a.id,
        v=venue_id,
    ):
        raise HTTPException(409, "Move or cancel upcoming schedules at this venue first.")
    a.db.execute(
        "UPDATE {s}.venues SET archived_at=CURRENT_TIMESTAMP WHERE workspace_id=:w AND id=:v",
        w=a.id,
        v=venue_id,
    )
    a.db.execute(
        "UPDATE {s}.venue_spaces SET archived_at=CURRENT_TIMESTAMP WHERE workspace_id=:w AND venue_id=:v",
        w=a.id,
        v=venue_id,
    )
    return {"ok": True}


def archive_student(a, student_id):
    a.allow("OWNER", "ADMIN")
    student = a.db.get("students", a.id, student_id)
    if student["status"] == "ARCHIVED":
        raise HTTPException(409, "This student has already been deleted.")
    session_ids = [
        str(row["session_id"])
        for row in a.db.all(
            """SELECT DISTINCT p.session_id FROM {s}.session_participants p
            JOIN {s}.class_sessions ss ON ss.workspace_id=p.workspace_id AND ss.id=p.session_id
            WHERE p.workspace_id=:w AND p.student_id=:st AND p.status='BOOKED'
              AND ss.status='SCHEDULED' AND ss.starts_at>CURRENT_TIMESTAMP""",
            w=a.id,
            st=student_id,
        )
    ]
    a.db.execute(
        "UPDATE {s}.students SET status='ARCHIVED' WHERE workspace_id=:w AND id=:st",
        w=a.id,
        st=student_id,
    )
    a.db.execute(
        "UPDATE {s}.enrollments SET status='CANCELLED' WHERE workspace_id=:w AND student_id=:st AND status IN ('ACTIVE','PAUSED')",
        w=a.id,
        st=student_id,
    )
    a.db.execute(
        """UPDATE {s}.session_participants p SET status='CANCELLED'
        FROM {s}.class_sessions ss
        WHERE p.workspace_id=:w AND p.student_id=:st AND p.status='BOOKED'
          AND ss.workspace_id=p.workspace_id AND ss.id=p.session_id
          AND ss.status='SCHEDULED' AND ss.starts_at>CURRENT_TIMESTAMP""",
        w=a.id,
        st=student_id,
    )
    a.db.execute(
        "UPDATE {s}.makeup_entitlements SET status='WAIVED' WHERE workspace_id=:w AND student_id=:st AND status='OPEN'",
        w=a.id,
        st=student_id,
    )
    return {"ok": True, "session_ids": session_ids}


def enroll(a, pid, p):
    from .scheduling import add_participant

    a.allow(*MANAGERS)
    prog = a.program(pid)
    if prog["program_kind"] != "COURSE":
        raise HTTPException(422, "Events use session bookings rather than enrollments.")
    st = a.db.get("students", a.id, p.student_id)
    if st["status"] != "ACTIVE":
        raise HTTPException(409, "Student is archived.")
    if p.ends_on and p.ends_on < p.starts_on:
        raise HTTPException(422, "End date must follow start date.")
    count = a.db.first(
        "SELECT count(*) n FROM {s}.enrollments WHERE workspace_id=:w AND program_id=:p AND status IN ('ACTIVE','PAUSED')",
        w=a.id,
        p=pid,
    )["n"]
    if count >= prog["capacity"]:
        raise HTTPException(409, "This class is full.")
    row = a.db.insert(
        "enrollments", workspace_id=a.id, program_id=pid, **p.model_dump()
    )
    sessions = a.db.all(
        "SELECT * FROM {s}.class_sessions WHERE workspace_id=:w AND program_id=:p AND status='SCHEDULED' AND starts_at>CURRENT_TIMESTAMP AND (starts_at AT TIME ZONE :tz)::date>=:start AND (CAST(:finish AS date) IS NULL OR (starts_at AT TIME ZONE :tz)::date<=CAST(:finish AS date))",
        w=a.id,
        p=pid,
        tz=a.workspace["timezone"],
        start=p.starts_on,
        finish=p.ends_on,
    )
    for session in sessions:
        add_participant(a, session, p.student_id, "ENROLLMENT", row["id"])
    return row


def update_student(a, student_id, p):
    a.allow(*MANAGERS)
    a.db.get("students", a.id, student_id)
    fields = p.model_dump(exclude={"guardian_name", "guardian_email", "guardian_phone"})
    fields["linked_user_id"] = _student_link_id(a, p.email, student_id)
    a.db.execute(
        "UPDATE {s}.students SET "
        + ",".join(f"{k}=:{k}" for k in fields)
        + " WHERE workspace_id=:w AND id=:id",
        w=a.id,
        id=student_id,
        **fields,
    )
    guardian = a.db.first(
        "SELECT guardian_id FROM {s}.student_guardians WHERE workspace_id=:w AND student_id=:st AND is_primary",
        w=a.id,
        st=student_id,
    )
    if p.guardian_name:
        if guardian:
            a.db.execute(
                "UPDATE {s}.guardians SET full_name=:n,email=:e,phone=:p,linked_user_id=:u WHERE workspace_id=:w AND id=:id",
                n=p.guardian_name,
                e=p.guardian_email,
                p=p.guardian_phone,
                u=_verified_user_id(a, p.guardian_email),
                w=a.id,
                id=guardian["guardian_id"],
            )
        else:
            row = a.db.insert(
                "guardians",
                workspace_id=a.id,
                full_name=p.guardian_name,
                email=p.guardian_email,
                phone=p.guardian_phone,
                linked_user_id=_verified_user_id(a, p.guardian_email),
            )
            a.db.execute(
                "INSERT INTO {s}.student_guardians(workspace_id,student_id,guardian_id,relationship,is_primary) VALUES (:w,:st,:g,'GUARDIAN',true)",
                w=a.id,
                st=student_id,
                g=row["id"],
            )
    return a.db.get("students", a.id, student_id)


def end_enrollment(a, eid):
    a.allow(*MANAGERS)
    enrollment = a.db.get("enrollments", a.id, eid)
    if enrollment["status"] not in ("ACTIVE", "PAUSED"):
        raise HTTPException(409, "Enrollment has already ended.")
    a.db.execute(
        "UPDATE {s}.enrollments SET status='CANCELLED' WHERE workspace_id=:w AND id=:id",
        w=a.id,
        id=eid,
    )
    # Keep past attendance, missed-lesson credits and separate makeup bookings intact.
    a.db.execute(
        "UPDATE {s}.session_participants p SET status='CANCELLED' FROM {s}.class_sessions s WHERE p.workspace_id=:w AND s.workspace_id=p.workspace_id AND s.id=p.session_id AND p.enrollment_id=:e AND s.status='SCHEDULED' AND s.starts_at>CURRENT_TIMESTAMP",
        w=a.id,
        e=eid,
    )
    return {"ok": True}


def assign_teachers(a, pid, p):
    a.allow(*MANAGERS)
    a.program(pid)
    ids = teachers(a, p.teacher_ids)
    _replace_program_teachers(a, pid, ids)
    return {
        "ok": True,
        "detail": "Defaults updated. Existing session assignments are unchanged.",
    }
