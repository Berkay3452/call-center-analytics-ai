/**
 * E2E oturum yardımcıları (#372). Sahte (mock) modda backend yoktur; testler, sunucunun tanıdığı
 * imzayla (aynı `SESSION_SECRET`) üretilmiş gerçek oturum çerezi kullanır. Sahte bir "test girişi"
 * ucu yoktur: üretimdeki doğrulama yolu aynen çalışır.
 */

import {
  SESSION_COOKIE,
  createSessionToken,
  getSessionKey,
  type SessionRole,
} from "../lib/server/session";

/** Yalnızca testler içindir (gizli değer değil). Dev sunucusu da aynı değerle başlatılır. */
export const E2E_SESSION_SECRET =
  process.env.SESSION_SECRET ?? "e2e-test-session-secret-not-for-production-0123456789";

const ADMIN_ID = "a0a0a0a0-0000-4000-8000-000000000001";
const OWNER_ID = "b0b0b0b0-0000-4000-8000-000000000002";
/** Seed tekne sahibi (Ahmet Yılmaz) müşteri kimliği. */
export const OWNER_CUSTOMER_ID = "606bd734-644f-5c21-af2f-dc734c4ecd67";

export async function sessionToken(role: SessionRole, expiresInS = 3600): Promise<string> {
  const key = await getSessionKey({ SESSION_SECRET: E2E_SESSION_SECRET });
  if (!key) throw new Error("E2E oturum anahtarı oluşturulamadı.");
  return createSessionToken(
    role === "admin"
      ? { role, sub: ADMIN_ID, cid: null, name: "Test Yöneticisi", exp: Math.floor(Date.now() / 1000) + expiresInS }
      : { role, sub: OWNER_ID, cid: OWNER_CUSTOMER_ID, name: "Test Tekne Sahibi", exp: Math.floor(Date.now() / 1000) + expiresInS },
    key,
  );
}

export async function storageStateFor(role: SessionRole, baseURL: string) {
  return {
    cookies: [
      {
        name: SESSION_COOKIE,
        value: await sessionToken(role),
        domain: new URL(baseURL).hostname,
        path: "/",
        httpOnly: true,
        secure: false,
        sameSite: "Lax" as const,
        expires: -1,
      },
    ],
    origins: [],
  };
}
