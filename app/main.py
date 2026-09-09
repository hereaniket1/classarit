from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .database import Base, engine, get_db, SessionLocal
from . import models, schemas
from .config import UPLOAD_DIR

app = FastAPI(title="Classarit MVP")
APP_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")



@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


def seed_data():
    db = SessionLocal()
    try:
        teacher = db.query(models.Teacher).filter_by(email="demo@classarit.local").first()
        if teacher:
            return
        teacher = models.Teacher(
            name="Ananya Music Academy",
            email="demo@classarit.local",
            phone="+91 90000 00000",
            default_class_duration=60,
            default_meeting_link="https://meet.google.com/demo-meeting",
            currency="INR",
            timezone="Asia/Kolkata",
            default_payment_model="Monthly",
        )
        db.add(teacher)
        db.flush()

        students = [
            models.Student(teacher_id=teacher.id, name="Aarav Sharma", subject="Piano", guardian_name="Neha Sharma", email="aarav@example.com", phone="9876500001", class_duration=60, fee_type="Monthly", fee_amount=4000, start_date=date.today() - timedelta(days=40), notes="Preparing for recital."),
            models.Student(teacher_id=teacher.id, name="Meera Rao", subject="Singing", guardian_name="Rahul Rao", email="meera@example.com", phone="9876500002", class_duration=45, fee_type="Per Class", fee_amount=700, start_date=date.today() - timedelta(days=18), notes="Warm-up before each lesson."),
            models.Student(teacher_id=teacher.id, name="Rohan Das", subject="Guitar", guardian_name="Sanjay Das", email="rohan@example.com", phone="9876500003", class_duration=60, fee_type="Package", fee_amount=9000, start_date=date.today() - timedelta(days=60), notes="Focus on chord transitions."),
        ]
        db.add_all(students)
        db.flush()

        today = date.today()
        sessions = [
            models.ClassSession(student_id=students[0].id, subject="Piano", date=today, start_time=datetime.strptime("10:00", "%H:%M").time(), duration=60, meeting_url="https://meet.google.com/aarav-piano", status="Scheduled"),
            models.ClassSession(student_id=students[1].id, subject="Singing", date=today, start_time=datetime.strptime("16:00", "%H:%M").time(), duration=45, meeting_url="https://zoom.us/j/demo-singing", status="Scheduled"),
            models.ClassSession(student_id=students[2].id, subject="Guitar", date=today + timedelta(days=1), start_time=datetime.strptime("18:30", "%H:%M").time(), duration=60, meeting_url="https://meet.google.com/rohan-guitar", status="Scheduled"),
            models.ClassSession(student_id=students[0].id, subject="Piano", date=today - timedelta(days=2), start_time=datetime.strptime("10:00", "%H:%M").time(), duration=60, meeting_url="https://meet.google.com/aarav-piano", status="Completed"),
        ]
        db.add_all(sessions)
        db.flush()
        db.add_all([
            models.Attendance(class_session_id=sessions[3].id, status="Present"),
            models.Payment(student_id=students[0].id, billing_month=today.strftime("%B %Y"), amount_due=4000, amount_paid=4000, payment_date=today - timedelta(days=5), payment_method="UPI", status="Paid", notes="On time."),
            models.Payment(student_id=students[1].id, billing_month=today.strftime("%B %Y"), amount_due=2800, amount_paid=1000, payment_date=today - timedelta(days=2), payment_method="Cash", status="Partial", notes="Balance pending."),
            models.Payment(student_id=students[2].id, billing_month=today.strftime("%B %Y"), amount_due=4500, amount_paid=0, payment_method="Bank Transfer", status="Due", notes="Reminder sent."),
        ])
        db.add_all([
            models.Material(title="Piano Sheet Music Pack", description="Major scales and beginner pieces", subject="Piano", file_path="/uploads/piano-sheet.pdf"),
            models.Material(title="Vocal Warm-up Audio", description="Daily vocal exercises", subject="Singing", file_path="/uploads/vocal-warmup.mp3"),
            models.Material(title="Guitar Chord Chart", description="Open chords and practice notes", subject="Guitar", file_path="/uploads/guitar-chart.pdf"),
        ])
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    seed_data()


def serialize_student(student):
    return {
        "id": student.id,
        "name": student.name,
        "guardian_name": student.guardian_name,
        "email": student.email,
        "phone": student.phone,
        "subject": student.subject,
        "class_duration": student.class_duration,
        "fee_type": student.fee_type,
        "fee_amount": student.fee_amount,
        "start_date": student.start_date.isoformat(),
        "active": student.active,
        "notes": student.notes,
    }


def serialize_session(session):
    return {
        "id": session.id,
        "student_id": session.student_id,
        "student_name": session.student.name,
        "subject": session.subject,
        "date": session.date.isoformat(),
        "start_time": session.start_time.strftime("%H:%M"),
        "duration": session.duration,
        "meeting_url": session.meeting_url,
        "repeat_type": session.repeat_type,
        "status": session.status,
        "is_makeup": session.is_makeup,
        "original_class_id": session.original_class_id,
        "lesson_notes": session.lesson_notes,
        "homework": session.homework,
        "practice_instructions": session.practice_instructions,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if request.query_params.get("demo") != "1":
        return templates.TemplateResponse("login.html", {"request": request})
    teacher = db.query(models.Teacher).first()
    today = date.today()
    sessions = db.query(models.ClassSession).options(selectinload(models.ClassSession.student)).order_by(models.ClassSession.date, models.ClassSession.start_time).all()
    payments = db.query(models.Payment).all()
    active_students = db.query(models.Student).filter(models.Student.active.is_(True)).count()
    today_sessions = [s for s in sessions if s.date == today]
    upcoming_sessions = [s for s in sessions if s.date >= today]
    pending_payments = sum(max((p.amount_due or 0) - (p.amount_paid or 0), 0) for p in payments if p.status in {"Due", "Partial", "Overdue"})
    monthly_revenue = sum(p.amount_paid or 0 for p in payments if p.payment_date and p.payment_date.month == today.month and p.payment_date.year == today.year)
    materials = db.query(models.Material).order_by(models.Material.created_date.desc()).all()
    students = db.query(models.Student).order_by(models.Student.name).all()
    assignments = db.query(models.Assignment).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "teacher": teacher,
            "students": students,
            "sessions": sessions,
            "today_sessions": today_sessions,
            "upcoming_sessions": upcoming_sessions,
            "active_students": active_students,
            "pending_payments": pending_payments,
            "monthly_revenue": monthly_revenue,
            "payments": payments,
            "materials": materials,
            "assignments": assignments,
            "today": today,
        },
    )


@app.post("/login")
def login():
    return RedirectResponse("/?demo=1", status_code=303)


@app.get("/api/students")
def list_students(db: Session = Depends(get_db)):
    students = db.query(models.Student).order_by(models.Student.name).all()
    return [serialize_student(s) for s in students]


@app.post("/api/students")
def create_student(payload: schemas.StudentCreate, db: Session = Depends(get_db)):
    student = models.Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return serialize_student(student)


@app.put("/api/students/{student_id}")
def update_student(student_id: int, payload: schemas.StudentUpdate, db: Session = Depends(get_db)):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    for key, value in payload.model_dump().items():
        setattr(student, key, value)
    db.commit()
    db.refresh(student)
    return serialize_student(student)


@app.get("/api/classes")
def list_classes(db: Session = Depends(get_db)):
    sessions = db.query(models.ClassSession).options(selectinload(models.ClassSession.student)).order_by(models.ClassSession.date, models.ClassSession.start_time).all()
    return [serialize_session(s) for s in sessions]


@app.post("/api/classes")
def create_class(payload: schemas.ClassSessionCreate, db: Session = Depends(get_db)):
    session = models.ClassSession(**payload.model_dump())
    db.add(session)
    if payload.lesson_notes or payload.homework or payload.practice_instructions:
        db.flush()
        db.add(models.LessonNote(class_session_id=session.id, lesson_notes=payload.lesson_notes, homework=payload.homework, practice_instructions=payload.practice_instructions))
    db.commit()
    db.refresh(session)
    return serialize_session(db.query(models.ClassSession).options(selectinload(models.ClassSession.student)).get(session.id))


@app.put("/api/classes/{class_id}")
def update_class(class_id: int, payload: schemas.ClassSessionUpdate, db: Session = Depends(get_db)):
    session = db.get(models.ClassSession, class_id)
    if not session:
        raise HTTPException(status_code=404, detail="Class not found")
    for key, value in payload.model_dump().items():
        setattr(session, key, value)
    db.commit()
    db.refresh(session)
    return serialize_session(db.query(models.ClassSession).options(selectinload(models.ClassSession.student)).get(session.id))


@app.post("/api/classes/{class_id}/join")
def join_class(class_id: int, db: Session = Depends(get_db)):
    session = db.get(models.ClassSession, class_id)
    if not session:
        raise HTTPException(status_code=404, detail="Class not found")
    if not session.meeting_url:
        raise HTTPException(status_code=400, detail="No meeting URL set")
    return {"meeting_url": session.meeting_url}


@app.post("/api/classes/{class_id}/attendance")
def mark_attendance(class_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    session = db.get(models.ClassSession, class_id)
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


@app.post("/api/classes/{class_id}/makeup")
def create_makeup_class(class_id: int, new_date: date = Form(...), new_time: str = Form(...), db: Session = Depends(get_db)):
    original = db.get(models.ClassSession, class_id)
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
    return serialize_session(db.query(models.ClassSession).options(selectinload(models.ClassSession.student)).get(session.id))


@app.post("/api/payments")
def create_payment(payload: schemas.PaymentCreate, db: Session = Depends(get_db)):
    payment = models.Payment(**payload.model_dump())
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"id": payment.id}


@app.post("/api/materials")
def upload_material(title: str = Form(...), description: str = Form(""), subject: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".mp3", ".wav", ".docx", ".txt"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    dest = UPLOAD_DIR / stored_name
    dest.write_bytes(file.file.read())
    material = models.Material(title=title, description=description, subject=subject, file_path=f"/uploads/{stored_name}")
    db.add(material)
    db.commit()
    db.refresh(material)
    return {"id": material.id, "file_path": material.file_path}


@app.get("/api/dashboard")
def dashboard_data(db: Session = Depends(get_db)):
    today = date.today()
    sessions = db.query(models.ClassSession).all()
    payments = db.query(models.Payment).all()
    return {
        "today_classes": sum(1 for s in sessions if s.date == today),
        "upcoming_classes": sum(1 for s in sessions if s.date >= today),
        "active_students": db.query(models.Student).filter_by(active=True).count(),
        "pending_payments": sum(max((p.amount_due or 0) - (p.amount_paid or 0), 0) for p in payments if p.status in {"Due", "Partial", "Overdue"}),
        "monthly_revenue": sum(p.amount_paid or 0 for p in payments if p.payment_date and p.payment_date.month == today.month and p.payment_date.year == today.year),
    }
