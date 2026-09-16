"""Authentication, CSRF and account-type boundaries shared by route groups."""

import secrets
from fastapi import HTTPException, Request
from .repository import session_user


def current_user(request: Request):
    if hasattr(request.state, "user"):
        return request.state.user
    try:
        user = session_user(request.session.get("sid"))
    except Exception:
        raise HTTPException(
            503, "Sign-in is temporarily unavailable. Please try again."
        ) from None
    request.state.user = user
    return user


def require_dashboard_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Please log in to continue.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        expected = request.session.get("csrf", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            raise HTTPException(403, "Invalid request. Refresh and try again.")
    return user


def require_user(request: Request):
    """Business endpoints never grant APPOWNER access to customer operations."""
    user = require_dashboard_user(request)
    if user.get("user_type") == "APPOWNER":
        raise HTTPException(
            403, "APPOWNER accounts are reserved for product performance only."
        )
    return user


def require_legacy_user(request: Request):
    user = require_user(request)
    if user.get("user_type") == "MEMBER":
        from .database import auth_engine, schema_name
        from sqlalchemy import text

        with auth_engine().connect() as connection:
            if connection.execute(
                text(
                    f"SELECT 1 FROM {schema_name()}.workspace_memberships WHERE user_id=:u LIMIT 1"
                ),
                {"u": user["id"]},
            ).first():
                raise HTTPException(
                    403,
                    "Invited staff can access only their assigned workspace details.",
                )
    return user
