"""add user role

Revision ID: b8ec7bdd3f0b
Revises: 2e6b8bef6ca6
Create Date: 2026-08-03 16:50:19.877234

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8ec7bdd3f0b"
down_revision: Union[str, Sequence[str], None] = "2e6b8bef6ca6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "users",
        "role",
    )