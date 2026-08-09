from __future__ import annotations

import logging
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _payload(*, code: str, message: str, request_id: str, retryable: bool = False, upstream_status: int | None = None) -> dict:
    error = {
        "code": code,
        "message": message,
        "request_id": request_id,
        "retryable": retryable,
    }
    if upstream_status is not None:
        error["upstream_status"] = upstream_status
    return {"error": error}


def _upstream_classification(status: int) -> tuple[int, str, str, bool]:
    if status in {401, 403}:
        return 502, "upstream_auth_error", "The configured AI provider rejected authentication or model access.", False
    if status == 429:
        return 503, "upstream_rate_limited", "The AI provider is rate limited or quota constrained. Try again shortly.", True
    if 400 <= status < 500:
        return 502, "upstream_request_error", "The AI provider rejected the request.", False
    return 502, "upstream_service_error", "The upstream AI service returned an error.", True


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(httpx.HTTPStatusError)
    async def http_status_error(request: Request, exc: httpx.HTTPStatusError):
        request_id = uuid4().hex
        upstream_status = exc.response.status_code
        status, code, message, retryable = _upstream_classification(upstream_status)
        logger.warning(
            "upstream_http_error request_id=%s path=%s upstream_status=%s host=%s",
            request_id,
            request.url.path,
            upstream_status,
            exc.request.url.host,
        )
        return JSONResponse(
            status_code=status,
            content=_payload(
                code=code,
                message=message,
                request_id=request_id,
                retryable=retryable,
                upstream_status=upstream_status,
            ),
        )

    @app.exception_handler(httpx.TimeoutException)
    async def upstream_timeout(request: Request, exc: httpx.TimeoutException):
        request_id = uuid4().hex
        logger.warning("upstream_timeout request_id=%s path=%s error=%s", request_id, request.url.path, type(exc).__name__)
        return JSONResponse(
            status_code=504,
            content=_payload(
                code="upstream_timeout",
                message="The upstream service timed out. Try again.",
                request_id=request_id,
                retryable=True,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        request_id = uuid4().hex
        logger.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_payload(
                code="internal_error",
                message="Nisr encountered an unexpected internal error.",
                request_id=request_id,
                retryable=False,
            ),
        )
