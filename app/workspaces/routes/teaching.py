from uuid import UUID
from fastapi import APIRouter, Depends
from ..access import access
from ..schemas import (
    ActivityInput,
    VenueInput,
    StudentInput,
    ProgramInput,
    EnrollmentInput,
)
from ..services import catalog

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


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
