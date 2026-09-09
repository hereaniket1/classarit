"""Legacy demo seed, retained for reference; never run during authenticated startup."""
from datetime import date, datetime, timedelta
from ..database import SessionLocal
from .. import models

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


