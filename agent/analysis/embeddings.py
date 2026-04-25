from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen

from agent.config import RuntimeSettings


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str:
        ...

    def embed(self, text: str) -> list[float]:
        ...


def embedding_sha1(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


@dataclass(frozen=True)
class LocalHashEmbeddingProvider:
    model_name: str
    dimensions: int

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha1(token.encode()).digest()
            bucket = int.from_bytes(digest[:2], byteorder="big") % self.dimensions
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            weight = 1.0 + ((digest[3] % 13) / 13.0)
            vector[bucket] += sign * weight
        return _normalize(vector)


@dataclass(frozen=True)
class OpenAIEmbeddingProvider:
    model_name: str
    api_key: str

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({"input": text, "model": self.model_name}).encode()
        request = Request(
            "https://api.openai.com/v1/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310
            body = json.load(response)
        return [float(value) for value in body["data"][0]["embedding"]]


def load_embedding_provider(settings: RuntimeSettings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            msg = "OPENAI_API_KEY is required when embedding_provider=openai"
            raise RuntimeError(msg)
        return OpenAIEmbeddingProvider(model_name=settings.embedding_model, api_key=api_key)

    return LocalHashEmbeddingProvider(
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]
