import logging
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DataError, OperationalError
from ..auth.database import auth_engine, schema_name

logger = logging.getLogger(__name__)


class Store:
    """Small explicit SQL boundary. Identifiers below are internal constants only."""

    def __init__(self, connection):
        self.connection = connection
        self.schema = schema_name()

    def execute(self, sql, **params):
        return self.connection.execute(text(sql.replace("{s}", self.schema)), params)

    def all(self, sql, **params):
        return [dict(row) for row in self.execute(sql, **params).mappings()]

    def first(self, sql, **params):
        row = self.execute(sql, **params).mappings().first()
        return dict(row) if row else None

    def get(self, table, workspace_id, row_id):
        row = self.first(
            f"SELECT * FROM {{s}}.{table} WHERE workspace_id=:w AND id=:id",
            w=workspace_id,
            id=row_id,
        )
        if not row:
            raise HTTPException(404, "Record not found in this workspace.")
        return row

    def insert(self, table, **fields):
        fields.setdefault("id", uuid4())
        columns = ",".join(fields)
        values = ",".join(":" + key for key in fields)
        return self.first(
            f"INSERT INTO {{s}}.{table} ({columns}) VALUES ({values}) RETURNING *",
            **fields,
        )


def transaction():
    try:
        with auth_engine().begin() as connection:
            yield Store(connection)
    except OperationalError as error:
        logger.error(
            "Workspace database unavailable: sqlstate=%s",
            getattr(error.orig, "sqlstate", None),
        )
        raise HTTPException(
            503, "Workspace storage is temporarily unavailable. Please retry."
        ) from error
    except IntegrityError as error:
        logger.warning(
            "Workspace constraint conflict: %s",
            getattr(getattr(error.orig, "diag", None), "constraint_name", None),
        )
        raise HTTPException(
            409,
            "This change conflicts with an existing record or relationship. Check duplicates and selected records.",
        ) from error
    except DataError as error:
        raise HTTPException(
            422, "One or more values are invalid for this record."
        ) from error
