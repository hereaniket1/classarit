"""Session timing, resource conflicts, roster capacity, and attendance."""

import calendar
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from ..access import MANAGERS
from .catalog import location, teachers



WEEKDAY_INDEX = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}
MAX_RECURRING_OCCURRENCES = 200


def add_months(day, months):
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return day.replace(day=min(day.day, calendar.monthrange(year, month)[1]), month=month, year=year)


def recurring_dates(start_date, repeat_months, repeat_weekdays):
    selected = {WEEKDAY_INDEX[day] for day in dict.fromkeys(repeat_weekdays)}
    until = add_months(start_date, repeat_months) - timedelta(days=1)
    day = start_date
    dates = []
    while day <= until:
        if day.weekday() in selected:
            dates.append(day)
            if len(dates) > MAX_RECURRING_OCCURRENCES:
                raise HTTPException(
                    422,
                    f"Create {MAX_RECURRING_OCCURRENCES} or fewer sessions at a time. Reduce the repeat months or selected days.",
                )
        day += timedelta(days=1)
    if not dates:
        raise HTTPException(422, "Choose at least one repeat day on or after the start date.")
    return dates

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


def add_direct_participants(a, session, student_ids, kind):
    for student_id in list(dict.fromkeys(student_ids or [])):
        existing = a.db.first(
            "SELECT * FROM {s}.session_participants WHERE workspace_id=:w AND session_id=:s AND student_id=:st",
            w=a.id,
            s=session["id"],
            st=student_id,
        )
        if existing and existing["status"] == "BOOKED":
            continue
        add_participant(a, session, student_id, kind)


def roster_student_ids(a, program_id, day, selected_student_ids):
    student_ids = {
        row["student_id"]
        for row in a.db.all(
            "SELECT student_id FROM {s}.enrollments WHERE workspace_id=:w AND program_id=:p AND status='ACTIVE' AND starts_on<=:day AND (ends_on IS NULL OR ends_on>=:day)",
            w=a.id,
            p=program_id,
            day=day,
        )
    }
    for student_id in selected_student_ids or []:
        student_ids.add(student_id)
    return student_ids


def validate_roster_capacity(a, prog, start, capacity, selected_student_ids):
    day = start.astimezone(ZoneInfo(a.workspace["timezone"])).date()
    total = len(roster_student_ids(a, prog["id"], day, selected_student_ids))
    if total > capacity:
        raise HTTPException(
            409,
            f"This schedule has {capacity} seat{'s' if capacity != 1 else ''}, but {total} students would be booked. Increase seats or choose fewer students.",
        )


def session_defaults(a, p):
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
    return prog, ids, start, end, mode, url, vid, space, capacity


def create(a, p):
    a.allow(*MANAGERS)
    prog, ids, start, end, mode, url, vid, space, capacity = session_defaults(a, p)
    validate_roster_capacity(a, prog, start, capacity, getattr(p, "student_ids", []))
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
        recurring_series_id=getattr(p, "recurring_series_id", None),
        series_original_starts_at=getattr(p, "series_original_starts_at", None),
        edited_from_series=getattr(p, "edited_from_series", False),
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
    direct_kind = "EVENT" if prog["program_kind"] == "EVENT" else "DIRECT"
    add_direct_participants(a, row, getattr(p, "student_ids", []), direct_kind)
    return row

def create_recurring(a, p):
    a.allow(*MANAGERS)
    if p.start_time.tzinfo is not None:
        raise HTTPException(422, "Use a local start time without a timezone offset.")
    dates = recurring_dates(p.start_date, p.repeat_months, p.repeat_weekdays)
    first_start = datetime.combine(dates[0], p.start_time)
    duration = p.duration_minutes
    preview = SimpleNamespace(
        program_id=p.program_id,
        title=p.title,
        starts_at=first_start,
        ends_at=first_start + timedelta(minutes=duration) if duration else None,
        delivery_mode=p.delivery_mode,
        meeting_url=p.meeting_url,
        venue_id=p.venue_id,
        space_id=p.space_id,
        capacity=p.capacity,
        teacher_ids=p.teacher_ids,
    )
    prog, ids, start, end, mode, url, vid, space, capacity = session_defaults(a, preview)
    duration_minutes = int((end - start).total_seconds() // 60)
    repeat_weekdays = list(dict.fromkeys(p.repeat_weekdays))
    for day in dates:
        validate_roster_capacity(
            a,
            prog,
            instant(a, datetime.combine(day, p.start_time)),
            capacity,
            p.student_ids,
        )
    series = a.db.insert(
        "recurring_session_series",
        workspace_id=a.id,
        program_id=prog["id"],
        title=p.title or prog["name"],
        start_date=p.start_date,
        start_time=p.start_time,
        duration_minutes=duration_minutes,
        repeat_weekdays=repeat_weekdays,
        repeat_months=p.repeat_months,
        delivery_mode=mode,
        meeting_url=url,
        venue_id=vid,
        space_id=space,
        capacity=capacity,
        created_by_membership_id=a.member["id"],
    )
    rows = []
    for day in dates:
        original_start = instant(a, datetime.combine(day, p.start_time))
        rows.append(
            create(
                a,
                SimpleNamespace(
                    program_id=prog["id"],
                    title=p.title,
                    starts_at=datetime.combine(day, p.start_time),
                    ends_at=datetime.combine(day, p.start_time) + timedelta(minutes=duration_minutes),
                    delivery_mode=mode,
                    meeting_url=url,
                    venue_id=vid,
                    space_id=space,
                    capacity=capacity,
                    teacher_ids=ids,
                    student_ids=p.student_ids,
                    recurring_series_id=series["id"],
                    series_original_starts_at=original_start,
                    edited_from_series=False,
                ),
            )
        )
    return {"count": len(rows), "series": series, "sessions": rows}

def disable_recurring_series(a, series_id):
    a.allow(*MANAGERS)
    series = a.db.get("recurring_session_series", a.id, series_id)
    if series["status"] != "ACTIVE":
        return {"ok": True, "cancelled_count": 0, "series": series}
    result = a.db.execute(
        """UPDATE {s}.class_sessions
        SET status='CANCELLED',cancelled_at=CURRENT_TIMESTAMP,cancellation_reason='Recurring schedule disabled'
        WHERE workspace_id=:w
          AND recurring_series_id=:series
          AND edited_from_series=false
          AND status='SCHEDULED'
          AND starts_at>CURRENT_TIMESTAMP
        RETURNING id""",
        w=a.id,
        series=series_id,
    )
    cancelled_count = len(result.fetchall())
    updated = a.db.first(
        "UPDATE {s}.recurring_session_series SET status='ARCHIVED' WHERE workspace_id=:w AND id=:id RETURNING *",
        w=a.id,
        id=series_id,
    )
    return {"ok": True, "cancelled_count": cancelled_count, "series": updated}


def update_recurring_series(a, series_id, p):
    a.allow(*MANAGERS)
    series = a.db.get("recurring_session_series", a.id, series_id)
    program = a.program(series["program_id"])
    title = p.title or program["name"]
    updated = a.db.first(
        "UPDATE {s}.recurring_session_series SET title=:title WHERE workspace_id=:w AND id=:id RETURNING *",
        title=title,
        w=a.id,
        id=series_id,
    )
    a.db.execute(
        """UPDATE {s}.class_sessions
        SET title=:title
        WHERE workspace_id=:w
          AND recurring_series_id=:series
          AND edited_from_series=false
          AND status='SCHEDULED'
          AND starts_at>CURRENT_TIMESTAMP""",
        title=title,
        w=a.id,
        series=series_id,
    )
    return updated


def restore_recurring_series(a, series_id):
    a.allow(*MANAGERS)
    series = a.db.get("recurring_session_series", a.id, series_id)
    updated = a.db.first(
        "UPDATE {s}.recurring_session_series SET status='ACTIVE' WHERE workspace_id=:w AND id=:id RETURNING *",
        w=a.id,
        id=series_id,
    )
    result = a.db.execute(
        """UPDATE {s}.class_sessions
        SET status='SCHEDULED', cancelled_at=NULL, cancellation_reason=NULL
        WHERE workspace_id=:w
          AND recurring_series_id=:series
          AND edited_from_series=false
          AND status='CANCELLED'
          AND cancellation_reason='Recurring schedule disabled'
          AND starts_at>CURRENT_TIMESTAMP
        RETURNING id""",
        w=a.id,
        series=series_id,
    )
    restored_count = len(result.fetchall())
    return {"ok": True, "restored_count": restored_count, "series": updated}


def reschedule(a, sid, p):
    a.allow(*MANAGERS)
    row = a.session(sid)
    if row["status"] != "SCHEDULED" or row["starts_at"] <= datetime.now(timezone.utc):
        raise HTTPException(409, "Only future scheduled sessions can be rescheduled.")
    start, end = timing(a, p.starts_at, p.ends_at)
    url, vid, space = location(
        a, p.delivery_mode, p.meeting_url, p.venue_id, p.space_id
    )
    edited_from_series = bool(row.get("recurring_series_id"))
    title = row.get("title") or "Session"
    if edited_from_series and not row.get("edited_from_series") and not title.endswith(" - Edited"):
        title = f"{title} - Edited"
    row.update(
        title=title,
        starts_at=start,
        ends_at=end,
        delivery_mode=p.delivery_mode,
        meeting_url=url,
        venue_id=vid,
        space_id=space,
        edited_from_series=edited_from_series or row.get("edited_from_series", False),
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
        """UPDATE {s}.class_sessions
        SET title=:title,starts_at=:start,ends_at=:end,delivery_mode=:mode,meeting_url=:url,venue_id=:v,space_id=:sp,
            edited_from_series=:edited,series_edited_at=CASE WHEN :edited THEN CURRENT_TIMESTAMP ELSE series_edited_at END
        WHERE id=:id""",
        title=title,
        start=start,
        end=end,
        mode=p.delivery_mode,
        url=url,
        v=vid,
        sp=space,
        edited=row["edited_from_series"],
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
