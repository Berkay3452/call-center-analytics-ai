import { test, expect } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";

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
      page.getByRole("region", { name: "Konuşma metni", exact: true }).getByText("Miço Usta", { exact: true }).first(),
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
  // Senaryo 3b: Kısmi analiz tutarlılığı (#170)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 3b (Kısmi analiz): rozet 'Kısmi', yüzde gösterilmez, eksik bölüm adlandırılır; tam analizde yüzde görünür", async ({
    page,
  }) => {
    // Mock'ta f32beed7… çağrısı kısmi: sınıflandırma ajanı çökmüş
    await page.goto("/admin/calls/f32beed7-2e2b-595b-b022-9d68c3b8161d");
    await expect(page.getByText("Analiz: Kısmi")).toBeVisible();
    await expect(page.getByText("Analiz kısmen tamamlandı")).toBeVisible();
    await expect(page.getByText(/Çağrı sınıflandırma üretilemedi/)).toBeVisible();
    // Üretilemeyen ajanın skoru yüzde yerine "Hesaplanamadı" gösterir
    await expect(page.getByText("Çağrı türü güveni")).toBeVisible();
    await expect(page.getByText("Hesaplanamadı")).toBeVisible();

    // Tam analiz: rozet "Tamam" ve güven yüzdesi
    await page.goto("/admin/calls/11111111-1111-4111-8111-111111111111");
    await expect(page.getByText("Analiz: Tamam")).toBeVisible();
    await expect(page.getByText("Çağrı türü güveni")).toBeVisible();
    await expect(page.getByText("Satış sonucu güveni")).toBeVisible();
    await expect(page.getByText(/^%\d+$/)).toHaveCount(2);
    await expect(page.getByRole("button", { name: "Çağrıyı yeniden analiz et" })).toHaveClass(/bg-amber-600/);
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

  test("Senaryo 4b (CRM): eşleşmemiş çağrıda açık uyarı ve erken engel vardır, müşteri ve tekne seçilince onaylanır (#209)", async ({
    page,
  }) => {
    await page.goto("/admin/crm");
    // Mock: bu çağrı elle eşleştirilene kadar müşteriyle eşleşmemiş sayılır
    const card = page.locator("div.rounded-xl.border", {
      has: page.locator('a[href="/admin/calls/22222222-2222-4222-8222-222222222222"]'),
    });

    // 1. Açık Türkçe uyarı metni kontrolü
    const alert = card.getByRole("alert");
    await expect(alert).toContainText("Bu çağrı otomatik olarak bir müşteri ve tekneye bağlanamadı. Servis emri açmak için önce müşteri ve tekneyi seçin.");

    // 2. Onay butonunun disabled olduğunu ve ipucu metnini doğrula (Erken engel)
    const approveButton = card.getByRole("button", { name: "Onayla ve Servis Emri Oluştur" });
    await expect(approveButton).toBeDisabled();
    await expect(approveButton).toHaveAttribute("title", "Servis emri oluşturabilmek için önce müşteri ve tekne eşleştirmesi yapmalısınız.");

    // 3. "Müşteri ve tekne seç" butonuna tıkla
    await card.getByRole("button", { name: "Müşteri ve tekne seç" }).click();

    // 4. Modal kontrolü: başlık ve Önerilen bölümü
    const dialog = page.getByRole("dialog", { name: "Müşteri ve tekne seç" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Önerilen:")).toBeVisible();
    await expect(dialog.getByText("Fatma Kaya", { exact: true }).last()).toBeVisible();

    // 5. Müşteri arama ve seçim
    const searchInput = dialog.getByLabel("Müşteri ara");
    await searchInput.fill("Fatma");
    await expect(dialog.getByText("Fatma Kaya", { exact: true }).last()).toBeVisible();

    // Fatma Kaya radio seçimi
    const customerRadio = dialog.locator('input[name="customer-selection"]').first();
    await customerRadio.check();
    await expect(dialog.getByRole("button", { name: "Eşleştir", exact: true })).toBeDisabled();

    // Tekne seçeneklerinde Albatros seçimi
    await expect(dialog.getByText("Albatros", { exact: true }).last()).toBeVisible();
    const boatRadio = dialog.locator('input[name="boat-selection"][value="22222222-3333-4222-8222-222222222222"]');
    await boatRadio.check();

    // 6. Eşleştir butonuna bas
    await dialog.getByRole("button", { name: "Eşleştir" }).click();
    await expect(dialog).not.toBeVisible();

    // 7. Uyarının kalktığını, onay butonunun aktifleştiğini doğrula
    await expect(card.getByText("Bu çağrı otomatik olarak bir müşteri ve tekneye bağlanamadı.")).not.toBeVisible();
    await expect(card.getByText("Çağrı müşteri ve tekneye bağlandı")).toBeVisible();
    await expect(approveButton).toBeEnabled();

    // 8. Onayla ve servis emri açıldığını doğrula
    await approveButton.click();
    await expect(card.getByText("Onaylandı, servis emri açıldı.")).toBeVisible();
    await expect(card.getByRole("link", { name: "Servis emrini aç" })).toBeVisible();
  });
  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 4c: Servis Emirleri kart listesi (#173)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 4c (Servis Emirleri): kartlar, durum sekmeleri, marina filtresi, detay bağlantıları ve durum ilerletme", async ({
    page,
  }) => {
    await page.goto("/admin/service-orders");
    const tabs = page.getByRole("navigation", { name: "Servis emri durumu" });
    await expect(tabs.getByRole("link", { name: "Tümü" })).toHaveAttribute("aria-current", "page");

    const cards = page.locator("ul > li").filter({ has: page.getByRole("button", { name: "Detay" }) });
    const first = cards.first();
    await expect(first.getByRole("heading")).toContainText("—");
    await expect(first.getByRole("link", { name: "Kaynak çağrı" })).toHaveCount(0);

    // Durum ilerletme: rozet değişir
    const advance = first.getByRole("button", { name: /→/ });
    await expect(advance).toBeVisible();
    await advance.click();
    await expect(first.getByRole("button", { name: /→|tamamlandı/ }).or(first.getByText("Servis emri tamamlandı"))).toBeVisible();

    // Detay penceresi açılır ve Escape ile kapanır
    await first.getByRole("button", { name: "Detay" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("dialog").getByRole("link", { name: /Çağrıyı Aç/i })).toHaveAttribute("href", /\/admin\/calls\//);
    await expect(page.getByRole("dialog").getByRole("link", { name: /CRM Önerisine Git/i })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();

    // Marina filtresi URL'e yazılır
    await page.locator("#so-filter-marina").selectOption({ index: 1 });
    await expect(page).toHaveURL(/marina=/);
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

      // Kaynaklar varsayılan açıktır; ayrıca açma adımı gerekmez.
      await expect(page.locator("details").first()).toHaveAttribute("open", "");
      const citationCard = page.getByRole("region", { name: /Kaynak:/i }).first();
      await expect(citationCard).toBeVisible();
      await expect(
        citationCard.getByText("Servis Kaydı", { exact: true }),
      ).toBeVisible();
    }
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 5b: Miço AI — hazır sorular ve sohbet silme (#175, #176)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 5b (Miço AI): hazır soru kartları ilk ekranda, tek sohbet ve tümü onayla silinir", async ({
    page,
  }) => {
    await page.goto("/owner/assistant");
    const sidebar = page.getByRole("navigation", { name: "Sohbet geçmişi" });

    // İlk ekranda hazır soru kartları görünür, "Temizle" düğmesi yoktur
    await expect(page.getByRole("group", { name: "Hazır soru önerileri" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Temizle", exact: true })).toHaveCount(0);

    // Tek sohbet: onay sorusu → Vazgeç listeyi değiştirmez
    const items = sidebar.locator("ul > li");
    await expect(items.first()).toBeVisible();
    const before = await items.count();
    expect(before).toBeGreaterThan(1);
    await sidebar.getByRole("button", { name: /^Sohbeti sil:/ }).first().click();
    await expect(sidebar.getByText("Bu sohbeti sil?")).toBeVisible();
    await sidebar.getByRole("button", { name: "Vazgeç" }).click();
    await expect(items).toHaveCount(before);

    // Onaylayınca listeden kalkar
    await sidebar.getByRole("button", { name: /^Sohbeti sil:/ }).first().click();
    await sidebar.getByRole("button", { name: "Sil", exact: true }).click();
    await expect(items).toHaveCount(before - 1);

    // Tümünü temizle: onay sonrası liste boşalır
    await sidebar.getByRole("button", { name: "Tümünü temizle" }).click();
    await expect(sidebar.getByText("Tüm sohbetler silinsin mi?")).toBeVisible();
    await sidebar.getByRole("button", { name: "Hepsini sil" }).click();
    await expect(sidebar.getByText("Henüz kayıtlı sohbet yok.")).toBeVisible();
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
  // Senaryo 8: Çağrı Yükle (#171) — metin yükleme baştan sona, otomatik detaya geçiş
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 8 (Çağrı Yükle): metin yüklenir, adımlar görünür, tamamlanınca detaya geçilir", async ({
    page,
  }) => {
    test.skip(
      process.env.NEXT_PUBLIC_USE_MOCKS === "false",
      "Mock akışı gerektirir: NEXT_PUBLIC_USE_MOCKS=true ile koşun.",
    );

    await page.goto("/admin/calls/upload");
    await page.getByRole("tab", { name: "Metin / transkript" }).click();
    await page.getByRole("button", { name: "Örnek metin doldur" }).click();
    await page.getByRole("button", { name: "Analizi başlat" }).click();

    await expect(page.getByRole("list", { name: "Analiz adımları" })).toBeVisible();
    await expect(page).toHaveURL(/\/admin\/calls\/mock-text-/, { timeout: 30000 });
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 7: Miço AI sayısal cevap (mock ve gerçek backend sözleşmesi)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 7 (Miço AI sayısal cevap): sayısal soru kaynak kartıyla cevaplanır", async ({
    page,
  }) => {
    await page.goto("/owner/assistant");
    const chatInput = page.getByRole("textbox", { name: "Soru giriş kutusu" });
    await expect(chatInput).toBeEnabled();
    await chatInput.fill("Kaç bakım hakkım kaldı?");
    await chatInput.press("Enter");

    // Sayısal sorular LLM'siz, kodla cevaplanır: cevap ve paket kaynak kartı gelir.
    await expect(page.getByText(/bakım hakkınız kaldı/i).first()).toBeVisible({ timeout: 20000 });
    // Kaynaklar açılır liste: kapalıysa aç (varsayılan durumdan bağımsız)
    const sourcesToggle = page.getByText(/^Kaynaklar \(\d+\)$/).first();
    await expect(sourcesToggle).toBeVisible();
    if (!(await page.locator("details").first().evaluate((d) => (d as HTMLDetailsElement).open))) {
      await sourcesToggle.click();
    }
    await expect(page.getByRole("region", { name: /Kaynak:/i }).first()).toBeVisible();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 9: Miço AI — cevap gelmeden boş balon / imleç yok (#212)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 9 (Miço AI bekleme): ilk kelimeye kadar yalnızca durum göstergesi görünür, boş balon olmaz", async ({
    page,
  }) => {
    test.skip(
      process.env.NEXT_PUBLIC_USE_MOCKS === "false",
      "Zamanlama mock akışına bağlı; gerçek backend ile Senaryo 7 koşar.",
    );
    await page.goto("/owner/assistant");
    await page.waitForLoadState("networkidle"); // hidrasyon bitmeden yazılan metin kaybolmasın
    const messages = page.getByTestId("chat-message");
    await expect(messages).toHaveCount(1); // yalnızca karşılama

    const chatInput = page.locator("#assistant-chat-input");
    await chatInput.fill("Son bakım ne zaman yapıldı?");
    await chatInput.press("Enter");

    // Bekleme: durum göstergesi var; yalnızca kullanıcı balonu eklendi, boş asistan balonu ve imleç yok
    await expect(page.getByRole("status").filter({ hasText: /aranıyor/ })).toBeVisible();
    await expect(messages).toHaveCount(2);
    await expect(messages.last()).toHaveAttribute("data-role", "user");
    await expect(page.locator('[role="log"] .animate-pulse')).toHaveCount(0);

    // Cevap gelince asistan balonu metinle oluşur
    await expect(messages).toHaveCount(3);
    await expect(messages.last()).toHaveAttribute("data-role", "assistant");
    await expect(messages.last()).not.toHaveText("");
    await expect(page.getByRole("status")).toHaveCount(0);
    await expect(page.locator('[role="log"] .animate-pulse')).toHaveCount(0);
  });

  test("Senaryo 9b (Miço AI hata): hatada boş balon kalmaz, hata mesajı ve 'Yeniden dene' görünür", async ({
    page,
  }) => {
    test.skip(
      process.env.NEXT_PUBLIC_USE_MOCKS === "false",
      "Hata tetikleme mock akışına bağlı.",
    );
    await page.goto("/owner/assistant");
    await page.waitForLoadState("networkidle");
    const chatInput = page.locator("#assistant-chat-input");
    await chatInput.fill("llm-error");
    await chatInput.press("Enter");

    const alert = page.getByRole("alert").filter({ hasText: /yapılandırılmamış/ });
    await expect(alert).toBeVisible();
    await expect(alert.getByRole("button", { name: "Yeniden dene" })).toBeVisible();
    await expect(page.getByRole("status")).toHaveCount(0);
    await expect(page.locator('[role="log"] .animate-pulse')).toHaveCount(0);
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Senaryo 10: CRM "Konuşmadan alıntılar" alan adları Türkçe (#208)
  // ──────────────────────────────────────────────────────────────────────────
  test("Senaryo 10 (CRM alıntılar): alıntı alan adları Türkçe, ham değişken adı görünmez", async ({ page }) => {
    await page.goto("/admin/crm");
    const card = page.locator("div.rounded-xl.border").filter({ hasText: "Burak Çelik" }).first();
    const details = card.locator("details", { hasText: "Konuşmadan alıntılar" });
    await expect(details).toBeVisible();
    await details.locator("summary").click();
    await expect(details.getByText("Talep kategorisi:")).toBeVisible();
    await expect(details.getByText("Hizmet biçimi:")).toBeVisible();
    await expect(details.getByText("Sonraki adım:")).toBeVisible();
    // Etiket kısmında alt çizgili kod adı kalmamalı (ör. request_category:)
    await expect(details.locator("li > span")).not.toContainText([/_/]);
    await expect(card).not.toContainText(/request_category|service_mode|potential_job|next_action/);
  });
});


test("Issue #204: müşteri sağda, Miço Usta solda; balonlarda süre yok", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_USE_MOCKS === "false", "Sabit mock transkripti gerektirir.");
  await page.goto("/admin/calls/11111111-1111-4111-8111-111111111111");
  const transcript = page.getByRole("region", { name: "Konuşma metni", exact: true });
  const bubbles = transcript.getByTestId("transcript-bubble");
  await expect(bubbles).toHaveCount(5);
  for (const [speaker, label, alignment] of [
    ["musteri", "Müşteri", "flex-end"],
    ["firma", "Miço Usta", "flex-start"],
  ]) {
    const bubble = transcript.locator(`[data-testid="transcript-bubble"][data-speaker="${speaker}"]`).first();
    await expect(bubble.getByText(label, { exact: true })).toBeVisible();
    await expect(bubble.locator("..")).toHaveCSS("justify-content", alignment);
  }
  await expect(bubbles.first()).toContainText("Miço Usta, buyurun.");
  await expect(transcript).not.toContainText(/\b\d+:\d{2}\b|\bsüre\b/i);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const bubble of await bubbles.all()) {
      const bounds = await bubble.boundingBox();
      const row = await bubble.locator("..").boundingBox();
      expect(bounds!.width).toBeLessThanOrEqual(row!.width * 0.75 + 1);
    }
  }
});


test("Issue #203: 10 kayıt, kalıcı filtreler, duyarlı grid ve belirgin Detay butonu", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_USE_MOCKS === "false", "Sabit mock çağrı listesi gerektirir.");
  await page.goto("/admin/calls");
  const rows = page.locator("table tbody tr");
  const filters = page.getByRole("search", { name: "Çağrı filtreleri" });
  const pagination = page.getByRole("navigation", { name: "Sayfalama", exact: true });
  await expect(rows).toHaveCount(10);
  await expect(pagination).toContainText(/Toplam \d+ kayıttan 1-10/);
  await expect(pagination.getByRole("button", { name: "Önceki sayfaya git" })).toBeDisabled();
  const firstCustomer = await rows.first().innerText();
  await pagination.getByRole("button", { name: "Sayfa 2", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(rows.first()).not.toHaveText(firstCustomer);
  await page.reload();
  await expect(pagination.getByRole("button", { name: "Sayfa 2", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(rows).toHaveCount(10);
  await filters.getByLabel("Marina filtresi").selectOption("Tuzla Marina");
  await expect(page).toHaveURL(/page=1/);
  await expect(page).toHaveURL(/marina=Tuzla/);
  await page.reload();
  await expect(filters.getByLabel("Marina filtresi")).toHaveValue("Tuzla Marina");
  await filters.getByRole("button", { name: "Temizle", exact: true }).click();
  await expect(filters.getByLabel("Marina filtresi")).toHaveValue("all");
  await expect(rows).toHaveCount(10);
  const detail = rows.first().getByRole("link", { name: "Detay", exact: true });
  await expect(detail).toHaveCSS("cursor", "pointer");
  await expect(detail).toHaveCSS("border-top-width", "1px");
  await detail.focus();
  await expect(detail).toBeFocused();
  await expect(detail).toHaveClass(/focus-visible:ring-2/);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const search = await filters.getByLabel("Arama kutusu").boundingBox();
    const marina = await filters.getByLabel("Marina filtresi").boundingBox();
    if (width === 1280) expect(Math.abs(search!.y - marina!.y)).toBeLessThan(4);
    else expect(marina!.y).toBeGreaterThan(search!.y + search!.height);
    const bounds = await filters.boundingBox();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    await expect(filters.getByLabel("Talep kategorisi")).toBeVisible();
  }
  await detail.click();
  await expect(page).toHaveURL(/\/admin\/calls\/[a-zA-Z0-9-]+$/);
});


test("Issue #207: CRM grid, tarih sınırları, 10 kayıt ve Çağrıyı gör butonu", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_USE_MOCKS === "false", "Sabit mock CRM listesi gerektirir.");
  await page.goto("/admin/crm");
  const filters = page.getByRole("search", { name: "CRM filtreleri" });
  const links = page.getByRole("link", { name: "Çağrıyı gör", exact: true });
  const pagination = page.getByRole("navigation", { name: "Sayfalama", exact: true });
  await expect(links).toHaveCount(10);
  await expect(pagination).toContainText(/Toplam \d+ kayıttan 1-10/);
  await pagination.getByRole("button", { name: "Sonraki sayfaya git" }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.reload();
  await expect(pagination.getByRole("button", { name: "Sayfa 2", exact: true })).toHaveAttribute("aria-current", "page");
  const from = filters.getByLabel("Başlangıç tarihi", { exact: true });
  const to = filters.getByLabel("Bitiş tarihi", { exact: true });
  await expect(filters.locator('label[for="filter-date-from"]')).toBeVisible();
  await expect(filters.locator('label[for="filter-date-to"]')).toBeVisible();
  await expect(from).toHaveAttribute("placeholder", "gg.aa.yyyy");
  await expect(to).toHaveAttribute("placeholder", "gg.aa.yyyy");
  await from.fill("2026-10-01");
  await expect(page).toHaveURL(/date_from=2026-10-01/);
  await expect(page).toHaveURL(/page=1/);
  await expect(to).toHaveAttribute("min", "2026-10-01");
  await to.fill("2026-10-31");
  await expect(page).toHaveURL(/date_to=2026-10-31/);
  await expect(from).toHaveAttribute("max", "2026-10-31");
  await to.fill("2026-09-30");
  await expect(filters.getByRole("alert")).toContainText("Bitiş tarihi başlangıç tarihinden önce olamaz");
  await expect(page).toHaveURL(/date_to=2026-10-31/);
  await page.reload();
  await expect(from).toHaveValue("2026-10-01");
  await expect(to).toHaveValue("2026-10-31");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const bounds = await filters.boundingBox();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    const startBounds = await from.boundingBox();
    const endBounds = await to.boundingBox();
    if (width === 1280) expect(Math.abs(startBounds!.y - endBounds!.y)).toBeLessThan(4);
    else expect(endBounds!.y).toBeGreaterThan(startBounds!.y + startBounds!.height);
  }
  await filters.getByRole("button", { name: "Temizle", exact: true }).click();
  await expect(from).toHaveValue("");
  await expect(to).toHaveValue("");
  const view = links.first();
  await expect(view).toHaveCSS("cursor", "pointer");
  await expect(view).toHaveCSS("border-top-width", "1px");
  await view.focus();
  await expect(view).toBeFocused();
  await expect(view).toHaveClass(/focus-visible:ring-2/);
  await view.click();
  await expect(page).toHaveURL(/\/admin\/calls\/[a-zA-Z0-9-]+$/);
});


test("Issue #210: gereksiz bağlantılar yok, 10 kayıt ve durum düğmelerinde etkileşim stilleri", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_USE_MOCKS === "false", "Sabit mock servis geçmişi gerektirir.");
  await page.goto("/admin/service-orders");
  await expect(page.getByRole("link", { name: "CRM önerilerine git", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Kaynak çağrı", exact: true })).toHaveCount(0);
  const cards = page.locator("ul > li").filter({ has: page.getByRole("button", { name: "Detay", exact: true }) });
  const pagination = page.getByRole("navigation", { name: "Sayfalama", exact: true });
  await expect(cards).toHaveCount(10);
  await expect(pagination).toContainText(/Toplam \d+ kayıttan 1-10/);
  await expect(pagination.getByRole("button", { name: "Önceki sayfaya git" })).toBeDisabled();
  const advance = cards.first().getByRole("button", { name: /→/ });
  await expect(advance).toHaveCSS("cursor", "pointer");
  const background = await advance.evaluate((element) => getComputedStyle(element).backgroundColor);
  await advance.hover();
  await expect(advance).not.toHaveCSS("background-color", background);
  await advance.focus();
  await expect(advance).toBeFocused();
  await expect(advance).toHaveClass(/focus-visible:ring-2/);
  await expect(cards.first().getByTestId("service-order-status")).toHaveCSS("cursor", "default");
  await pagination.getByRole("button", { name: "Sonraki sayfaya git" }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.reload();
  await expect(pagination.getByRole("button", { name: "Sayfa 2", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(pagination.getByRole("button", { name: "Sonraki sayfaya git" })).toBeDisabled();
  await pagination.getByRole("button", { name: "Önceki sayfaya git" }).click();
  await expect(cards).toHaveCount(10);
  await cards.first().getByRole("button", { name: "Detay", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("link", { name: /Çağrıyı Aç/i })).toBeVisible();
  await expect(dialog.getByRole("link", { name: /CRM Önerisine Git/i })).toBeVisible();
});


test("Issue #202: erişilebilir halka grafikler, altı dilim sınırı ve canlı filtreler", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_USE_MOCKS === "false", "Deterministik mock analitik verisi gerektirir.");
  await page.clock.setFixedTime(new Date("2026-11-05T12:00:00+03:00"));
  await page.goto("/admin/analytics");
  const date = page.getByLabel("Tarih aralığı", { exact: true });
  await expect(date).toBeEnabled();
  await date.selectOption("oct2026");
  const charts = page.getByTestId("distribution-chart");
  await expect(charts).toHaveCount(4);
  for (const title of ["Talep Kategorisi", "Aciliyet Dağılımı", "En Yoğun Marinalar", "Satış Kaçırma Sebepleri"]) {
    const chart = charts.filter({ has: page.getByRole("heading", { name: title, exact: true }) });
    await expect(chart.getByRole("img")).toHaveAttribute("aria-label", new RegExp(title));
    const slices = chart.getByTestId("donut-slice");
    expect(await slices.count()).toBeGreaterThan(0);
    expect(await slices.count()).toBeLessThanOrEqual(6);
    await expect(chart.getByRole("list")).toContainText(/\d+.*%\d+,\d/);
    const colors = await slices.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("stroke")));
    expect(new Set(colors).size).toBe(colors.length);
  }
  const result = await new AxeBuilder({ page }).include('[data-testid="analytics-charts"]').withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(result.violations).toEqual([]);
  for (const width of [1280, 820, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const first = await charts.nth(0).boundingBox();
    const second = await charts.nth(1).boundingBox();
    if (width >= 768) expect(Math.abs(first!.y - second!.y)).toBeLessThan(4);
    else expect(second!.y).toBeGreaterThan(first!.y + first!.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  const marinaChart = charts.filter({ has: page.getByRole("heading", { name: "En Yoğun Marinalar", exact: true }) });
  const before = await marinaChart.getByRole("img").getAttribute("aria-label");
  await page.getByLabel("Marina filtresi", { exact: true }).selectOption("Tuzla Marina");
  await expect(marinaChart.getByTestId("donut-slice")).toHaveCount(1);
  await expect(marinaChart.getByRole("img")).not.toHaveAttribute("aria-label", before!);
  await expect(marinaChart.getByRole("list")).toContainText("%100,0");
  await date.selectOption("7");
  await expect(page.getByRole("heading", { name: "Henüz çağrı verisi bulunmuyor" })).toBeVisible();
  await expect(charts).toHaveCount(0);
  await date.selectOption("oct2026");
  await expect(charts).toHaveCount(4);
});


test("Issue #205: dikey ses, klavye, önceki seviye ve oynatıcı kontrolleri", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_USE_MOCKS === "false", "Mock çağrı detayı gerektirir.");
  // Gerçek HTMLAudioElement davranışını ağdaki bir ses dosyasına bağımlı olmadan sına.
  const wav = Buffer.alloc(44 + 8000 * 30 * 2);
  wav.write("RIFF", 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28);
  wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34);
  wav.write("data", 36); wav.writeUInt32LE(wav.length - 44, 40);
  await page.route("**/api/backend/calls/*/audio", (route) => {
    const range = /^bytes=(\d+)-(\d*)$/.exec(route.request().headers()["range"] ?? "");
    const start = range ? Number(range[1]) : 0;
    const end = range?.[2] ? Math.min(Number(range[2]), wav.length - 1) : wav.length - 1;
    return route.fulfill({ status: range ? 206 : 200, contentType: "audio/wav",
      headers: { "Accept-Ranges": "bytes", ...(range ? { "Content-Range": `bytes ${start}-${end}/${wav.length}` } : {}) },
      body: wav.subarray(start, end + 1) });
  });
  await page.addInitScript(() => {
    if (!localStorage.getItem("mico-audio-volume")) localStorage.setItem("mico-audio-volume", JSON.stringify({ volume: 70, previous: 70 }));
  });
  await page.goto("/admin/calls/11111111-1111-4111-8111-111111111111");
  const player = page.getByRole("region", { name: "Ses Kaydı Oynatıcı", exact: true });
  const audio = player.locator("audio");
  const volume = player.getByRole("slider", { name: "Ses seviyesi", exact: true });
  await expect(audio).toHaveJSProperty("volume", 0.7);
  await player.getByRole("button", { name: "Sesi Kapat", exact: true }).hover();
  await expect(volume).toBeVisible();
  await expect(volume).toHaveValue("70");
  await expect(volume).toHaveAttribute("aria-valuemin", "0");
  await expect(volume).toHaveAttribute("aria-valuemax", "100");
  await expect(volume).toHaveAttribute("aria-orientation", "vertical");
  const bounds = await volume.boundingBox();
  expect(bounds!.height).toBeGreaterThan(bounds!.width);
  await volume.focus();
  await volume.press("Home");
  await expect(audio).toHaveJSProperty("muted", true);
  await expect(player.locator('[data-volume-level="muted"]')).toBeVisible();
  await player.getByRole("button", { name: "Sesi Aç", exact: true }).click();
  await expect(volume).toHaveValue("70");
  await expect(audio).toHaveJSProperty("muted", false);
  await volume.press("End");
  await expect(player.locator('[data-volume-level="high"]')).toBeVisible();
  await volume.press("Home");
  for (let i = 0; i < 6; i++) await volume.press("ArrowUp");
  await expect(volume).toHaveAttribute("aria-valuenow", "30");
  await expect(audio).toHaveJSProperty("volume", 0.3);
  await expect(player.locator('[data-volume-level="low"]')).toBeVisible();
  const result = await new AxeBuilder({ page }).include('[aria-label="Ses Kaydı Oynatıcı"]').withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(result.violations).toEqual([]);
  await volume.press("Escape");
  await expect(volume).toHaveCount(0);
  await expect(player.getByRole("button", { name: "Sesi Kapat", exact: true })).toBeFocused();
  await page.reload();
  await expect(audio).toHaveJSProperty("volume", 0.3);
  await player.getByRole("button", { name: "Sesi Kapat", exact: true }).click();
  await expect(audio).toHaveJSProperty("muted", true);
  await page.reload();
  await expect(audio).toHaveJSProperty("muted", true);
  await player.getByRole("button", { name: "Sesi Aç", exact: true }).click();
  await expect(audio).toHaveJSProperty("volume", 0.3);
  await player.getByRole("button", { name: "Oynatma hızı 1x", exact: true }).click();
  await expect(audio).toHaveJSProperty("playbackRate", 1.25);
  await expect(audio).toHaveJSProperty("duration", 30);
  await player.getByRole("slider", { name: "Ses ilerleme çubuğu", exact: true }).press("ArrowRight");
  await player.getByRole("button", { name: "5 saniye ileri", exact: true }).click();
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeGreaterThan(5);
  await player.getByRole("button", { name: "5 saniye geri", exact: true }).click();
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeLessThan(1);
  await player.getByRole("button", { name: "Oynat", exact: true }).click();
  await expect(player.getByRole("button", { name: "Duraklat", exact: true })).toBeVisible();
  await player.getByRole("button", { name: "Duraklat", exact: true }).click();
  await expect(audio).toHaveJSProperty("paused", true);
});
