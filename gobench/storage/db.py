from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from gobench.storage.models import Base


def database_url(path: str | None = None) -> str:
    db_path = path or os.getenv("GOBENCH_DB", "./data/gobench.sqlite")
    return f"sqlite:///{db_path}"


def create_session_factory(path: str | None = None) -> sessionmaker[Session]:
    db_path = path or os.getenv("GOBENCH_DB", "./data/gobench.sqlite")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url(db_path), connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


SessionLocal = create_session_factory()


def get_session() -> Session:
    with SessionLocal() as session:
        yield session
