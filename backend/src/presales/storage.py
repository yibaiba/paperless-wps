from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def identifier() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class CatalogImport(Base):
    __tablename__ = "catalog_imports"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    filename: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sheets: Mapped[list] = mapped_column(JSON)
    record_count: Mapped[int] = mapped_column(Integer)
    issue_count: Mapped[int] = mapped_column(Integer)


class ProductRecord(Base):
    __tablename__ = "product_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    import_id: Mapped[str] = mapped_column(ForeignKey("catalog_imports.id"), index=True)
    model: Mapped[str] = mapped_column(Text, index=True)
    name: Mapped[str] = mapped_column(Text)
    sheet: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)


class ReviewIssue(Base):
    __tablename__ = "review_issues"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    import_id: Mapped[str] = mapped_column(ForeignKey("catalog_imports.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (UniqueConstraint("issue_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    issue_id: Mapped[str] = mapped_column(ForeignKey("review_issues.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectItem(Base):
    __tablename__ = "project_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("product_records.id"))
    quantity: Mapped[str] = mapped_column(String)
    group_name: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)


def database_factory(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
