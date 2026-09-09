from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATA_DIR

DATABASE_PATH = DATA_DIR / "classarit.db"
DATABASE_URL = URL.create("sqlite", database=str(DATABASE_PATH))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
