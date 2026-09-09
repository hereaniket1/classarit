from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    default_class_duration: Mapped[int] = mapped_column(Integer, default=60)
    default_meeting_link: Mapped[str | None] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    default_payment_model: Mapped[str] = mapped_column(String(20), default="Monthly")

    students: Mapped[list["Student"]] = relationship(back_populates="teacher")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    guardian_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    class_duration: Mapped[int] = mapped_column(Integer, default=60)
    fee_type: Mapped[str] = mapped_column(String(20), default="Monthly")
    fee_amount: Mapped[float] = mapped_column(Float, default=0)
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    teacher: Mapped["Teacher"] = relationship(back_populates="students")
    class_sessions: Mapped[list["ClassSession"]] = relationship(back_populates="student")


class ClassSession(Base):
    __tablename__ = "class_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    original_class_id: Mapped[int | None] = mapped_column(ForeignKey("class_sessions.id"))
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, default=60)
    meeting_url: Mapped[str | None] = mapped_column(String(500))
    repeat_type: Mapped[str] = mapped_column(String(20), default="One Time")
    status: Mapped[str] = mapped_column(String(40), default="Scheduled")
    lesson_notes: Mapped[str | None] = mapped_column(Text)
    homework: Mapped[str | None] = mapped_column(Text)
    practice_instructions: Mapped[str | None] = mapped_column(Text)
    is_makeup: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped["Student"] = relationship(back_populates="class_sessions")
    attendance: Mapped["Attendance"] = relationship(back_populates="class_session", uselist=False)
    lesson_note: Mapped["LessonNote"] = relationship(back_populates="class_session", uselist=False)


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_session_id: Mapped[int] = mapped_column(ForeignKey("class_sessions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="Present")
    marked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    class_session: Mapped["ClassSession"] = relationship(back_populates="attendance")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    billing_month: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_due: Mapped[float] = mapped_column(Float, default=0)
    amount_paid: Mapped[float] = mapped_column(Float, default=0)
    payment_date: Mapped[date | None] = mapped_column(Date)
    payment_method: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="Due")
    notes: Mapped[str | None] = mapped_column(Text)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    created_date: Mapped[date] = mapped_column(Date, default=date.today)


class MaterialAssignment(Base):
    __tablename__ = "material_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    material_attachment: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="Assigned")


class LessonNote(Base):
    __tablename__ = "lesson_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_session_id: Mapped[int] = mapped_column(ForeignKey("class_sessions.id"), unique=True)
    lesson_notes: Mapped[str | None] = mapped_column(Text)
    homework: Mapped[str | None] = mapped_column(Text)
    practice_instructions: Mapped[str | None] = mapped_column(Text)

    class_session: Mapped["ClassSession"] = relationship(back_populates="lesson_note")
