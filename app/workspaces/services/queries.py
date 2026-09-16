"""Dashboard projection. Teacher-only memberships see assigned teaching records."""

from datetime import date, datetime, timezone
import re
from zoneinfo import ZoneInfo
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
        "recurring_series": "recurring_session_series",
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
        series_ids = {r["recurring_series_id"] for r in result["sessions"] if r.get("recurring_series_id")}
        result["recurring_series"] = [r for r in result["recurring_series"] if r["id"] in series_ids]
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
        # A teacher sees class/session details, not company-wide catalog or policies.
        activity_ids = {r["activity_id"] for r in result["programs"]}
        venue_ids = {r["venue_id"] for r in result["sessions"]} | {
            r["default_venue_id"] for r in result["programs"]
        }
        member_ids = {
            r["membership_id"]
            for r in result["session_teachers"] + result["program_teachers"]
        } | {a.member["id"]}
        result["activities"] = [
            r for r in result["activities"] if r["id"] in activity_ids
        ]
        result["venues"] = [r for r in result["venues"] if r["id"] in venue_ids]
        result["spaces"] = [r for r in result["spaces"] if r["venue_id"] in venue_ids]
        result["members"] = [r for r in result["members"] if r["id"] in member_ids]
        result["policy"] = None
        result["entitlements"] = []
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


def calendar_month(a, month):
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        from fastapi import HTTPException

        raise HTTPException(422, "Month must use YYYY-MM format.")
    first = date.fromisoformat(f"{month}-01")
    next_month = (
        date(first.year + 1, 1, 1)
        if first.month == 12
        else date(first.year, first.month + 1, 1)
    )
    last = date.fromordinal(next_month.toordinal() - 1)
    params = {
        "w": a.id,
        "tz": a.workspace["timezone"],
        "first": first,
        "last": last,
        "m": a.member["id"],
    }
    teacher_clause = ""
    if not a.roles.intersection(MANAGERS):
        teacher_clause = """
        AND EXISTS (
            SELECT 1 FROM {s}.session_teachers st
            WHERE st.workspace_id=s.workspace_id
              AND st.session_id=s.id
              AND st.membership_id=:m
        )
        """
    sessions = a.db.all(
        f"""SELECT s.*
        FROM {{s}}.class_sessions s
        WHERE s.workspace_id=:w
          AND s.status IN ('SCHEDULED','COMPLETED')
          AND (s.starts_at AT TIME ZONE :tz)::date <= :last
          AND ((s.ends_at - interval '1 millisecond') AT TIME ZONE :tz)::date >= :first
          {teacher_clause}
        ORDER BY s.starts_at""",
        **params,
    )
    return {"month": month, "sessions": sessions}


SECTION_TABLE_KEYS = {
    "activities": "activities",
    "venues": "venues",
    "spaces": "venue_spaces",
    "programs": "teaching_programs",
    "program_teachers": "program_teachers",
    "students": "students",
    "enrollments": "enrollments",
    "sessions": "class_sessions",
    "recurring_series": "recurring_session_series",
    "session_teachers": "session_teachers",
    "participants": "session_participants",
    "attendance": "attendance",
    "entitlements": "makeup_entitlements",
    "bookings": "makeup_bookings",
    "guardians": "guardians",
    "student_guardians": "student_guardians",
}


def _blank(a):
    result = {
        "workspace": a.workspace,
        "roles": sorted(a.roles),
        "membership_id": a.member["id"],
        "policy": None,
        "invitations": [],
        "members": [],
        "metrics": {},
    }
    for key in SECTION_TABLE_KEYS:
        result[key] = []
    return result


def _all(a, table, order="id"):
    return a.db.all(
        f"SELECT * FROM {{s}}.{table} WHERE workspace_id=:w ORDER BY {order}",
        w=a.id,
    )


def _active_students(a):
    return a.db.all(
        "SELECT * FROM {s}.students WHERE workspace_id=:w AND status='ACTIVE' ORDER BY full_name",
        w=a.id,
    )


def _members(a):
    return a.db.all(
        "SELECT m.id,m.status,u.full_name,array_agg(r.role ORDER BY r.role) roles "
        "FROM {s}.workspace_memberships m "
        "JOIN {s}.app_users u ON u.id=m.user_id "
        "JOIN {s}.membership_roles r ON r.membership_id=m.id AND r.workspace_id=m.workspace_id "
        "WHERE m.workspace_id=:w GROUP BY m.id,u.full_name ORDER BY u.full_name",
        w=a.id,
    )


def _teacher_programs(a):
    return a.db.all(
        """SELECT DISTINCT p.*
        FROM {s}.teaching_programs p
        LEFT JOIN {s}.program_teachers pt
          ON pt.workspace_id=p.workspace_id AND pt.program_id=p.id AND pt.membership_id=:m
        LEFT JOIN {s}.class_sessions cs
          ON cs.workspace_id=p.workspace_id AND cs.program_id=p.id
        LEFT JOIN {s}.session_teachers st
          ON st.workspace_id=cs.workspace_id AND st.session_id=cs.id AND st.membership_id=:m
        WHERE p.workspace_id=:w AND (pt.membership_id IS NOT NULL OR st.membership_id IS NOT NULL)
        ORDER BY p.name""",
        w=a.id,
        m=a.member["id"],
    )


def _programs(a):
    return _all(a, "teaching_programs", "name") if a.roles.intersection(MANAGERS) else _teacher_programs(a)


def _program_ids(rows):
    return {r["id"] for r in rows}


def _sessions(a, include_history=False):
    history_filter = "" if include_history else "AND s.status='SCHEDULED' AND s.ends_at>=CURRENT_TIMESTAMP"
    teacher_clause = ""
    params = {"w": a.id, "m": a.member["id"]}
    if not a.roles.intersection(MANAGERS):
        teacher_clause = """
        AND EXISTS (
            SELECT 1 FROM {s}.session_teachers st
            WHERE st.workspace_id=s.workspace_id
              AND st.session_id=s.id
              AND st.membership_id=:m
        )
        """
    return a.db.all(
        f"""SELECT s.* FROM {{s}}.class_sessions s
        WHERE s.workspace_id=:w {history_filter} {teacher_clause}
        ORDER BY s.starts_at""",
        **params,
    )


def _rows_for_ids(rows, key, ids):
    return [r for r in rows if r.get(key) in ids]


def _action_refs(a, result):
    # Small reference data needed by the header Quick Add buttons. Managers can create
    # sessions from every tab without forcing a full workspace snapshot first.
    if a.roles.intersection(MANAGERS):
        if not result["programs"]:
            result["programs"] = _programs(a)
        if not result["members"]:
            result["members"] = _members(a)
        if not result["venues"]:
            result["venues"] = _all(a, "venues", "name")
        if not result["spaces"]:
            result["spaces"] = _all(a, "venue_spaces", "name")
        if not result["students"]:
            result["students"] = _active_students(a)
    return result


def _load_policy(a, result):
    result["policy"] = a.db.first(
        "SELECT * FROM {s}.makeup_policies WHERE workspace_id=:w", w=a.id
    )


def section(a, tab, month=None, history=False):
    from fastapi import HTTPException

    allowed = {"calendar", "classes", "students", "sessions", "venues", "team", "makeups", "reporting"}
    if tab not in allowed:
        raise HTTPException(404, "Workspace section not found.")
    if tab == "reporting" and "OWNER" not in a.roles:
        raise HTTPException(403, "Only the workspace owner can view reporting.")

    result = _blank(a)
    _action_refs(a, result)

    if tab == "calendar":
        month_key = month
        if not month_key:
            month_key = datetime.now(timezone.utc).astimezone(ZoneInfo(a.workspace["timezone"])).strftime("%Y-%m")
        calendar = calendar_month(a, month_key)
        result["calendar"] = calendar
        result["sessions"] = calendar["sessions"]
        _load_policy(a, result)
        return result

    if tab == "classes":
        result["programs"] = _programs(a)
        program_ids = _program_ids(result["programs"])
        result["activities"] = _rows_for_ids(_all(a, "activities", "name"), "id", {r["activity_id"] for r in result["programs"]})
        result["program_teachers"] = _rows_for_ids(_all(a, "program_teachers", "program_id"), "program_id", program_ids)
        result["enrollments"] = _rows_for_ids(_all(a, "enrollments"), "program_id", program_ids)
        if a.roles.intersection(MANAGERS):
            result["students"] = _active_students(a)
        return result

    if tab == "students":
        if not a.roles.intersection(MANAGERS):
            raise HTTPException(403, "This section is not available for your role.")
        result["students"] = _all(a, "students", "full_name")
        student_ids = {r["id"] for r in result["students"]}
        result["student_guardians"] = _rows_for_ids(_all(a, "student_guardians", "student_id"), "student_id", student_ids)
        guardian_ids = {r["guardian_id"] for r in result["student_guardians"]}
        result["guardians"] = _rows_for_ids(_all(a, "guardians", "full_name"), "id", guardian_ids)
        result["enrollments"] = _all(a, "enrollments")
        if not result["programs"]:
            result["programs"] = _programs(a)
        return result

    if tab == "sessions":
        result["history_included"] = bool(history)
        result["sessions"] = _sessions(a, include_history=history)
        session_ids = {r["id"] for r in result["sessions"]}
        program_ids = {r["program_id"] for r in result["sessions"]}
        if not result["programs"]:
            result["programs"] = _rows_for_ids(_programs(a), "id", program_ids)
        result["recurring_series"] = _rows_for_ids(_all(a, "recurring_session_series", "start_date"), "id", {r["recurring_series_id"] for r in result["sessions"] if r.get("recurring_series_id")})
        result["participants"] = _rows_for_ids(_all(a, "session_participants"), "session_id", session_ids)
        participant_ids = {r["id"] for r in result["participants"]}
        student_ids = {r["student_id"] for r in result["participants"]}
        if a.roles.intersection(MANAGERS):
            result["students"] = _active_students(a)
        else:
            result["students"] = _rows_for_ids(_all(a, "students", "full_name"), "id", student_ids)
        result["attendance"] = _rows_for_ids(_all(a, "attendance"), "participant_id", participant_ids)
        _load_policy(a, result)
        return result

    if tab == "venues":
        if not a.roles.intersection(MANAGERS):
            raise HTTPException(403, "This section is not available for your role.")
        result["venues"] = _all(a, "venues", "name")
        result["spaces"] = _all(a, "venue_spaces", "name")
        return result

    if tab == "team":
        if not a.roles.intersection({"OWNER", "ADMIN"}):
            raise HTTPException(403, "This section is not available for your role.")
        result["members"] = _members(a)
        result["invitations"] = a.db.all(
            "SELECT id,email,proposed_roles,status,expires_at FROM {s}.workspace_invitations WHERE workspace_id=:w ORDER BY created_at DESC",
            w=a.id,
        )
        return result

    if tab == "makeups":
        if not a.roles.intersection(MANAGERS):
            raise HTTPException(403, "This section is not available for your role.")
        _load_policy(a, result)
        result["entitlements"] = _all(a, "makeup_entitlements")
        result["bookings"] = _all(a, "makeup_bookings")
        result["students"] = _active_students(a)
        result["participants"] = _all(a, "session_participants")
        result["sessions"] = _sessions(a)
        if not result["programs"]:
            result["programs"] = _programs(a)
        return result

    if tab == "reporting":
        result["metrics"] = {
            "students": a.db.first("SELECT count(*) n FROM {s}.students WHERE workspace_id=:w AND status='ACTIVE'", w=a.id)["n"],
            "classes": a.db.first("SELECT count(*) n FROM {s}.teaching_programs WHERE workspace_id=:w AND status='ACTIVE'", w=a.id)["n"],
            "upcoming_sessions": a.db.first("SELECT count(*) n FROM {s}.class_sessions WHERE workspace_id=:w AND status='SCHEDULED' AND starts_at>CURRENT_TIMESTAMP", w=a.id)["n"],
            "teachers": a.db.first("""SELECT count(DISTINCT m.id) n
                FROM {s}.workspace_memberships m
                JOIN {s}.membership_roles r ON r.workspace_id=m.workspace_id AND r.membership_id=m.id AND r.role='TEACHER'
                WHERE m.workspace_id=:w AND m.status='ACTIVE'""", w=a.id)["n"],
        }
        return result

    return result
