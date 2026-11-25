"""Minimal async REST client shared by public third-party API adapters."""

import httpx


class ExternalServiceError(Exception):
    """Sanitized upstream error safe to return to an API client."""

    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.service = service
        self.status_code = status_code


class AsyncRestClient:
    def __init__(
        self, service: str, base_url: str, headers: dict[str, str],
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._service = service
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers,
            timeout=httpx.Timeout(timeout_seconds), transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Do not propagate upstream response bodies: they can contain
            # credentials, private metadata, or misleading HTML error pages.
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            raise ExternalServiceError(
                self._service,
                f"{self._service} request failed (HTTP {status_code or 'unavailable'}).",
                status_code=status_code,
            ) from exc
