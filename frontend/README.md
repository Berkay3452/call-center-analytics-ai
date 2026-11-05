# Frontend — Miço Usta Çağrı Analitiği Sistemi

Next.js (App Router, TypeScript, Tailwind CSS) tabanlı frontend iskelet.  
Backend hazır olana kadar `mocks/` klasöründeki JSON verileriyle çalışır.

---

## Gereksinimler

| Araç | Minimum Sürüm |
|------|---------------|
| Node.js | 20 |
| npm | 9 |

---

## Kurulum

```bash
# 1. Bağımlılıkları yükle
npm install

# 2. Geliştirme sunucusunu başlat (http://localhost:3000)
npm run dev
```

---

## Komutlar

| Komut | Açıklama |
|-------|----------|
| `npm run dev` | Geliştirme sunucusunu başlatır |
| `npm run build` | Production build oluşturur (TypeScript tip kontrolü dahil) |
| `npm run start` | Production build'i başlatır |
| `npm run lint` | ESLint kontrolü çalıştırır |

---

## Tarayıcılar arası E2E testleri (#155)

Komutları `frontend` dizininde çalıştırın. Aynı E2E paketi (temel duman senaryoları dahil)
üç projede çalışır: Chrome motorunu kullanan Playwright Chromium (`chromium`), gerçek
Microsoft Edge (`msedge` kanalı) ve Playwright Firefox (`firefox`). Edge projesi Chromium'a
sessizce geri dönmez; Microsoft Edge'in kurulu olması gerekir.

```bash
# İlk kurulum / Playwright sürümü güncellendiğinde
npx playwright install chromium firefox

# Microsoft Edge kurulu değilse (sistem kurulumu; yönetici yetkisi gerekebilir)
npx playwright install msedge

# Üç tarayıcıda tüm senaryolar
npm run e2e
# Eşdeğer komut
npx playwright test

# Tek tarayıcı veya yalnızca duman senaryoları
npm run e2e -- --project=chromium
npm run e2e -- --project=msedge
npm run e2e -- --project=firefox
npx playwright test e2e/smoke.spec.ts --project=firefox

# Görünür tarayıcı ve HTML sonuç raporu
npx playwright test --project=msedge --headed
npx playwright show-report
```

Linux/CI ortamında tarayıcıların işletim sistemi bağımlılıkları için
`npx playwright install --with-deps chromium firefox` kullanın; Edge'i ayrıca
`npx playwright install msedge` ile kurun. Tarayıcı indirmeleri ağ erişimi gerektirir.

Playwright geliştirme sunucusunu otomatik başlatır; varsayılan olarak mock verileri
kullanır. Açık bir sunucu varsa aynı mock ayarıyla çalıştığından emin olun veya testten
önce kapatın. Gerçek backend için `NEXT_PUBLIC_USE_MOCKS=false` ayarlayın; mock'a özel
senaryolar bu modda atlanır. PowerShell örneği: `$env:NEXT_PUBLIC_USE_MOCKS='true'; npm run e2e`.
`BASE_URL` ve `PORT` ortam değişkenleri mevcut sunucu/adres seçimini destekler.

Testler paylaşılan mock akışlarının birbirini etkilememesi için tek worker ile sıralı
çalışır. Genel düğme denetimi her tıklamayı ayrı bir sayfada başlatır; bu,
Firefox'ta önceki istemci yönlendirmesinin sonraki gezinmeyi iptal etmesini önler.
Odak halkası kontrolleri gerçek Tab/Shift+Tab geçişi kullanır; programatik `focus()`
çağrısının `:focus-visible` üretmesi tarayıcılar arasında farklılık gösterebilir.
Başarısız testlerin ekran görüntüleri ve videoları `test-results/`, HTML raporu
`playwright-report/` altında oluşur; CI tekrarlarında trace kaydedilir. Mevcut GitHub
Actions işi lint ve build çalıştırır; bu iş E2E testlerini henüz çalıştırmaz.

---

## Klasör Yapısı

```
frontend/
├── app/                        # Next.js App Router sayfaları
│   ├── admin/
│   │   ├── analytics/page.tsx  # Çağrı analitiği & KPI kartları
│   │   ├── calls/
│   │   │   ├── page.tsx        # Çağrı listesi
│   │   │   └── [id]/page.tsx   # Çağrı detay
│   │   └── crm/page.tsx        # CRM AI önerileri
│   ├── owner/
│   │   └── assistant/page.tsx  # Sesli asistan sohbet ekranı
│   ├── layout.tsx              # Kök layout (Sidebar + Header)
│   └── page.tsx                # Kök → /admin/analytics yönlendirme
├── components/
│   ├── Header.tsx              # Üst çubuk + rol seçici
│   ├── Sidebar.tsx             # Sol menü (role göre navigasyon)
│   └── PlaceholderCard.tsx     # Placeholder kart bileşeni
├── lib/
│   ├── api.ts                  # Mock API istemcisi (backend hazır olunca gerçek fetch ile değişir)
│   ├── role-context.tsx        # Rol yönetimi React context (auth yokken state/URL bazlı)
│   └── types.ts                # Paylaşılan TypeScript tip tanımları
└── mocks/
    ├── calls.json              # Örnek çağrı kayıtları
    ├── kpis.json               # KPI özet verileri
    └── crm-suggestions.json    # CRM AI öneri verileri
```

---

## Rol Sistemi

Gerçek bir auth mekanizması yoktur. Header'daki **Rol Seçici** dropdown ile `Admin` ve `Tekne Sahibi` rolleri arasında geçiş yapılabilir.

- **Admin**: Çağrı Analitiği, Çağrı Listesi, CRM Önerileri
- **Tekne Sahibi**: Asistan Sohbet Ekranı

> **Not:** Miço Usta JWT entegrasyonunda `lib/role-context.tsx` içindeki `RoleProvider` doğrudan JWT claim'lerini okuyacak şekilde güncellenecektir.

---

## Mock Veriler

`mocks/` klasöründeki JSON dosyaları, backend hazır olana kadar arayüzü besler.  
`lib/api.ts` içindeki her fonksiyon, ileride `fetch()` ile gerçek endpoint'e bağlanacak şekilde tasarlanmıştır — değiştirilmesi gereken tek yer burasıdır.

---

## CI

GitHub Actions: `.github/workflows/frontend-ci.yml`  
Her PR'da `frontend/**` değiştiğinde otomatik lint + build kontrolü çalışır.
