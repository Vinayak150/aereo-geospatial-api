"""One transaction stores metadata and all processed feature results."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings


class Base(DeclarativeBase):
    pass


class UploadedFile(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(16))
    feature_count: Mapped[int] = mapped_column(Integer)
    crs: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(16))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    measured_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer)


class Feature(Base):
    __tablename__ = "features"

    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), primary_key=True)
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)


def connect(settings: Settings) -> tuple[Engine, sessionmaker]:
    settings.prepare_database_directory()
    options: dict[str, Any] = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if settings.database_url.endswith(":memory:"):
        options["poolclass"] = StaticPool
    engine = create_engine(settings.database_url, **options)

    @event.listens_for(engine, "connect")
    def pragmas(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)
