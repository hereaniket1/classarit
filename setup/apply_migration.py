"""Apply one reviewed SQL migration atomically using the app's .env DB settings.
Usage: .venv/bin/python setup/apply_migration.py 001_workspaces_and_teaching.sql
Already-applied migrations are skipped only when their SHA-256 checksum matches.
"""

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.auth.database import auth_engine, schema_name


def apply(filename):
    if schema_name() != "classarit":
        raise RuntimeError("This migration targets the classarit schema.")
    path = ROOT / "setup" / "migrations" / filename
    if (
        path.parent != (ROOT / "setup" / "migrations")
        or path.suffix != ".sql"
        or not path.is_file()
    ):
        raise ValueError("Choose a SQL filename from setup/migrations.")
    source = path.read_text()
    checksum = hashlib.sha256(source.encode()).hexdigest()
    # The reviewed scripts support psql too; the runner owns the outer transaction.
    before, sep, body = source.partition("\nBEGIN;")
    if not sep or not body.rstrip().endswith("COMMIT;"):
        raise ValueError("Expected one outer BEGIN/COMMIT transaction.")
    body = before + "\n" + body.rstrip()[: -len("COMMIT;")]
    connection = auth_engine().raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='5s'")
            cursor.execute("SELECT pg_advisory_xact_lock(724133501)")
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS classarit.schema_migrations (filename text PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            cursor.execute(
                "SELECT sha256 FROM classarit.schema_migrations WHERE filename=%s",
                (filename,),
            )
            previous = cursor.fetchone()
            if previous:
                if previous[0] != checksum:
                    raise RuntimeError(
                        "Applied migration checksum differs; create a new migration instead."
                    )
                connection.rollback()
                print(f"Already applied: {filename} (checksum verified)")
                return
            cursor.execute(body, prepare=False)
            cursor.execute(
                "INSERT INTO classarit.schema_migrations(filename,sha256) VALUES (%s,%s)",
                (filename, checksum),
            )
        connection.commit()
        print(f"Applied: {filename}; schema=classarit; sha256={checksum}")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filename")
    args = parser.parse_args()
    try:
        apply(args.filename)
    except Exception as error:
        # Do not print driver errors/DSNs; credentials are never diagnostic output.
        print(
            f"Migration failed ({type(error).__name__}); transaction rolled back. Check schema prerequisites and migration state.",
            file=sys.stderr,
        )
        sys.exit(1)
