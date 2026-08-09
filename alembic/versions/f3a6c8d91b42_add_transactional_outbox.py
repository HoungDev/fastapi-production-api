"""add transactional outbox

Revision ID: f3a6c8d91b42
Revises: e91a5c7d3b20
Create Date: 2026-08-09 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f3a6c8d91b42"
down_revision: Union[str, Sequence[str], None] = "e91a5c7d3b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("encryption_version", sa.Integer(), nullable=False),
        sa.Column("payload_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_category", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_outbox_messages_attempt_count"
        ),
        sa.CheckConstraint(
            "((status = 'processing' AND lease_owner IS NOT NULL AND "
            "lease_expires_at IS NOT NULL) OR (status <> 'processing' AND "
            "lease_owner IS NULL AND lease_expires_at IS NULL))",
            name="ck_outbox_messages_lease_state",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'dead_letter')",
            name="ck_outbox_messages_status",
        ),
        sa.CheckConstraint(
            "((status IN ('succeeded', 'dead_letter') AND terminal_at IS NOT NULL "
            "AND payload_encrypted IS NULL) OR (status IN ('pending', 'processing') "
            "AND terminal_at IS NULL AND payload_encrypted IS NOT NULL))",
            name="ck_outbox_messages_terminal_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_outbox_messages_claim",
        "outbox_messages",
        ["status", "available_at", "lease_expires_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_claim", table_name="outbox_messages")
    op.drop_table("outbox_messages")
