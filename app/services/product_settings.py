"""Runtime product toggles for auth, signup and notification features."""

import logging
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..auth.database import auth_engine, schema_name

logger = logging.getLogger(__name__)

DEFAULTS = {
    "google_new_accounts_enabled": True,
    "signup_enabled": True,
    "notification_emails_enabled": True,
}


def _bool(value, default=True):
    if value is None:
        return default
    return str(value).lower() == "true"


def setting_enabled(key, default=None):
    if default is None:
        default = DEFAULTS.get(key, True)
    if key not in DEFAULTS:
        return default
    try:
        with auth_engine().connect() as conn:
            row = conn.execute(
                text(f"SELECT value FROM {schema_name()}.app_settings WHERE key=:key"),
                {"key": key},
            ).first()
            return _bool(row[0] if row else None, default)
    except SQLAlchemyError:
        # During rollout, old databases must keep existing login behavior until the
        # migration is applied. The executive page will surface the missing table.
        logger.debug("Product setting %s unavailable; using default", key)
        return default


def all_settings(conn=None):
    values = {key: DEFAULTS[key] for key in DEFAULTS}
    close = False
    if conn is None:
        conn = auth_engine().connect()
        close = True
    try:
        rows = conn.execute(
            text(f"SELECT key,value FROM {schema_name()}.app_settings")
        ).mappings()
        for row in rows:
            if row["key"] in values:
                values[row["key"]] = _bool(row["value"], values[row["key"]])
    finally:
        if close:
            conn.close()
    return values


def set_settings(updates, user_id):
    allowed = {key: bool(value) for key, value in updates.items() if key in DEFAULTS}
    if not allowed:
        return all_settings()
    with auth_engine().begin() as conn:
        for key, value in allowed.items():
            conn.execute(
                text(
                    f"""INSERT INTO {schema_name()}.app_settings(key,value,updated_by)
                    VALUES (:key,:value,:user)
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,updated_by=EXCLUDED.updated_by"""
                ),
                {"key": key, "value": "true" if value else "false", "user": user_id},
            )
        return all_settings(conn)
