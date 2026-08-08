from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def success_response(data):
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": jsonable_encoder(data),
        },
    )
