"""Temporary executive maintenance actions."""

from sqlalchemy import text

from ..auth.database import auth_engine, schema_name
from .product_settings import DEFAULTS

PRESERVED_TABLES = {"schema_migrations", "user_terms_acceptances"}


def flush_application_data():
    """Delete app/auth data while keeping migration and terms audit history."""
    schema = schema_name()
    with auth_engine().begin() as conn:
        table_rows = conn.execute(
            text(
                """SELECT tablename FROM pg_tables
                WHERE schemaname=:schema
                ORDER BY tablename"""
            ),
            {"schema": schema},
        ).mappings()
        tables = [row["tablename"] for row in table_rows if row["tablename"] not in PRESERVED_TABLES]
        if tables:
            quoted = ", ".join(f'"{schema}"."{table}"' for table in tables)
            conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
        for key, value in DEFAULTS.items():
            conn.execute(
                text(
                    f"""INSERT INTO {schema}.app_settings(key,value)
                    VALUES (:key,:value)
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,updated_by=NULL"""
                ),
                {"key": key, "value": "true" if value else "false"},
            )
        return {"truncated_tables": tables}


def delete_terms_acceptance_audit():
    schema = schema_name()
    with auth_engine().begin() as conn:
        deleted = conn.execute(
            text(f"DELETE FROM {schema}.user_terms_acceptances")
        ).rowcount
    return {"deleted_terms_acceptances": deleted or 0}
