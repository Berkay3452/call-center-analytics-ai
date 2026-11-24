import { test as base } from "@playwright/test";
import { SESSION_COOKIE } from "../lib/server/session";
import { sessionToken } from "./auth";

export { expect } from "@playwright/test";
export type { Page, Locator } from "@playwright/test";

/**
 * Oturumlu test: varsayılan çerez yöneticidir (`playwright.config.ts` → `storageState`). Bir
 * `/owner` adresine `page.goto` yapılınca oturum çerezi tekne sahibininkiyle değişir (diğer
 * adreslerde yöneticininkiyle); böylece tek dosyada hem yönetici hem sahip senaryoları yazılabilir.
 * Sunucu tarafı doğrulama gerçek yolla çalışır, hiçbir kontrol atlanmaz.
 */
export const test = base.extend({
  page: async ({ page, baseURL }, provide) => {
    const domain = new URL(baseURL ?? "http://localhost:3000").hostname;
    const tokens = { admin: await sessionToken("admin"), owner: await sessionToken("owner") };
    const goto = page.goto.bind(page);
    page.goto = async (url, options) => {
      const target = String(url);
      const role = /^(https?:\/\/[^/]+)?\/owner(\/|\?|$)/.test(target) ? "owner" : "admin";
      await page.context().addCookies([
        { name: SESSION_COOKIE, value: tokens[role], domain, path: "/", httpOnly: true, sameSite: "Lax" },
      ]);
      return goto(url, options);
    };
    await provide(page);
  },
});
