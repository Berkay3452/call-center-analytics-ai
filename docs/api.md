# API Sözleşmesi

**Issue:** #46 · **Şemalar:** `backend/app/schemas/api.py` (+ `analysis.py`, `assistant.py`, `common.py`) · **Frontend tipleri:** `frontend/lib/api-types.ts` · **Örnekler:** `docs/ornekler/api/` · **Tarih:** 2026-10-13

Bu dosya Python AI servisinin dışa açtığı uçların sözleşmesidir. Backend uçları (#48, #49, #51, #52, #28) ve arayüz ekranları (#10, #29, #53, #54) **bu şemalara göre** yazılır. Şema değişecekse önce bu dosya, `api.py` ve `api-types.ts` birlikte güncellenir; `backend/tests/test_api_contract.py` üçünün ve örnek JSON'ların uyumunu denetler.

## 1. Genel kurallar

| Konu | Kural |
|---|---|
| Önek | Tüm uçlar `/api/v1` altındadır. |
| Alan adları | snake_case (backend ile aynı). Arayüz kendi tiplerine (`lib/types.ts`) `lib/api.ts` içinde çevirir. |
| Tarih/saat | ISO 8601, saat dilimli (UTC): `2026-10-12T09:05:00Z`. Gün: `2026-10-12`. |
| Boş bilgi | Konuşmada geçmeyen alan `null` gelir, uydurulmaz. Arayüz "—" gösterir. |
| Enum değerleri | `docs/enums.md` listeleri; ekranda Türkçe karşılık `lib/types.ts` etiketlerinden. |
| Sayfalama | Liste uçları `Page` döner: `items`, `total`, `page`, `page_size` (en fazla 100). |
| Hata | Her hata `ErrorResponse` biçimindedir: `error.code`, `error.message`, `error.details`, `error.request_id`. |

## 2. Kimlik doğrulama (#24)

Servisi yalnızca Miço Usta .NET uygulaması çağırır; tarayıcı doğrudan çağırmaz (geliştirmede Next.js sunucu tarafı çağırır).

| Başlık | Ne zaman | Açıklama |
|---|---|---|
| `X-Service-Key` | Her istekte | Paylaşılan servis anahtarı. Eksik/yanlışsa 401. |
| `X-User-Id` | Tekne sahibi uçlarında zorunlu | Oturumdaki tekne sahibinin kimliği (UUID, `customers.id`). Eksikse veya UUID değilse 400. |

Admin/tekne sahibi rol ayrımını .NET uygulaması yapar. Tekne sahibi uçları **yalnızca** `X-User-Id`'deki kişinin verisini döndürür; gövdede kimlik alınmaz.

## 3. Uç listesi

| Yöntem ve yol | Kim | Gövde / parametre | Yanıt | Issue |
|---|---|---|---|---|
| `GET /calls` | Admin | `CallFilters` (sorgu) | `Page` of `CallListItem` | #51 |
| `GET /calls/{call_id}` | Admin | — | `CallDetail` | #51 |
| `GET /crm` | Admin | `CallFilters` (sorgu) | `Page` of `CrmRecordItem` | #51 |
| `POST /crm/{call_id}/approve` | Admin | `CrmApproveIn` (isteğe bağlı) | `CrmReviewOut`; eşleşme yoksa 409 | #106 |
| `POST /crm/{call_id}/reject` | Admin | `CrmRejectIn` (isteğe bağlı) | `CrmReviewOut` | #106 |
| `GET /service-orders` | Admin | `ServiceOrderFilters` (sorgu) | `Page` of `ServiceOrderListItem` | #118 |
| `GET /service-orders/{order_id}` | Admin | — | `ServiceOrderDetail` | #118 |
| `PATCH /service-orders/{order_id}/status` | Admin | `ServiceOrderStatusUpdate` | `ServiceOrderDetail` | #118 |
| `GET /analytics/summary` | Admin | `PeriodFilter` (sorgu) | `KpiSummary` | #52 |
| `POST /calls` | Admin | `CallCreate` (JSON) | 202 `CallAccepted` | #48 |
| `POST /calls/audio` | Admin | multipart: `file` (wav/mp3/m4a/ogg/flac/aac/webm, en fazla 25 MB) + `AudioCallMeta` alanları | 202 `CallAccepted`; aynı ses daha önce yüklendiyse 409 (`details.call_id`) | #49 |
| `POST /calls/{call_id}/analyze` | Admin | — | 202 `CallAccepted` (yeni analiz sürümü) | #48 |
| `GET /calls/{call_id}/status` | Admin | — | `CallStatus` | #48 |
| `GET /calls/{call_id}/audio` | Admin | — | Ses dosyası akışı (Range destekli 200/206) | #80 |
| `POST /chat/messages` | Tekne sahibi | `ChatQuestion` | `ChatReply` | #28 |
| `POST /chat/messages/stream` | Tekne sahibi | `ChatQuestion` | SSE akışı (`ChatStreamEvent`, bkz. §4) | #28 |
| `POST /assistant/chat` | Tekne sahibi | `ChatQuestion` | SSE akışı (`token` -> `sources` -> `done`) | #28 |
| `GET /chat/sessions` | Tekne sahibi | — | `ChatSessionOut` listesi (yeniden eskiye) | #28 |
| `GET /chat/sessions/{session_id}` | Tekne sahibi | — | `ChatSessionDetail` | #28 |
| `GET /assistant/sessions` | Tekne sahibi | — | `ChatSessionOut` listesi | #28 |
| `GET /assistant/sessions/{id}` | Tekne sahibi | — | `ChatSessionDetail` | #28 |

Başka kullanıcının sohbet oturumu istenirse 404 döner (varlığı da sızdırılmaz).

## 4. Şemalar

### Çağrılar
- `CallListItem`: liste satırı. Santral bilgisi + en son analizden `call_type`, `request_category`, `urgency`, `sales_outcome`, `loss_reason`, `summary`. Analiz yoksa bu alanlar `null`.
- `CallDetail`: çağrı, `TranscriptOut` (metin + `TranscriptSegmentOut` listesi; kişisel veriler maskeli) ve en son analiz `AnalysisOut`.
- `AnalysisOut`: bir analiz sürümü. Agent çıktıları `CallClassification`, `CrmExtraction`, `SalesAnalysis`, `CallSummary`; agent kayıtları `AgentRun`. Başarısız agent'ın alanı `null`, nedeni `errors`'ta.
- `CallFilters`: `date_from`, `date_to`, `call_type`, `urgency`, `request_category`, `state`, `status`, `marina` (tam eşleşme), `q` (müşteri/tekne/marina adında arama), `page`, `page_size`.

### Çağrı durumu (`CallState`)
| Değer | Anlamı |
|---|---|
| `beklemede` | Kuyrukta |
| `yaziya_cevriliyor` | Ses STT ile yazıya çevriliyor (yalnızca sesli çağrı) |
| `isleniyor` | Agent'lar çalışıyor |
| `tamam` / `kismi` / `basarisiz` | Analiz sonucu (`AnalysisStatus` ile aynı) |

Arayüz `GET /calls/{id}/status` ile durumu 2–3 saniyede bir sorar; `tamam`, `kismi` veya `basarisiz` gelince durur.

> `calls.state` ve `calls.error` sütunları #48 ile eklendi; seed verisindeki analizli çağrılar `tamam` durumundadır.

### Servis emirleri (#118)
- `ServiceOrderListItem`: sayfalı liste satırı (`id`, `status`, `category`, `description`, `scheduled_at`, `completed_at`, `created_at`, `customer_id`, `customer_name`, `customer_phone`, `boat_id`, `boat_name`, `boat_model`, `marina`, `craftsman_id`, `craftsman_name`, `source_call_id`).
- `ServiceOrderDetail`: servis emri detayı (`customer`: `ServiceOrderCustomerOut`, `boat`: `ServiceOrderBoatOut`, `craftsman`: `ServiceOrderCraftsmanOut`, `source_call`: `ServiceOrderSourceCallOut`).
- `ServiceOrderCustomerOut`: müşteri bilgisi (`id`, `full_name`, `phone`, `email`, `marina`).
- `ServiceOrderBoatOut`: tekne bilgisi (`id`, `name`, `model`, `year`, `marina`).
- `ServiceOrderCraftsmanOut`: atanan usta bilgisi (`id`, `full_name`, `specialty`, `phone`).
- `ServiceOrderSourceCallOut`: servis emrinin kaynak çağrısı ve CRM önerisi özeti (#106).
- `ServiceOrderStatusUpdate`: durum güncelleme gövdesi (`status`: `ServiceOrderStatus`).
- `ServiceOrderFilters`: `status`, `date_from`, `date_to`, `marina`, `q`, `page`, `page_size`.
- **Durum Geçişi:** `yeni_atandi` -> `kesifte` -> `onaylandi` -> `devam_ediyor` -> `tamamlandi`. Geçersiz geçiş 400 döner. `tamamlandi` durumuna geçildiğinde `completed_at` otomatik doldurulur.

### CRM önerileri (#106)
- `CrmRecordItem`: hocanın 7 alanı (`request_category`, `location`, `problem`, `service_mode`, `urgency`, `potential_job`, `next_action`), alıntılar (`evidence`), inceleme durumu (`review_status`: `bekliyor` / `onaylandi` / `reddedildi`), düzenlenen alanlar (`edited_fields`), servis emri (`service_order_id`) ve kaynağı olan çağrı. Her çağrının en son analiz sürümünden gelir.
- `CrmApproveIn`: isteğe bağlı 7 alan düzenlemesi (`request_category`, `location`, `problem`, `service_mode`, `urgency`, `potential_job`, `next_action`) ve `note`.
- `CrmRejectIn`: red nedeni veya not (`note`).
- `CrmReviewOut`: inceleme kaydı (`id`, `call_id`, `analysis_id`, `status`, `edited_fields`, `note`, `reviewed_at`, `service_order_id`).

### Çağrı alma
- `CallCreate`: sesi olmayan çağrı (geliştirme ve sentetik veri için). `transcript` (düz metin) veya `SegmentIn` listesinden biri zorunlu.
- `AudioCallMeta`: sesli çağrının form alanları (`CallCreate` ile aynı, transkript hariç). Akış: ses kaydedilir → `yaziya_cevriliyor` (STT) → `isleniyor` (agent'lar) → sonuç. STT hata verirse `POST /calls/{id}/analyze` yeniden yazıya çevirmeyi başlatır.
- `CallAccepted`: oluşturulan çağrının kimliği, durumu ve arka plan görevinin kimliği.
- `CallStatus`: anlık durum, biten son analiz sürümü, hata.

### KPI
- `KpiSummary`: dönem, toplam/analiz edilen çağrı, çağrı tiplerine göre sayılar, `converted_sales` ve `conversion_rate`, `lost_by_reason`, `top_problems` ve `busiest_marinas` (`CountItem`), `by_category`, `by_urgency`, `daily_calls` (`DailyCount`; boş gün 0), `avg_answer_delay_s`.
- `PeriodFilter`: `date_from`, `date_to`, `marina` (tam eşleşme); boşsa son 30 gün. Sayılar her çağrının **en son** analiz sürümünden hesaplanır; LLM kullanılmaz.

### Miço AI sohbeti
- `ChatQuestion`: `question` ve isteğe bağlı `session_id` (boşsa yeni oturum, başlık ilk sorudan).
- `ChatReply`: kaydedilen soru ve cevap (`ChatMessageOut`). Cevapta `question_type`, `sources` (`SourceRef` kaynak kartları) ve `found` (false ise "bulamadım" durumu).
- `ChatSessionOut`, `ChatSessionDetail`: oturum listesi ve geçmiş.
- `StatusEvent`, `DeltaEvent`, `DoneEvent`, `ErrorEvent`: akış olayları (`ChatStreamEvent`).
- **Akışlı cevap:** arayüz `POST /chat/messages/stream` kullanır (Server-Sent Events, `text/event-stream`); `POST /chat/messages` aynı cevabı tek seferde döner (test ve yedek). Her olay `event: <tür>` ve `data: <JSON>` satırlarıdır, olaylar boş satırla ayrılır. Sıra:
  1. `StatusEvent` (`araniyor`, `dogrulaniyor`): arayüz "Kayıtlar aranıyor…" gibi durum gösterir.
  2. `DeltaEvent`: cevap metninin parçaları; arayüz sırayla birleştirir (yazma efekti).
  3. `DoneEvent`: kaydedilen soru/cevap (`ChatReply`), kaynak kartları ve `found`. Arayüz kaynak kartlarını bu olayda çizer.
  4. Hata olursa `ErrorEvent`; akış kapanır.
  Metin, **kaynak kontrolü bittikten sonra** akıtılır: desteklenmeyen iddia cevaptan düşürüldüğü için ekrandaki cümle sonradan silinmez. Akış koparsa arayüz `GET /chat/sessions/{id}` ile kayıtlı cevabı alabilir.

## 5. Frontend bağlantısı (#10)

- **OpenAPI belgesi:** `frontend/openapi.json` (tek kopya). TypeScript tipleri `npm run gen:api` ile `frontend/lib/api/schema.ts` içine üretilir. Alan listesi backend şemalarıyla uyumlu kalsın diye `test_api_contract.py` karşılaştırır.
- **Mock/gerçek geçişi:** `NEXT_PUBLIC_USE_MOCKS=true` iken `frontend/mocks/` (örneklerin kopyası), `false` iken gerçek servis. Ayarlar `frontend/.env.example` dosyasında.
- **Servis anahtarı tarayıcıya verilmez.** Sunucu bileşenleri servisi `API_URL` ile doğrudan çağırır; tarayıcıdaki kod `/api/backend/...` vekil uç noktasından geçer ve anahtarı (`SERVICE_KEY`) orası ekler.

## 6. Örnekler

| Dosya | Şema |
|---|---|
| `cagri_listesi.json` | `Page` of `CallListItem` |
| `cagri_detayi.json` | `CallDetail` (hocanın Tuzla Marina senaryosu) |
| `crm_listesi.json` | `Page` of `CrmRecordItem` |
| `servis_emirleri.json` | `Page` of `ServiceOrderListItem` |
| `servis_emri_detayi.json` | `ServiceOrderDetail` |
| `kpi_ozeti.json` | `KpiSummary` |
| `cagri_olustur_istek.json` | `CallCreate` |
| `cagri_kabul.json` | `CallAccepted` |
| `cagri_durumu.json` | `CallStatus` |
| `sohbet_soru_istek.json` | `ChatQuestion` |
| `sohbet_cevabi.json` | `ChatReply` |
| `sohbet_oturumu.json` | `ChatSessionDetail` |
| `sohbet_akisi.sse` | `ChatStreamEvent` dizisi (SSE biçimi) |

Arayüz bu dosyaları mock olarak kullanabilir; gerçek uç gelince yalnızca `lib/api.ts` değişir.

## 7. Şema değiştirirken
1. `backend/app/schemas/api.py` (veya `analysis.py`, `assistant.py`)
2. `frontend/lib/api-types.ts` ve `frontend/openapi.json` (sonra `npm run gen:api`)
3. Bu dosya ve `docs/ornekler/api/` örnekleri
4. `uv run pytest tests/test_api_contract.py`
