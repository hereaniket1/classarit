from datetime import date
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload
from ..database import get_db
from .. import models
from ..views import templates
from ..auth.dependencies import require_user
from ..services.ownership import get_teacher

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), teacher=Depends(get_teacher), user=Depends(require_user)):
    today = date.today()
    sessions = db.query(models.ClassSession).join(models.Student).filter(models.Student.teacher_id == teacher.id).options(selectinload(models.ClassSession.student)).order_by(models.ClassSession.date, models.ClassSession.start_time).all()
    payments = db.query(models.Payment).join(models.Student).filter(models.Student.teacher_id == teacher.id).all()
    active_students = db.query(models.Student).filter(models.Student.teacher_id == teacher.id).filter(models.Student.active.is_(True)).count()
    today_sessions = [s for s in sessions if s.date == today]
    upcoming_sessions = [s for s in sessions if s.date >= today]
    pending_payments = sum(max((p.amount_due or 0) - (p.amount_paid or 0), 0) for p in payments if p.status in {"Due", "Partial", "Overdue"})
    monthly_revenue = sum(p.amount_paid or 0 for p in payments if p.payment_date and p.payment_date.month == today.month and p.payment_date.year == today.year)
    materials = db.query(models.Material).filter_by(teacher_id=teacher.id).order_by(models.Material.created_date.desc()).all()
    students = db.query(models.Student).filter_by(teacher_id=teacher.id).order_by(models.Student.name).all()
    assignments = db.query(models.Assignment).join(models.Student).filter(models.Student.teacher_id == teacher.id).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "csrf_token": request.session.get("csrf", ""),
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


