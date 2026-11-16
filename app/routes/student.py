"""Free student discovery and self-enrollment, without workspace membership."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict

from ..auth.dependencies import require_user
from ..views import templates
from ..workspaces.db import transaction
from ..workspaces.schemas import EnrollmentInput
from ..workspaces.services.catalog import enroll_student
from .dashboard import context

router = APIRouter()


class PlannerTaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime | None = None
    timezone: str = Field(default='Asia/Kolkata', min_length=3, max_length=80)
    location: str | None = Field(default=None, max_length=250)
    notes: str | None = Field(default=None, max_length=2000)


def require_student(user=Depends(require_user)):
    if user.get('account_type') != 'STUDENT':
        raise HTTPException(403, 'This page is for student accounts.')
    return user


@router.get('/student')
def student_page(request: Request, user=Depends(require_student)):
    return templates.TemplateResponse('student.html', context(request, user, display_role='STUDENT', student_view='dashboard'))


@router.get('/student/calendar')
def student_calendar_page(request: Request, user=Depends(require_student)):
    return templates.TemplateResponse('student.html', context(request, user, display_role='STUDENT', student_view='calendar'))


@router.get('/student/planner')
def student_planner_page(request: Request, user=Depends(require_student)):
    return templates.TemplateResponse('student.html', context(request, user, display_role='STUDENT', student_view='planner'))


@router.get('/api/student/classes')
def search_classes(q: str = Query('', max_length=150), location: str = Query('', max_length=150),
                   mode: Literal['', 'ONLINE', 'IN_PERSON', 'HYBRID'] = '',
                   offset: int = Query(0, ge=0, le=10000),
                   user=Depends(require_student), db=Depends(transaction)):
    # Explicit projection: no private meeting URLs, contacts, rosters or business identity.
    rows = db.all("""SELECT p.id,p.name,p.description,p.level,p.default_delivery_mode,
        p.default_duration_minutes,w.name AS workspace_name,w.timezone,
        v.name AS venue_name,v.address AS location,
        (SELECT string_agg(u.full_name, ', ' ORDER BY u.full_name)
         FROM {s}.program_teachers pt JOIN {s}.workspace_memberships m ON m.id=pt.membership_id AND m.workspace_id=pt.workspace_id
         JOIN {s}.app_users u ON u.id=m.user_id
         WHERE pt.program_id=p.id AND pt.workspace_id=p.workspace_id AND m.status='ACTIVE') AS teachers,
        GREATEST(0,p.capacity-(SELECT count(*) FROM {s}.enrollments e
          WHERE e.workspace_id=p.workspace_id AND e.program_id=p.id AND e.status IN ('ACTIVE','PAUSED'))) AS seats_available,
        EXISTS(SELECT 1 FROM {s}.enrollments e JOIN {s}.students st ON st.id=e.student_id AND st.workspace_id=e.workspace_id
          WHERE e.program_id=p.id AND e.workspace_id=p.workspace_id AND st.linked_user_id=:u AND e.status IN ('ACTIVE','PAUSED')) AS enrolled
        FROM {s}.teaching_programs p JOIN {s}.workspaces w ON w.id=p.workspace_id AND w.status='ACTIVE'
        LEFT JOIN {s}.venues v ON v.id=p.default_venue_id AND v.workspace_id=p.workspace_id AND v.archived_at IS NULL
        WHERE p.status='ACTIVE' AND p.program_kind='COURSE' AND p.student_discoverable
          AND (:q='' OR p.name ILIKE :search OR w.name ILIKE :search OR COALESCE(p.description,'') ILIKE :search)
          AND (:location='' OR v.address ILIKE :place OR v.name ILIKE :place)
          AND (:mode='' OR p.default_delivery_mode=:mode OR (p.default_delivery_mode='HYBRID' AND :mode IN ('ONLINE','IN_PERSON')))
        ORDER BY lower(p.name),p.id LIMIT 21 OFFSET :offset""",
        u=user['id'], q=q.strip(), search='%'+q.strip()+'%', location=location.strip(),
        place='%'+location.strip()+'%', mode=mode, offset=offset)
    return {'classes': rows[:20], 'has_more': len(rows)>20}


@router.get('/api/student/upcoming')
def upcoming(user=Depends(require_student), db=Depends(transaction)):
    sessions = db.all("""SELECT cs.id,COALESCE(cs.title,p.name) AS title,cs.starts_at,cs.ends_at,
        cs.delivery_mode,cs.meeting_url,v.name AS venue_name,v.address,w.name AS workspace_name,w.timezone
        FROM {s}.session_participants sp
        JOIN {s}.students st ON st.id=sp.student_id AND st.workspace_id=sp.workspace_id AND st.status='ACTIVE'
        JOIN {s}.class_sessions cs ON cs.id=sp.session_id AND cs.workspace_id=sp.workspace_id
        JOIN {s}.teaching_programs p ON p.id=cs.program_id AND p.workspace_id=cs.workspace_id
        JOIN {s}.workspaces w ON w.id=cs.workspace_id AND w.status='ACTIVE'
        LEFT JOIN {s}.venues v ON v.id=cs.venue_id AND v.workspace_id=cs.workspace_id
        WHERE st.linked_user_id=:u AND sp.status='BOOKED' AND cs.status='SCHEDULED' AND cs.ends_at>CURRENT_TIMESTAMP
        ORDER BY cs.starts_at,cs.id LIMIT 100""",u=user['id'])
    classes = db.all("""SELECT p.id,p.name,w.name AS workspace_name,e.status
        FROM {s}.enrollments e JOIN {s}.students st ON st.id=e.student_id AND st.workspace_id=e.workspace_id
        JOIN {s}.teaching_programs p ON p.id=e.program_id AND p.workspace_id=e.workspace_id
        JOIN {s}.workspaces w ON w.id=e.workspace_id AND w.status='ACTIVE'
        WHERE st.linked_user_id=:u AND st.status='ACTIVE' AND e.status IN ('ACTIVE','PAUSED')
        AND p.status='ACTIVE' ORDER BY p.name,p.id""",u=user['id'])
    tasks = db.all("""SELECT id,title,starts_at,ends_at,timezone,location,notes,status
        FROM {s}.student_planner_tasks
        WHERE student_user_id=:u AND status='ACTIVE' AND ends_at>CURRENT_TIMESTAMP
        ORDER BY starts_at,id LIMIT 100""", u=user['id'])
    return {'sessions': sessions, 'classes': classes, 'tasks': tasks}


@router.get('/api/student/calendar')
def calendar_month(month: str = Query(pattern=r'^\d{4}-\d{2}$'), user=Depends(require_student), db=Depends(transaction)):
    try:
        year, number = (int(part) for part in month.split('-'))
        zone = ZoneInfo('Asia/Kolkata')
        start = datetime(year, number, 1, tzinfo=zone)
        end = datetime(year + (number == 12), 1 if number == 12 else number + 1, 1, tzinfo=zone)
    except Exception:
        raise HTTPException(422, 'Choose a valid calendar month.')
    sessions = db.all("""SELECT cs.id,COALESCE(cs.title,p.name) AS title,cs.starts_at,cs.ends_at,
        cs.delivery_mode,w.name AS workspace_name,w.timezone
        FROM {s}.session_participants sp JOIN {s}.students st ON st.id=sp.student_id AND st.workspace_id=sp.workspace_id
        JOIN {s}.class_sessions cs ON cs.id=sp.session_id AND cs.workspace_id=sp.workspace_id
        JOIN {s}.teaching_programs p ON p.id=cs.program_id AND p.workspace_id=cs.workspace_id
        JOIN {s}.workspaces w ON w.id=cs.workspace_id AND w.status='ACTIVE'
        WHERE st.linked_user_id=:u AND sp.status='BOOKED' AND cs.status='SCHEDULED'
          AND cs.starts_at>=:start AND cs.starts_at<:end ORDER BY cs.starts_at,cs.id""",u=user['id'],start=start,end=end)
    tasks = db.all("""SELECT id,title,starts_at,ends_at,timezone,location,notes,status
        FROM {s}.student_planner_tasks WHERE student_user_id=:u AND status='ACTIVE'
          AND starts_at>=:start AND starts_at<:end ORDER BY starts_at,id""",u=user['id'],start=start,end=end)
    return {'month': month, 'sessions': sessions, 'tasks': tasks}


@router.post('/api/student/planner/tasks', status_code=201)
def create_planner_task(payload: PlannerTaskInput, user=Depends(require_student), db=Depends(transaction)):
    try:
        zone = ZoneInfo(payload.timezone)
    except Exception:
        raise HTTPException(422, 'Choose a valid time zone.')
    start = payload.starts_at
    end = payload.ends_at or (start + timedelta(hours=1))
    if start.tzinfo is None:
        start = start.replace(tzinfo=zone)
    if end.tzinfo is None:
        end = end.replace(tzinfo=zone)
    if end <= start:
        raise HTTPException(422, 'End time must be after the start time.')
    return db.insert('student_planner_tasks', student_user_id=user['id'], title=payload.title,
                     starts_at=start, ends_at=end, timezone=payload.timezone,
                     location=payload.location, notes=payload.notes, status='ACTIVE')


@router.delete('/api/student/planner/tasks/{task_id}')
def delete_planner_task(task_id: UUID, user=Depends(require_student), db=Depends(transaction)):
    row = db.first("""UPDATE {s}.student_planner_tasks SET status='CANCELLED',updated_at=CURRENT_TIMESTAMP
        WHERE id=:id AND student_user_id=:u AND status='ACTIVE' RETURNING id""", id=task_id, u=user['id'])
    if not row:
        raise HTTPException(404, 'Planner task not found.')
    return {'ok': True}


@router.post('/api/student/classes/{program_id}/enroll')
def self_enroll(program_id: UUID, user=Depends(require_student), db=Depends(transaction)):
    if not user.get('email_verified'):
        raise HTTPException(403, 'Verify your email in Edit profile before joining a class.')
    # Same workspace lock as staff mutations, so capacity checks cannot race.
    workspace = db.first("""SELECT w.* FROM {s}.workspaces w JOIN {s}.teaching_programs p ON p.workspace_id=w.id
        WHERE p.id=:p AND w.status='ACTIVE' FOR UPDATE OF w""",p=program_id)
    if not workspace:
        raise HTTPException(404, 'Class not found.')
    program = db.get('teaching_programs',workspace['id'],program_id)
    if not program.get('student_discoverable') or program['status']!='ACTIVE' or program['program_kind']!='COURSE':
        raise HTTPException(404, 'This class is not open for enrollment.')
    student = db.first('SELECT * FROM {s}.students WHERE workspace_id=:w AND linked_user_id=:u',w=workspace['id'],u=user['id'])
    if student and student['status']!='ACTIVE':
        raise HTTPException(409, 'Ask the teacher to reactivate your student record.')
    if not student:
        student = db.insert('students',workspace_id=workspace['id'],linked_user_id=user['id'],
                            full_name=user['full_name'],email=user['email'],phone=user.get('phone'))
    existing = db.first("""SELECT id,status FROM {s}.enrollments WHERE workspace_id=:w AND program_id=:p
        AND student_id=:st AND status IN ('ACTIVE','PAUSED')""",w=workspace['id'],p=program_id,st=student['id'])
    if existing:
        return {'id': existing['id'], 'already_enrolled': True}
    # This internal context grants no staff access or membership to the student.
    a = SimpleNamespace(db=db,id=workspace['id'],workspace=workspace)
    payload = EnrollmentInput(student_id=student['id'],starts_on=datetime.now(timezone.utc).astimezone(ZoneInfo(workspace['timezone'])).date())
    enrollment = enroll_student(a, program, payload)
    return {'id': enrollment['id'], 'already_enrolled': False}
