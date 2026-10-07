"""Manual, read-only benchmark of workspace projections against configured storage."""
import time
from app.main import app  # Load configured environment; do not start application jobs.
from app.auth.database import auth_engine
from app.workspaces.db import Store
from app.workspaces.access import Access
from app.workspaces.services import queries, overview


def main():
    with auth_engine().connect() as conn:
        db = Store(conn)
        workspace = db.first("SELECT * FROM {s}.workspaces WHERE status='ACTIVE' ORDER BY created_at DESC LIMIT 1")
        if not workspace:
            print('No active workspace to benchmark.')
            return
        user = db.first('SELECT * FROM {s}.app_users WHERE id=:id', id=workspace['owner_user_id'])
        member = db.first("SELECT * FROM {s}.workspace_memberships WHERE workspace_id=:w AND user_id=:u AND status='ACTIVE'", w=workspace['id'], u=user['id'])
        roles = {r['role'] for r in db.all('SELECT role FROM {s}.membership_roles WHERE membership_id=:m AND workspace_id=:w', m=member['id'], w=workspace['id'])}
        access = Access(db, workspace, member, roles, user)
        execute = db.execute
        count = 0
        def counted(*args, **kwargs):
            nonlocal count
            count += 1
            return execute(*args, **kwargs)
        db.execute = counted
        for page in ['dashboard', 'calendar', 'classes', 'students', 'sessions', 'venues', 'settings', 'reporting', 'account']:
            count = 0
            start = time.perf_counter()
            if page == 'account':
                overview.dashboard_data(db, user)
            else:
                queries.section(access, page)
            print(f'{page}: {time.perf_counter()-start:.2f}s, {count} queries', flush=True)
        conn.rollback()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Benchmark failed:', type(error).__name__)
        raise SystemExit(1)
