"""add outbox trace context

Revision ID: 65bcb8a12535
Revises: f3a6c8d91b42
Create Date: 2026-08-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "65bcb8a12535"
down_revision: Union[str, Sequence[str], None] = "f3a6c8d91b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outbox_messages",
        sa.Column(
            "traceparent",
            sa.String(length=256),
            nullable=True,
        ),
    )
    op.add_column(
        "outbox_messages",
        sa.Column(
            "tracestate",
            sa.String(length=512),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("outbox_messages", "tracestate")
    op.drop_column("outbox_messages", "traceparent")
