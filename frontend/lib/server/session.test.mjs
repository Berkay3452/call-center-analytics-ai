// Çalıştırma: `npm run test:unit` (Node >= 22.18, yerleşik test koşucusu).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  SESSION_MAX_AGE_S,
  createSessionToken,
  getSessionKey,
  isSameOrigin,
  sessionCookieOptions,
  verifySessionToken,
} from "./session.ts";

const ENV = { USER_SIGNING_KEY: "x".repeat(40) };
const NOW = 1_800_000_000;
const ID = "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b";
const CID = "606bd734-644f-5c21-af2f-dc734c4ecd67";
const owner = { role: "owner", sub: ID, cid: CID, name: "Ahmet Yılmaz", exp: NOW + 3600 };
const admin = { role: "admin", sub: ID, cid: null, name: "Yönetici 1", exp: NOW + 3600 };

test("anahtar yoksa null; USER_SIGNING_KEY veya SESSION_SECRET ile oluşur", async () => {
  assert.equal(await getSessionKey({}), null);
  assert.ok(await getSessionKey(ENV));
  assert.ok(await getSessionKey({ SERVICE_KEY: "servis-anahtari" })); // yerel yedek
  assert.ok(await getSessionKey({ SESSION_SECRET: "s".repeat(32) }));
  assert.equal(await getSessionKey({ SESSION_SECRET: "kisa" }), null); // kısa gizli değer kabul edilmez
});

test("imzalı oturum doğrulanır (tekne sahibi ve yönetici)", async () => {
  const key = await getSessionKey(ENV);
  for (const s of [owner, admin]) {
    const token = await createSessionToken(s, key);
    assert.deepEqual(await verifySessionToken(token, key, NOW), s);
  }
});

test("süresi dolmuş, kurcalanmış ve yabancı anahtarla imzalı oturum reddedilir", async () => {
  const key = await getSessionKey(ENV);
  const other = await getSessionKey({ USER_SIGNING_KEY: "y".repeat(40) });
  const token = await createSessionToken(owner, key);
  assert.equal(await verifySessionToken(token, key, owner.exp + 1), null);
  assert.equal(await verifySessionToken(token, other, NOW), null);
  const [payload, mac] = token.split(".");
  // Rol yükseltme denemesi: yükü değiştirip eski imzayı tut.
  const forged = Buffer.from(JSON.stringify({ ...owner, role: "admin", cid: null })).toString("base64url");
  assert.equal(await verifySessionToken(`${forged}.${mac}`, key, NOW), null);
  assert.equal(await verifySessionToken(`${payload}.${mac}x`, key, NOW), null);
  for (const bad of ["", "abc", "a.b.c", `${payload}.`, undefined, null, "x".repeat(3000)]) {
    assert.equal(await verifySessionToken(bad, key, NOW), null);
  }
});

test("yük kuralları: sahip için müşteri kimliği şart, yönetici için yok", async () => {
  const key = await getSessionKey(ENV);
  for (const bad of [
    { ...owner, cid: null },
    { ...admin, cid: CID },
    { ...owner, sub: "uuid-degil" },
    { ...owner, role: "root" },
  ]) {
    const token = await createSessionToken(bad, key);
    assert.equal(await verifySessionToken(token, key, NOW), null);
  }
});

test("çerez seçenekleri: httpOnly, SameSite=Lax, secure yalnız canlıda, süre sınırlı", () => {
  const dev = sessionCookieOptions({ NODE_ENV: "development" });
  const prod = sessionCookieOptions({ NODE_ENV: "production" });
  assert.equal(dev.httpOnly, true);
  assert.equal(dev.sameSite, "lax");
  assert.equal(dev.secure, false);
  assert.equal(prod.secure, true);
  assert.equal(prod.maxAge, SESSION_MAX_AGE_S);
});

test("aynı kaynak denetimi", () => {
  assert.equal(isSameOrigin(null, "localhost:3000"), true);
  assert.equal(isSameOrigin("http://localhost:3000", "localhost:3000"), true);
  assert.equal(isSameOrigin("http://evil.example", "localhost:3000"), false);
  assert.equal(isSameOrigin("not a url", "localhost:3000"), false);
  assert.equal(isSameOrigin("http://localhost:3000", null), false);
});
