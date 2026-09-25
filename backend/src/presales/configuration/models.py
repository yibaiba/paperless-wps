from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from presales.storage import Base, identifier, now


class Entity(Base):
    __tablename__ = "configuration_entities"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    kind: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Revision(Base):
    __tablename__ = "configuration_revisions"
    __table_args__ = (UniqueConstraint("entity_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    entity_id: Mapped[str] = mapped_column(ForeignKey("configuration_entities.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SourceLink(Base):
    __tablename__ = "configuration_source_links"
    source_id: Mapped[str] = mapped_column(ForeignKey("product_records.id"), primary_key=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("configuration_entities.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    actor: Mapped[str] = mapped_column(String)
    evidence: Mapped[str] = mapped_column(String)


class ExtractionJob(Base):
    __tablename__ = "configuration_extraction_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    status: Mapped[str] = mapped_column(String, index=True, default="queued")
    payload: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SourceRevision(Base):
    __tablename__ = "configuration_source_revisions"
    __table_args__ = (UniqueConstraint("source_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    source_id: Mapped[str] = mapped_column(ForeignKey("product_records.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


SEARCH_EMBEDDING_DIMENSIONS = 1024


class SearchDocument(Base):
    __tablename__ = "configuration_search_documents"
    variant_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_entities.id"), primary_key=True
    )
    variant_revision: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String, index=True)
    document: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(String, index=True)
    embedding_dimensions: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(SEARCH_EMBEDDING_DIMENSIONS).with_variant(JSON(), "sqlite"), nullable=True
    )
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SearchIndexJob(Base):
    __tablename__ = "configuration_search_index_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    status: Mapped[str] = mapped_column(String, index=True, default="queued")
    payload: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
