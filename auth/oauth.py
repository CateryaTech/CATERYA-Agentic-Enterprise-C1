"""
OAuth Provider Integration (Supabase / Auth0)
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY     = os.getenv("SUPABASE_ANON_KEY", "")
AUTH0_DOMAIN     = os.getenv("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID  = os.getenv("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "")


class OAuthProvider:
    """Base class for OAuth providers."""

    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class SupabaseAuth(OAuthProvider):
    """Supabase Auth integration."""

    def __init__(self):
        self.url  = SUPABASE_URL
        self.key  = SUPABASE_KEY

    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": self.key,
                },
                timeout=10,
            )

        if resp.status_code != 200:
            logger.warning("Supabase token verification failed: %s", resp.status_code)
            return None

        data = resp.json()
        return {
            "sub":      data.get("id"),
            "email":    data.get("email"),
            "provider": "supabase",
            "raw":      data,
        }

    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        return await self.verify_token(token)


class Auth0Provider(OAuthProvider):
    """Auth0 integration."""

    def __init__(self):
        self.domain        = AUTH0_DOMAIN
        self.client_id     = AUTH0_CLIENT_ID
        self.client_secret = AUTH0_CLIENT_SECRET

    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not self.domain:
            raise RuntimeError("AUTH0_DOMAIN must be set")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://{self.domain}/userinfo",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )

        if resp.status_code != 200:
            logger.warning("Auth0 token verification failed: %s", resp.status_code)
            return None

        data = resp.json()
        return {
            "sub":      data.get("sub"),
            "email":    data.get("email"),
            "name":     data.get("name"),
            "provider": "auth0",
            "raw":      data,
        }

    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        return await self.verify_token(token)

    def get_login_url(self, redirect_uri: str, state: str = "") -> str:
        return (
            f"https://{self.domain}/authorize"
            f"?client_id={self.client_id}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope=openid+profile+email"
            f"&state={state}"
        )


def get_oauth_provider(provider: str = "supabase") -> OAuthProvider:
    if provider == "auth0":
        return Auth0Provider()
    return SupabaseAuth()
