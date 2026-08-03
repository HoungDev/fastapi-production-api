"""add user production fields

Revision ID: 4c1b48a8c021
Revises: b8ec7bdd3f0b
Create Date: 2026-08-03 21:30:18.577242

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c1b48a8c021"
down_revision: Union[str, Sequence[str], None] = "b8ec7bdd3f0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "users",
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_unique_constraint(
        "uq_users_email",
        "users",
        ["email"],
    )

    op.alter_column(
        "users",
        "is_active",
        server_default=None,
    )

    op.alter_column(
        "users",
        "created_at",
        server_default=None,
    )

    op.alter_column(
        "users",
        "updated_at",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "uq_users_email",
        "users",
        type_="unique",
    )

    op.drop_column(
        "users",
        "updated_at",
    )

    op.drop_column(
        "users",
        "created_at",
    )

    op.drop_column(
        "users",
        "is_active",
    )

    op.drop_column(
        "users",
        "email",
    )