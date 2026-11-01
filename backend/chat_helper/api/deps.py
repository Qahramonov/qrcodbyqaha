"""API dependencies: authentication (Bearer session tokens), RBAC, rate limits, pagination."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Query, Request

from ..auth.service import AuthError


class APIError(HTTPException):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(status_code=status, detail={"code": code, "message": message}, headers=headers)


@dataclass
class Principal:
    user_id: int
    role: str
    session_id: int
    device_name: str | None

    @property
    def is_admin(self) -> bool:
        return self.role in ("super_admin", "moderator")

    @property
    def is_super(self) -> bool:
        return self.role == "super_admin"


def get_app(request: Request) -> Any:
    return request.app.state.ctx


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def principal(request: Request) -> Principal:
    app = request.app.state.ctx
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise APIError(401, "unauthorized", "Missing bearer token")
    try:
        s = await app.auth.authenticate(auth[7:].strip(), client_ip(request))
    except AuthError as e:
        raise APIError(e.status, e.code, e.message) from None
    ok, retry = app.limiter.check(f"api:s:{s.id}", 240, 60)
    if not ok:
        raise APIError(429, "rate_limited", "Too many requests", {"Retry-After": str(retry)})
    request.state.principal = s
    return Principal(user_id=s.user_id, role=s.role, session_id=s.id, device_name=s.device_name)


async def admin(p: Principal = Depends(principal)) -> Principal:
    if not p.is_admin:
        raise APIError(403, "forbidden", "Administrator role required")
    return p


async def super_admin(p: Principal = Depends(principal)) -> Principal:
    if not p.is_super:
        raise APIError(403, "forbidden", "Super admin role required")
    return p


class Page:
    def __init__(self, page: int = Query(1, ge=1, le=100000), page_size: int = Query(30, ge=1, le=100)) -> None:
        self.page = page
        self.page_size = page_size


def scope_user(p: Principal, requested: int | None) -> int:
    """Regular users can only see themselves; admins may pass a user id explicitly."""
    if requested is None or requested == p.user_id:
        return p.user_id
    if not p.is_admin:
        raise APIError(403, "forbidden", "You can only access your own data")
    return requested
