"""Email notifications for invitations, staff changes and scheduled students."""

from collections import defaultdict
from html import escape
from starlette.background import BackgroundTasks

from .emailer import paragraph, send_email_safely
from .product_settings import setting_enabled


def _queue(background_tasks: BackgroundTasks | None, to, subject, html, text=None):
    if not setting_enabled("notification_emails_enabled", True):
        return
    if background_tasks is not None:
        background_tasks.add_task(send_email_safely, to, subject, html, text)
    else:
        send_email_safely(to, subject, html, text)


def send_registration_otp(background_tasks: BackgroundTasks | None, email, full_name, code):
    subject = "Your Classarit verification code"
    html = (
        "<h2>Your Classarit verification code</h2>"
        + paragraph(f"Hi {full_name or 'there'},")
        + paragraph("Use this code to finish creating your Classarit account. It expires in 10 minutes.")
        + f"<p style='font-size:28px;font-weight:700;letter-spacing:4px'>{escape(code)}</p>"
    )
    text = f"Your Classarit verification code is {code}. It expires in 10 minutes."
    if background_tasks is not None:
        background_tasks.add_task(send_email_safely, email, subject, html, text)
    else:
        send_email_safely(email, subject, html, text)


def send_invitation(background_tasks, email, workspace_name, invite_url, roles, expires_hours=72):
    role_text = ", ".join(roles)
    subject = f"Join {workspace_name} on Classarit"
    html = (
        f"<h2>{escape(workspace_name)} invited you to Classarit</h2>"
        + paragraph(f"Role: {role_text}")
        + paragraph(f"This invitation expires in {expires_hours} hours.")
        + f"<p><a href='{escape(invite_url)}'>Accept invitation</a></p>"
    )
    text = f"Join {workspace_name} on Classarit as {role_text}. This invitation expires in {expires_hours} hours: {invite_url}"
    _queue(background_tasks, email, subject, html, text)


def send_staff_change(background_tasks, email, workspace_name, full_name, change):
    subject = f"Your {workspace_name} access was updated"
    html = f"<h2>Classarit access update</h2>{paragraph(f'Hi {full_name or email},')}{paragraph(change)}{paragraph(f'Workspace: {workspace_name}')}"
    _queue(background_tasks, email, subject, html, f"{change}\nWorkspace: {workspace_name}")


def _recipient_rows(a, session_ids):
    rows = []
    for session_id in session_ids:
        rows.extend(
            a.db.all(
                """SELECT st.id AS student_id, st.full_name AS student_name, st.email AS student_email,
                          g.email AS guardian_email, cs.title, cs.starts_at, cs.ends_at, p.name AS program_name
                FROM {s}.session_participants sp
                JOIN {s}.students st ON st.workspace_id=sp.workspace_id AND st.id=sp.student_id
                JOIN {s}.class_sessions cs ON cs.workspace_id=sp.workspace_id AND cs.id=sp.session_id
                JOIN {s}.teaching_programs p ON p.workspace_id=cs.workspace_id AND p.id=cs.program_id
                LEFT JOIN {s}.student_guardians sg ON sg.workspace_id=st.workspace_id AND sg.student_id=st.id AND sg.is_primary
                LEFT JOIN {s}.guardians g ON g.workspace_id=sg.workspace_id AND g.id=sg.guardian_id
                WHERE sp.workspace_id=:w AND sp.session_id=:session AND sp.status='BOOKED'""",
                w=a.id,
                session=session_id,
            )
        )
    return rows


def send_student_schedule_notice(background_tasks, a, session_ids, action="added"):
    if not session_ids:
        return
    grouped = defaultdict(list)
    for row in _recipient_rows(a, session_ids):
        recipients = list(dict.fromkeys([row.get("student_email"), row.get("guardian_email")]))
        recipients = [email for email in recipients if email]
        if not recipients:
            continue
        grouped[(row["student_id"], tuple(recipients))].append(row)
    verb = "added to" if action == "added" else "removed from"
    for (_student_id, recipients), rows in grouped.items():
        first = rows[0]
        subject = f"Schedule update for {first['student_name']}"
        html = (
            f"<h2>{escape(first['student_name'])} was {escape(verb)} a schedule</h2>"
            + paragraph(f"Workspace: {a.workspace['name']}")
            + paragraph(f"Class: {first['program_name']}")
            + paragraph(f"Sessions affected: {len(rows)}")
            + paragraph(f"First session: {first['starts_at']}")
        )
        text = f"{first['student_name']} was {verb} a schedule in {a.workspace['name']}. Class: {first['program_name']}. Sessions affected: {len(rows)}."
        _queue(background_tasks, recipients, subject, html, text)
