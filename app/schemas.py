from datetime import date, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class StudentBase(BaseModel):
    name: str
    guardian_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    subject: str
    class_duration: int = 60
    fee_type: str = "Monthly"
    fee_amount: float = 0
    start_date: date
    active: bool = True
    notes: Optional[str] = None


class StudentCreate(StudentBase):
    teacher_id: int = 1


class StudentUpdate(StudentBase):
    pass


class ClassSessionBase(BaseModel):
    student_id: int
    subject: str
    date: date
    start_time: time
    duration: int = 60
    meeting_url: Optional[str] = None
    repeat_type: str = "One Time"
    status: str = "Scheduled"
    is_makeup: bool = False
    original_class_id: Optional[int] = None
    lesson_notes: Optional[str] = None
    homework: Optional[str] = None
    practice_instructions: Optional[str] = None

    @field_validator("meeting_url")
    @classmethod
    def validate_url(cls, value):
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("Meeting URL must start with http:// or https://")
        return value


class ClassSessionCreate(ClassSessionBase):
    pass


class ClassSessionUpdate(ClassSessionBase):
    pass


class PaymentBase(BaseModel):
    student_id: int
    billing_month: str
    amount_due: float
    amount_paid: float
    payment_date: Optional[date] = None
    payment_method: Optional[str] = None
    status: str = "Due"
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(PaymentBase):
    pass
