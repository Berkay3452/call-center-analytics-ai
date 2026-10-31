import { test, expect } from "@playwright/test";

test.describe("Miço Usta — Uçtan Uca Duman Testleri (#116)", () => {
  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 1: Analitik Sayfası
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 1 (Analitik): KPI kartları, arama hacmi ve kayıp nedenleri render edilir", async ({
    page,
  }) => {
    await page.goto("/admin/analytics");

    // Sayfa başlığı / dashboard başlığı
    await expect(page.locator("h1")).toContainText(/Çağrı Analitiği|Analitik/i);

    // KPI özet kartları
    await expect(page.getByText("Gelen Çağrı")).toBeVisible();
    await expect(page.getByText("Yeni Müşteri")).toBeVisible();
    await expect(page.getByText("Servis Talebi")).toBeVisible();
    await expect(page.getByText("Satışa Dönüşen")).toBeVisible();

    // Arama hacmi / Günlük trend grafiği
    await expect(
      page.getByRole("heading", { name: "Günlük Çağrı Sayısı Trendi" }),
    ).toBeVisible();

    // Satış kaçırma sebepleri bölümü
    await expect(
      page.getByRole("heading", { name: "Satış Kaçırma Sebepleri" }),
    ).toBeVisible();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 2: Çağrı Listesi (Sayfalama, Filtreleme ve Arama)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 2 (Çağrı Listesi): Sayfalama, marina seçici ve arama kutusu çalışır", async ({
    page,
  }) => {
    await page.goto("/admin/calls");

    // Çağrı listesi tablosunun yüklendiğini doğrula
    const callsTable = page.locator("table.min-w-full").first();
    await expect(callsTable).toBeVisible();
    await expect(callsTable.locator("tbody tr").first()).toBeVisible();

    // 1. Marina filtresi
    const marinaSelect = page.locator("#filter-marina");
    await expect(marinaSelect).toBeVisible();
    await marinaSelect.selectOption({ label: "Tuzla Marina" });
    await expect(page).toHaveURL(/marina=Tuzla\+Marina|marina=Tuzla%20Marina/);

    // 2. Arama kutusu ile filtreleme (300ms debounce)
    const searchInput = page.locator("#calls-filter-search-input");
    await expect(searchInput).toBeVisible();
    await searchInput.fill("Ahmet");
    await expect(searchInput).toHaveValue("Ahmet");
    await expect(page).toHaveURL(/q=Ahmet/);

    // Filtreyi temizle
    await searchInput.fill("");
    await marinaSelect.selectOption({ value: "all" });

    // 3. Sayfalama (Sayfa Değiştirme)
    const page2Button = page.getByRole("button", { name: "Sayfa 2" });
    if (await page2Button.isVisible()) {
      await page2Button.click();
      await expect(page).toHaveURL(/page=2/);
      await expect(page2Button).toHaveAttribute("aria-current", "page");
    } else {
      // 2. sayfa butonu yoksa sonraki sayfaya git butonunu sına
      const nextButton = page.getByRole("button", { name: "Sonraki sayfaya git" });
      if (await nextButton.isEnabled()) {
        await nextButton.click();
        await expect(page).toHaveURL(/page=2/);
      }
    }
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 3: Çağrı Detayı (Konuşmacı Etiketleri, Satış Analizi ve Ses Çalar)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 3 (Çağrı Detayı): Konuşmacı etiketleri, satış analizi ve ses oynatıcı doğrulanır", async ({
    page,
  }) => {
    // Çağrı listesine git ve ilk çağrı detayına tıkla
    await page.goto("/admin/calls");
    const callsTable = page.locator("table.min-w-full").first();
    const firstCallLink = callsTable.locator("tbody tr a").first();
    await expect(firstCallLink).toBeVisible();
    await firstCallLink.click();

    // URL'in /admin/calls/[id] formatına geçtiğini doğrula
    await expect(page).toHaveURL(/\/admin\/calls\/[a-zA-Z0-9-]+/);

    // 1. Konuşmacı etiketleri (Transkript bölümü)
    await expect(page.getByText(/⚓ Müşteri|Müşteri/i).first()).toBeVisible();
    await expect(
      page.getByText(/🛠 Temsilci|Temsilci \(Miço Usta\)/i).first(),
    ).toBeVisible();

    // 2. Satış Analizi kutusu
    await expect(
      page.getByRole("heading", { name: "Satış Analizi" }),
    ).toBeVisible();
    await expect(page.getByText("Satış Durumu").first()).toBeVisible();

    // 3. Ses Oynatıcı (AudioPlayer) ve Oynat/Duraklat kontrolü
    await expect(
      page.getByRole("heading", { name: "Görüşme Ses Kaydı" }),
    ).toBeVisible();
    const playButton = page.locator('button[aria-label="Oynat"], button[aria-label="Duraklat"]');
    await expect(playButton).toBeVisible();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 4: CRM Akışı (#113 - Onay, Düzenleme ve Ret Butonları)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 4 (CRM Akışı): sekmeler, Düzenle/Reddet pencereleri, onay ve elle eşleştirme çalışır", async ({
    page,
  }) => {
    await page.goto("/admin/crm");

    // Durum sekmeleri: Bekliyor / Onaylandı / Reddedildi (varsayılan Bekliyor)
    const tabs = page.getByRole("navigation", { name: "Öneri durumu" });
    await expect(tabs.getByRole("link", { name: /Bekliyor/ })).toHaveAttribute("aria-current", "page");
    await expect(tabs.getByRole("link", { name: /Onaylandı/ })).toBeVisible();
    await expect(tabs.getByRole("link", { name: /Reddedildi/ })).toBeVisible();

    const firstCard = page.locator("div.rounded-xl.border").filter({ hasText: "Burak Çelik" }).first();
    await expect(firstCard).toBeVisible();
    const editButton = firstCard.getByRole("button", { name: "Düzenle" });
    const rejectButton = firstCard.getByRole("button", { name: "Reddet" });
    await expect(firstCard.getByRole("button", { name: "Onayla ve Servis Emri Oluştur" })).toBeVisible();

    // Düzenle penceresi: Escape ile kapanır
    await editButton.click();
    const dialog = page.getByRole("dialog");
    await expect(page.getByRole("heading", { name: "Öneri alanlarını düzenle" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();

    // Reddet penceresi: Vazgeç ile kapanır
    await rejectButton.click();
    await expect(page.getByRole("heading", { name: "Öneriyi reddet" })).toBeVisible();
    await dialog.getByRole("button", { name: "Vazgeç" }).click();
    await expect(dialog).not.toBeVisible();

    // Onayla: durum bilgisi ve servis emrine bağlantı görünür, "Tekrar Onayla" yok
    await firstCard.getByRole("button", { name: "Onayla ve Servis Emri Oluştur" }).click();
    await expect(firstCard.getByText("Onaylandı, servis emri açıldı.")).toBeVisible();
    await expect(firstCard.getByRole("link", { name: "Servis emrini aç" })).toBeVisible();
    await expect(firstCard.getByRole("button", { name: /Tekrar Onayla/ })).toHaveCount(0);
  });

  test("Senaryo 4b (CRM): eşleşmemiş çağrı onayı anlaşılır uyarı verir, elle eşleştirince onaylanır", async ({
    page,
  }) => {
    await page.goto("/admin/crm");
    // Mock: bu çağrı elle eşleştirilene kadar müşteriyle eşleşmemiş sayılır
    const card = page.locator("div.rounded-xl.border", {
      has: page.locator('a[href="/admin/calls/22222222-2222-4222-8222-222222222222"]'),
    });
    await card.getByRole("button", { name: "Onayla ve Servis Emri Oluştur" }).click();

    const alert = card.getByRole("alert");
    await expect(alert).toContainText("henüz bir müşteri veya tekneyle eşleşmediği");
    await expect(alert).not.toContainText("409");

    // Geçersiz numara anlaşılır hata verir
    await alert.getByRole("button", { name: "Elle eşleştir" }).click();
    const dialog = page.getByRole("dialog", { name: "Çağrıyı elle eşleştir" });
    await dialog.getByLabel("Müşteri numarası").fill("abc");
    await dialog.getByRole("button", { name: "Eşleştir" }).click();
    await expect(dialog.getByRole("alert")).toContainText("geçerli bir kimlik");

    await dialog.getByLabel("Müşteri numarası").fill("123e4567-e89b-12d3-a456-426614174000");
    await dialog.getByRole("button", { name: "Eşleştir" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(card.getByText("Çağrı müşteriye bağlandı")).toBeVisible();

    await card.getByRole("button", { name: "Onayla ve Servis Emri Oluştur" }).click();
    await expect(card.getByText("Onaylandı, servis emri açıldı.")).toBeVisible();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 5: Miço AI Asistanı (Kenar Çubuğu, Giriş Alanı ve Kaynak Kartları)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 5 (Miço AI Asistanı): Sohbet kenar çubuğu, mesaj alanı ve kaynak kartları doğrulanır", async ({
    page,
  }) => {
    await page.goto("/owner/assistant");

    // 1. Sohbet geçmişi kenar çubuğu
    const sidebar = page.getByRole("navigation", { name: "Sohbet geçmişi" });
    await expect(sidebar).toBeVisible();
    await expect(page.getByText("Geçmiş Sohbetler")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Yeni sohbet başlat" }),
    ).toBeVisible();

    // 2. Mesaj gönderme alanı (ChatInput)
    const chatInput = page.locator("#assistant-chat-input");
    await expect(chatInput).toBeVisible();
    await expect(chatInput).toBeEnabled();
    await chatInput.fill("Merhaba Miço");
    await expect(chatInput).toHaveValue("Merhaba Miço");
    await chatInput.fill("");

    // 3. Kaynak kartları (Citations)
    // Kenar çubuğundaki mevcut oturumlardan birine tıkla (örn. "Teknemin son bakımı")
    const existingSession = page
      .getByRole("navigation", { name: "Sohbet geçmişi" })
      .locator("button")
      .filter({ hasText: /Teknemin son bakımı|bakım/i })
      .first();

    if (await existingSession.isVisible()) {
      await existingSession.click();

      // Kaynak kartının (CitationCard) yüklendiğini doğrula
      const citationCard = page.getByRole("region", { name: /Kaynak:/i }).first();
      await expect(citationCard).toBeVisible();
      await expect(
        citationCard.getByText("Servis Kaydı", { exact: true }),
      ).toBeVisible();
    }
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 6: Uygulama kabuğu (#166) — yan menü yok, üstte sekmeli gezinme
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 6 (Kabuk): üst bar, rol rozeti ve sekmeler çalışır, yan menü yoktur", async ({
    page,
  }) => {
    await page.goto("/admin/analytics");

    await expect(page.getByRole("complementary")).toHaveCount(0);
    const nav = page.getByRole("navigation", { name: "Ana gezinme" });
    for (const label of ["Gösterge Paneli", "Çağrılar", "CRM Önerileri", "Servis Emirleri"]) {
      await expect(nav.getByRole("link", { name: label })).toBeVisible();
    }
    await expect(nav.getByRole("link", { name: "Gösterge Paneli" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    await nav.getByRole("link", { name: "CRM Önerileri" }).click();
    await expect(page).toHaveURL(/\/admin\/crm/);

    // Rol seçici: Tekne Sahibi yalnızca Miço AI sekmesini gösterir
    await page.getByLabel("Rol seç").selectOption("owner");
    await expect(page).toHaveURL(/\/owner\/assistant/);
    await expect(nav.getByRole("link")).toHaveCount(1);
    await expect(nav.getByRole("link", { name: "Miço AI" })).toBeVisible();
  });
  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 7: Miço AI gerçek cevap (yalnızca gerçek backend; mock modunda atlanır)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 7 (Miço AI gerçek cevap): sayısal soru kaynak kartıyla cevaplanır", async ({
    page,
  }) => {
    test.skip(
      process.env.NEXT_PUBLIC_USE_MOCKS !== "false",
      "Gerçek backend gerekir: NEXT_PUBLIC_USE_MOCKS=false ile koşun.",
    );

    await page.goto("/owner/assistant");
    const chatInput = page.locator("#assistant-chat-input");
    await chatInput.fill("Kaç bakım hakkım kaldı?");
    await chatInput.press("Enter");

    // Sayısal sorular LLM'siz, kodla cevaplanır: cevap ve paket kaynak kartı gelir.
    await expect(page.getByText(/bakım hakkınız kaldı/i).first()).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole("region", { name: /Kaynak:/i }).first()).toBeVisible();
  });
});
