// Çalıştırma: `npm run test:unit` (Node >= 22.18, yerleşik test koşucusu).
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import { identityHeaders, signUserId } from "./identity.ts";

const SUB = "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b";
const CID = "606bd734-644f-5c21-af2f-dc734c4ecd67";
const KEY = "k".repeat(40);
const owner = { role: "owner", sub: SUB, cid: CID, name: "Ahmet", exp: 9_999_999_999 };
const admin = { role: "admin", sub: SUB, cid: null, name: "Yönetici", exp: 9_999_999_999 };

test("imza backend sign_user_id ile aynı: HMAC(kimlik.rol.zaman)", () => {
  const sig = signUserId(CID, "owner", KEY, 1_800_000_000);
  const expected = createHmac("sha256", KEY).update(`${CID}.owner.1800000000`).digest("hex");
  assert.equal(sig, `1800000000.${expected}`);
});

test("tekne sahibi: kimlik müşteri kimliğidir, rol sahiptir", () => {
  const h = identityHeaders(owner, KEY, 1_800_000_000);
  assert.equal(h["x-user-id"], CID);
  assert.equal(h["x-user-role"], "owner");
  assert.equal(h["x-user-signature"], signUserId(CID, "owner", KEY, 1_800_000_000));
});

test("yönetici: kimlik hesap kimliğidir, rol yöneticidir, müşteri kimliği yoktur", () => {
  const h = identityHeaders(admin, KEY, 1_800_000_000);
  assert.equal(h["x-user-id"], SUB);
  assert.equal(h["x-user-role"], "admin");
  assert.notEqual(h["x-user-signature"], signUserId(SUB, "owner", KEY, 1_800_000_000)); // rol imzaya dahil
});

test("imza anahtarı yoksa imza başlığı konmaz (yalnız yerel/test backend'i kabul eder)", () => {
  const h = identityHeaders(owner, undefined);
  assert.equal("x-user-signature" in h, false);
});
