"""Embedding sağlayıcı sözleşmesi (TEI üzerinde bge-m3 veya OpenAI-uyumlu bir API)."""

from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dim: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Belge parçalarını vektöre çevirir (indeksleme)."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Kullanıcı sorusunu vektöre çevirir (arama)."""
        ...
