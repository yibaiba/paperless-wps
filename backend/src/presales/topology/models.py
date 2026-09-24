from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from presales.storage import Base, identifier, now


class Topology(Base):
    __tablename__ = "topologies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TopologyRevision(Base):
    __tablename__ = "topology_revisions"
    __table_args__ = (UniqueConstraint("topology_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    topology_id: Mapped[str] = mapped_column(ForeignKey("topologies.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TopologyRule(Base):
    __tablename__ = "topology_rules"
    __table_args__ = (UniqueConstraint("topology_id", "relation_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    topology_id: Mapped[str] = mapped_column(ForeignKey("topologies.id"), index=True)
    relation_id: Mapped[str] = mapped_column(String)
    topology_revision: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(ForeignKey("accessory_rules.id"))
