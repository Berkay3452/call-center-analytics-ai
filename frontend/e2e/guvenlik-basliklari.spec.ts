import { test, expect } from "@playwright/test";

test.describe("Güvenlik başlıkları ve vekil kısıtları (#271)", () => {
  test("sayfa yanıtında güvenlik başlıkları var", async ({ request }) => {
    const res = await request.get("/admin/analytics");
    const h = res.headers();
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["x-frame-options"]).toBe("DENY");
    expect(h["referrer-policy"]).toBeTruthy();
    expect(h["permissions-policy"]).toContain("camera=()");
    expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(h["content-security-policy"]).toContain("object-src 'none'");
    expect(h["x-powered-by"]).toBeUndefined();
    // HSTS yalnızca üretim derlemesinde (HTTPS); dev sunucuda yok.
  });

  test("CSP sayfayı bozmaz: ihlal konsol hatası yok", async ({ page }) => {
    const violations: string[] = [];
    page.on("console", (msg) => {
      if (/content security policy/i.test(msg.text())) violations.push(msg.text());
    });
    await page.goto("/admin/analytics");
    await expect(page.locator("h1")).toBeVisible();
    expect(violations).toEqual([]);
  });

  test("vekil izinli olmayan yöntemi 405 ile reddeder", async ({ request }) => {
    const res = await request.delete("/api/backend/calls/abc");
    expect(res.status()).toBe(405);
    expect(res.headers()["allow"]).toContain("GET");
    const body = await res.json();
    expect(body.error.code).toBe("method_not_allowed");
  });

  test("vekil bilinmeyen yolu 404 ile reddeder", async ({ request }) => {
    const res = await request.get("/api/backend/health");
    expect(res.status()).toBe(404);
  });
});
