"""Map a PostgreSQL account to its private teaching workspace in SQLite."""
from fastapi import Depends
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth.dependencies import require_legacy_user


def upgrade_local_ownership(engine):
    # Existing demo rows remain NULL-owned and are never assigned to a new login.
    with engine.begin() as conn:
        for table, column, declaration in [
            ('teachers', 'auth_user_id', 'VARCHAR(36)'),
            ('materials', 'teacher_id', 'INTEGER REFERENCES teachers(id)')]:
            if column not in {c['name'] for c in inspect(conn).get_columns(table)}:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}'))
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_teachers_auth_user_id ON teachers(auth_user_id)'))


def get_teacher(db: Session = Depends(get_db), user=Depends(require_legacy_user)):
    teacher = db.query(models.Teacher).filter_by(auth_user_id=user['id']).first()
    if teacher:
        return teacher
    # Identity-owned internal email avoids collisions with pre-existing demo records.
    teacher = models.Teacher(auth_user_id=user['id'], name=user['full_name'] or 'My classroom',
                             email=f"{user['id']}@account.classarit.local")
    db.add(teacher)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(models.Teacher).filter_by(auth_user_id=user['id']).one()
    db.refresh(teacher)
    return teacher
