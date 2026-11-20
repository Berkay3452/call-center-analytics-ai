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

## 2. Model karşılaştırması (#337)

Aynı 62 soru ve 85 not, 20 Kasım 2026. Ham sonuçlar ve soru başına sıralar:
`docs/rag_olcum_sonuclari/*.json`. Hepsinin boyutu 1024: `rag_chunks` sütunu değişmez.

### Kaynaktan doğrulanan model bilgileri

| Model | Boyut | Lisans | Türkçe | Önek / talimat | Not |
|---|---|---|---|---|---|
| bge-m3 (üretim) | 1024 | MIT | Evet (100+ dil) | yok | TEI ile sunuluyor |
| multilingual-e5-large | 1024 | MIT | Evet (`tr` dil listesinde) | sorguya `query: `, nota `passage: ` | |
| multilingual-e5-large-instruct | 1024 | MIT | Evet | yalnız sorguya `Instruct: <görev>\nQuery: ` | not öneksiz |
| Snowflake arctic-embed-l-v2.0 | 1024 | Apache-2.0 | Evet (`tr` dil listesinde) | yalnız sorguya `query: ` | |
| Qwen3-Embedding-0.6B | 1024 (32-1024 arası kısaltılabilir) | Apache-2.0 | Evet (100+ dil) | yalnız sorguya `Instruct: <görev>\nQuery:` | |
| jina-embeddings-v3 | 1024 | **CC-BY-NC-4.0 (ticari kullanım yok)** | Evet | görev adaptörü (`retrieval.query` / `retrieval.passage`) | `trust_remote_code` gerekir |
| bge-reranker-v2-m3 | (yeniden sıralayıcı) | Apache-2.0 | Evet | sorgu-not çifti | |

Önekler yukarıdaki kartlardaki varsayılanlardır; Qwen3 ve e5-instruct için görev
cümlesi kartlardaki genel arama talimatıdır (alana özel talimat denenmedi).

### Sonuçlar

**Sahip kapsamı (üretimdeki gibi)**

| Model | isabet@1 | isabet@3 | isabet@5 | MRR | Sorgu medyan | Sorgu p95 | 85 not indeksleme | Bellek |
|---|---|---|---|---|---|---|---|---|
| **bge-m3 (üretim, TEI)** | 0,85 | 0,95 | 1,00 | 0,91 | 94 ms | 180 ms | 21,0 sn | 5,9 GiB (konteyner) |
| multilingual-e5-large | 0,89 | 1,00 | 1,00 | 0,94 | 330 ms | 416 ms | 40,2 sn | 2,8 GB |
| multilingual-e5-large-instruct | 0,89 | 0,98 | 1,00 | 0,93 | 641 ms | 2561 ms | 63,0 sn | 1,9 GB |
| arctic-embed-l-v2.0 | 0,85 | 0,97 | 1,00 | 0,91 | 99 ms | 122 ms | 14,8 sn | 3,0 GB |
| Qwen3-Embedding-0.6B | 0,82 | 0,92 | 1,00 | 0,89 | 945 ms | 1129 ms | 426,4 sn | 1,7 GB |
| jina-embeddings-v3 | ölçülemedi | | | | | | | bkz. aşağısı |
| bge-m3 + bge-reranker-v2-m3 | **1,00** | 1,00 | 1,00 | **1,00** | 2519 ms | 2606 ms | 30,3 sn | 3,0 GB (+ TEI) |

**Tüm notlar (sahip filtresi yok, zor)**

| Model | isabet@1 | isabet@3 | isabet@5 | MRR |
|---|---|---|---|---|
| **bge-m3 (üretim)** | 0,77 | 0,85 | 0,95 | 0,84 |
| multilingual-e5-large | 0,81 | 0,94 | 0,98 | 0,88 |
| multilingual-e5-large-instruct | 0,76 | 0,92 | 0,94 | 0,84 |
| arctic-embed-l-v2.0 | 0,77 | 0,90 | 0,95 | 0,85 |
| Qwen3-Embedding-0.6B | 0,73 | 0,87 | 0,90 | 0,81 |
| bge-m3 + bge-reranker-v2-m3 | 0,90 | 0,95 | 0,98 | 0,93 |

**Kategori başına isabet@3 (tüm notlar)**

| Model | eski | es_anlamli | ekli | kisa | sayi | yazim | ayirt |
|---|---|---|---|---|---|---|---|
| bge-m3 | 0,57 | 1,00 | 1,00 | 1,00 | 1,00 | 0,62 | 1,00 |
| e5-large | 0,71 | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| e5-large-instruct | 0,79 | 1,00 | 1,00 | 1,00 | 1,00 | 0,75 | 1,00 |
| arctic-l-v2 | 0,71 | 1,00 | 1,00 | 1,00 | 1,00 | 0,75 | 1,00 |
| qwen3-0.6b | 0,64 | 1,00 | 1,00 | 1,00 | 1,00 | 0,75 | 0,88 |
| bge-m3 + reranker | 0,86 | 1,00 | 1,00 | 1,00 | 1,00 | 0,88 | 1,00 |

### Ölçüm sınırları (tabloyu okurken)

- **Küçük örneklem:** 62 soru; 0,03-0,05'lik farklar 2-3 soru demek. "yazim" ve diğer
  kategorilerde 8'er soru var. Küçük farklar model üstünlüğü sayılmamalı.
- **Gecikmeler birebir karşılaştırılamaz:** bge-m3 TEI'de (ayrı konteyner, iyileştirilmiş
  çıkarım); diğerleri bu işlemde sentence-transformers ile CPU'da, makine başka işlerle
  meşgulken koşuldu (RAM dar, sayfa dosyası C:'de dolu). Qwen3'ün 426 sn'lik indekslemesi
  büyük olasılıkla bellek baskısından. Sıralamayı değil büyüklük mertebesini gösterir.
- **Bellek:** bge-m3 için konteynerin `docker stats` değeri; diğerleri için işlemin tepe
  belleği. Aynı şey değil.
- Yalnız sentetik not ve sorular; gerçek kullanıcı sorusu dağılımı farklı olabilir.

### Ölçülemeyenler

- **jina-embeddings-v3:** üç denemede de yüklenemedi: önce `einops` eksikti (eklendi), sonra
  uzak kod yeni `transformers` ile uyumsuzdu (`<5` ile çözüldü), sonra model yüklenirken
  bellek yetmedi (`MemoryError`, boş RAM ~4 GB, sayfa dosyası C:'de dolu). Daha fazla
  belleği olan bir makinede şu komutla ölçülür (uzak kod `bd55a5ec` sürümünde incelendi:
  ağ, `subprocess`, `exec` çağrısı yok; yine de kod çalıştırır ve model **CC-BY-NC**
  olduğundan ticari kullanıma uygun değildir):

  ```powershell
  uv run --with torch --with sentence-transformers --with einops --with "transformers<5" python -m scripts.rag_model_karsilastirma --backend st --name jina-v3 --model jinaai/jina-embeddings-v3 --trust-remote-code --revision ab036b023d30b4d1138c4c3bfa9f0c445ab455d6 --st-task-query retrieval.query --st-task-passage retrieval.passage --out jina-v3.json
  ```

- **Hugging Face API (bge-m3):** `backend/.env` içinde `EMBEDDING_API_KEY` boş ve başka
  bir Hugging Face anahtarı yok; kota (429), hız ve hazır olma durumu ölçülemedi. Betik
  hazır: anahtar `backend/.env` içine yazıldıktan sonra yalnız sentetik not gönderilir.
  429'da üstel bekleme ile yeniden dener.

  ```powershell
  uv run python -m scripts.rag_model_karsilastirma --backend openai --base-url <HF OpenAI uyumlu adres>/v1 --model BAAI/bge-m3 --api-key-env EMBEDDING_API_KEY --name bge-m3-hf-api --out hf-api.json
  ```

### Karar önerisi

1. **Varsayılan embedding değişmez: bge-m3 kalır.** Hiçbir aday kararlı bir üstünlük
   göstermedi. En iyi aday e5-large: sahip kapsamında isabet@3 0,95→1,00 (62 sorunun
   ~3'ü) ve "yazim" kategorisinde 0,62→1,00 iyileşme var, ama fark küçük, bu sette
   gecikme 3-4 kat yüksek çıktı ve geçişte 85 nottan büyük gerçek veride tüm notların yeniden
   indekslenmesi gerekir. arctic-l-v2 bge-m3 ile aynı düzeyde (MRR 0,91 / 0,85), Qwen3 ve
   e5-instruct daha iyi değil. Bu yüzden yeniden indeksleme issue'su açılmadı.
2. **Asıl kazanç yeniden sıralayıcıdan geliyor.** bge-m3 + bge-reranker-v2-m3: sahip
   kapsamında isabet@1 0,85→1,00 ve MRR 0,91→1,00; tüm notlarda MRR 0,84→0,93; zayıf
   kategoriler "eski" 0,57→0,86 ve "yazim" 0,62→0,88. Bedeli: CPU'da sorgu başına ~2,4 sn
   ek gecikme (10 aday), ~3 GB ek bellek. Üretimde şu an yeniden sıralama yok. Eklenip
   eklenmeyeceği (ve hangi gecikmeyle, TEI reranker ya da GPU ile) Berkay'ın kararıdır;
   verilirse ayrı issue olarak ele alınır.
