/**
 * Oturum çerezi (#371): imzalı, süreli, `httpOnly`. Yalnızca sunucu tarafında kullanılır.
 *
 * Çerez içeriği `<base64url(JSON)>.<base64url(HMAC-SHA256)>` biçimindedir. İmza anahtarı yalnızca
 * sunucudadır; tarayıcı içeriği okuyabilir ama değiştiremez, sahteleyemez. Rol ve kimlik (hesap,
 * müşteri) buradan gelir: tarayıcının gönderdiği hiçbir başlık kimlik sayılmaz (#372).
 *
 * Web Crypto kullanılır: aynı kod `proxy.ts`, rota işleyicileri ve testlerde çalışır.
 */

export type SessionRole = "admin" | "owner";

export interface Session {
  role: SessionRole;
  /** Hesap kimliği (`admin_accounts.id` veya `owner_accounts.id`). */
  sub: string;
  /** Tekne sahibi için müşteri kimliği; yönetici için null. */
  cid: string | null;
  /** Arayüzde gösterilen ad. */
  name: string;
  /** Bitiş zamanı (unix saniye). */
  exp: number;
}

export const SESSION_COOKIE = "mico_session";
export const SESSION_MAX_AGE_S = 8 * 60 * 60;

export type Env = Record<string, string | undefined>;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const enc = new TextEncoder();

function toB64Url(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64Url(text: string): Uint8Array | null {
  if (!/^[A-Za-z0-9_-]*$/.test(text)) return null;
  try {
    const bin = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

/**
 * İmza anahtarı: `SESSION_SECRET` (en az 32 karakter) varsa o; yoksa `USER_SIGNING_KEY`, o da
 * yoksa `SERVICE_KEY` alan ayrımlı (`mico-session-v1:` öneki) türetilir; ayrı bir değişken
 * eklemeden yerelde çalışsın diye. Hiçbiri yoksa null: giriş kapalı kalır, sahte oturum üretilmez.
 * Türetilen anahtar değişirse (ör. servis anahtarı döndürülürse) açık oturumlar geçersiz olur.
 */
export async function getSessionKey(env: Env): Promise<CryptoKey | null> {
  const direct = env.SESSION_SECRET?.trim();
  const base = env.USER_SIGNING_KEY?.trim() || env.SERVICE_KEY?.trim();
  const material = direct && direct.length >= 32 ? direct : base ? `mico-session-v1:${base}` : null;
  if (!material) return null;
  return crypto.subtle.importKey("raw", enc.encode(material), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}

export async function createSessionToken(session: Session, key: CryptoKey): Promise<string> {
  const payload = toB64Url(enc.encode(JSON.stringify(session)));
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(payload)));
  return `${payload}.${toB64Url(mac)}`;
}

function parseSession(raw: unknown, nowSec: number): Session | null {
  if (typeof raw !== "object" || raw === null) return null;
  const d = raw as Record<string, unknown>;
  const { role, sub, cid, name, exp } = d;
  if (role !== "admin" && role !== "owner") return null;
  if (typeof sub !== "string" || !UUID.test(sub)) return null;
  if (role === "owner" ? typeof cid !== "string" || !UUID.test(cid) : cid !== null) return null;
  if (typeof name !== "string" || name.length > 200) return null;
  if (typeof exp !== "number" || !Number.isFinite(exp) || exp <= nowSec) return null;
  return { role, sub, cid: cid as string | null, name, exp };
}

/** Geçerli imzalı ve süresi dolmamış oturumu döner; aksi halde null (neden belli edilmez). */
export async function verifySessionToken(
  token: string | undefined | null,
  key: CryptoKey,
  nowSec: number = Math.floor(Date.now() / 1000),
): Promise<Session | null> {
  if (!token || token.length > 2048) return null;
  const [payload, mac, extra] = token.split(".");
  if (!payload || !mac || extra !== undefined) return null;
  const macBytes = fromB64Url(mac);
  if (!macBytes) return null;
  const ok = await crypto.subtle.verify("HMAC", key, macBytes as BufferSource, enc.encode(payload));
  if (!ok) return null;
  const body = fromB64Url(payload);
  if (!body) return null;
  try {
    return parseSession(JSON.parse(new TextDecoder().decode(body)), nowSec);
  } catch {
    return null;
  }
}

export const ROLE_HOME: Record<SessionRole, string> = {
  admin: "/admin/analytics",
  owner: "/owner/assistant",
};

/** Çerez seçenekleri: `secure` yalnızca canlıda (yerelde http://localhost çalışsın). */
export function sessionCookieOptions(env: Env) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  };
}

/** Durum değiştiren isteklerde (giriş/çıkış) CSRF'ye karşı: `Origin` varsa ana makineyle aynı olmalı. */
export function isSameOrigin(origin: string | null, host: string | null): boolean {
  if (!origin) return true; // aynı site formları/araçlar Origin göndermeyebilir; SameSite=Lax korur
  if (!host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
