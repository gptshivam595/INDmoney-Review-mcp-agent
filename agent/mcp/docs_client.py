from __future__ import annotations

import json
from typing import Protocol
from urllib import error, parse, request

from agent.config import RuntimeSettings
from agent.models import DocsAppendPayload, DocsDocumentState


class DocsMCPClient(Protocol):
    def ensure_document(self, title: str) -> tuple[DocsDocumentState, bool]:
        ...

    def get_document(self, document_id: str) -> DocsDocumentState:
        ...

    def append_section(self, document_id: str, payload: DocsAppendPayload) -> None:
        ...


class DocsMCPTransportError(RuntimeError):
    """Raised when the Docs MCP transport cannot complete a request."""


class HttpDocsMCPClient:
    def __init__(self, *, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def ensure_document(self, title: str) -> tuple[DocsDocumentState, bool]:
        payload = self._request_json(
            method="POST",
            path="/docs/ensure-document",
            body={"title": title},
        )
        created_raw = payload.pop("created", False)
        return DocsDocumentState.model_validate(payload), bool(created_raw)

    def get_document(self, document_id: str) -> DocsDocumentState:
        payload = self._request_json(
            method="GET",
            path=f"/docs/{parse.quote(document_id, safe='')}",
        )
        return DocsDocumentState.model_validate(payload)

    def append_section(self, document_id: str, payload: DocsAppendPayload) -> None:
        self._request_json(
            method="POST",
            path=f"/docs/{parse.quote(document_id, safe='')}/append-section",
            body=payload.model_dump(mode="json"),
        )

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
            msg = f"Docs MCP request failed with HTTP {exc.code}: {detail}"
            raise DocsMCPTransportError(msg) from exc
        except error.URLError as exc:
            msg = f"Docs MCP request failed: {exc.reason}"
            raise DocsMCPTransportError(msg) from exc

        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            msg = "Docs MCP response was not a JSON object"
            raise DocsMCPTransportError(msg)
        return parsed


def load_docs_client(settings: RuntimeSettings) -> DocsMCPClient:
    if settings.docs_mcp_transport in {"stdio", "http"}:
        return HttpDocsMCPClient(
            base_url=settings.docs_mcp_base_url,
            timeout_seconds=settings.docs_mcp_timeout_seconds,
        )
    msg = f"Unsupported docs_mcp_transport: {settings.docs_mcp_transport}"
    raise ValueError(msg)
