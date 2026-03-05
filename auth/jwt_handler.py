"""
JWT Authentication Handler
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

SECRET_KEY      = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_in_env")
ALGORITHM       = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_EXPIRE   = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))
REFRESH_EXPIRE  = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthError(Exception):
    pass


class JWTHandler:
    """
    Issues and validates JWT tokens.

    Payload structure::

        {
            "sub":       "<user_id>",
            "tenant_id": "<tenant_slug>",
            "email":     "<email>",
            "role":      "admin|member|viewer",
            "type":      "access|refresh",
            "jti":       "<unique token id>",
            "exp":       <unix timestamp>,
        }
    """

    @staticmethod
    def hash_password(password: str) -> str:
        return _pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return _pwd_context.verify(plain, hashed)

    @staticmethod
    def create_access_token(
        user_id: str,
        tenant_id: str,
        email: str,
        role: str = "member",
    ) -> str:
        expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE)
        payload = {
            "sub":       user_id,
            "tenant_id": tenant_id,
            "email":     email,
            "role":      role,
            "type":      "access",
            "jti":       str(uuid.uuid4()),
            "exp":       expires,
            "iat":       datetime.now(timezone.utc),
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(user_id: str, tenant_id: str) -> str:
        expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE)
        payload = {
            "sub":       user_id,
            "tenant_id": tenant_id,
            "type":      "refresh",
            "jti":       str(uuid.uuid4()),
            "exp":       expires,
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise AuthError("Token expired")
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"Invalid token: {exc}")

        if payload.get("type") != expected_type:
            raise AuthError(f"Expected {expected_type} token, got {payload.get('type')}")

        return payload

    @staticmethod
    def refresh_access_token(refresh_token: str) -> str:
        payload = JWTHandler.decode_token(refresh_token, expected_type="refresh")
        return JWTHandler.create_access_token(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            email=payload.get("email", ""),
            role=payload.get("role", "member"),
        )
