# RAG embedding ölçüm raporu

Üst issue: #318. Bu belge embedding modellerinin karşılaştırmasını tutar. Bölümler alt
issue'larla birlikte büyür: önce ölçüm altyapısı (#336), sonra modellerin ölçümü (#337).

Yalnız sentetik veri kullanılır (`data/synthetic/boat_notes.json`, 85 not). Üretimdeki
`rag_chunks` tablosuna **dokunulmaz**: tüm vektörler bellekte tutulur, veritabanına yazılmaz.

## 1. Ölçüm altyapısı (#336)

### Tek komutla ölçüm

`backend/` klasöründen:

```powershell
# TEI (üretimdeki bge-m3)
uv run python -m scripts.rag_model_karsilastirma --backend tei --url http://localhost:8080 --name bge-m3 --tei-container call-center-dev-embeddings-1 --out sonuc/bge-m3.json

# OpenAI uyumlu API (ör. Hugging Face)
uv run python -m scripts.rag_model_karsilastirma --backend openai --base-url <adres> --model <ad> --api-key-env EMBEDDING_API_KEY --name bge-m3-api --out sonuc/bge-m3-api.json

# Yerel sentence-transformers (e5 için önek, jina için --trust-remote-code)
uv run --with torch --with sentence-transformers python -m scripts.rag_model_karsilastirma --backend st --model intfloat/multilingual-e5-large --name e5-large --query-prefix "query: " --passage-prefix "passage: " --out sonuc/e5-large.json

# Birkaç sonucu tek tabloda topla
uv run python -m scripts.rag_model_karsilastirma --compare sonuc/*.json
```

Modeller indirilirken disk için `HF_HOME` proje altındaki D: önbelleğine verilir
(C: diski dolu olduğundan).

### Ölçütler

- **isabet@k** (recall@k): beklenen not ilk k sonuçta mı (k = 1, 3, 5).
- **MRR**: beklenen notun sırasının tersinin ortalaması.
- **Gecikme**: tek sorgunun gömülme süresi (ilk, medyan, p95), tüm notların indeksleme süresi.
- **Tepe bellek**: TEI için konteynerin `docker stats` değeri, yerel modelde işlem belleği.
- İki kapsam raporlanır: **sahip kapsamı** (üretimdeki gibi, yalnız sorgulayanın notları aday
  olur) ve **tüm notlar** (sahip filtresi yok; asıl ayırt etme gücünü ölçer, daha zordur).

### Soru seti

Eski 14 soru (`rag_eval.json`) korunur. Zor set `data/synthetic/rag_eval_zor.json`: 48 soru,
altı kategori, her kategoride 8 soru:

| Kategori | Neyi sınar | Örnek |
|---|---|---|
| es_anlamli | Notta geçen sözcük sorudan farklı | "Kutup'ta kabin soğutması için ne yapıldı?" |
| ekli | Türkçe ekler | "Çapariz'ın klimasındaki süzgeçler temizlenmiş miydi?" |
| kisa | İki üç sözcüklük sorgu | "Zıpkın FM200" |
| sayi | Sayı, birim, sürüm | "Karayel'de antifriz kaç derece?" |
| yazim | Aksansız ve yazım hatalı | "Poyraz akulerı degistirildi mi" |
| ayirt | Aynı teknede benzer notlar | "Kalyon'un yedek filtresi teknede bırakıldı mı?" |

Her soruda teknenin adı geçer; böylece sahip filtresi olmayan "tüm notlar" kapsamı da adil
olur. Testler (`tests/test_rag_model_karsilastirma.py`) soru setinin bütünlüğünü, kategori
dengesini, beklenen notların sahiple tutarlılığını ve ölçüt hesaplarını doğrular.

### Referans ölçüm: bge-m3 (TEI, CPU, 1024 boyut)

62 soru (14 eski + 48 zor), 85 not, 20 Kasım 2026:

| Kapsam | isabet@1 | isabet@3 | isabet@5 | MRR |
|---|---|---|---|---|
| Sahip kapsamı | 0,85 | 0,95 | 1,00 | 0,91 |
| Tüm notlar (zor) | 0,77 | 0,85 | 0,95 | 0,84 |

| Gecikme | Değer |
|---|---|
| Sorgu (medyan / p95) | 94 ms / 180 ms |
| 85 notu indeksleme | 21,0 sn |
| TEI konteyner belleği | 5,9 GiB |

Kategori başına isabet@3 (tüm notlar): es_anlamli 1,00; ekli 1,00; kisa 1,00; sayi 1,00;
ayirt 1,00; **eski 0,57; yazim 0,62**.

Okuma: bge-m3 eş anlamlıyı, ekleri ve kısa sorguyu iyi çözüyor. Zayıf yerleri, eski sette
sahip adı geçmeyen sorular (tüm notlar kapsamında doğal olarak zor; üretimde sahip filtresi
bunu kapatıyor) ve aksansız/yazım hatalı sorgular. Diğer modeller bu iki sütuna göre
değerlendirilecek.

Ham sonuç ve soru başına sıralar JSON çıktısında (`siralar`) durur; yanlış sıralanan
sorular oradan bulunabilir.
