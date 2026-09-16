"""Account dashboard projections: owner aggregates and assigned staff classes."""

from .organizations import memberships


def dashboard_data(db, user):
    choices = memberships(db, user)
    owned = [w for w in choices if str(w["owner_user_id"]) == str(user["id"])]
    assigned = [w for w in choices if str(w["owner_user_id"]) != str(user["id"])]
    # Each count is computed before joining programs, avoiding enrollment/roster fan-out.
    programs = db.all(
        """
        WITH owned AS (
            SELECT id,timezone FROM {s}.workspaces
            WHERE owner_user_id=:u AND status='ACTIVE'
        ), current_students AS (
            SELECT e.workspace_id,e.program_id,e.student_id
            FROM {s}.enrollments e JOIN owned w ON w.id=e.workspace_id
            JOIN {s}.students st ON st.workspace_id=e.workspace_id AND st.id=e.student_id AND st.status='ACTIVE'
            WHERE e.status='ACTIVE' AND e.starts_on<=(CURRENT_TIMESTAMP AT TIME ZONE w.timezone)::date
                AND (e.ends_on IS NULL OR e.ends_on>=(CURRENT_TIMESTAMP AT TIME ZONE w.timezone)::date)
            UNION
            SELECT p.workspace_id,p.program_id,p.student_id
            FROM {s}.session_participants p JOIN owned w ON w.id=p.workspace_id
            JOIN {s}.class_sessions s ON s.workspace_id=p.workspace_id AND s.id=p.session_id
            JOIN {s}.teaching_programs t ON t.workspace_id=p.workspace_id AND t.id=p.program_id
            JOIN {s}.students st ON st.workspace_id=p.workspace_id AND st.id=p.student_id AND st.status='ACTIVE'
            WHERE t.program_kind='EVENT' AND p.status='BOOKED' AND s.status='SCHEDULED' AND s.starts_at>CURRENT_TIMESTAMP
        ), students AS (
            SELECT workspace_id,program_id,count(DISTINCT student_id) students
            FROM current_students GROUP BY workspace_id,program_id
        ), usage AS (
            SELECT s.workspace_id,s.program_id,count(*) completed_sessions
            FROM {s}.class_sessions s JOIN owned w ON w.id=s.workspace_id
            WHERE s.status='COMPLETED' AND s.ends_at>=CURRENT_TIMESTAMP-interval '30 days'
                AND s.ends_at<=CURRENT_TIMESTAMP GROUP BY s.workspace_id,s.program_id
        )
        SELECT p.id,p.workspace_id,p.name,p.program_kind,p.status,
            COALESCE(st.students,0) students, COALESCE(us.completed_sessions,0) completed_sessions
        FROM {s}.teaching_programs p JOIN owned w ON w.id=p.workspace_id
        LEFT JOIN students st ON st.workspace_id=p.workspace_id AND st.program_id=p.id
        LEFT JOIN usage us ON us.workspace_id=p.workspace_id AND us.program_id=p.id
        ORDER BY students DESC,p.name,p.id
        """,
        u=user["id"],
    )
    teacher_rows = db.all("""SELECT DISTINCT m.workspace_id,m.user_id
        FROM {s}.workspace_memberships m
        JOIN {s}.workspaces w ON w.id=m.workspace_id AND w.owner_user_id=:u AND w.status='ACTIVE'
        JOIN {s}.membership_roles r ON r.workspace_id=m.workspace_id AND r.membership_id=m.id AND r.role='TEACHER'
        JOIN {s}.app_users u ON u.id=m.user_id AND u.status='ACTIVE'
        WHERE m.status='ACTIVE'""",u=user['id'])
    for workspace in owned:
        workspace['teacher_count'] = len({r['user_id'] for r in teacher_rows if r['workspace_id']==workspace['id']})
        workspace["programs"] = [
            p for p in programs if p["workspace_id"] == workspace["id"]
        ]
        workspace["student_count"] = db.first(
            "SELECT count(*) n FROM {s}.students WHERE workspace_id=:w AND status='ACTIVE'",
            w=workspace["id"],
        )["n"]
        workspace["upcoming_sessions"] = db.first(
            "SELECT count(*) n FROM {s}.class_sessions WHERE workspace_id=:w AND status='SCHEDULED' AND starts_at>CURRENT_TIMESTAMP",
            w=workspace["id"],
        )["n"]
        workspace["popular"] = sorted(
            [
                p
                for p in workspace["programs"]
                if p["status"] == "ACTIVE" and p["students"] > 0
            ],
            key=lambda p: (-p["students"], p["name"]),
        )[:3]
        workspace["most_used"] = sorted(
            [p for p in workspace["programs"] if p["completed_sessions"] > 0],
            key=lambda p: (-p["completed_sessions"], p["name"]),
        )[:3]
    for workspace in assigned:
        manager = bool(set(workspace["roles"]) & {"ADMIN", "OPERATOR"})
        workspace["can_manage"] = manager
        workspace["classes"] = db.all(
            """SELECT p.id,p.name,p.program_kind,
            (SELECT count(*) FROM {s}.class_sessions s WHERE s.workspace_id=p.workspace_id AND s.program_id=p.id
             AND s.status='SCHEDULED' AND s.starts_at>CURRENT_TIMESTAMP
             AND (:manager OR EXISTS (SELECT 1 FROM {s}.session_teachers st WHERE st.workspace_id=s.workspace_id AND st.session_id=s.id AND st.membership_id=:m))) upcoming_sessions
            FROM {s}.teaching_programs p WHERE p.workspace_id=:w AND (
                :manager OR EXISTS (SELECT 1 FROM {s}.program_teachers pt WHERE pt.workspace_id=p.workspace_id AND pt.program_id=p.id AND pt.membership_id=:m)
                OR EXISTS (SELECT 1 FROM {s}.class_sessions s JOIN {s}.session_teachers st ON st.workspace_id=s.workspace_id AND st.session_id=s.id
                    WHERE s.workspace_id=p.workspace_id AND s.program_id=p.id AND st.membership_id=:m)
            ) ORDER BY p.name""",
            w=workspace["id"],
            m=workspace["membership_id"],
            manager=manager,
        )
    return {
        "owned_workspaces": owned,
        "assigned_workspaces": assigned,
        "totals": {
            "workspaces": len(owned),
            "students": sum(w["student_count"] for w in owned),
            "classes": sum(len(w["programs"]) for w in owned),
            "active_teachers": len({r["user_id"] for r in teacher_rows}),
        },
        "can_create": user["user_type"] == "OWNER"
        or not db.first(
            "SELECT 1 FROM {s}.workspace_memberships WHERE user_id=:u", u=user["id"]
        ),
        "is_owner": user["user_type"] == "OWNER",
    }
