"""Shared-secret API authentication with no identity-provider dependency."""

import hmac

from fastapi import HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param


class ApiKeyAuthenticator:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def authenticate(self, request: Request) -> str:
        authorization = request.headers.get("Authorization", "")
        scheme, token = get_authorization_scheme_param(authorization)
        if scheme.lower() != "bearer" or not hmac.compare_digest(token, self._api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid bearer token is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        actor = request.headers.get("X-Actor", "").strip()
        # This is an audit label, not an authenticated human identity. API keys
        # are typically shared by operators or automation.
        return actor[:120] if actor else "api-client"
