"""Supabase JWT authentication (WIN 9.1).

The user identity is derived ONLY from the verified Supabase token — request
bodies never carry a user id, so a caller cannot impersonate another user. The
token is validated server-side via the Supabase client (works with Supabase's
asymmetric JWTs without a local secret).
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from supabase import Client, create_client

from api.schemas import AuthedUser
from settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_secret_key.get_secret_value())


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed bearer token")
    return token


async def get_current_user(authorization: str = Header(default="")) -> AuthedUser:
    """FastAPI dependency: verify the Supabase JWT and return the authed user."""
    token = _bearer_token(authorization)
    try:
        # supabase-py is sync; validate off the event loop.
        response = await asyncio.to_thread(get_supabase().auth.get_user, token)
    except Exception:  # noqa: BLE001 - never leak the underlying error to the client
        logger.exception("Token verification failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = getattr(response, "user", None)
    if user is None or not getattr(user, "id", None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return AuthedUser(id=str(user.id), email=getattr(user, "email", None))
