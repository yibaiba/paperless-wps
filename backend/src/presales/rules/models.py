from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from presales.storage import Base, identifier, now


class AccessoryRule(Base):
    __tablename__ = "accessory_rules"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RuleRevision(Base):
    __tablename__ = "rule_revisions"
    __table_args__ = (UniqueConstraint("rule_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    rule_id: Mapped[str] = mapped_column(ForeignKey("accessory_rules.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RuleApplication(Base):
    __tablename__ = "rule_applications"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    calculation: Mapped[dict] = mapped_column(JSON)
    item_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
