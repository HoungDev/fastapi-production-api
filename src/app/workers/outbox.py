import argparse
import logging
import signal
import threading
from uuid import uuid4

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.metrics import OUTBOX_FAILURES_TOTAL
from app.db.session import SessionLocal
from app.services.email_delivery import SMTPEmailSender
from app.services.outbox_worker import OutboxWorker

logger = logging.getLogger("fastapi-production-api.outbox_worker")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process transactional outbox work.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim and process at most one batch, then exit.",
    )
    return parser


def run_worker(*, once: bool = False) -> int:
    if settings.EMAIL_DELIVERY_MODE != "outbox":
        raise RuntimeError("EMAIL_DELIVERY_MODE must be outbox to run the worker")

    worker = OutboxWorker(
        SessionLocal,
        SMTPEmailSender(),
        owner=uuid4().hex,
    )
    stop_event = threading.Event()

    def request_stop(signum, frame) -> None:
        worker.request_stop()
        stop_event.set()
        logger.info(
            "outbox_worker_shutdown_requested",
            extra={"outbox_event": "shutdown_requested"},
        )

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    if once:
        return worker.run_once()

    while not stop_event.is_set():
        try:
            processed = worker.run_once()
        except Exception:
            OUTBOX_FAILURES_TOTAL.labels(category="worker_loop").inc()
            logger.error(
                "outbox_worker_loop_failed",
                extra={
                    "outbox_event": "loop_failed",
                    "outbox_failure_category": "worker_loop",
                },
            )
            processed = 0
        if processed == 0:
            stop_event.wait(settings.OUTBOX_POLL_INTERVAL_SECONDS)
    return 0


def main() -> None:
    setup_logging()
    args = build_parser().parse_args()
    run_worker(once=args.once)


if __name__ == "__main__":
    main()
