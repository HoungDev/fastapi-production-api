"""add email verification lifecycle

Revision ID: c2f45f831a2d
Revises: 906770b858da
Create Date: 2026-08-09 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c2f45f831a2d"
down_revision: Union[str, Sequence[str], None] = "906770b858da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(trim(email)) WHERE email IS NOT NULL")
    op.drop_index("uq_users_email", table_name="users")
    op.create_index(
        "uq_users_email_normalized",
        "users",
        [sa.text("lower(trim(email))")],
        unique=True,
    )
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_action_tokens_id"),
        "account_action_tokens",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_action_tokens_purpose"),
        "account_action_tokens",
        ["purpose"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_action_tokens_token_hash"),
        "account_action_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_account_action_tokens_user_id"),
        "account_action_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_account_action_tokens_user_id"),
        table_name="account_action_tokens",
    )
    op.drop_index(
        op.f("ix_account_action_tokens_token_hash"),
        table_name="account_action_tokens",
    )
    op.drop_index(
        op.f("ix_account_action_tokens_purpose"),
        table_name="account_action_tokens",
    )
    op.drop_index(
        op.f("ix_account_action_tokens_id"),
        table_name="account_action_tokens",
    )
    op.drop_table("account_action_tokens")
    op.drop_column("users", "email_verified_at")
    op.drop_index("uq_users_email_normalized", table_name="users")
    op.create_index("uq_users_email", "users", ["email"], unique=True)
