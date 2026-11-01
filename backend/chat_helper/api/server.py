"""FastAPI application for Chat helper Control (Android). Binds to 127.0.0.1 by default."""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__

log = logging.getLogger(__name__)
MAX_BODY = 2 * 1024 * 1024


def error(status: int, code: str, message: str, extra: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if extra:
        body["error"].update(extra)
    return JSONResponse(status_code=status, content=body, headers=headers)


def create_api(ctx: Any) -> FastAPI:
    api = FastAPI(title="Chat helper Control API", version=__version__, docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json",
                  description="Local REST API used by the Chat helper Control Android app. All endpoints except /api/v1/health and "
                              "/api/v1/auth/* require `Authorization: Bearer <access_token>` obtained via Telegram pairing.")
    api.state.ctx = ctx

    @api.middleware("http")
    async def guard(request: Request, call_next):
        t0 = time.monotonic()
        ip = request.client.host if request.client else "unknown"
        ok, retry = ctx.limiter.check(f"api:ip:{ip}", 600, 60)
        if not ok:
            return error(429, "rate_limited", "Too many requests", headers={"Retry-After": str(retry)})
        override = request.headers.get("x-http-method-override", "").upper()
        if request.method == "POST" and override in ("PATCH", "PUT", "DELETE"):
            request.scope["method"] = override
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY:
            return error(413, "payload_too_large", "Request body too large")
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled API error on %s", request.url.path)
            return error(500, "internal_error", "Internal server error")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Response-Time"] = f"{int((time.monotonic() - t0) * 1000)}ms"
        return response

    @api.exception_handler(StarletteHTTPException)
    async def http_exc(_: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return error(exc.status_code, exc.detail["code"], exc.detail["message"], headers=getattr(exc, "headers", None))
        return error(exc.status_code, "http_error", str(exc.detail))

    @api.exception_handler(RequestValidationError)
    async def validation_exc(_: Request, exc: RequestValidationError):
        details = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg")} for e in exc.errors()][:20]
        return error(422, "validation_error", "Invalid request", {"details": details})

    @api.exception_handler(ValueError)
    async def value_exc(_: Request, exc: ValueError):
        return error(400, "bad_request", str(exc)[:300])

    from .routers import admin_routes, ai_routes, auth_routes, ops_routes, user_routes
    for r in (auth_routes.router, user_routes.router, ai_routes.router, ops_routes.router, admin_routes.router):
        api.include_router(r, prefix="/api/v1")
    return api
