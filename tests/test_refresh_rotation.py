from app.auth.refresh import (
    refresh_access_token,
)
from app.auth.refresh_token import (
    hash_refresh_token,
)
from app.db.session import SessionLocal
from app.models.refresh_token import RefreshToken
from app.models.user import User


def test_refresh_token_rotation():
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.username == "houngdev").first()

        assert user is not None

        from app.auth.refresh_token import (
            create_refresh_token,
        )

        old_token, expires_at = create_refresh_token()

        db_token = RefreshToken(
            user_id=user.id,
            token=hash_refresh_token(old_token),
            expires_at=expires_at,
        )

        db.add(db_token)
        db.commit()

        access_token, new_token = refresh_access_token(
            old_token,
            db,
        )

        assert access_token is not None
        assert new_token != old_token

        old_record = (
            db.query(RefreshToken)
            .filter(RefreshToken.token == hash_refresh_token(old_token))
            .first()
        )

        assert old_record.revoked is True

        second_old_token = None

        try:
            refresh_access_token(
                old_token,
                db,
            )

        except Exception as error:
            second_old_token = error

        assert second_old_token is not None

    finally:
        db.close()
