import { test, expect, type Page } from "@playwright/test";

/**
 * Canlı testler gerçek backend'e (mock'suz, seed'li veritabanı) karşı çalışır.
 * Çalıştırma: backend + frontend (`NEXT_PUBLIC_USE_MOCKS=false`) açıkken
 *   LIVE=1 npx playwright test e2e/live --project=chromium
 * CI'da ve LIVE tanımsızken atlanır (mock tabanlı e2e testlerini etkilemez).
 */
export function liveOnly() {
  test.skip(process.env.LIVE !== "1", "Canlı backend gerektirir (LIVE=1).");
}

export async function ask(page: Page, question: string) {
  const input = page.locator("#assistant-chat-input");
  const messages = page.getByTestId("chat-message");
  const before = await messages.count();
  await input.fill(question);
  await input.press("Enter");
  // Kullanıcı mesajı ve asistan yer tutucusu eklenir; cevap bitene kadar "Durdur" düğmesi görünür.
  await expect(messages).toHaveCount(before + 2, { timeout: 15000 });
  await expect(page.getByRole("button", { name: "Akışı Durdur" })).toBeHidden({ timeout: 60000 });
  const last = messages.last();
  await expect(last).toHaveAttribute("data-role", "assistant");
  return ((await last.innerText()) || "").replace(/\s+/g, " ");
}
