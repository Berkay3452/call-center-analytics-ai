# Miço Usta Çağrı Analitiği ve Miço AI

İstanbul Gedik Üniversitesi, MFK420 Mezuniyet Projesi. Telefon görüşmelerini otomatik analiz eden, tekne bakım ve servis firması **Miço Usta** için tasarlanmış, yapay zekâ destekli çağrı analitiği sistemi.

Ekip: Berkay Öztürk (AI, agent, RAG), Ahmet Aydın (frontend), Melih Uyanık (backend, veri).

## Ne yapar?

1. **Çağrıdan CRM kaydı (Admin):** Ses veya metin yüklenir; konuşma yazıya çevrilir, 4 yapay zekâ agent'ı 7 CRM alanını çıkarır. Yönetici öneriyi onaylar, düzenler veya reddeder; onayda servis emri açılır.
2. **Çağrı Analitiği (Admin):** Çağrı sayısı, acil, satışa dönüşen ve kaybedilen çağrılar, kategori ve marina dağılımları, satış kaybı nedenleri.
3. **Miço AI (Tekne Sahibi):** Tekne sahibinin kendi verisinden, kaynak göstererek cevap veren sohbet asistanı. Sayıları kod hesaplar, model uydurmaz.

Tüm veri sentetiktir (gerçek müşteri verisi yok).

## Teknolojiler

Python 3.12 · FastAPI · Celery + Redis · PostgreSQL 17 + pgvector · LangGraph · faster-whisper · bge-m3 · Next.js 16 · TypeScript · Tailwind · Docker

## Çalıştırma

Ayrıntılı rehber: [`docs/calistirma.md`](docs/calistirma.md).

```bash
# Tüm sistem Docker'da (6 parça)
docker compose -f infra/docker-compose.yml --profile app up -d
```

Geliştirme için: backend klasöründe `uv run python -m scripts.dev`, frontend klasöründe `npm run dev` (http://localhost:3000). `backend/.env` içinde `LLM_API_KEY` gerekir (`backend/.env.example`).

## Belgeler

| Belge | İçerik |
|---|---|
| [`Sistem_mimarisi_v4.md`](Sistem_mimarisi_v4.md) | Mimari, kararlar, mevcut durum (v4.1) |
| [`docs/db_schema.md`](docs/db_schema.md) | Veritabanı şeması ve ER diyagramı |
| [`docs/api.md`](docs/api.md) | API sözleşmesi |
| [`docs/agent_dogrulugu.md`](docs/agent_dogrulugu.md) | Yapay zekâ doğruluk ölçümü |
| [`docs/stt_karari.md`](docs/stt_karari.md) | Konuşma tanıma kararı ve ölçümü |
| [`docs/canliya_alma.md`](docs/canliya_alma.md) | Canlıya alma rehberi |
| [`docs/ekip_test_senaryosu.md`](docs/ekip_test_senaryosu.md) | Ekip içi test senaryosu (Miço AI örnek soruları: `docs/test_senaryosu.md`) |
| [`docs/hoca_demo_akisi.md`](docs/hoca_demo_akisi.md) | Hoca toplantısı demo akışı |
| [`docs/calistirma.md`](docs/calistirma.md) | Çalıştırma rehberi ve sorun giderme |
| [`docs/dayaniklilik.md`](docs/dayaniklilik.md), [`docs/guvenlik_yuk.md`](docs/guvenlik_yuk.md) | Dayanıklılık, yük ve güvenlik ölçümleri |
