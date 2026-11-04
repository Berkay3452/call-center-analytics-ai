import { test, expect } from "@playwright/test";

test.describe("Canlı analiz takibi (#217)", () => {
  test("arka planda devam eder; yenilemede şerit, listede rozet ve sayfa değişince bildirim görünür", async ({ page }) => {
    test.setTimeout(60000);
    const id = "11111111-1111-4111-8111-111111111111";
    let statusRequests = 0;
    page.on("request", (request) => {
      if (request.url().endsWith(`/api/mock-analysis/${id}`) && request.method() === "GET") statusRequests++;
    });
    await page.goto(`/admin/calls/${id}`);
    await page.getByRole("button", { name: "Çağrıyı yeniden analiz et", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Evet, Yeniden Analiz Et" }).click();
    const banner = page.getByRole("status", { name: "Analiz durumu" });
    await expect(banner).toContainText("Analiz sürüyor");
    await expect(banner.locator(".animate-spin")).toBeVisible();
    await expect(page.getByRole("button", { name: "Analiz sürüyor", exact: true })).toBeDisabled();
    await dialog.getByRole("button", { name: "Arka planda sürdür" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(banner).toBeVisible();

    await page.reload();
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("geçen süre");
    await expect(page.getByRole("button", { name: "Analiz sürüyor", exact: true })).toBeDisabled();
    await expect(banner).toContainText(/Yazıya çevriliyor|Analiz ediliyor/, { timeout: 12000 });

    await page.getByRole("link", { name: "← Çağrı listesine dön" }).click();
    const row = page.getByRole("row").filter({ has: page.locator(`a[href="/admin/calls/${id}"]`) });
    await expect(row.getByText("Analiz sürüyor", { exact: true })).toBeVisible();
    await expect(row.locator(".animate-spin")).toBeVisible();
    await page.getByRole("navigation", { name: "Ana gezinme" }).getByRole("link", { name: "Gösterge Paneli" }).click();
    const result = page.getByRole("link", { name: "Analiz tamamlandı, sonucu gör" }).and(page.locator(`a[href="/admin/calls/${id}"]`));
    await expect(result).toBeVisible({ timeout: 30000 });
    const finalCount = statusRequests;
    await page.waitForTimeout(5000);
    expect(statusRequests).toBe(finalCount);
    await page.getByRole("navigation", { name: "Ana gezinme" }).getByRole("link", { name: "Çağrılar", exact: true }).click();
    await expect(row.getByText("Analiz sürüyor", { exact: true })).toHaveCount(0);
    await result.click();
    await expect(page.getByText(/Yeni analiz tamamlandı \(sürüm/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Çağrıyı yeniden analiz et", exact: true })).toBeEnabled();
  });

  for (const [id, message] of [
    ["mock-slow-partial", "Analiz kısmen tamamlandı: Çağrı sınıflandırma bölümü üretilemedi."],
    ["mock-slow-failed", "Analiz tamamlanamadı: Ses kaydı okunamadı."],
  ]) {
    test(`${id}: tamamlanma bildirimi sunucunun nedenini gösterir`, async ({ page }) => {
      test.setTimeout(45000);
      const response = await page.request.post(`/api/mock-analysis/${id}`);
      expect(response.status()).toBe(202);
      await page.goto(`/admin/calls/${id}`);
      await expect(page.getByRole("status", { name: "Analiz durumu" })).toBeVisible();
      await page.getByRole("navigation", { name: "Ana gezinme" }).getByRole("link", { name: "Gösterge Paneli" }).click();
      await expect(page.getByRole("link", { name: message, exact: true })).toBeVisible({ timeout: 30000 });
    });
  }
});
