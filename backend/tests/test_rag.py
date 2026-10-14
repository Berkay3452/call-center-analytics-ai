"""RAG (#26): embedding sağlayıcıları ve tam metin sorgusu. Veritabanı/servis gerektirmez."""

import json
import math
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.rag.embedders import (
    EmbeddingError,
    HashEmbedder,
    OpenAICompatibleEmbedder,
    TeiEmbedder,
    build_embedder,
)
from app.rag.search import build_tsquery, turkish_lower
from tests.conftest import make_settings

# --- TEI (bge-m3) -------------------------------------------------------------------------


def tei_transport(dim: int, calls: list[list[str]], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/embed"
        body = json.loads(request.content)
        assert body["normalize"] is True
        calls.append(body["inputs"])
        if status != 200:
            return httpx.Response(status, text="hata")
        return httpx.Response(200, json=[[0.1] * dim for _ in body["inputs"]])

    return httpx.MockTransport(handler)


async def test_tei_batches_documents() -> None:
    calls: list[list[str]] = []
    embedder = TeiEmbedder("http://tei:80/", dim=4, batch_size=2, transport=tei_transport(4, calls))

    vectors = await embedder.embed_documents(["a", "b", "c"])

    assert len(vectors) == 3
    assert calls == [["a", "b"], ["c"]]
    assert await embedder.embed_documents([]) == []


async def test_tei_query_and_dimension_check() -> None:
    calls: list[list[str]] = []
    ok = TeiEmbedder("http://tei", dim=4, transport=tei_transport(4, calls))
    wrong = TeiEmbedder("http://tei", dim=1024, transport=tei_transport(4, calls))

    assert len(await ok.embed_query("yakıt filtresi")) == 4
    with pytest.raises(EmbeddingError, match="EMBEDDING_DIM"):
        await wrong.embed_query("x")


async def test_tei_unreachable_raises_embedding_error() -> None:
    embedder = TeiEmbedder("http://tei", dim=4, transport=tei_transport(4, [], status=503))

    with pytest.raises(EmbeddingError, match="ulaşılamadı"):
        await embedder.embed_query("x")


# --- OpenAI uyumlu ------------------------------------------------------------------------


async def test_openai_compatible_normalizes_vectors() -> None:
    class Api:
        async def create(self, **kwargs: Any) -> Any:
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[3.0, 4.0]) for _ in kwargs["input"]]
            )

    embedder = OpenAICompatibleEmbedder(
        base_url="http://x",
        api_key="k",
        model_name="m",
        dim=2,
        client=SimpleNamespace(embeddings=Api()),
    )

    assert await embedder.embed_query("x") == pytest.approx([0.6, 0.8])


async def test_openai_compatible_requires_key() -> None:
    embedder = OpenAICompatibleEmbedder(base_url="http://x", api_key=None, model_name="m")

    with pytest.raises(EmbeddingError, match="EMBEDDING_API_KEY"):
        await embedder.embed_query("x")


# --- Hash (test/geliştirme) ---------------------------------------------------------------


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_hash_embedder_is_deterministic_and_unit_length() -> None:
    embedder = HashEmbedder(dim=64)

    v1 = await embedder.embed_query("Yakıt filtresi değiştirildi")
    v2 = (await embedder.embed_documents(["Yakıt filtresi değiştirildi"]))[0]

    assert v1 == v2
    assert math.isclose(sum(x * x for x in v1), 1.0)


async def test_hash_embedder_prefers_shared_word_stems() -> None:
    embedder = HashEmbedder(dim=256)
    query = await embedder.embed_query("yakıt filtresi")

    related = await embedder.embed_query("Yakıt filtreleri değiştirildi")
    unrelated = await embedder.embed_query("Klima gaz basıncı tamamlandı")

    assert _cos(query, related) > _cos(query, unrelated)


def test_build_embedder_selects_provider() -> None:
    settings = make_settings(embedding_provider="tei", tei_url="http://tei:80")

    assert isinstance(build_embedder(settings), TeiEmbedder)
    assert isinstance(build_embedder(settings, "hash"), HashEmbedder)
    with pytest.raises(ValueError, match="EMBEDDING_BASE_URL"):
        build_embedder(settings, "openai_compatible")
    with pytest.raises(ValueError, match="Bilinmeyen"):
        build_embedder(settings, "bge")


# --- Tam metin sorgusu --------------------------------------------------------------------


def test_build_tsquery_uses_prefixes_for_turkish_suffixes() -> None:
    # "filtresi" ve "filtre" aynı ön eki (filtr) paylaşır; iyelik eki sorun olmaz.
    assert build_tsquery("Yakıt filtresi ne zaman değişti?") == "yakıt:* | filtr:*"


def test_build_tsquery_drops_stopwords_symbols_suffixes_and_duplicates() -> None:
    assert build_tsquery("Teknemin akü & akü'leri; (bozuk) mu?") == "akü:* | bozuk:*"
    assert build_tsquery("Poyraz'ın aküleri, filtreleri") == "poyra:* | akü:* | filtr:*"


def test_build_tsquery_returns_none_without_meaningful_words() -> None:
    assert build_tsquery("bu ne?") is None
    assert build_tsquery("   ") is None
    assert build_tsquery("2024 12") is None


def test_turkish_lower() -> None:
    assert turkish_lower("IŞIK İSTANBUL") == "ışık istanbul"
