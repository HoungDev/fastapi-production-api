from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
    )

    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    password_login_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        default="user",
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    mfa_secret_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    mfa_enrollment_created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    mfa_enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    mfa_last_counter: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_users_email_normalized",
            func.lower(func.trim(email)),
            unique=True,
        ),
    )
