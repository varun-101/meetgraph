"""SQLAlchemy 2.0 models for every plan.md §5.1 table.

Owned by api-core (see CONTRACTS.md). Everyone else imports from here:

    from api.models import (User, Org, OrgMember, Project, ProjectMember, Meeting,
                            MeetingGuest, Recording, Transcript, ActionItem, AuditLog)

Conventions (CONTRACTS.md):
- UUIDv4 PKs everywhere (``uuid.UUID`` in Python, string in JSON).
- Timezone-aware timestamps.
- Meeting status enum: scheduled | live | processing | ready.
- Roles: org ``admin|member``; project ``manager|member``.

SQLite compatibility (tests run on aiosqlite): UUIDs use a GUID TypeDecorator
that renders native ``UUID`` on Postgres and ``CHAR(36)`` elsewhere, storing
``str(uuid)`` — the same wire format fastapi-users' own GUID type uses, so
joins against ``users.id`` stay consistent. JSONB is applied as a Postgres
variant of the generic JSON type.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, TypeDecorator

from api.db import Base

# --------------------------------------------------------------------------
# Cross-dialect column types
# --------------------------------------------------------------------------


class GUID(TypeDecorator):
    """Platform-independent UUID: native UUID on Postgres, CHAR(36) elsewhere.

    Stores ``str(uuid)`` (dashed, 36 chars) on non-Postgres backends — the same
    format fastapi-users-db-sqlalchemy's GUID uses for ``users.id``.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return str(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# JSONB on Postgres, plain JSON on SQLite (tests).
JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Enums (stored as plain strings; classes exist for validation/reference)
# --------------------------------------------------------------------------


class OrgRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class ProjectRole(str, enum.Enum):
    manager = "manager"
    member = "member"


class MeetingStatus(str, enum.Enum):
    scheduled = "scheduled"
    live = "live"
    processing = "processing"
    ready = "ready"


class ActionItemStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"


class AuditOp(str, enum.Enum):
    """§4.5: op ∈ {search, add, cognify, forget, export}."""

    search = "search"
    add = "add"
    cognify = "cognify"
    forget = "forget"
    export = "export"


# --------------------------------------------------------------------------
# users — fastapi-users compatible (§5.1: id, email, name, hashed_pw)
# --------------------------------------------------------------------------


class User(SQLAlchemyBaseUserTableUUID, Base):
    """fastapi-users base gives: id (UUID PK), email (unique, indexed),
    hashed_password, is_active, is_superuser, is_verified."""

    __tablename__ = "users"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )


# --------------------------------------------------------------------------
# orgs / org_members
# --------------------------------------------------------------------------


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    members: Mapped[list["OrgMember"]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="org", cascade="all, delete-orphan", passive_deletes=True
    )


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'member')", name="ck_org_members_role"),
        Index("ix_org_members_user_id", "user_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=OrgRole.member.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    org: Mapped["Org"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()


# --------------------------------------------------------------------------
# projects / project_members
# --------------------------------------------------------------------------


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_org_id", "org_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    org: Mapped["Org"] = relationship(back_populates="projects")
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    meetings: Mapped[list["Meeting"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class ProjectMember(Base):
    """org_id is denormalized here on purpose — the §4.4 resolver's single query
    is ``WHERE user_id = ? AND org_id = ?`` and must hit one index."""

    __tablename__ = "project_members"
    __table_args__ = (
        CheckConstraint("role IN ('manager', 'member')", name="ck_project_members_role"),
        Index("ix_project_members_user_org", "user_id", "org_id"),
        Index("ix_project_members_project_id", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ProjectRole.member.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()


# --------------------------------------------------------------------------
# meetings / meeting_guests
# --------------------------------------------------------------------------


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'live', 'processing', 'ready')", name="ck_meetings_status"
        ),
        Index("ix_meetings_project_id", "project_id"),
        Index("ix_meetings_livekit_room", "livekit_room"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    livekit_room: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MeetingStatus.scheduled.value
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="meetings")
    guests: Mapped[list["MeetingGuest"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True
    )
    recordings: Mapped[list["Recording"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True
    )
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True
    )
    action_items: Mapped[list["ActionItem"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True
    )


class MeetingGuest(Base):
    """§4.1 guest role: single-meeting access, expires with the meeting.
    Guests hold zero memory-query capability (§4.3)."""

    __tablename__ = "meeting_guests"
    __table_args__ = (
        Index("ix_meeting_guests_meeting_id", "meeting_id"),
        Index("ix_meeting_guests_token_hash", "token_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="guests")


# --------------------------------------------------------------------------
# recordings / transcripts
# --------------------------------------------------------------------------


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (Index("ix_recordings_meeting_id", "meeting_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    participant_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)  # seconds
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="recordings")


class Transcript(Base):
    """One canonical transcript per meeting (PK = meeting_id).

    ``json_utterances`` format (CONTRACTS.md):
    ``[{"speaker_identity": str, "speaker_name": str, "start": float,
        "end": float, "text": str}, ...]``
    ``canonical_text`` = lines of ``[mm:ss] Name: text``.
    """

    __tablename__ = "transcripts"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    json_utterances: Mapped[list] = mapped_column(JSONVariant, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="transcript")


# --------------------------------------------------------------------------
# action_items
# --------------------------------------------------------------------------


class ActionItem(Base):
    """§5.1 note: status lives here for fast UI mutation; status changes sync
    into the graph via append-only ``add()`` docs, never graph mutation."""

    __tablename__ = "action_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'done')", name="ck_action_items_status"
        ),
        Index("ix_action_items_meeting_id", "meeting_id"),
        Index("ix_action_items_project_id", "project_id"),
        Index("ix_action_items_owner_user_id", "owner_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ActionItemStatus.open.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="action_items")
    owner: Mapped["User | None"] = relationship()


# --------------------------------------------------------------------------
# audit_log (§4.5) / sync_state (§9 connectors, reserved)
# --------------------------------------------------------------------------


class AuditLog(Base):
    """§4.5: audit_log(id, org_id, user_id, op ∈ {search, add, cognify, forget,
    export}, dataset, meeting_id?, ts). Every memory op writes a row."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            "op IN ('search', 'add', 'cognify', 'forget', 'export')", name="ck_audit_log_op"
        ),
        Index("ix_audit_log_org_ts", "org_id", "ts"),
        Index("ix_audit_log_dataset", "dataset"),
        Index("ix_audit_log_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    op: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )


class SyncState(Base):
    """Reserved for §9 connectors (Notion/Slack cursors, hashes)."""

    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )
