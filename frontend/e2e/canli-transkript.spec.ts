import { test, expect } from "@playwright/test";

// Canlı transkript pop-up'ı (#326). Sahte modda akış senaryolu konuşma üretir (gerçek STT yok).
test.describe("Canlı transkript pop-up (#326)", () => {
  test("yazıya çevirme başlayınca açılır; cümleler konuşmacıya göre canlı yazılır", async ({ page }) => {
    test.setTimeout(45000);
    const id = "mock-live-transcript";
    expect((await page.request.post(`/api/mock-analysis/${id}`)).status()).toBe(202);
    await page.goto(`/admin/calls/upload?call_id=${id}`);

    const dialog = page.getByRole("dialog", { name: "Canlı yazıya çevirme" });
    await expect(dialog).toBeVisible({ timeout: 15000 });

    const log = dialog.getByRole("log", { name: "Canlı transkript" });
    await expect(log).toContainText("Miço Usta, buyurun.", { timeout: 10000 });
    await expect(log).toContainText("Temsilci");
    await expect(log).toContainText("Müşteri");
    await expect(log).toContainText("Usta uygunluğuna bakıp sizi bilgilendireceğiz.", { timeout: 10000 });

    // Konuşmacı yerleşimi: temsilci solda, müşteri sağda.
    const rep = log.getByText("Miço Usta, buyurun.");
    const customer = log.getByText("Rüzgar. Yarın bir usta gelebilir mi?");
    const repBox = await rep.boundingBox();
    const customerBox = await customer.boundingBox();
    expect(repBox!.x).toBeLessThan(customerBox!.x);

    await expect(dialog.getByText("Tamamlandı", { exact: true })).toBeVisible({ timeout: 10000 });
    // Yazıya çevirme bitince pencere kendiliğinden kapanır (analiz adımları görünür kalır).
    await expect(dialog).toBeHidden({ timeout: 10000 });
  });

  test("kapatılan pop-up kendiliğinden açılmaz; Canlı izle ile yeniden açılır", async ({ page }) => {
    test.setTimeout(45000);
    const id = "mock-live-transcript-2";
    expect((await page.request.post(`/api/mock-analysis/${id}`)).status()).toBe(202);
    await page.goto(`/admin/calls/upload?call_id=${id}`);

    const dialog = page.getByRole("dialog", { name: "Canlı yazıya çevirme" });
    await expect(dialog).toBeVisible({ timeout: 15000 });
    await dialog.getByRole("button", { name: /Arka planda sürdür|Kapat/ }).click();
    await expect(dialog).toBeHidden();

    const watch = page.getByRole("button", { name: "Canlı izle" });
    if (await watch.isVisible().catch(() => false)) {
      await watch.click();
      await expect(dialog).toBeVisible();
    }
  });
});
