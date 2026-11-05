import { test, expect, type Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";

async function checkAccessibility(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(result.violations).toEqual([]);
}

async function checkComposer(page: Page) {
  const composer = page.getByRole("region", { name: "Mesaj yazma alanı" });
  const prompts = composer.getByRole("group", { name: "Hazır soru önerileri" });
  const input = composer.getByRole("textbox", { name: "Soru giriş kutusu" });
  await expect(prompts).toBeVisible();
  await expect(input).toBeEnabled();
  const promptBox = await prompts.boundingBox();
  const inputBox = await input.boundingBox();
  expect(promptBox!.y + promptBox!.height).toBeLessThanOrEqual(inputBox!.y);
  await expect(page.getByRole("log").getByRole("group", { name: "Hazır soru önerileri" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test.describe("Miço AI yerleşimi (#211)", () => {
  test("sorular girdinin üstündedir, kaynaklar açık ve tarih tektir, yeni sohbet başlığın yanındadır", async ({ page }) => {
    await page.goto("/owner/assistant");
    await checkComposer(page);
    const header = page.locator("main header");
    const heading = header.getByRole("heading", { name: "Miço AI", exact: true });
    const newChat = header.getByRole("button", { name: "Yeni sohbet başlat" });
    await expect(newChat).toHaveCount(1);
    const headingBox = await heading.boundingBox();
    const buttonBox = await newChat.boundingBox();
    expect(buttonBox!.x).toBeGreaterThanOrEqual(headingBox!.x + headingBox!.width);
    expect(Math.abs(buttonBox!.y - headingBox!.y)).toBeLessThan(20);

    const sidebar = page.getByRole("navigation", { name: "Sohbet geçmişi" });
    await expect(sidebar.getByRole("button", { name: "Yeni sohbet başlat" })).toHaveCount(0);
    await sidebar.getByRole("button", { name: "Teknemin son bakımı", exact: false }).first().click();
    const sources = page.locator("details").first();
    await expect(sources).toHaveAttribute("open", "");
    const card = sources.getByRole("region", { name: /Kaynak:/ }).first();
    await expect(card.getByText("Kayıt tarihi:", { exact: true })).toHaveCount(1);
    await expect(card.locator("time")).toHaveCount(1);
    await expect(card.locator("time")).toHaveText("15.08.2026");
    await expect(card).not.toContainText("15 Ağustos 2026");
    await checkComposer(page);
    await checkAccessibility(page);

    const summary = sources.locator("summary");
    await summary.focus();
    // Firefox, programatik odağı fare odağı olarak sınıflandırabilir.
    // Gerçek klavye geçişiyle geri gelerek :focus-visible davranışını sına.
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(summary).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(sources).not.toHaveAttribute("open", "");
    await page.keyboard.press("Enter");
    await expect(sources).toHaveAttribute("open", "");
    expect(await summary.evaluate((element) => {
      const style = getComputedStyle(element);
      return style.outlineStyle !== "none" || style.boxShadow !== "none";
    })).toBe(true);
    await newChat.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("chat-message")).toHaveCount(1);
    await expect(sidebar.locator("ul > li").first()).toBeVisible();
    await checkComposer(page);
  });

  for (const width of [320, 768]) {
    test(`${width}px: taşma yok, geçmiş çekmecesi klavyeyle kullanılır ve Axe denetimi geçer`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/owner/assistant");
      await checkComposer(page);
      const history = page.getByRole("button", { name: "Sohbet geçmişini aç" });
      await history.focus();
      await page.keyboard.press("Enter");
      const drawer = page.getByRole("dialog", { name: "Sohbet geçmişi" });
      await expect(drawer).toBeVisible();
      await expect(drawer.getByRole("button", { name: "Kenar çubuğunu kapat" })).toBeFocused();
      await checkAccessibility(page);
      await page.keyboard.press("Shift+Tab");
      expect(await drawer.evaluate((element) => element.contains(document.activeElement))).toBe(true);
      await page.keyboard.press("Escape");
      await expect(drawer).not.toBeVisible();
      await expect(history).toBeFocused();

      await page.getByRole("group", { name: "Hazır soru önerileri" }).getByRole("button", { name: "Son bakım ne zaman yapıldı?", exact: true }).click();
      await expect(page.locator("details").first()).toHaveAttribute("open", "");
      await checkComposer(page);
      await expect(page.getByRole("button", { name: "Yeni sohbet başlat" })).toBeVisible();
      await checkAccessibility(page);
      if (width === 768) {
        await history.click();
        await expect(drawer).toBeVisible();
        await page.setViewportSize({ width: 1280, height: 800 });
        await expect(drawer).not.toBeVisible();
        await expect(page.getByRole("textbox", { name: "Soru giriş kutusu" })).toBeEnabled();
        await expect(page.getByRole("textbox", { name: "Soru giriş kutusu" })).toBeEditable();
      }

    });
  }
});
