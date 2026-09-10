"""Dashboard projection. Teacher-only memberships see assigned teaching records."""

from ..access import MANAGERS


def snapshot(a):
    db = a.db
    result = {
        "workspace": a.workspace,
        "roles": sorted(a.roles),
        "membership_id": a.member["id"],
    }
    tables = {
        "activities": "activities",
        "venues": "venues",
        "spaces": "venue_spaces",
        "programs": "teaching_programs",
        "program_teachers": "program_teachers",
        "students": "students",
        "enrollments": "enrollments",
        "sessions": "class_sessions",
        "session_teachers": "session_teachers",
        "participants": "session_participants",
        "attendance": "attendance",
        "entitlements": "makeup_entitlements",
        "bookings": "makeup_bookings",
        "guardians": "guardians",
        "student_guardians": "student_guardians",
    }
    for key, table in tables.items():
        result[key] = db.all(
            f"SELECT * FROM {{s}}.{table} WHERE workspace_id=:w", w=a.id
        )
    result["members"] = db.all(
        "SELECT m.id,m.status,u.full_name,array_agg(r.role ORDER BY r.role) roles FROM {s}.workspace_memberships m JOIN {s}.app_users u ON u.id=m.user_id JOIN {s}.membership_roles r ON r.membership_id=m.id AND r.workspace_id=m.workspace_id WHERE m.workspace_id=:w GROUP BY m.id,u.full_name ORDER BY u.full_name",
        w=a.id,
    )
    result["policy"] = db.first(
        "SELECT * FROM {s}.makeup_policies WHERE workspace_id=:w", w=a.id
    )
    if not a.roles.intersection(MANAGERS):
        programs = {
            r["program_id"]
            for r in result["program_teachers"]
            if r["membership_id"] == a.member["id"]
        }
        sessions = {
            r["session_id"]
            for r in result["session_teachers"]
            if r["membership_id"] == a.member["id"]
        }
        result["sessions"] = [r for r in result["sessions"] if r["id"] in sessions]
        enrollment_programs = programs.copy()
        programs.update(r["program_id"] for r in result["sessions"])
        result["programs"] = [r for r in result["programs"] if r["id"] in programs]
        result["program_teachers"] = [
            r for r in result["program_teachers"] if r["program_id"] in programs
        ]
        result["session_teachers"] = [
            r for r in result["session_teachers"] if r["session_id"] in sessions
        ]
        result["participants"] = [
            r for r in result["participants"] if r["session_id"] in sessions
        ]
        participants = {r["id"] for r in result["participants"]}
        result["enrollments"] = [
            r for r in result["enrollments"] if r["program_id"] in enrollment_programs
        ]
        students = {
            r["student_id"] for r in result["participants"] + result["enrollments"]
        }
        result["students"] = [r for r in result["students"] if r["id"] in students]
        result["student_guardians"] = [
            r for r in result["student_guardians"] if r["student_id"] in students
        ]
        guardians = {r["guardian_id"] for r in result["student_guardians"]}
        result["guardians"] = [r for r in result["guardians"] if r["id"] in guardians]
        result["attendance"] = [
            r for r in result["attendance"] if r["participant_id"] in participants
        ]
        result["entitlements"] = [
            r
            for r in result["entitlements"]
            if r["original_participant_id"] in participants
        ]
        credits = {r["id"] for r in result["entitlements"]}
        result["bookings"] = [
            r
            for r in result["bookings"]
            if r["entitlement_id"] in credits
            and r["replacement_participant_id"] in participants
        ]
    result["invitations"] = (
        db.all(
            "SELECT id,email,proposed_roles,status,expires_at FROM {s}.workspace_invitations WHERE workspace_id=:w ORDER BY created_at DESC",
            w=a.id,
        )
        if a.roles.intersection({"OWNER", "ADMIN"})
        else []
    )
    return result
