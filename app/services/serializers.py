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


