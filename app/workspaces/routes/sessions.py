from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from ..access import access, MANAGERS
from ..schemas import (
    SessionInput,
    RescheduleInput,
    ParticipantInput,
    CancelInput,
    AttendanceInput,
    EntitlementInput,
    BookingInput,
)
from ..services import scheduling, makeups

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@router.post("/sessions", status_code=201)
def create(p: SessionInput, a=Depends(access)):
    return scheduling.create(a, p)


@router.patch("/sessions/{session_id}")
def reschedule(session_id: UUID, p: RescheduleInput, a=Depends(access)):
    return scheduling.reschedule(a, session_id, p)


@router.post("/sessions/{session_id}/participants", status_code=201)
def participant(session_id: UUID, p: ParticipantInput, a=Depends(access)):
    return scheduling.book_event(a, session_id, p)


@router.post("/sessions/{session_id}/cancel")
def cancel(session_id: UUID, p: CancelInput, a=Depends(access)):
    return makeups.cancel(a, session_id, p)


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
