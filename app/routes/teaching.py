from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, selectinload
from ..database import get_db
from .. import models, schemas
from ..config import UPLOAD_DIR
from ..services.ownership import get_teacher
from ..services.serializers import serialize_student, serialize_session

router = APIRouter()


def check_student(db, student_id, teacher_id):
    if not db.query(models.Student).filter_by(id=student_id, teacher_id=teacher_id).first():
        raise HTTPException(404, 'Student not found')


def owned_class(db, class_id, teacher_id):
    return db.query(models.ClassSession).join(models.Student).filter(
        models.ClassSession.id == class_id, models.Student.teacher_id == teacher_id).first()


def require_class(db, class_id, teacher_id):
    if not owned_class(db, class_id, teacher_id):
        raise HTTPException(404, 'Class not found')


@router.get("/api/students")
def list_students(db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    students = db.query(models.Student).filter_by(teacher_id=teacher.id).order_by(models.Student.name).all()
    return [serialize_student(s) for s in students]


@router.post("/api/students")
def create_student(payload: schemas.StudentCreate, db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    student = models.Student(**{**payload.model_dump(), "teacher_id": teacher.id})
    db.add(student)
    db.commit()
    db.refresh(student)
    return serialize_student(student)


@router.put("/api/students/{student_id}")
def update_student(student_id: int, payload: schemas.StudentUpdate, db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    student = db.query(models.Student).filter_by(id=student_id, teacher_id=teacher.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    for key, value in payload.model_dump().items():
        setattr(student, key, value)
    db.commit()
    db.refresh(student)
    return serialize_student(student)


@router.get("/api/classes")
def list_classes(db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    sessions = db.query(models.ClassSession).join(models.Student).filter(models.Student.teacher_id == teacher.id).options(selectinload(models.ClassSession.student)).order_by(models.ClassSession.date, models.ClassSession.start_time).all()
    return [serialize_session(s) for s in sessions]


@router.post("/api/classes")
def create_class(payload: schemas.ClassSessionCreate, db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    check_student(db, payload.student_id, teacher.id)
    if payload.original_class_id:
        require_class(db, payload.original_class_id, teacher.id)
    session = models.ClassSession(**payload.model_dump())
    db.add(session)
    if payload.lesson_notes or payload.homework or payload.practice_instructions:
        db.flush()
        db.add(models.LessonNote(class_session_id=session.id, lesson_notes=payload.lesson_notes, homework=payload.homework, practice_instructions=payload.practice_instructions))
    db.commit()
    db.refresh(session)
    return serialize_session(db.query(models.ClassSession).join(models.Student).filter(models.Student.teacher_id == teacher.id).options(selectinload(models.ClassSession.student)).filter(models.ClassSession.id == session.id).one())


@router.put("/api/classes/{class_id}")
def update_class(class_id: int, payload: schemas.ClassSessionUpdate, db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    session = owned_class(db, class_id, teacher.id)
    if not session:
        raise HTTPException(status_code=404, detail="Class not found")
    check_student(db, payload.student_id, teacher.id)
    if payload.original_class_id:
        require_class(db, payload.original_class_id, teacher.id)
    for key, value in payload.model_dump().items():
        setattr(session, key, value)
    db.commit()
    db.refresh(session)
    return serialize_session(db.query(models.ClassSession).join(models.Student).filter(models.Student.teacher_id == teacher.id).options(selectinload(models.ClassSession.student)).filter(models.ClassSession.id == session.id).one())


@router.post("/api/classes/{class_id}/join")
def join_class(class_id: int, db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    session = owned_class(db, class_id, teacher.id)
    if not session:
        raise HTTPException(status_code=404, detail="Class not found")
    if not session.meeting_url:
        raise HTTPException(status_code=400, detail="No meeting URL set")
    return {"meeting_url": session.meeting_url}


@router.post("/api/classes/{class_id}/attendance")
def mark_attendance(class_id: int, status: str = Form(...), db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    session = owned_class(db, class_id, teacher.id)
    if not session:
        raise HTTPException(status_code=404, detail="Class not found")
    attendance = db.query(models.Attendance).filter_by(class_session_id=class_id).first()
    if attendance:
        attendance.status = status
    else:
        attendance = models.Attendance(class_session_id=class_id, status=status)
        db.add(attendance)
    db.commit()
    return {"status": status}


@router.post("/api/classes/{class_id}/makeup")
def create_makeup_class(class_id: int, new_date: date = Form(...), new_time: str = Form(...), db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    original = owned_class(db, class_id, teacher.id)
    if not original:
        raise HTTPException(status_code=404, detail="Original class not found")
    session = models.ClassSession(
        student_id=original.student_id,
        original_class_id=original.id,
        subject=original.subject,
        date=new_date,
        start_time=datetime.strptime(new_time, "%H:%M").time(),
        duration=original.duration,
        meeting_url=original.meeting_url,
        repeat_type="One Time",
        status="Scheduled",
        is_makeup=True,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return serialize_session(db.query(models.ClassSession).join(models.Student).filter(models.Student.teacher_id == teacher.id).options(selectinload(models.ClassSession.student)).filter(models.ClassSession.id == session.id).one())


@router.post("/api/payments")
def create_payment(payload: schemas.PaymentCreate, db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    check_student(db, payload.student_id, teacher.id)
    payment = models.Payment(**payload.model_dump())
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"id": payment.id}


@router.post("/api/materials")
def upload_material(title: str = Form(...), description: str = Form(""), subject: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    ext = Path(file.filename or "").suffix.lower()
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".mp3", ".wav", ".docx", ".txt"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    stored_name = f"{uuid4().hex}{ext}"
    dest = UPLOAD_DIR / stored_name
    dest.write_bytes(file.file.read())
    material = models.Material(teacher_id=teacher.id, title=title, description=description, subject=subject, file_path=f"/uploads/{stored_name}")
    db.add(material)
    db.commit()
    db.refresh(material)
    return {"id": material.id, "file_path": material.file_path}


@router.get("/api/dashboard")
def dashboard_data(db: Session = Depends(get_db), teacher=Depends(get_teacher)):
    today = date.today()
    sessions = db.query(models.ClassSession).join(models.Student).filter(models.Student.teacher_id == teacher.id).all()
    payments = db.query(models.Payment).join(models.Student).filter(models.Student.teacher_id == teacher.id).all()
    return {
        "today_classes": sum(1 for s in sessions if s.date == today),
        "upcoming_classes": sum(1 for s in sessions if s.date >= today),
        "active_students": db.query(models.Student).filter_by(teacher_id=teacher.id, active=True).count(),
        "pending_payments": sum(max((p.amount_due or 0) - (p.amount_paid or 0), 0) for p in payments if p.status in {"Due", "Partial", "Overdue"}),
        "monthly_revenue": sum(p.amount_paid or 0 for p in payments if p.payment_date and p.payment_date.month == today.month and p.payment_date.year == today.year),
    }
