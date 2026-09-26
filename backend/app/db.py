import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://mesto:change-me-for-local-development@localhost:5432/mesto",
    )


def create_session_factory(url: str | None = None):
    engine = create_engine(url or database_url(), pool_pre_ping=True)
    return sessionmaker(bind=engine), engine
