"""One entitlement per missed booking; replacement attendance consumes it."""

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from ..access import MANAGERS
from .scheduling import add_participant


def grant(a, p):
    a.allow(*MANAGERS)
    policy = a.db.first(
        "SELECT * FROM {s}.makeup_policies WHERE workspace_id=:w", w=a.id
    )
    now = datetime.now(timezone.utc)
    results = []
    for pid in set(p.participant_ids):
        participant = a.db.get("session_participants", a.id, pid)
        session = a.session(participant["session_id"])
        if participant["participation_kind"] == "MAKEUP":
            raise HTTPException(
                409,
                "Release the existing makeup booking instead of granting another credit.",
            )
        if participant["status"] != "BOOKED":
            raise HTTPException(409, "Only booked participants are eligible.")
        if p.reason in ("TEACHER_CANCELLED", "VENUE_UNAVAILABLE", "WEATHER"):
            if (
                session["status"] != "CANCELLED"
                or not policy["teacher_cancellation_eligible"]
            ):
                raise HTTPException(
                    409, "Cancel the session first and enable cancellation eligibility."
                )
        elif p.reason == "STUDENT_ABSENT":
            if not policy["student_absence_eligible"]:
                raise HTTPException(
                    409, "Student absence makeups are disabled by policy."
                )
            att = a.db.first(
                "SELECT status FROM {s}.attendance WHERE workspace_id=:w AND participant_id=:p",
                w=a.id,
                p=pid,
            )
            if not att or att["status"] not in ("ABSENT", "EXCUSED"):
                raise HTTPException(409, "Mark the student absent or excused first.")
            if policy["minimum_notice_hours"]:
                raise HTTPException(
                    409,
                    "Notice eligibility needs administrator review. An owner/admin can grant an OTHER exception with a note.",
                )
        else:
            a.allow("OWNER", "ADMIN")
            if not p.reason_notes:
                raise HTTPException(422, "Explain this policy exception.")
        existing = a.db.first(
            "SELECT * FROM {s}.makeup_entitlements WHERE workspace_id=:w AND original_participant_id=:p",
            w=a.id,
            p=pid,
        )
        if existing:
            results.append(existing)
            continue
        expiry = (
            now + timedelta(days=policy["validity_days"])
            if policy["validity_days"]
            else None
        )
        results.append(
            a.db.insert(
                "makeup_entitlements",
                workspace_id=a.id,
                student_id=participant["student_id"],
                original_participant_id=pid,
                reason=p.reason,
                reason_notes=p.reason_notes,
                granted_by_membership_id=a.member["id"],
                expires_at=expiry,
                included_in_original_fee=policy["included_in_original_fee"],
            )
        )
    return results


def book(a, eid, p):
    a.allow(*MANAGERS)
    credit = a.db.get("makeup_entitlements", a.id, eid)
    now = datetime.now(timezone.utc)
    if credit["status"] != "OPEN" or (
        credit["expires_at"] and credit["expires_at"] <= now
    ):
        raise HTTPException(409, "This makeup credit is no longer available.")
    if a.db.first(
        "SELECT 1 FROM {s}.makeup_bookings WHERE workspace_id=:w AND entitlement_id=:e AND status IN ('BOOKED','FULFILLED')",
        w=a.id,
        e=eid,
    ):
        raise HTTPException(409, "This credit already has a replacement booking.")
    original = a.db.get("session_participants", a.id, credit["original_participant_id"])
    target = a.session(p.session_id)
    if target["id"] == original["session_id"]:
        raise HTTPException(422, "Choose a different session.")
    source = a.program(original["program_id"])
    dest = a.program(target["program_id"])
    if source["activity_id"] != dest["activity_id"] or (source["level"] or "") != (
        dest["level"] or ""
    ):
        raise HTTPException(422, "Choose a session with the same activity and level.")
    if credit["expires_at"] and target["starts_at"] > credit["expires_at"]:
        raise HTTPException(409, "The replacement session is after the credit expiry.")
    participant = add_participant(a, target, credit["student_id"], "MAKEUP")
    return a.db.insert(
        "makeup_bookings",
        workspace_id=a.id,
        student_id=credit["student_id"],
        entitlement_id=eid,
        replacement_participant_id=participant["id"],
    )


def release(a, bid):
    a.allow(*MANAGERS)
    booking = a.db.get("makeup_bookings", a.id, bid)
    if booking["status"] != "BOOKED":
        raise HTTPException(409, "Only an unfulfilled booking can be released.")
    a.db.execute(
        "UPDATE {s}.makeup_bookings SET status='CANCELLED',cancelled_at=CURRENT_TIMESTAMP WHERE id=:id",
        id=bid,
    )
    a.db.execute(
        "UPDATE {s}.session_participants SET status='CANCELLED' WHERE id=:id",
        id=booking["replacement_participant_id"],
    )
    return {"ok": True}


def cancel(a, sid, p):
    from ..schemas import EntitlementInput

    a.allow(*MANAGERS)
    session = a.session(sid)
    if session["status"] != "SCHEDULED":
        raise HTTPException(409, "Only scheduled sessions can be cancelled.")
    if a.db.first(
        "SELECT 1 FROM {s}.attendance at JOIN {s}.session_participants p ON p.id=at.participant_id AND p.workspace_id=at.workspace_id WHERE p.workspace_id=:w AND p.session_id=:s",
        w=a.id,
        s=sid,
    ):
        raise HTTPException(
            409, "A session with recorded attendance cannot be cancelled."
        )
    edited_from_series = bool(session.get("recurring_series_id"))
    title = session.get("title") or "Session"
    if edited_from_series and not session.get("edited_from_series") and not title.endswith(" - Edited"):
        title = f"{title} - Edited"
    a.db.execute(
        """UPDATE {s}.class_sessions
        SET title=:title,status='CANCELLED',cancelled_at=CURRENT_TIMESTAMP,cancellation_reason=:r,
            edited_from_series=:edited,series_edited_at=CASE WHEN :edited THEN CURRENT_TIMESTAMP ELSE series_edited_at END
        WHERE id=:id""",
        title=title,
        r=p.reason,
        edited=edited_from_series or session.get("edited_from_series", False),
        id=sid,
    )
    for booking in a.db.all(
        "SELECT b.id FROM {s}.makeup_bookings b JOIN {s}.session_participants p ON p.id=b.replacement_participant_id AND p.workspace_id=b.workspace_id WHERE b.workspace_id=:w AND p.session_id=:s AND b.status='BOOKED'",
        w=a.id,
        s=sid,
    ):
        release(a, booking["id"])
    if p.grant_makeups:
        ids = [
            r["id"]
            for r in a.db.all(
                "SELECT id FROM {s}.session_participants WHERE workspace_id=:w AND session_id=:s AND status='BOOKED' AND participation_kind<>'MAKEUP'",
                w=a.id,
                s=sid,
            )
        ]
        if ids:
            grant(
                a,
                EntitlementInput(
                    participant_ids=ids,
                    reason="TEACHER_CANCELLED",
                    reason_notes=p.reason,
                ),
            )
    return {"ok": True}


def policy(a, p):
    a.allow("OWNER", "ADMIN")
    fields = p.model_dump()
    a.db.execute(
        "UPDATE {s}.makeup_policies SET "
        + ",".join(f"{k}=:{k}" for k in fields)
        + " WHERE workspace_id=:w",
        w=a.id,
        **fields,
    )
    return fields
