import { expect, test } from "@playwright/test";
import { sessionToken } from "./auth";

/**
 * Giriş sayfası (#371). Backend'e ihtiyaç duymaz: `/api/auth/login` yanıtı taklit edilir; bu
 * testler formun davranışını (rol seçimi, hata iletisi, yönlendirme) doğrular. Sunucu tarafı
 * (çerez imzası, genel hata) birim ve backend testlerindedir.
 */

// Giriş sayfası oturumsuz kullanıcı içindir (oturumlu kullanıcı ana sayfaya yönlenir).
test.use({ storageState: { cookies: [], origins: [] } });

test("giriş sayfası kabuksuz açılır ve rol seçimi etiketi değiştirir", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: /Miço/ }).or(page.getByText("Çağrı Analitiği ve Miço AI"))).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Ana gezinme" })).toHaveCount(0);
  await expect(page.getByRole("radio", { name: "Yönetici" })).toBeChecked();
  await expect(page.getByRole("button", { name: "Yönetici olarak giriş yap" })).toBeVisible();

  await page.getByRole("radio", { name: "Tekne sahibi" }).click();
  await expect(page.getByRole("radio", { name: "Tekne sahibi" })).toBeChecked();
  await expect(page.getByRole("button", { name: "Tekne sahibi olarak giriş yap" })).toBeVisible();
});

test("boş alanla gönderilemez; yanlış parolada genel hata gösterilir ve parola temizlenir", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/auth/login", async (route) => {
    calls += 1;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "unauthorized", message: "Kullanıcı adı veya parola hatalı." } }),
    });
  });
  await page.goto("/login", { waitUntil: "networkidle" }); // form etkileşime hazır (hidrasyon bitti)

  await page.getByRole("button", { name: "Yönetici olarak giriş yap" }).click();
  await expect(page.locator("form [role=alert]")).toContainText("Kullanıcı adı ve parolayı girin");
  expect(calls).toBe(0);

  await page.getByLabel("Kullanıcı adı").fill("yonetici1");
  await page.getByLabel("Parola").fill("yanlis-parola-123");
  await page.getByRole("button", { name: "Yönetici olarak giriş yap" }).click();
  await expect(page.locator("form [role=alert]")).toContainText("Kullanıcı adı veya parola hatalı.");
  await expect(page.getByLabel("Parola")).toHaveValue("");
});

test("parola göster/gizle düğmesi alan türünü değiştirir", async ({ page }) => {
  await page.goto("/login");
  const field = page.getByLabel("Parola");
  await expect(field).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Göster" }).click();
  await expect(field).toHaveAttribute("type", "text");
});

test("başarılı girişte seçilen rolün ana sayfasına gidilir ve rol bilgisi gönderilir", async ({ page }) => {
  let sent: Record<string, string> | null = null;
  await page.route("**/api/auth/login", async (route) => {
    sent = route.request().postDataJSON();
    // Gerçek sunucu imzalı çerezi kurar; burada aynı biçimde üretilmiş çerez taklit edilir.
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "set-cookie": `mico_session=${await sessionToken("owner")}; Path=/; HttpOnly; SameSite=Lax` },
      body: JSON.stringify({ role: "owner", display_name: "Ahmet Yılmaz", home: "/owner/assistant" }),
    });
  });
  await page.goto("/login");
  await page.getByRole("radio", { name: "Tekne sahibi" }).click();
  await page.getByLabel("Kullanıcı adı").fill("ahmet.yilmaz");
  await page.getByLabel("Parola").fill("herhangi-bir-parola");
  await page.getByRole("button", { name: "Tekne sahibi olarak giriş yap" }).click();
  await expect(page).toHaveURL(/\/owner\/assistant/);
  expect(sent).toMatchObject({ role: "owner", username: "ahmet.yilmaz" });
});
