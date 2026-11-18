"""Free student discovery and self-enrollment, without workspace membership."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict
from psycopg.types.json import Jsonb

from ..auth.dependencies import require_user
from ..views import templates
from ..workspaces.db import transaction
from ..workspaces.schemas import EnrollmentInput
from ..workspaces.services.catalog import enroll_student
from ..workspaces.services.scheduling import instant, recurring_dates
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
    repeat: Literal['NONE','DAILY','WEEKLY'] = 'NONE'
    repeat_count: int = Field(default=1, ge=1, le=52)
    duration_minutes: int = Field(default=60, ge=1, le=1440)
    repeat_weekdays: list[Literal['MON','TUE','WED','THU','FRI','SAT','SUN']] = Field(default_factory=list, max_length=7)
    repeat_months: int | None = Field(default=None, ge=1, le=24)
    preserve_dates: bool = False


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


@router.get('/student/classes')
def student_classes_page(request: Request, user=Depends(require_student)):
    return templates.TemplateResponse('student.html', context(request, user, display_role='STUDENT', student_view='classes'))


@router.get('/student/planner')
def student_planner_page(request: Request, user=Depends(require_student)):
    return templates.TemplateResponse('student.html', context(request, user, display_role='STUDENT', student_view='planner'))


@router.get('/student/draw')
def student_draw_page(request: Request, user=Depends(require_student)):
    return templates.TemplateResponse('student.html', context(request, user, display_role='STUDENT', student_view='draw'))


@router.get('/student/puzzle')
def student_puzzle_page(request: Request, user=Depends(require_student)):
    return templates.TemplateResponse('student.html', context(request, user, display_role='STUDENT', student_view='puzzle'))


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
    sessions = db.all("""SELECT cs.id,cs.program_id,COALESCE(cs.title,p.name) AS title,cs.starts_at,cs.ends_at,
        cs.status,cs.session_kind,
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
    tasks = db.all("""SELECT id,series_id,title,starts_at,ends_at,timezone,location,notes,status
        FROM {s}.student_planner_tasks
        WHERE student_user_id=:u AND status='ACTIVE' AND ends_at>CURRENT_TIMESTAMP
        ORDER BY starts_at,id LIMIT 100""", u=user['id'])
    return {'sessions': sessions, 'classes': classes, 'tasks': tasks}


@router.get('/api/student/calendar')
def calendar_month(
    month: str = Query(pattern=r'^\d{4}-\d{2}$'),
    user=Depends(require_student),
    db=Depends(transaction),
    tz: Annotated[str, Query(alias='timezone', min_length=1, max_length=80)] = 'Asia/Kolkata',
):
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise HTTPException(422, 'Choose a valid time zone.') from error
    try:
        year, number = (int(part) for part in month.split('-'))
        start = datetime(year, number, 1, tzinfo=zone)
        end = datetime(year + (number == 12), 1 if number == 12 else number + 1, 1, tzinfo=zone)
    except ValueError as error:
        raise HTTPException(422, 'Choose a valid calendar month.') from error
    sessions = db.all("""SELECT cs.id,cs.program_id,COALESCE(cs.title,p.name) AS title,cs.starts_at,cs.ends_at,
        cs.status,cs.session_kind,cs.delivery_mode,
        CASE WHEN cs.status='SCHEDULED' AND cs.ends_at>CURRENT_TIMESTAMP THEN cs.meeting_url END AS meeting_url,
        v.name AS venue_name,v.address,w.name AS workspace_name,w.timezone
        FROM {s}.session_participants sp
        JOIN {s}.students st ON st.id=sp.student_id AND st.workspace_id=sp.workspace_id AND st.status='ACTIVE'
        JOIN {s}.class_sessions cs ON cs.id=sp.session_id AND cs.workspace_id=sp.workspace_id
        JOIN {s}.teaching_programs p ON p.id=cs.program_id AND p.workspace_id=cs.workspace_id
        JOIN {s}.workspaces w ON w.id=cs.workspace_id AND w.status='ACTIVE'
        LEFT JOIN {s}.venues v ON v.id=cs.venue_id AND v.workspace_id=cs.workspace_id
        WHERE st.linked_user_id=:u AND sp.status='BOOKED' AND cs.status IN ('SCHEDULED','COMPLETED')
          AND cs.ends_at>:start AND cs.starts_at<:end ORDER BY cs.starts_at,cs.id""",
        u=user['id'], start=start, end=end)
    tasks = db.all("""SELECT id,series_id,title,starts_at,ends_at,timezone,location,notes,status
        FROM {s}.student_planner_tasks WHERE student_user_id=:u AND status IN ('ACTIVE','COMPLETED')
          AND ends_at>:start AND starts_at<:end ORDER BY starts_at,id""",
        u=user['id'], start=start, end=end)
    return {'month': month, 'sessions': sessions, 'tasks': tasks}


def _planner_rows(payload, user, series_id, existing=None):
    try:
        zone = ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, 'Choose a valid time zone.')
    schedule = SimpleNamespace(workspace={'timezone': payload.timezone})
    start = instant(schedule, payload.starts_at)
    end = instant(schedule, payload.ends_at) if payload.ends_at else start + timedelta(minutes=payload.duration_minutes)
    if end <= start:
        raise HTTPException(422, 'End time must be after the start time.')
    local_start = start.astimezone(zone)
    if payload.preserve_dates:
        if not existing:
            raise HTTPException(422, 'Existing dates are required.')
        original_start = existing[0]['starts_at'].astimezone(zone).date()
        dates = [local_start.date() + (item['starts_at'].astimezone(zone).date() - original_start)
                 for item in existing]
    elif payload.repeat_months is not None or payload.repeat_weekdays:
        if payload.repeat != 'WEEKLY' or payload.repeat_months is None or not payload.repeat_weekdays:
            raise HTTPException(422, 'Choose repeat weekdays and a repeat period.')
        dates = recurring_dates(local_start.date(), payload.repeat_months, payload.repeat_weekdays)
    else:
        interval = 1 if payload.repeat == 'DAILY' else 7
        count = payload.repeat_count if payload.repeat != 'NONE' else 1
        dates = [local_start.date() + timedelta(days=index * interval) for index in range(count)]
    duration = end - start
    completed_starts = {item['starts_at'] for item in (existing or []) if item['status'] == 'COMPLETED'}
    rows = []
    for day in dates:
        begins = start if day == local_start.date() else instant(
            schedule, datetime.combine(day, local_start.time().replace(tzinfo=None)))
        rows.append(dict(id=uuid4(), student_user_id=user['id'], series_id=series_id,
                         recurrence=Jsonb(payload.model_dump(mode='json')), title=payload.title,
                         starts_at=begins, ends_at=begins + duration, timezone=payload.timezone,
                         location=payload.location, notes=payload.notes,
                         status='COMPLETED' if begins in completed_starts else 'ACTIVE'))
    return rows


@router.post('/api/student/planner/tasks', status_code=201)
def create_planner_task(payload: PlannerTaskInput, user=Depends(require_student), db=Depends(transaction)):
    rows = _planner_rows(payload, user, uuid4())
    if len(rows) == 1:
        return db.insert('student_planner_tasks', **rows[0])
    db.insert_many('student_planner_tasks', rows)
    return {'id': rows[0]['id'], 'series_id': rows[0]['series_id'], 'count': len(rows)}


@router.get('/api/student/planner')
def planner_groups(user=Depends(require_student), db=Depends(transaction)):
    rows = db.all("""SELECT series_id AS id, min(title) AS title, min(timezone) AS timezone,
        min(starts_at) AS starts_at, max(ends_at) AS ends_at, count(*) AS count,
        count(*) FILTER (WHERE ends_at>CURRENT_TIMESTAMP AND status='ACTIVE') AS upcoming_count,
        min(location) AS location
        FROM {s}.student_planner_tasks
        WHERE student_user_id=:u AND status IN ('ACTIVE','COMPLETED')
        GROUP BY series_id ORDER BY min(starts_at) DESC""", u=user['id'])
    return {'groups': rows}


def _planner_group(db, user, series_id, lock=False):
    if lock:
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))",
                   key=str(user['id']) + ':' + str(series_id))
    rows = db.all("""SELECT * FROM {s}.student_planner_tasks
        WHERE student_user_id=:u AND series_id=:id AND status IN ('ACTIVE','COMPLETED')
        ORDER BY starts_at,id""" + (' FOR UPDATE' if lock else ''), u=user['id'], id=series_id)
    if not rows:
        raise HTTPException(404, 'Planner schedule not found.')
    return rows


@router.get('/api/student/planner/series/{series_id}')
def planner_details(series_id: UUID, user=Depends(require_student), db=Depends(transaction)):
    return {'tasks': _planner_group(db, user, series_id)}


@router.patch('/api/student/planner/series/{series_id}')
def update_planner_series(series_id: UUID, payload: PlannerTaskInput,
                          user=Depends(require_student), db=Depends(transaction)):
    existing = _planner_group(db, user, series_id, lock=True)
    rows = _planner_rows(payload, user, series_id, existing)
    db.execute("""UPDATE {s}.student_planner_tasks SET status='CANCELLED',updated_at=CURRENT_TIMESTAMP
        WHERE student_user_id=:u AND series_id=:id AND status IN ('ACTIVE','COMPLETED')""",
        u=user['id'], id=series_id)
    db.insert_many('student_planner_tasks', rows)
    return {'id': rows[0]['id'], 'series_id': series_id, 'count': len(rows)}


@router.delete('/api/student/planner/series/{series_id}')
def delete_planner_series(series_id: UUID, user=Depends(require_student), db=Depends(transaction)):
    _planner_group(db, user, series_id, lock=True)
    db.execute("""UPDATE {s}.student_planner_tasks SET status='CANCELLED',updated_at=CURRENT_TIMESTAMP
        WHERE student_user_id=:u AND series_id=:id AND status IN ('ACTIVE','COMPLETED')""",
        u=user['id'], id=series_id)
    return {'ok': True}


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
