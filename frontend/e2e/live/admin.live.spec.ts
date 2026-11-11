import { test, expect } from "@playwright/test";
import { liveOnly } from "./helpers";

test.describe("Admin paneli (canlı backend)", () => {
  liveOnly();

  test("Analitik: sayfa açılır, hata uyarısı yok", async ({ page }) => {
    await page.goto("/admin/analytics");
    await expect(page.getByRole("heading", { name: "Çağrı Analitiği" })).toBeVisible();
    await expect(page.locator("main")).toContainText(/\d+/);
    await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
  });

  test("Çağrılar: satırlar listelenir, olmayan arama boş sonuç verir", async ({ page }) => {
    await page.goto("/admin/calls");
    const rows = page.getByRole("row");
    await expect(rows.nth(3)).toBeVisible({ timeout: 15000 });
    expect(await rows.count()).toBeGreaterThan(5);
    await page.getByRole("searchbox").first().fill("zzzzzzzz-yok");
    await expect(rows.nth(3)).toBeHidden({ timeout: 10000 });
  });

  test("Çağrı detayı: transkript ve yeniden analiz düğmesi", async ({ page }) => {
    await page.goto("/admin/calls");
    await page.getByRole("link", { name: "Detay", exact: true }).first().click();
    await expect(page).toHaveURL(/\/admin\/calls\/[0-9a-f-]{36}/);
    const transcript = page.getByRole("region", { name: "Konuşma metni", exact: true });
    await expect(transcript.getByTestId("transcript-bubble").first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: "Çağrıyı yeniden analiz et", exact: true })).toBeVisible();
  });

  test("CRM: durum sekmelerinde kayıt sayıları var", async ({ page }) => {
    await page.goto("/admin/crm");
    const tabs = page.getByRole("navigation", { name: "Öneri durumu" });
    const labels = await tabs.getByRole("link").allInnerTexts();
    const total = labels.map((t) => Number(/\((\d+)\)/.exec(t)?.[1] ?? 0)).reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThan(0);
  });

  test("Servis emirleri: durum sekmesi değişir", async ({ page }) => {
    await page.goto("/admin/service-orders");
    const tabs = page.getByRole("navigation", { name: "Servis emri durumu" });
    await expect(tabs.getByRole("link", { name: "Tümü" })).toHaveAttribute("aria-current", "page");
    await tabs.getByRole("link", { name: "Tamamlandı" }).click();
    await expect(tabs.getByRole("link", { name: "Tamamlandı" })).toHaveAttribute("aria-current", "page");
  });

  test("Çağrı yükle: sayfa açılır, takılı analiz ekranı yok", async ({ page }) => {
    await page.goto("/admin/calls/upload");
    await expect(page.getByRole("heading", { name: "Çağrı Yükle" })).toBeVisible();
    await expect(page.getByText("Analiz sürüyor")).toHaveCount(0);
  });

  test("Tüm panel sayfaları hatasız açılır", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const path of ["/admin/analytics", "/admin/calls", "/admin/crm", "/admin/service-orders", "/owner/assistant"]) {
      const res = await page.goto(path);
      expect(res?.status(), path).toBeLessThan(400);
    }
    expect(errors).toEqual([]);
  });
});
