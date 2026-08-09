"""add totp mfa foundation

Revision ID: d82e194f6b7a
Revises: a71f0c4d9e32
Create Date: 2026-08-09 17:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d82e194f6b7a"
down_revision: Union[str, Sequence[str], None] = "a71f0c4d9e32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("mfa_enrollment_created_at", sa.DateTime(), nullable=True)
    )
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users", sa.Column("mfa_last_counter", sa.BigInteger(), nullable=True)
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mfa_recovery_codes_code_hash"),
        "mfa_recovery_codes",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_mfa_recovery_codes_id"),
        "mfa_recovery_codes",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mfa_recovery_codes_user_id"),
        "mfa_recovery_codes",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_mfa_recovery_codes_user_id"), table_name="mfa_recovery_codes"
    )
    op.drop_index(op.f("ix_mfa_recovery_codes_id"), table_name="mfa_recovery_codes")
    op.drop_index(
        op.f("ix_mfa_recovery_codes_code_hash"), table_name="mfa_recovery_codes"
    )
    op.drop_table("mfa_recovery_codes")
    op.drop_column("users", "mfa_last_counter")
    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_enrollment_created_at")
    op.drop_column("users", "mfa_secret_encrypted")
