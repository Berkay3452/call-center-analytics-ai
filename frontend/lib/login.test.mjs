// Çalıştırma: `npm run test:unit` (Node >= 22.18, yerleşik test koşucusu).
import assert from "node:assert/strict";
import { test } from "node:test";
import { loginErrorMessage, safeNext } from "./login.ts";

test("safeNext: yalnızca rolün kendi alanındaki göreli yol kabul edilir", () => {
  assert.equal(safeNext("/admin/calls", "admin"), "/admin/calls");
  assert.equal(safeNext("/owner/assistant", "owner"), "/owner/assistant");
  assert.equal(safeNext(null, "admin"), "/admin/analytics");
  assert.equal(safeNext(undefined, "owner"), "/owner/assistant");
});

test("safeNext: açık yönlendirme ve rol dışı yol ana sayfaya düşer", () => {
  for (const bad of ["//evil.example", "https://evil.example", "/\\evil", "admin/calls", "/adminx", "/api/backend/calls"]) {
    assert.equal(safeNext(bad, "admin"), "/admin/analytics", bad);
  }
  assert.equal(safeNext("/admin/calls", "owner"), "/owner/assistant"); // sahip yönetici yoluna atlayamaz
  assert.equal(safeNext("/owner/assistant", "admin"), "/admin/analytics");
});

test("hata iletileri genel ve kullanıcı dostu", () => {
  assert.equal(loginErrorMessage(401), "Kullanıcı adı veya parola hatalı.");
  assert.match(loginErrorMessage(429, 30), /30 sn/);
  assert.doesNotMatch(loginErrorMessage(429), /sn\)/);
  assert.match(loginErrorMessage(503), /şu anda yapılamıyor/);
  assert.match(loginErrorMessage(500), /şu anda yapılamıyor/);
});
