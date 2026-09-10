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


def student(a, p):
    a.allow(*MANAGERS)
    row = a.db.insert(
        "students",
        workspace_id=a.id,
        **p.model_dump(exclude={"guardian_name", "guardian_email", "guardian_phone"}),
    )
    if p.guardian_name:
        guardian = a.db.insert(
            "guardians",
            workspace_id=a.id,
            full_name=p.guardian_name,
            email=p.guardian_email,
            phone=p.guardian_phone,
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
    aid = p.activity_id
    if aid:
        a.db.get("activities", a.id, aid)
    else:
        name = (p.activity_name or "").strip()
        if not name:
            raise HTTPException(422, "Choose or name an activity.")
        row = a.db.first(
            "SELECT id FROM {s}.activities WHERE workspace_id=:w AND lower(btrim(name))=lower(:n)",
            w=a.id,
            n=name,
        )
        aid = (
            row
            or a.db.insert(
                "activities", workspace_id=a.id, name=name, category=p.category
            )
        )["id"]
    ids = teachers(
        a, p.teacher_ids or ([a.member["id"]] if "TEACHER" in a.roles else [])
    )
    url, vid, sid = location(
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
        activity_id=aid,
        default_meeting_url=url,
        default_venue_id=vid,
        default_space_id=sid,
    )
    if p.teaching_format == "ONE_TO_ONE":
        fields["capacity"] = 1
    row = a.db.insert("teaching_programs", workspace_id=a.id, status="ACTIVE", **fields)
    for i, mid in enumerate(ids):
        a.db.execute(
            "INSERT INTO {s}.program_teachers(workspace_id,program_id,membership_id,assignment_type) VALUES (:w,:p,:m,:t)",
            w=a.id,
            p=row["id"],
            m=mid,
            t="LEAD" if i == 0 else "ASSISTANT",
        )
    return row


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
                "UPDATE {s}.guardians SET full_name=:n,email=:e,phone=:p WHERE workspace_id=:w AND id=:id",
                n=p.guardian_name,
                e=p.guardian_email,
                p=p.guardian_phone,
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
    a.db.execute(
        "DELETE FROM {s}.program_teachers WHERE workspace_id=:w AND program_id=:p",
        w=a.id,
        p=pid,
    )
    for index, mid in enumerate(ids):
        a.db.execute(
            "INSERT INTO {s}.program_teachers(workspace_id,program_id,membership_id,assignment_type) VALUES (:w,:p,:m,:kind)",
            w=a.id,
            p=pid,
            m=mid,
            kind="LEAD" if index == 0 else "ASSISTANT",
        )
    return {
        "ok": True,
        "detail": "Defaults updated. Existing session assignments are unchanged.",
    }
