from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'dead_letter')",
            name="ck_outbox_messages_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_outbox_messages_attempt_count",
        ),
        CheckConstraint(
            "((status = 'processing' AND lease_owner IS NOT NULL AND "
            "lease_expires_at IS NOT NULL) OR (status <> 'processing' AND "
            "lease_owner IS NULL AND lease_expires_at IS NULL))",
            name="ck_outbox_messages_lease_state",
        ),
        CheckConstraint(
            "((status IN ('succeeded', 'dead_letter') AND terminal_at IS NOT NULL "
            "AND payload_encrypted IS NULL) OR (status IN ('pending', 'processing') "
            "AND terminal_at IS NULL AND payload_encrypted IS NOT NULL))",
            name="ck_outbox_messages_terminal_state",
        ),
        Index(
            "ix_outbox_messages_claim",
            "status",
            "available_at",
            "lease_expires_at",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    encryption_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payload_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    failure_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    terminal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
