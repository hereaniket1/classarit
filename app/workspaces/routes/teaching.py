from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks
from ..access import access
from ..schemas import (
    ActivityInput,
    VenueInput,
    StudentInput,
    ProgramInput,
    EnrollmentInput,
)
from ..services import catalog
from ...services import notifications

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@router.post("/activities", status_code=201)
def activity(p: ActivityInput, a=Depends(access)):
    return catalog.activity(a, p)


@router.post("/venues", status_code=201)
def venue(p: VenueInput, a=Depends(access)):
    return catalog.venue(a, p)


@router.post("/students", status_code=201)
def student(p: StudentInput, a=Depends(access)):
    return catalog.student(a, p)


@router.post("/programs", status_code=201)
def program(p: ProgramInput, a=Depends(access)):
    return catalog.program(a, p)


@router.patch("/programs/{program_id}")
def update_program(program_id: UUID, p: ProgramInput, a=Depends(access)):
    return catalog.update_program(a, program_id, p)


@router.delete("/programs/{program_id}")
def delete_program(
    program_id: UUID,
    background_tasks: BackgroundTasks,
    a=Depends(access),
):
    result = catalog.archive_program(a, program_id)
    notifications.send_student_schedule_notice(
        background_tasks, a, result.get("cancelled_session_ids", []), "removed"
    )
    return result


@router.delete("/venues/{venue_id}")
def delete_venue(venue_id: UUID, a=Depends(access)):
    return catalog.archive_venue(a, venue_id)


@router.delete("/students/{student_id}")
def delete_student(
    student_id: UUID,
    background_tasks: BackgroundTasks,
    a=Depends(access),
):
    session_ids = [
        row["session_id"]
        for row in a.db.all(
            """SELECT DISTINCT sp.session_id
            FROM {s}.session_participants sp
            JOIN {s}.class_sessions cs
              ON cs.workspace_id=sp.workspace_id AND cs.id=sp.session_id
            WHERE sp.workspace_id=:w AND sp.student_id=:student
              AND sp.status='BOOKED' AND cs.status='SCHEDULED'
              AND cs.starts_at>CURRENT_TIMESTAMP""",
            w=a.id,
            student=student_id,
        )
    ]
    notifications.send_student_schedule_notice(
        background_tasks, a, session_ids, "removed"
    )
    return catalog.archive_student(a, student_id)


@router.post("/programs/{program_id}/enrollments", status_code=201)
def enroll(program_id: UUID, p: EnrollmentInput, a=Depends(access)):
    return catalog.enroll(a, program_id, p)


from ..schemas import TeacherAssignmentInput


@router.patch("/students/{student_id}")
def update_student(student_id: UUID, p: StudentInput, a=Depends(access)):
    return catalog.update_student(a, student_id, p)


@router.post("/enrollments/{enrollment_id}/end")
def end_enrollment(enrollment_id: UUID, a=Depends(access)):
    return catalog.end_enrollment(a, enrollment_id)


@router.put("/programs/{program_id}/teachers")
def assign_teachers(program_id: UUID, p: TeacherAssignmentInput, a=Depends(access)):
    return catalog.assign_teachers(a, program_id, p)
