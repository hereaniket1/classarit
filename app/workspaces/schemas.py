from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkspaceInput(Input):
    name: str = Field(min_length=1, max_length=150)
    workspace_type: Literal["INDIVIDUAL", "INSTITUTE"]
    timezone: str = "Asia/Kolkata"
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("Choose a valid IANA timezone, such as Asia/Kolkata.")
        return value


class InviteInput(Input):
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    roles: list[Literal["ADMIN", "OPERATOR", "TEACHER"]] = Field(min_length=1)


class MemberInput(Input):
    roles: list[Literal["ADMIN", "OPERATOR", "TEACHER"]] = Field(default_factory=list)
    status: Literal["ACTIVE", "SUSPENDED", "LEFT"] = "ACTIVE"


class ActivityInput(Input):
    name: str = Field(min_length=1, max_length=150)
    category: Literal["ACADEMIC", "ARTS", "SPORTS", "OTHER"] = "OTHER"


class VenueInput(Input):
    name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=1, max_length=1000)
    directions: str = ""
    map_url: str | None = None
    space_names: list[str] = Field(default_factory=list, max_length=50)


class StudentInput(Input):
    full_name: str = Field(min_length=1, max_length=150)
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    guardian_name: str | None = None
    guardian_email: str | None = None
    guardian_phone: str | None = None


class ProgramInput(Input):
    name: str = Field(min_length=1, max_length=150)
    activity_id: UUID | None = None
    activity_name: str | None = None
    category: Literal["ACADEMIC", "ARTS", "SPORTS", "OTHER"] = "OTHER"
    program_kind: Literal["COURSE", "EVENT"] = "COURSE"
    teaching_format: Literal["ONE_TO_ONE", "GROUP"] = "GROUP"
    capacity: int = Field(default=10, gt=0, le=10000)
    level: str | None = None
    default_duration_minutes: int = Field(default=60, gt=0, le=1440)
    default_delivery_mode: Literal["ONLINE", "IN_PERSON", "HYBRID"] = "ONLINE"
    default_meeting_url: str | None = None
    default_venue_id: UUID | None = None
    default_space_id: UUID | None = None
    teacher_ids: list[UUID] = Field(default_factory=list)


class EnrollmentInput(Input):
    student_id: UUID
    starts_on: date
    ends_on: date | None = None


class SessionInput(Input):
    program_id: UUID
    title: str | None = None
    student_ids: list[UUID] = Field(default_factory=list)
    starts_at: datetime
    ends_at: datetime | None = None
    delivery_mode: Literal["ONLINE", "IN_PERSON", "HYBRID"] | None = None
    meeting_url: str | None = None
    venue_id: UUID | None = None
    space_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0, le=10000)
    teacher_ids: list[UUID] | None = None


class RecurringSessionInput(Input):
    program_id: UUID
    title: str | None = None
    student_ids: list[UUID] = Field(default_factory=list)
    start_date: date
    start_time: time
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    repeat_weekdays: list[
        Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    ] = Field(min_length=1, max_length=7)
    repeat_months: int = Field(default=1, ge=1, le=24)
    delivery_mode: Literal["ONLINE", "IN_PERSON", "HYBRID"] | None = None
    meeting_url: str | None = None
    venue_id: UUID | None = None
    space_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0, le=10000)
    teacher_ids: list[UUID] | None = None


class RescheduleInput(Input):
    starts_at: datetime
    ends_at: datetime
    delivery_mode: Literal["ONLINE", "IN_PERSON", "HYBRID"]
    meeting_url: str | None = None
    venue_id: UUID | None = None
    space_id: UUID | None = None


class RecurringSeriesUpdateInput(Input):
    title: str | None = Field(default=None, max_length=150)


class ParticipantInput(Input):
    student_id: UUID


class CancelInput(Input):
    reason: str = Field(min_length=1, max_length=500)
    grant_makeups: bool = False


class AttendanceInput(Input):
    status: Literal["PRESENT", "LATE", "ABSENT", "EXCUSED"]
    notes: str | None = None


class EntitlementInput(Input):
    participant_ids: list[UUID] = Field(min_length=1)
    reason: Literal[
        "TEACHER_CANCELLED", "VENUE_UNAVAILABLE", "WEATHER", "STUDENT_ABSENT", "OTHER"
    ]
    reason_notes: str | None = None


class BookingInput(Input):
    session_id: UUID


class PolicyInput(Input):
    teacher_cancellation_eligible: bool = True
    student_absence_eligible: bool = False
    minimum_notice_hours: int = Field(default=0, ge=0)
    validity_days: int | None = Field(default=30, gt=0)
    included_in_original_fee: bool = True


class TeacherAssignmentInput(Input):
    teacher_ids: list[UUID] = Field(min_length=1)
