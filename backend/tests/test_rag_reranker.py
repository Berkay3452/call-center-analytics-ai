"""Yeniden sıralayıcı (#357): TEI istemcisi, sıralama mantığı ve hata durumunda RRF'ye dönüş."""

import json
from uuid import uuid4

import httpx
import pytest

from app.rag.rerankers import RerankError, TeiReranker, build_reranker
from app.rag.search import RERANK_TOP, SearchHit, _rerank
from app.schemas.assistant import SourceRef
from tests.conftest import make_settings

# --- TEI /rerank --------------------------------------------------------------------------


def rerank_transport(
    scores: dict[int, float], calls: list[dict[str, object]]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rerank"
        body = json.loads(request.content)
        calls.append(body)
        assert body["truncate"] is True
        # TEI en yüksek puandan başlayarak sıralı döner.
        items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return httpx.Response(200, json=[{"index": i, "score": s} for i, s in items])

    return httpx.MockTransport(handler)


async def test_tei_reranker_returns_scores_in_input_order() -> None:
    calls: list[dict[str, object]] = []
    reranker = TeiReranker(
        "http://rr:80/", transport=rerank_transport({0: 0.1, 1: 0.9, 2: 0.5}, calls)
    )

    assert await reranker.rerank("yakıt filtresi", ["a", "b", "c"]) == [0.1, 0.9, 0.5]
    assert calls == [{"query": "yakıt filtresi", "texts": ["a", "b", "c"], "truncate": True}]
    assert await reranker.rerank("x", []) == []  # boş girdi için istek atılmaz
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="hata"),
        httpx.Response(200, text="json değil"),
        httpx.Response(200, json=[{"index": 0, "score": 0.5}]),  # 2 metinden biri eksik
        httpx.Response(200, json=[{"index": 7, "score": 0.5}, {"index": 0, "score": 0.1}]),
        httpx.Response(200, json=[{"skor": 1}]),
    ],
)
async def test_tei_reranker_errors_become_rerank_error(response: httpx.Response) -> None:
    reranker = TeiReranker("http://rr", transport=httpx.MockTransport(lambda _r: response))

    with pytest.raises(RerankError):
        await reranker.rerank("gizli sorgu", ["a", "b"])


async def test_error_message_does_not_contain_query() -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bağlantı reddedildi")

    reranker = TeiReranker("http://rr", transport=httpx.MockTransport(refuse))

    with pytest.raises(RerankError) as info:
        await reranker.rerank("Ahmet Yılmaz'ın tc kimlik no", ["a"])
    assert "Ahmet" not in str(info.value)


def test_build_reranker_selects_provider() -> None:
    assert build_reranker(make_settings(reranker_provider="none")) is None
    built = build_reranker(make_settings(reranker_provider="tei", reranker_url="http://rr:80"))
    assert isinstance(built, TeiReranker)
    assert built.url == "http://rr:80"
    assert built.model_name == "onnx-community/bge-reranker-v2-m3-ONNX"


# --- Sıralama mantığı ---------------------------------------------------------------------


def make_hit(text: str) -> SearchHit:
    source = SourceRef(kind="boat_note", record_id=text, title=text, excerpt=text)
    return SearchHit(
        chunk_id=uuid4(), source=source, text=text, score=0.0, similarity=None, text_match=False
    )


class FakeReranker:
    model_name = "fake"

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.seen: list[str] = []

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        self.seen = texts
        return [self.scores.get(t, 0.0) for t in texts]


class BrokenReranker:
    model_name = "broken"

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        raise RerankError("servis kapalı")


async def test_rerank_reorders_head_and_keeps_tail() -> None:
    hits = [make_hit(t) for t in "abcdef"]
    reranker = FakeReranker({"c": 0.9, "a": 0.5, "b": 0.1})

    ranked = await _rerank(reranker, "soru", hits, top=3)

    assert [h.text for h in ranked] == ["c", "a", "b", "d", "e", "f"]
    assert reranker.seen == ["a", "b", "c"]  # yalnızca ilk 3 aday gönderildi
    assert [h.rerank_score for h in ranked[:3]] == [0.9, 0.5, 0.1]
    assert all(h.rerank_score is None for h in ranked[3:])


async def test_rerank_ties_keep_rrf_order() -> None:
    hits = [make_hit(t) for t in "abc"]

    ranked = await _rerank(FakeReranker({}), "soru", hits, top=RERANK_TOP)

    assert [h.text for h in ranked] == ["a", "b", "c"]


async def test_rerank_failure_falls_back_to_rrf_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    hits = [make_hit(t) for t in "abc"]

    ranked = await _rerank(BrokenReranker(), "kişisel sorgu metni", hits, top=3)

    assert ranked == hits
    assert all(h.rerank_score is None for h in ranked)
    logged = capsys.readouterr()
    assert "kişisel sorgu metni" not in logged.out + logged.err  # sorgu günlüğe yazılmaz
