"""Plain-text product terms; HTML is never accepted or rendered as trusted markup."""
import hashlib
from sqlalchemy import text
from ..auth.database import auth_engine, schema_name

DEFAULT_BODY = '''Classarit is provided as an early access teaching management tool. Information in the app is for organizing classes, schedules, students and workspace operations, and is not legal, tax, financial, medical or professional advice.

You are responsible for the accuracy of the information you enter, for getting any consent needed before adding another person's information, and for using the service lawfully. Do not upload unlawful, harmful or sensitive information that you do not have permission to store.

The service may change, pause or lose availability during testing. Data may be corrected, removed or reset while the product is under development. Use your own records as the source of truth for payments, attendance and compliance until formal launch terms are published.

Classarit is provided without warranties during this demo period. To the extent allowed by law, liability is limited to stopping use of the service. Final commercial terms, privacy policy and compliance wording should be reviewed by a qualified attorney before public launch.'''


def terms():
    with auth_engine().connect() as conn:
        row = conn.execute(text(f"SELECT title,body FROM {schema_name()}.app_content WHERE key='terms'" )).mappings().first()
    value = dict(row) if row else {'title': 'Classarit terms and conditions', 'body': DEFAULT_BODY}
    value['version'] = hashlib.sha256((value['title']+'\n'+value['body']).encode()).hexdigest()
    return value


def terms_context(request):
    value = terms()
    request.session['terms_version'] = value['version']
    return value


def save_terms(title, body, user_id):
    with auth_engine().begin() as conn:
        conn.execute(text(f"""INSERT INTO {schema_name()}.app_content(key,title,body,updated_by)
            VALUES ('terms',:title,:body,:user)
            ON CONFLICT(key) DO UPDATE SET title=EXCLUDED.title,body=EXCLUDED.body,
                updated_by=EXCLUDED.updated_by,updated_at=CURRENT_TIMESTAMP"""),
            {'title': title, 'body': body, 'user': user_id})
    return terms()
