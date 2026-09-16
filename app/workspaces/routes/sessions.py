from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from ..access import access, MANAGERS
from ..schemas import (
    SessionInput,
    RecurringSessionInput,
    RecurringSeriesUpdateInput,
    RescheduleInput,
    ParticipantInput,
    CancelInput,
    AttendanceInput,
    EntitlementInput,
    BookingInput,
)
from ..services import scheduling, makeups
from ...services import notifications

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@router.post("/sessions", status_code=201)
def create(p: SessionInput, background_tasks: BackgroundTasks, a=Depends(access)):
    row = scheduling.create(a, p)
    notifications.send_student_schedule_notice(background_tasks, a, [row["id"]], "added")
    return row


@router.post("/sessions/recurring", status_code=201)
def create_recurring(p: RecurringSessionInput, background_tasks: BackgroundTasks, a=Depends(access)):
    result = scheduling.create_recurring(a, p)
    notifications.send_student_schedule_notice(background_tasks, a, [row["id"] for row in result.get("sessions", [])], "added")
    return result


@router.post("/recurring-series/{series_id}/disable")
def disable_recurring_series(series_id: UUID, a=Depends(access)):
    return scheduling.disable_recurring_series(a, series_id)


@router.patch("/recurring-series/{series_id}")
def update_recurring_series(series_id: UUID, p: RecurringSeriesUpdateInput, a=Depends(access)):
    return scheduling.update_recurring_series(a, series_id, p)


@router.post("/recurring-series/{series_id}/restore")
def restore_recurring_series(series_id: UUID, a=Depends(access)):
    return scheduling.restore_recurring_series(a, series_id)


@router.patch("/sessions/{session_id}")
def reschedule(session_id: UUID, p: RescheduleInput, a=Depends(access)):
    return scheduling.reschedule(a, session_id, p)


@router.post("/sessions/{session_id}/participants", status_code=201)
def participant(session_id: UUID, p: ParticipantInput, background_tasks: BackgroundTasks, a=Depends(access)):
    row = scheduling.book_event(a, session_id, p)
    notifications.send_student_schedule_notice(background_tasks, a, [session_id], "added")
    return row


@router.post("/sessions/{session_id}/cancel")
def cancel(session_id: UUID, p: CancelInput, background_tasks: BackgroundTasks, a=Depends(access)):
    result = makeups.cancel(a, session_id, p)
    notifications.send_student_schedule_notice(background_tasks, a, [session_id], "removed")
    return result


@router.post("/sessions/{session_id}/complete")
def complete(session_id: UUID, a=Depends(access)):
    from datetime import datetime, timezone

    session = a.session(session_id)
    if session["status"] != "SCHEDULED" or session["ends_at"] > datetime.now(
        timezone.utc
    ):
        raise HTTPException(409, "Complete a scheduled session after its end time.")
    if a.db.first(
        "SELECT 1 FROM {s}.session_participants p LEFT JOIN {s}.attendance at ON at.workspace_id=p.workspace_id AND at.participant_id=p.id WHERE p.workspace_id=:w AND p.session_id=:s AND p.status='BOOKED' AND at.id IS NULL",
        w=a.id,
        s=session_id,
    ):
        raise HTTPException(409, "Mark attendance for all booked students first.")
    a.db.execute(
        "UPDATE {s}.class_sessions SET status='COMPLETED' WHERE workspace_id=:w AND id=:id",
        w=a.id,
        id=session_id,
    )
    return {"ok": True}


@router.put("/participants/{participant_id}/attendance")
def attendance(participant_id: UUID, p: AttendanceInput, a=Depends(access)):
    return scheduling.attendance(a, participant_id, p)


@router.post("/makeup-entitlements", status_code=201)
def grant(p: EntitlementInput, a=Depends(access)):
    return makeups.grant(a, p)


@router.post("/makeup-entitlements/{entitlement_id}/book", status_code=201)
def book(entitlement_id: UUID, p: BookingInput, a=Depends(access)):
    return makeups.book(a, entitlement_id, p)


@router.delete("/makeup-bookings/{booking_id}")
def release(booking_id: UUID, a=Depends(access)):
    return makeups.release(a, booking_id)
