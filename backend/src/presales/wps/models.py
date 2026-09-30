from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from presales.storage import Base, identifier, now


class WpsPairing(Base):
    __tablename__ = "wps_pairings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    code_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    actor: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WpsAccessToken(Base):
    __tablename__ = "wps_access_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    actor: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WpsSuggestionFeedback(Base):
    __tablename__ = "wps_suggestion_feedback"
    __table_args__ = (Index("ix_wps_feedback_actor_previous", "actor", "previous_variant_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    operation_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    actor: Mapped[str] = mapped_column(Text)
    workbook_instance_id: Mapped[str] = mapped_column(String, index=True)
    template_profile_id: Mapped[str] = mapped_column(String, index=True)
    template_profile_revision: Mapped[int] = mapped_column(Integer)
    context_hash: Mapped[str] = mapped_column(String, index=True)
    previous_variant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_variant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    chosen_variant_id: Mapped[str] = mapped_column(String)
    chosen_source_id: Mapped[str] = mapped_column(String)
    query_kind: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WpsDiagnosticEvent(Base):
    __tablename__ = "wps_diagnostic_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    event_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    installation_id: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    plugin_version: Mapped[str] = mapped_column(String)
    host_os: Mapped[str] = mapped_column(String)
    host_version: Mapped[str] = mapped_column(String)
    event_type: Mapped[str] = mapped_column(String, index=True)
    completion_phase: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_ready: Mapped[bool | None] = mapped_column(nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    template_profile_id: Mapped[str | None] = mapped_column(String, nullable=True)
    template_profile_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
