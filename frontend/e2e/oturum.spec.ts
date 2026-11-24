import { expect, test } from "@playwright/test";
import { sessionToken } from "./auth";

/**
 * Rota koruması ve oturum (#372). Sahte modda backend yoktur; oturum çerezi üretimdeki imza yoluyla
 * doğrulanır (bkz. `e2e/auth.ts`). Burada panel erişimi, rol çaprazlama, sahte çerez ve çıkış denenir.
 */

const ANONYMOUS = { cookies: [], origins: [] };

test.describe("oturumsuz", () => {
  test.use({ storageState: ANONYMOUS });

  test("panel sayfaları girişe yönlenir ve dönülecek yol korunur", async ({ page }) => {
    await page.goto("/admin/calls?page_size=30");
    await expect(page).toHaveURL(/\/login\?next=%2Fadmin%2Fcalls%3Fpage_size%3D30/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/owner/assistant");
    await expect(page).toHaveURL(/\/login\?next=%2Fowner%2Fassistant/);
  });

  test("vekil API oturumsuz 401 döner, giriş ucu herkese açıktır", async ({ request }) => {
    const calls = await request.get("/api/backend/calls");
    expect(calls.status()).toBe(401);
    expect((await calls.json()).error.code).toBe("unauthorized");
    const audio = await request.get("/api/backend/calls/abc/audio");
    expect(audio.status()).toBe(401);
    const login = await request.post("/api/auth/login", { data: {} });
    expect(login.status()).toBe(400); // açık, ama doğrulama yapar (401 değil: oturum istemez)
  });

  test("sahte, kurcalanmış veya süresi dolmuş çerez oturum sayılmaz", async ({ page, context, baseURL }) => {
    const host = new URL(baseURL ?? "http://localhost:3000").hostname;
    const valid = await sessionToken("admin");
    const [payload] = valid.split(".");
    const expired = await sessionToken("admin", -10);
    for (const value of ["bozuk", `${payload}.AAAA`, expired]) {
      await context.clearCookies();
      await context.addCookies([{ name: "mico_session", value, domain: host, path: "/" }]);
      await page.goto("/admin/analytics");
      await expect(page).toHaveURL(/\/login/);
    }
  });
});

test.describe("yönetici oturumu", () => {
  test.use({ storageState: "e2e/.auth/admin.json" });

  test("kendi alanında kalır; sahip alanı ve giriş sayfası ana sayfaya yönlenir", async ({ page }) => {
    await page.goto("/owner/assistant");
    await expect(page).toHaveURL(/\/admin\/analytics$/);
    await page.goto("/login");
    await expect(page).toHaveURL(/\/admin\/analytics$/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/admin\/analytics$/);
  });

  test("üst barda kullanıcı adı ve Çıkış var, rol seçici yok", async ({ page }) => {
    await page.goto("/admin/analytics");
    await expect(page.getByTestId("session-name")).toHaveText("Test Yöneticisi");
    await expect(page.getByRole("button", { name: "Çıkış" })).toBeVisible();
    await expect(page.getByLabel("Rol seç")).toHaveCount(0);
  });

  test("Çıkış oturumu kapatır; sonra paneller yeniden girişe yönlenir", async ({ page }) => {
    await page.goto("/admin/analytics", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Çıkış" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/admin/calls");
    await expect(page).toHaveURL(/\/login\?next=/);
  });
});

test.describe("tekne sahibi oturumu", () => {
  test.use({ storageState: "e2e/.auth/owner.json" });

  test("yönetici alanına giremez, kendi asistan sayfasına yönlenir", async ({ page }) => {
    await page.goto("/admin/calls");
    await expect(page).toHaveURL(/\/owner\/assistant$/);
    await page.goto("/admin/crm");
    await expect(page).toHaveURL(/\/owner\/assistant$/);
    await expect(page.getByTestId("session-name")).toHaveText("Test Tekne Sahibi");
  });
});
