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
