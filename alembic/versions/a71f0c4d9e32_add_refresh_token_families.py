"""add refresh token families

Revision ID: a71f0c4d9e32
Revises: c2f45f831a2d
Create Date: 2026-08-09 15:00:00.000000
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "a71f0c4d9e32"
down_revision: Union[str, Sequence[str], None] = "c2f45f831a2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens", sa.Column("family_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("device_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "refresh_tokens", sa.Column("revoked_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("revocation_reason", sa.String(length=32), nullable=True),
    )

    connection = op.get_bind()
    rows = list(
        connection.execute(
            sa.text("SELECT id, created_at, revoked FROM refresh_tokens")
        ).mappings()
    )
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE refresh_tokens SET family_id = :family_id, "
                "last_used_at = created_at, device_name = :device_name, "
                "revoked_at = CASE WHEN revoked THEN created_at ELSE NULL END, "
                "revocation_reason = CASE WHEN revoked THEN :reason ELSE NULL END "
                "WHERE id = :id"
            ),
            {
                "family_id": str(uuid4()),
                "device_name": "Legacy session",
                "reason": "legacy_revoked",
                "id": row["id"],
            },
        )

    with op.batch_alter_table("refresh_tokens") as batch_op:
        batch_op.alter_column(
            "family_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.alter_column(
            "last_used_at",
            existing_type=sa.DateTime(),
            nullable=False,
        )
        batch_op.alter_column(
            "device_name",
            existing_type=sa.String(length=100),
            nullable=False,
        )

    op.create_index(
        op.f("ix_refresh_tokens_family_id"),
        "refresh_tokens",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_tokens_user_id"),
        "refresh_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    with op.batch_alter_table("refresh_tokens") as batch_op:
        batch_op.drop_column("revocation_reason")
        batch_op.drop_column("revoked_at")
        batch_op.drop_column("device_name")
        batch_op.drop_column("last_used_at")
        batch_op.drop_column("family_id")
