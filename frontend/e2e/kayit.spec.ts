import { expect, test as base } from "@playwright/test";
import { sessionToken } from "./auth";
import { test as sessionTest } from "./fixtures";

/**
 * Kaydol sayfası ve Tekne ekle (#384). Sahte modda backend yoktur: kayıt ucu yanıtı, üretimdeki
 * imzayla üretilmiş gerçek bir oturum çerezi taşır; tekneler mock katmanında tutulur.
 */

const ANONYMOUS = { cookies: [], origins: [] };
const STRONG = "Güçlü-Parola_26";

async function fillRegister(page: import("@playwright/test").Page, over: Record<string, string> = {}) {
  const v = {
    ad: "Ayşe",
    soyad: "Demir",
    tel: "0532 123 45 67",
    eposta: "ayse.demir@example.com",
    parola: STRONG,
    tekrar: STRONG,
    ...over,
  };
  await page.getByLabel("Ad", { exact: true }).fill(v.ad);
  await page.getByLabel("Soyad").fill(v.soyad);
  await page.getByLabel("Telefon numarası").fill(v.tel);
  await page.getByLabel("E-posta", { exact: true }).fill(v.eposta);
  await page.getByLabel("Parola", { exact: true }).fill(v.parola);
  await page.getByLabel("Parolayı tekrarla").fill(v.tekrar);
}

base.describe("kaydol", () => {
  base.use({ storageState: ANONYMOUS });

  base("girişten kaydol sayfasına gidilir; doğum tarihi sorulmaz", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: "Kaydolun" }).click();
    await expect(page).toHaveURL(/\/register$/);
    await expect(page.getByText("Tekne sahibi hesabı oluşturun")).toBeVisible();
    for (const id of ["reg-first-name", "reg-last-name", "reg-phone", "reg-email", "reg-password", "reg-password-confirm"]) {
      await expect(page.locator(`#${id}`)).toBeVisible();
    }
    await expect(page.locator("form").getByText(/doğum/i)).toHaveCount(0);
  });

  base("parola kuralları canlı gösterilir ve zayıf parola gönderilmez", async ({ page }) => {
    let called = false;
    await page.route("**/api/auth/register", async (route) => {
      called = true;
      await route.abort();
    });
    await page.goto("/register");
    await fillRegister(page, { parola: "kucukharfsadece", tekrar: "kucukharfsadece" });
    await page.getByRole("button", { name: "Hesap oluştur" }).click();
    await expect(page.getByText(/Parola şunları içermeli/)).toBeVisible();
    expect(called).toBe(false);
    await fillRegister(page, { tekrar: "baska-parola" });
    await page.getByRole("button", { name: "Hesap oluştur" }).click();
    await expect(page.getByText("Parola ve tekrarı aynı olmalı.")).toBeVisible();
    expect(called).toBe(false);
  });

  base("eksik ve hatalı alanlar işaretlenir", async ({ page }) => {
    await page.goto("/register");
    await page.getByRole("button", { name: "Hesap oluştur" }).click();
    await expect(page.getByText("Adınızı girin.", { exact: true })).toBeVisible();
    await expect(page.getByText("Soyadınızı girin.", { exact: true })).toBeVisible();
    await expect(page.getByText(/geçerli bir cep telefonu/i)).toBeVisible();
    await expect(page.getByText(/geçerli bir e-posta/i)).toBeVisible();
  });

  base("başarılı kayıt: bilgiler tek tip gönderilir ve otomatik girilir", async ({ page }) => {
    let sent: Record<string, string> | null = null;
    await page.route("**/api/auth/register", async (route) => {
      sent = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        headers: { "set-cookie": `mico_session=${await sessionToken("owner")}; Path=/; HttpOnly; SameSite=Lax` },
        body: JSON.stringify({ role: "owner", display_name: "Ayşe Demir", home: "/owner/assistant" }),
      });
    });
    await page.goto("/register");
    await fillRegister(page);
    await page.getByRole("button", { name: "Hesap oluştur" }).click();
    await expect(page).toHaveURL(/\/owner\/assistant/);
    expect(sent).toMatchObject({
      first_name: "Ayşe",
      last_name: "Demir",
      email: "ayse.demir@example.com",
      password: STRONG,
      password_confirm: STRONG,
    });
    expect(sent).not.toHaveProperty("role");
  });

  base("kayıtlı e-posta: sunucu iletisi gösterilir, parola alanları temizlenir", async ({ page }) => {
    await page.route("**/api/auth/register", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "conflict", message: "Bu bilgilerle kayıt yapılamadı. Giriş yapmayı deneyin." } }),
      }),
    );
    await page.goto("/register");
    await fillRegister(page);
    await page.getByRole("button", { name: "Hesap oluştur" }).click();
    await expect(page.locator("form [role=alert]")).toContainText("Giriş yapmayı deneyin");
    await expect(page.getByLabel("Parola", { exact: true })).toHaveValue("");
  });

  base("kayıt ucu oturumsuz herkese açık, ama gövdesiz istek 400 döner", async ({ request }) => {
    const res = await request.post("/api/auth/register", { data: {} });
    expect(res.status()).toBe(400);
  });
});

sessionTest.describe("tekne ekle", () => {
  sessionTest("sahip tekne ekler ve listede görür; yinelenen ad reddedilir", async ({ page }) => {
    await page.goto("/owner/boats");
    await expect(page.getByText("Henüz tekne eklemediniz.")).toBeVisible();

    await page.getByRole("button", { name: "Tekne ekle" }).click();
    await page.getByRole("button", { name: "Teknemi kaydet" }).click();
    await expect(page.getByText("Tekne adını girin.")).toBeVisible();

    await page.getByLabel("Tekne adı").fill("Deniz Yıldızı");
    await page.getByLabel("Tekne modeli").fill("Beneteau Oceanis 40");
    await page.getByLabel("Üretim yılı").fill("2018");
    await page.getByLabel("Marina").fill("Göcek D-Marin");
    await page.getByRole("button", { name: "Teknemi kaydet" }).click();

    await expect(page.getByRole("status")).toContainText("Deniz Yıldızı");
    const list = page.getByRole("list", { name: "Tekneler" });
    await expect(list).toContainText("Deniz Yıldızı");
    await expect(list).toContainText("Beneteau Oceanis 40");
    await expect(list).toContainText("2018");
    await expect(list).toContainText("Göcek D-Marin");

    await page.getByRole("button", { name: "Tekne ekle" }).click();
    await page.getByLabel("Tekne adı").fill("deniz yıldızı");
    await page.getByRole("button", { name: "Teknemi kaydet" }).click();
    await expect(page.locator("form [role=alert]")).toContainText("zaten var");
  });

  sessionTest("yıl sınırı denetlenir; Teknelerim sekmesi yalnızca sahipte görünür", async ({ page }) => {
    await page.goto("/owner/boats");
    await expect(page.getByRole("navigation", { name: "Ana gezinme" }).getByRole("link", { name: "Teknelerim" })).toBeVisible();
    await page.getByRole("button", { name: "Tekne ekle" }).click();
    await page.getByLabel("Tekne adı").fill("Eski Tekne");
    await page.getByLabel("Üretim yılı").fill("1900");
    await page.getByRole("button", { name: "Teknemi kaydet" }).click();
    await expect(page.getByText(/1950 ile/)).toBeVisible();

    await page.goto("/admin/analytics");
    await expect(page.getByRole("link", { name: "Teknelerim" })).toHaveCount(0);
  });
});
