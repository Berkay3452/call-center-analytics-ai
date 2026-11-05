import { test, expect, type Page } from "@playwright/test";

/**
 * Düğme denetimi (#174): her görünür buton ve bağlantı bir sonuç vermelidir.
 * Sonuç = adres değişimi, açılan pencere ya da sayfada görünür bir değişiklik.
 * Aynı sayfaya giden (sonuç vermeyen) bağlantılar da başarısızlık sayılır.
 */

const PAGES = [
  "/admin/analytics",
  "/admin/calls",
  "/admin/calls/11111111-1111-4111-8111-111111111111",
  "/admin/calls/f32beed7-2e2b-595b-b022-9d68c3b8161d",
  "/admin/calls/upload",
  "/admin/crm",
  "/admin/service-orders",
  "/owner/assistant",
];

/** Kabukta her sayfada bulunan ve bilerek bulunduğu sayfayı gösteren öğeler. */
const SKIP_NAMES = [/^Miço Usta ana sayfa$/];

const SELECTOR = "main button:visible, main a[href]:visible, header a[href]:visible, nav a[href]:visible";

async function describe(page: Page, index: number) {
  const el = page.locator(SELECTOR).nth(index);
  const tag = await el.evaluate((n) => n.tagName.toLowerCase());
  const name = (
    (await el.getAttribute("aria-label")) ||
    (await el.innerText()) ||
    (await el.getAttribute("title")) ||
    ""
  )
    .replace(/\s+/g, " ")
    .trim();
  const disabled = await el.isDisabled().catch(() => false);
  // Zaten seçili sekme / düğme (aria-current, aria-selected, aria-pressed) sonuç üretmez
  const current =
    (await el.getAttribute("aria-current")) === "page" ||
    (await el.getAttribute("aria-selected")) === "true" ||
    (await el.getAttribute("aria-pressed")) === "true";
  return { el, tag, name, disabled, current };
}

for (const path of PAGES) {
  test(`Her görünür düğme sonuç verir: ${path}`, async ({ page: listingPage }) => {
    test.setTimeout(300_000);
    await listingPage.goto(path);
    await listingPage.waitForLoadState("domcontentloaded");
    await listingPage.waitForTimeout(800);
    const count = await listingPage.locator(SELECTOR).count();
    expect(count).toBeGreaterThan(0);

    const failures: string[] = [];

    for (let i = 0; i < count; i++) {
      // Her kontrol ayrı sayfada: önceki Next.js yönlendirmesi Firefox'ta
      // sonraki goto isteğini NS_BINDING_ABORTED ile iptal etmesin.
      const page = await listingPage.context().newPage();
      try {
        await page.goto(path);
        await page.waitForLoadState("domcontentloaded");
        await page.waitForTimeout(500);
        if ((await page.locator(SELECTOR).count()) <= i) continue;

        const { el, tag, name, disabled, current } = await describe(page, i);
        if (disabled || current || SKIP_NAMES.some((re) => re.test(name))) continue;

        const label = `${tag} "${name || "(adsız)"}"`;
        const startUrl = page.url();

        // Sonuçtan önce DOM değişimini izle
        await page.evaluate(() => {
          const w = window as unknown as { __mut?: number };
          w.__mut = 0;
          new MutationObserver((m) => {
            (window as unknown as { __mut: number }).__mut += m.length;
          }).observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
        });

        const href = tag === "a" ? await el.getAttribute("href") : null;
        try {
          await el.click({ timeout: 10000 });
          if (href && !href.startsWith("#")) {
            // Client navigation may need to compile its destination in development.
            await expect(page).toHaveURL(new URL(href, startUrl).href, { timeout: 15000 });
            expect(page.url(), label).not.toBe(startUrl);
          } else {
            await expect.poll(async () => {
              if (page.url() !== startUrl) return true;
              const mutated = await page.evaluate(() =>
                (window as unknown as { __mut?: number }).__mut ?? 0,
              ).catch(() => 1);
              return mutated > 0 || await page.getByRole("dialog").count() > 0;
            }, { message: label, timeout: 5000 }).toBe(true);
          }
        } catch (error) {
          failures.push(`${label}: ${error instanceof Error ? error.message : String(error)}`);
        }
      } finally {
        await page.close();
      }
    }

    expect(failures, `${path}\n${failures.join("\n")}`).toEqual([]);
  });
}
