"""Session timing, resource conflicts, roster capacity, and attendance."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from ..access import MANAGERS
from .catalog import location, teachers


def instant(a, value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(a.workspace["timezone"]))
        if value.astimezone(timezone.utc).astimezone(value.tzinfo).replace(
            tzinfo=None
        ) != value.replace(tzinfo=None):
            raise HTTPException(
                422, "This local time does not exist due to daylight saving time."
            )
        if value.utcoffset() != value.replace(fold=1).utcoffset():
            raise HTTPException(
                422, "This time is ambiguous. Supply an explicit UTC offset."
            )
    return value.astimezone(timezone.utc)


def timing(a, start, end):
    start, end = instant(a, start), instant(a, end)
    if end <= start:
        raise HTTPException(422, "End time must follow start time.")
    if start <= datetime.now(timezone.utc):
        raise HTTPException(422, "Choose a future session time.")
    return start, end


def conflicts(a, session, teacher_ids=(), student_ids=()):
    others = a.db.all(
        "SELECT * FROM {s}.class_sessions WHERE workspace_id=:w AND status='SCHEDULED' AND starts_at<:end AND ends_at>:start AND id<>:id",
        w=a.id,
        start=session["starts_at"],
        end=session["ends_at"],
        id=session["id"],
    )
    for other in others:
        if (
            session.get("venue_id")
            and str(other["venue_id"]) == str(session["venue_id"])
            and (
                not other["space_id"]
                or not session.get("space_id")
                or str(other["space_id"]) == str(session["space_id"])
            )
        ):
            raise HTTPException(
                409, "The venue or space is already booked at this time."
            )
        assigned = {
            str(r["membership_id"])
            for r in a.db.all(
                "SELECT membership_id FROM {s}.session_teachers WHERE workspace_id=:w AND session_id=:s",
                w=a.id,
                s=other["id"],
            )
        }
        if assigned.intersection(map(str, teacher_ids)):
            raise HTTPException(409, "A teacher has an overlapping session.")
        booked = {
            str(r["student_id"])
            for r in a.db.all(
                "SELECT student_id FROM {s}.session_participants WHERE workspace_id=:w AND session_id=:s AND status='BOOKED'",
                w=a.id,
                s=other["id"],
            )
        }
        if booked.intersection(map(str, student_ids)):
            raise HTTPException(409, "A student has an overlapping session.")


def add_participant(a, session, student_id, kind, enrollment_id=None):
    student = a.db.get("students", a.id, student_id)
    if student["status"] != "ACTIVE":
        raise HTTPException(409, "Student is archived.")
    if session["status"] != "SCHEDULED" or session["starts_at"] <= datetime.now(
        timezone.utc
    ):
        raise HTTPException(409, "Only future scheduled sessions accept bookings.")
    old = a.db.first(
        "SELECT * FROM {s}.session_participants WHERE workspace_id=:w AND session_id=:s AND student_id=:st",
        w=a.id,
        s=session["id"],
        st=student_id,
    )
    if old and old["status"] == "BOOKED":
        raise HTTPException(409, "Student is already booked into this session.")
    count = a.db.first(
        "SELECT count(*) n FROM {s}.session_participants WHERE workspace_id=:w AND session_id=:s AND status='BOOKED'",
        w=a.id,
        s=session["id"],
    )["n"]
    if count >= session["capacity"]:
        raise HTTPException(409, "This session is full.")
    conflicts(a, session, student_ids=[student_id])
    if old:
        return dict(
            a.db.execute(
                "UPDATE {s}.session_participants SET status='BOOKED',participation_kind=:kind,enrollment_id=:e WHERE id=:id RETURNING *",
                kind=kind,
                e=enrollment_id,
                id=old["id"],
            )
            .mappings()
            .one()
        )
    return a.db.insert(
        "session_participants",
        workspace_id=a.id,
        program_id=session["program_id"],
        session_id=session["id"],
        student_id=student_id,
        enrollment_id=enrollment_id,
        participation_kind=kind,
    )


def create(a, p):
    a.allow(*MANAGERS)
    prog = a.program(p.program_id)
    ids = teachers(
        a,
        (
            p.teacher_ids
            if p.teacher_ids is not None
            else [
                r["membership_id"]
                for r in a.db.all(
                    "SELECT membership_id FROM {s}.program_teachers WHERE workspace_id=:w AND program_id=:p",
                    w=a.id,
                    p=prog["id"],
                )
            ]
        ),
    )
    start = instant(a, p.starts_at)
    start, end = timing(
        a,
        start,
        p.ends_at or start + timedelta(minutes=prog["default_duration_minutes"]),
    )
    mode = p.delivery_mode or prog["default_delivery_mode"]
    url, vid, space = location(
        a,
        mode,
        p.meeting_url or prog["default_meeting_url"],
        p.venue_id or prog["default_venue_id"],
        p.space_id or prog["default_space_id"],
    )
    capacity = p.capacity or prog["capacity"]
    if prog["teaching_format"] == "ONE_TO_ONE" and capacity != 1:
        raise HTTPException(422, "One-to-one sessions have one seat.")
    row = a.db.insert(
        "class_sessions",
        workspace_id=a.id,
        program_id=prog["id"],
        title=p.title or prog["name"],
        starts_at=start,
        ends_at=end,
        session_kind="EVENT" if prog["program_kind"] == "EVENT" else "REGULAR",
        delivery_mode=mode,
        meeting_url=url,
        venue_id=vid,
        space_id=space,
        capacity=capacity,
    )
    conflicts(a, row, teacher_ids=ids)
    for mid in ids:
        a.db.execute(
            "INSERT INTO {s}.session_teachers(workspace_id,session_id,membership_id) VALUES (:w,:s,:m)",
            w=a.id,
            s=row["id"],
            m=mid,
        )
    day = start.astimezone(ZoneInfo(a.workspace["timezone"])).date()
    for en in a.db.all(
        "SELECT * FROM {s}.enrollments WHERE workspace_id=:w AND program_id=:p AND status='ACTIVE' AND starts_on<=:day AND (ends_on IS NULL OR ends_on>=:day)",
        w=a.id,
        p=prog["id"],
        day=day,
    ):
        add_participant(a, row, en["student_id"], "ENROLLMENT", en["id"])
    return row


def reschedule(a, sid, p):
    a.allow(*MANAGERS)
    row = a.session(sid)
    if row["status"] != "SCHEDULED" or row["starts_at"] <= datetime.now(timezone.utc):
        raise HTTPException(409, "Only future scheduled sessions can be rescheduled.")
    start, end = timing(a, p.starts_at, p.ends_at)
    url, vid, space = location(
        a, p.delivery_mode, p.meeting_url, p.venue_id, p.space_id
    )
    row.update(
        starts_at=start,
        ends_at=end,
        delivery_mode=p.delivery_mode,
        meeting_url=url,
        venue_id=vid,
        space_id=space,
    )
    mids = [
        r["membership_id"]
        for r in a.db.all(
            "SELECT membership_id FROM {s}.session_teachers WHERE workspace_id=:w AND session_id=:s",
            w=a.id,
            s=sid,
        )
    ]
    students = [
        r["student_id"]
        for r in a.db.all(
            "SELECT student_id FROM {s}.session_participants WHERE workspace_id=:w AND session_id=:s AND status='BOOKED'",
            w=a.id,
            s=sid,
        )
    ]
    teachers(a, mids)
    if a.db.first(
        """SELECT 1 FROM {s}.makeup_bookings b
        JOIN {s}.makeup_entitlements e ON e.workspace_id=b.workspace_id AND e.id=b.entitlement_id
        JOIN {s}.session_participants p ON p.workspace_id=b.workspace_id AND p.id=b.replacement_participant_id
        WHERE b.workspace_id=:w AND p.session_id=:s AND b.status='BOOKED' AND e.expires_at<:start""",
        w=a.id,
        s=sid,
        start=start,
    ):
        raise HTTPException(
            409,
            "The new time is after a booked makeup credit expires. Release that booking first.",
        )
    conflicts(a, row, mids, students)
    a.db.execute(
        "UPDATE {s}.class_sessions SET starts_at=:start,ends_at=:end,delivery_mode=:mode,meeting_url=:url,venue_id=:v,space_id=:sp WHERE id=:id",
        start=start,
        end=end,
        mode=p.delivery_mode,
        url=url,
        v=vid,
        sp=space,
        id=sid,
    )
    return row


def book_event(a, sid, p):
    a.allow(*MANAGERS)
    session = a.session(sid)
    prog = a.program(session["program_id"])
    if prog["program_kind"] != "EVENT":
        raise HTTPException(
            422, "Enroll the student in this class, or book a makeup credit."
        )
    return add_participant(a, session, p.student_id, "EVENT")


def attendance(a, pid, p):
    row = a.db.get("session_participants", a.id, pid)
    session = a.session(row["session_id"])
    if row["status"] != "BOOKED" or session["status"] == "CANCELLED":
        raise HTTPException(409, "Cancelled bookings cannot have attendance.")
    if session["starts_at"] > datetime.now(timezone.utc):
        raise HTTPException(409, "Attendance opens when the session starts.")
    booking = a.db.first(
        "SELECT * FROM {s}.makeup_bookings WHERE workspace_id=:w AND replacement_participant_id=:p AND status IN ('BOOKED','FULFILLED')",
        w=a.id,
        p=pid,
    )
    if (
        not booking
        and a.db.first(
            "SELECT 1 FROM {s}.makeup_bookings WHERE workspace_id=:w AND replacement_participant_id=:p AND status='NO_SHOW'",
            w=a.id,
            p=pid,
        )
        and p.status in ("PRESENT", "LATE")
    ):
        raise HTTPException(
            409,
            "A no-show makeup needs administrative correction before attendance can be changed to present.",
        )
    if (
        booking
        and booking["status"] == "FULFILLED"
        and p.status not in ("PRESENT", "LATE")
    ):
        raise HTTPException(409, "A fulfilled makeup cannot be reversed here.")
    a.db.execute(
        "INSERT INTO {s}.attendance(workspace_id,participant_id,status,marked_by_membership_id,notes) VALUES (:w,:p,:status,:m,:notes) ON CONFLICT(workspace_id,participant_id) DO UPDATE SET status=EXCLUDED.status,marked_by_membership_id=EXCLUDED.marked_by_membership_id,notes=EXCLUDED.notes,marked_at=CURRENT_TIMESTAMP",
        w=a.id,
        p=pid,
        status=p.status,
        m=a.member["id"],
        notes=p.notes,
    )
    if booking and booking["status"] == "BOOKED":
        fulfilled = p.status in ("PRESENT", "LATE")
        a.db.execute(
            "UPDATE {s}.makeup_bookings SET status=:status,fulfilled_at=:at WHERE id=:id",
            status="FULFILLED" if fulfilled else "NO_SHOW",
            at=datetime.now(timezone.utc) if fulfilled else None,
            id=booking["id"],
        )
        if fulfilled:
            a.db.execute(
                "UPDATE {s}.makeup_entitlements SET status='FULFILLED' WHERE id=:id",
                id=booking["entitlement_id"],
            )
    return {"ok": True}
