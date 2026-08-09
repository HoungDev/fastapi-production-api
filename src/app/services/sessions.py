from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.schemas.session import DeviceSession

USER_REVOCATION_REASON = "user_revoked"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def list_active_sessions(user_id: int, db: Session) -> list[DeviceSession]:
    records = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id)
        .order_by(RefreshToken.created_at.desc())
        .all()
    )
    now = datetime.now(UTC)
    families: dict[str, list[RefreshToken]] = {}
    for record in records:
        families.setdefault(record.family_id, []).append(record)

    sessions = []
    for family_id, family_records in families.items():
        active = [
            record
            for record in family_records
            if not record.revoked and _as_utc(record.expires_at) > now
        ]
        if not active:
            continue
        current = max(active, key=lambda record: _as_utc(record.last_used_at))
        sessions.append(
            DeviceSession(
                id=family_id,
                device_name=current.device_name,
                created_at=min(record.created_at for record in family_records),
                last_used_at=max(record.last_used_at for record in family_records),
                expires_at=max(record.expires_at for record in active),
            )
        )

    return sorted(sessions, key=lambda item: item.last_used_at, reverse=True)


def revoke_session_family(user_id: int, family_id: str, db: Session) -> None:
    _revoke_user_sessions(user_id, db, family_id=family_id)


def revoke_all_user_sessions(user_id: int, db: Session) -> None:
    _revoke_user_sessions(user_id, db)


def _revoke_user_sessions(
    user_id: int,
    db: Session,
    *,
    family_id: str | None = None,
) -> None:
    now = datetime.now(UTC)
    statement = update(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False),
    )
    if family_id is not None:
        statement = statement.where(RefreshToken.family_id == family_id)

    try:
        db.execute(
            statement.values(
                revoked=True,
                revoked_at=now,
                revocation_reason=USER_REVOCATION_REASON,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
