"""Yeniden sıralayıcı (reranker) sağlayıcıları (#357).

Vektör ve tam metin araması soruyu ve notu ayrı ayrı işler; reranker ikisini **birlikte** okuyup
her not için bir uygunluk puanı verir. Pahalıdır (CPU'da 10 aday için ~2,4 sn), bu yüzden
yalnızca aramanın ilk adayları yeniden sıralanır (`app.rag.search.RERANK_TOP`).

- `TeiReranker`: bge-reranker-v2-m3, Hugging Face Text Embeddings Inference `/rerank` ucu
  (Docker, CPU). Python tarafına torch/model yüklenmez.
- Ölçüm: docs/rag_olcum_raporu.md. Sağlayıcı `none` ise yeniden sıralama kapalıdır.
"""

from typing import Protocol

import httpx

from app.core.config import Settings


class RerankError(Exception):
    """Reranker servisine ulaşılamadı veya beklenmeyen yanıt döndü."""


class Reranker(Protocol):
    model_name: str

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        """Her metnin sorguyla uygunluk puanı (yüksek = daha ilgili), girdi sırasıyla."""
        ...


class TeiReranker:
    def __init__(
        self,
        url: str,
        *,
        model_name: str = "onnx-community/bge-reranker-v2-m3-ONNX",
        timeout_s: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.model_name = model_name
        self.timeout_s = timeout_s
        self._transport = transport  # testlerde sahte HTTP

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, transport=self._transport
            ) as client:
                resp = await client.post(
                    f"{self.url}/rerank",
                    # truncate: sorgu + not 512 jetonu aşarsa hata vermek yerine kısaltılır.
                    json={"query": query, "texts": texts, "truncate": True},
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Sorgu metni hata iletisine konmaz (kişisel veri içerebilir).
            raise RerankError(f"Reranker servisine ulaşılamadı ({self.url}): {exc}") from exc
        # TEI en yüksek puandan başlayarak sıralı döner; her kayıt girdinin `index`'ini taşır.
        scores: list[float | None] = [None] * len(texts)
        try:
            for item in data:
                scores[int(item["index"])] = float(item["score"])
        except (TypeError, KeyError, ValueError, IndexError) as exc:
            raise RerankError(f"Reranker beklenmeyen yanıt döndürdü ({self.url}).") from exc
        if any(s is None for s in scores):
            raise RerankError(f"Reranker {len(texts)} metinden bazıları için puan döndürmedi.")
        return [s for s in scores if s is not None]


def build_reranker(settings: Settings) -> Reranker | None:
    """Ayara göre reranker; kapalıysa None (arama RRF sırasıyla kalır)."""
    name = settings.reranker_provider
    if name == "none":
        return None
    if name == "tei":
        return TeiReranker(
            settings.reranker_url,
            model_name=settings.reranker_model,
            timeout_s=settings.reranker_timeout_s,
        )
    raise ValueError(f"Bilinmeyen reranker sağlayıcısı: {name}")
