from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.session_issuance import prepare_session_tokens


def test_session_issuance_flushes_pending_security_state_before_reload():
    events = []
    db = MagicMock()
    user = SimpleNamespace(id=123, username="active-user", is_active=True)
    query = MagicMock()
    locked_query = query.filter.return_value.populate_existing.return_value
    locked_query.with_for_update.return_value.first.return_value = user

    db.flush.side_effect = lambda: events.append("flush")
    db.query.side_effect = lambda _: events.append("query") or query

    tokens = prepare_session_tokens(
        user,
        "Test device",
        db,
        authentication_methods=["otp"],
    )

    assert events[:2] == ["flush", "query"]
    assert tokens.access_token
    assert tokens.refresh_token
    db.add.assert_called_once()
