from __future__ import annotations

import json
from typing import Protocol
from urllib import error, parse, request

from agent.config import RuntimeSettings
from agent.models import EmailRenderPayload, GmailDraftResult, GmailSearchMatch, GmailSendResult


class GmailMCPClient(Protocol):
    def search_messages(self, query: str) -> list[GmailSearchMatch]:
        ...

    def create_draft(self, payload: EmailRenderPayload) -> GmailDraftResult:
        ...

    def send_draft(self, draft_id: str) -> GmailSendResult:
        ...


class GmailMCPTransportError(RuntimeError):
    """Raised when the Gmail MCP transport cannot complete a request."""


class HttpGmailMCPClient:
    def __init__(self, *, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search_messages(self, query: str) -> list[GmailSearchMatch]:
        payload = self._request_json(
            method="GET",
            path=f"/gmail/search?query={parse.quote(query, safe='')}",
        )
        matches = payload.get("matches", [])
        if not isinstance(matches, list):
            msg = "Gmail MCP search response did not include a matches list"
            raise GmailMCPTransportError(msg)
        return [GmailSearchMatch.model_validate(match) for match in matches]

    def create_draft(self, payload: EmailRenderPayload) -> GmailDraftResult:
        response = self._request_json(
            method="POST",
            path="/gmail/create-draft",
            body=payload.model_dump(mode="json"),
        )
        return GmailDraftResult.model_validate(response)

    def send_draft(self, draft_id: str) -> GmailSendResult:
        response = self._request_json(
            method="POST",
            path="/gmail/send-draft",
            body={"draft_id": draft_id},
        )
        return GmailSendResult.model_validate(response)

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        data: bytes | None = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        http_request = request.Request(
            url=f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            msg = f"Gmail MCP request failed with HTTP {exc.code}: {detail}"
            raise GmailMCPTransportError(msg) from exc
        except error.URLError as exc:
            msg = f"Gmail MCP request failed: {exc.reason}"
            raise GmailMCPTransportError(msg) from exc

        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            msg = "Gmail MCP response was not a JSON object"
            raise GmailMCPTransportError(msg)
        return parsed


def load_gmail_client(settings: RuntimeSettings) -> GmailMCPClient:
    if settings.gmail_mcp_transport in {"stdio", "http"}:
        return HttpGmailMCPClient(
            base_url=settings.gmail_mcp_base_url,
            timeout_seconds=settings.gmail_mcp_timeout_seconds,
        )
    msg = f"Unsupported gmail_mcp_transport: {settings.gmail_mcp_transport}"
    raise ValueError(msg)
