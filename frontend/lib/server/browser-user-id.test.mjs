// Çalıştırma: `npm run test:unit` (Node >= 22.18, yerleşik test koşucusu).
import assert from "node:assert/strict";
import { test } from "node:test";
import { decideBrowserUserId } from "./browser-user-id.ts";

test("bayrak kapalıysa veya yoksa kimlik iletilmez", () => {
  assert.deepEqual(decideBrowserUserId({}), { allow: false, refusedInProduction: false });
  assert.equal(decideBrowserUserId({ ALLOW_BROWSER_USER_ID: "false" }).allow, false);
  assert.equal(decideBrowserUserId({ ALLOW_BROWSER_USER_ID: "1" }).allow, false);
});

test("geliştirmede bayrak açıksa izin verilir", () => {
  const d = decideBrowserUserId({ ALLOW_BROWSER_USER_ID: "true", NODE_ENV: "development" });
  assert.equal(d.allow, true);
});

test("canlıda bayrak açık olsa da reddedilir (APP_ENV yok veya prod)", () => {
  for (const extra of [{}, { APP_ENV: "prod" }, { APP_ENV: "production" }, { APP_ENV: "" }]) {
    const d = decideBrowserUserId({
      ALLOW_BROWSER_USER_ID: "true",
      NODE_ENV: "production",
      ...extra,
    });
    assert.deepEqual(d, { allow: false, refusedInProduction: true });
  }
});

test("yerel compose (NODE_ENV=production + APP_ENV=local) açıkça izinlidir", () => {
  const d = decideBrowserUserId({
    ALLOW_BROWSER_USER_ID: "true",
    NODE_ENV: "production",
    APP_ENV: "local",
  });
  assert.equal(d.allow, true);
});
