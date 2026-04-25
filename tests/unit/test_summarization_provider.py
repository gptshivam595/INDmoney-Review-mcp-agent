from __future__ import annotations

import io
import json
from datetime import datetime

import pytest

from agent.models import AnalysisCluster, RawReview
from agent.summarization.provider import (
    OpenAISummarizationProvider,
    ThemeSuggestion,
    load_summarization_provider,
)


class FakeHTTPResponse:
    def __init__(self, payload: object) -> None:
        self._buffer = io.StringIO(json.dumps(payload))

    def read(self, size: int = -1) -> str:
        return self._buffer.read(size)

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


def test_load_summarization_provider_requires_openai_key(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        load_summarization_provider("openai", "gpt-4.1-mini")


def test_openai_provider_parses_theme_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.summarization.provider.urlopen",
        lambda _request, timeout: FakeHTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "name": "App performance and reliability",
                                    "summary": "Users report login crashes during peak usage.",
                                    "sentiment": "negative",
                                }
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 123,
                    "completion_tokens": 21,
                    "total_tokens": 144,
                },
            }
        ),
    )

    provider = OpenAISummarizationProvider(
        model_name="gpt-4.1-mini",
        api_key="test-key",
        timeout_seconds=7,
    )

    response = provider.label_theme(_cluster(), [_review()])

    assert isinstance(response.payload, ThemeSuggestion)
    assert response.payload.name == "App performance and reliability"
    assert response.payload.sentiment == "negative"
    assert response.usage.prompt_tokens == 123
    assert response.usage.total_tokens == 144


def _review() -> RawReview:
    return RawReview(
        review_id="r1",
        product_key="indmoney",
        source="fixture",
        external_id="r1",
        rating=1,
        title=None,
        body_raw="App crashes during login and freezes at market open.",
        body_scrubbed="App crashes during login and freezes at market open.",
        reviewed_at=datetime.fromisoformat("2026-04-21T10:00:00+00:00"),
        locale="en-IN",
        raw_payload={"review_id": "r1"},
    )


def _cluster() -> AnalysisCluster:
    return AnalysisCluster(
        cluster_id="cluster-1",
        cluster_index=0,
        review_ids=["r1"],
        review_count=1,
        representative_review_id="r1",
        keyphrases=["crash", "login"],
        sentiment_score=-0.9,
        noise=False,
    )
