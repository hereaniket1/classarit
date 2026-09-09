"""Lazy PostgreSQL connection; authentication never falls back to demo data."""
import os
import re
from functools import lru_cache

from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

from ..config import PROJECT_DIR


def schema_name():
    schema = os.getenv("DB_SCHEMA", "classarit")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ValueError("Invalid DB_SCHEMA")
    return schema


@lru_cache
def auth_engine():
    if not all(os.getenv(key) for key in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")):
        raise RuntimeError("PostgreSQL authentication configuration is incomplete")
    url = URL.create(
        "postgresql+psycopg", username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"], host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")), database=os.environ["DB_NAME"],
    )
    return create_engine(url, poolclass=NullPool, hide_parameters=True,
                         connect_args={"sslmode": os.getenv("DB_SSLMODE", "require"),
                                       "connect_timeout": 8, "prepare_threshold": None})
