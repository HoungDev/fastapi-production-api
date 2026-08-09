from fastapi import APIRouter, Response

from app.core.metrics import render_metrics

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(
        content=payload,
        headers={
            "Cache-Control": "no-store",
            "Content-Type": content_type,
        },
    )
