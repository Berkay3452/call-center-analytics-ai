import { test, expect } from "./fixtures";

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
    // calls/{id} için GET ve DELETE (çağrı silme) izinlidir; PUT yasaktır.
    const res = await request.put("/api/backend/calls/abc");
    expect(res.status()).toBe(405);
    expect(res.headers()["allow"]).toContain("GET");
    expect(res.headers()["allow"]).toContain("DELETE");
    const body = await res.json();
    expect(body.error.code).toBe("method_not_allowed");
  });

  test("vekil, istemcinin çağırdığı yolları tanır (#391)", async ({ request }) => {
    // Mock modu istemcide yanıt verdiği için eksik izin ancak vekile doğrudan istekle görülür.
    // Arka uç çalışmasa da izinli yol "Bilinmeyen uç nokta" (404) ya da 405 dönmez.
    const paths = ["calls", "customers", "crm", "service-orders", "analytics/summary", "boats", "chat/sessions"];
    for (const path of paths) {
      const res = await request.get(`/api/backend/${path}`);
      expect([404, 405], path).not.toContain(res.status());
    }
  });

  test("vekil bilinmeyen yolu 404 ile reddeder", async ({ request }) => {
    const res = await request.get("/api/backend/health");
    expect(res.status()).toBe(404);
  });
});
