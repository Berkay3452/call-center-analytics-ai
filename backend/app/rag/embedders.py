"""Embedding sağlayıcıları (#26). Hepsi `Embedder` arayüzünü uygular (`app/rag/base.py`).

- `TeiEmbedder`: bge-m3, Hugging Face Text Embeddings Inference servisi üzerinden (Docker, CPU).
  Python tarafına torch/model yüklenmez; servis HTTP ile çağrılır. Varsayılan seçim.
- `OpenAICompatibleEmbedder`: OpenAI uyumlu `/embeddings` API'si (karşılaştırma/yedek).
- `HashEmbedder`: modelsiz, kelime köklerinden üretilen vektör. Anlamı değil kelime örtüşmesini
  yakalar; testler ve servis kurulmadan geliştirme içindir, gerçek arama için kullanılmaz.

Vektörler birim uzunluğa normalize edilir (kosinüs benzerliği = iç çarpım).
"""

import hashlib
import math
from typing import Any

import httpx
import structlog

from app.agents.grounding import normalize
from app.core.config import Settings
from app.rag.base import Embedder

log = structlog.get_logger(__name__)


class EmbeddingError(Exception):
    """Embedding servisine ulaşılamadı veya beklenmeyen yanıt döndü."""


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


def _check_dim(vectors: list[list[float]], dim: int, model: str) -> list[list[float]]:
    for v in vectors:
        if len(v) != dim:
            raise EmbeddingError(
                f"{model} {len(v)} boyutlu vektör döndü; veritabanı {dim} bekliyor (EMBEDDING_DIM)."
            )
    return vectors


class TeiEmbedder:
    def __init__(
        self,
        url: str,
        *,
        model_name: str = "BAAI/bge-m3",
        dim: int = 1024,
        timeout_s: float = 60.0,
        batch_size: int = 16,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.model_name = model_name
        self.dim = dim
        self.timeout_s = timeout_s
        self.batch_size = batch_size
        self._transport = transport  # testlerde sahte HTTP

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as client:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                try:
                    resp = await client.post(
                        f"{self.url}/embed", json={"inputs": batch, "normalize": True}
                    )
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    raise EmbeddingError(
                        f"Embedding servisine ulaşılamadı ({self.url}): {exc}"
                    ) from exc
                out.extend(resp.json())
        return _check_dim(out, self.dim, self.model_name)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts) if texts else []

    async def embed_query(self, text: str) -> list[float]:
        # bge-m3 sorgu için ön ek (instruction) istemez.
        return (await self._embed([text]))[0]


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_name: str,
        dim: int = 1024,
        timeout_s: float = 60.0,
        batch_size: int = 16,
        client: Any = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model_name = model_name
        self.dim = dim
        self.timeout_s = timeout_s
        self.batch_size = batch_size
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise EmbeddingError("EMBEDDING_API_KEY tanımlı değil.")
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=self.timeout_s
            )
        return self._client

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            try:
                resp = await client.embeddings.create(
                    model=self.model_name, input=texts[i : i + self.batch_size]
                )
            except Exception as exc:
                raise EmbeddingError(f"Embedding API hatası: {exc}") from exc
            out.extend(_unit(list(d.embedding)) for d in resp.data)
        return _check_dim(out, self.dim, self.model_name)

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


class HashEmbedder:
    """Kelime köklerini (ilk 5 harf) sabit boyutlu vektöre dağıtır; deterministiktir."""

    def __init__(self, dim: int = 1024) -> None:
        self.model_name = "hash"
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in normalize(text).split():
            if len(token) < 3:
                continue
            stem = token[:5]
            bucket = int.from_bytes(hashlib.sha256(stem.encode()).digest()[:4], "big")
            vector[bucket % self.dim] += 1.0
        return _unit(vector)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def build_embedder(settings: Settings, provider: str | None = None) -> Embedder:
    name = provider or settings.embedding_provider
    if name == "tei":
        return TeiEmbedder(
            settings.tei_url,
            model_name=settings.embedding_model,
            dim=settings.embedding_dim,
            timeout_s=settings.embedding_timeout_s,
            batch_size=settings.embedding_batch_size,
        )
    if name == "openai_compatible":
        if not settings.embedding_base_url:
            raise ValueError("openai_compatible için EMBEDDING_BASE_URL gerekir.")
        return OpenAICompatibleEmbedder(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key.get_secret_value()
            if settings.embedding_api_key
            else None,
            model_name=settings.embedding_model,
            dim=settings.embedding_dim,
            timeout_s=settings.embedding_timeout_s,
            batch_size=settings.embedding_batch_size,
        )
    if name == "hash":
        return HashEmbedder(settings.embedding_dim)
    raise ValueError(f"Bilinmeyen embedding sağlayıcısı: {name}")
