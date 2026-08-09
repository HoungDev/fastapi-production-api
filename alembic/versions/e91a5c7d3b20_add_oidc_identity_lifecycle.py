"""add oidc identity lifecycle

Revision ID: e91a5c7d3b20
Revises: d82e194f6b7a
Create Date: 2026-08-09 19:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e91a5c7d3b20"
down_revision: Union[str, Sequence[str], None] = "d82e194f6b7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_login_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_table(
        "external_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_external_identity_subject"),
        sa.UniqueConstraint(
            "user_id", "issuer", name="uq_external_identity_user_issuer"
        ),
    )
    op.create_index(
        op.f("ix_external_identities_id"),
        "external_identities",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_identities_user_id"),
        "external_identities",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "oidc_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("browser_binding_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier_encrypted", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("device_name", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_oidc_transactions_id"),
        "oidc_transactions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oidc_transactions_state_hash"),
        "oidc_transactions",
        ["state_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_oidc_transactions_user_id"),
        "oidc_transactions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_oidc_transactions_user_id"), table_name="oidc_transactions")
    op.drop_index(
        op.f("ix_oidc_transactions_state_hash"), table_name="oidc_transactions"
    )
    op.drop_index(op.f("ix_oidc_transactions_id"), table_name="oidc_transactions")
    op.drop_table("oidc_transactions")
    op.drop_index(
        op.f("ix_external_identities_user_id"), table_name="external_identities"
    )
    op.drop_index(op.f("ix_external_identities_id"), table_name="external_identities")
    op.drop_table("external_identities")
    op.drop_column("users", "password_login_enabled")
