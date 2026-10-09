from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
