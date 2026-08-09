from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.workers import outbox


def test_worker_parser_supports_once_mode():
    assert outbox.build_parser().parse_args(["--once"]).once is True


def test_worker_rejects_non_outbox_delivery_mode(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "disabled")

    with pytest.raises(RuntimeError, match="EMAIL_DELIVERY_MODE"):
        outbox.run_worker(once=True)


def test_worker_once_processes_one_batch(monkeypatch):
    worker = MagicMock()
    worker.run_once.return_value = 3
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "outbox")
    monkeypatch.setattr(outbox, "OutboxWorker", lambda *args, **kwargs: worker)
    monkeypatch.setattr(outbox.signal, "signal", lambda *args: None)

    assert outbox.run_worker(once=True) == 3
    worker.run_once.assert_called_once_with()
