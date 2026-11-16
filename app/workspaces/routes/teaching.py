from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, Query
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
from pydantic import BaseModel, Field
from datetime import date
from fastapi import HTTPException
from ..access import MANAGERS

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


class DiscoveryInput(BaseModel):
    student_discoverable: bool


class ClassStudentInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    phone: str | None = None
    starts_on: date


@router.get('/students/search')
def search_students(q: str = Query('', max_length=150), a=Depends(access)):
    """Return minimal active-student matches for staff lookup fields."""
    term = q.strip()
    if len(term) < 2:
        return {'students': []}
    return {'students': a.db.all("""WITH known_students AS (
        SELECT st.id,st.full_name,st.email,st.phone,w.name AS workspace_name,
               CASE WHEN st.workspace_id=:w THEN 0 ELSE 1 END AS scope_rank
        FROM {s}.students st
        JOIN {s}.workspaces w ON w.id=st.workspace_id AND w.status='ACTIVE'
        WHERE st.status='ACTIVE'
          AND (st.full_name ILIKE :q OR COALESCE(st.email,'') ILIKE :q)
    ), verified_student_accounts AS (
        SELECT NULL::uuid AS id,u.full_name,e.email,u.phone,NULL::text AS workspace_name,2 AS scope_rank
        FROM {s}.app_users u
        JOIN {s}.user_emails e ON e.app_user_id=u.id AND e.is_primary=true AND e.verified_at IS NOT NULL
        WHERE u.status='ACTIVE' AND u.account_type='STUDENT'
          AND (u.full_name ILIKE :q OR e.email::text ILIKE :q)
          AND NOT EXISTS (
            SELECT 1 FROM {s}.students st
            WHERE st.linked_user_id=u.id AND st.status='ACTIVE'
          )
    )
    SELECT id,full_name,email,phone,workspace_name
    FROM (SELECT * FROM known_students UNION ALL SELECT * FROM verified_student_accounts) matches
    ORDER BY scope_rank,lower(full_name),id NULLS LAST LIMIT 20""", w=a.id, q=f'%{term}%')}


@router.put('/programs/{program_id}/discovery')
def discovery(program_id: UUID, p: DiscoveryInput, a=Depends(access)):
    a.allow(*MANAGERS, 'TEACHER')
    program = a.program(program_id)
    if program['program_kind'] != 'COURSE':
        raise HTTPException(422, 'Only courses support student self-enrollment.')
    a.db.execute('UPDATE {s}.teaching_programs SET student_discoverable=:listed WHERE workspace_id=:w AND id=:p',
                 listed=p.student_discoverable, w=a.id, p=program_id)
    return {'ok': True}


@router.post('/programs/{program_id}/student-enrollment', status_code=201)
def class_student(program_id: UUID, p: ClassStudentInput, a=Depends(access)):
    a.allow(*MANAGERS, 'TEACHER')
    program = a.program(program_id)  # Teachers can add only to their assigned classes.
    student = a.db.first('SELECT * FROM {s}.students WHERE workspace_id=:w AND lower(btrim(email))=:email ORDER BY created_at,id LIMIT 1',
                         w=a.id, email=p.email.strip().lower())
    if not student:
        student = catalog.create_student_record(a, StudentInput(full_name=p.full_name.strip(),email=p.email.strip().lower(),phone=p.phone))
    existing = a.db.first("SELECT id FROM {s}.enrollments WHERE workspace_id=:w AND program_id=:p AND student_id=:st AND status IN ('ACTIVE','PAUSED')",
                          w=a.id,p=program_id,st=student['id'])
    if existing:
        return existing
    return catalog.enroll_student(a, program, EnrollmentInput(student_id=student['id'], starts_on=p.starts_on))


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
