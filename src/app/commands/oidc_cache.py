import argparse
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.services.oidc_cache import OIDCPublicDocumentCache

logger = logging.getLogger("fastapi-production-api.oidc_cache")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage public OIDC discovery and JWKS cache entries."
    )
    parser.add_argument(
        "operation",
        choices=("invalidate-oidc",),
        help="Delete discovery and JWKS entries for the configured issuer.",
    )
    return parser


def run_invalidation(cache: OIDCPublicDocumentCache | None = None) -> int:
    if settings.OIDC_CACHE_BACKEND != "redis":
        logger.error(
            "oidc_cache_invalidation_rejected",
            extra={"oidc_cache_event": "invalidation_disabled"},
        )
        return 2
    deleted = (cache or OIDCPublicDocumentCache()).invalidate()
    if deleted is None:
        return 1
    logger.info(
        "oidc_cache_invalidated",
        extra={
            "oidc_cache_event": "invalidated",
            "oidc_cache_document": "all",
        },
    )
    return 0


def main() -> None:
    setup_logging()
    args = build_parser().parse_args()
    exit_code = run_invalidation() if args.operation == "invalidate-oidc" else 2
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
