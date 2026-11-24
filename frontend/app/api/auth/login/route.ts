/**
 * Giriş (#371): tarayıcıdan gelen rol + kullanıcı adı + parolayı backend `/auth/login` ucuna iletir.
 *
 * Servis anahtarı yalnızca bu sunucuda bulunur. Başarılıysa imzalı, `httpOnly` oturum çerezi
 * kurulur; parola hiçbir yerde saklanmaz/günlüğe yazılmaz. Backend'in genel 401 iletisi aynen
 * korunur (hesabın varlığı belli edilmez).
 */

import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import {
  ROLE_HOME,
  SESSION_COOKIE,
  SESSION_MAX_AGE_S,
  createSessionToken,
  getSessionKey,
  isSameOrigin,
  sessionCookieOptions,
  type Session,
} from "@/lib/server/session";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function error(status: number, code: string, message: string, headers?: HeadersInit) {
  return Response.json({ error: { code, message } }, { status, headers });
}

export async function POST(req: NextRequest): Promise<Response> {
  if (!isSameOrigin(req.headers.get("origin"), req.headers.get("host"))) {
    return error(403, "forbidden", "İstek kaynağı geçersiz.");
  }

  let input: unknown;
  try {
    input = await req.json();
  } catch {
    return error(400, "bad_request", "Geçersiz istek gövdesi.");
  }
  const { role, username, password } = (input ?? {}) as Record<string, unknown>;
  if (
    (role !== "admin" && role !== "owner") ||
    typeof username !== "string" ||
    typeof password !== "string" ||
    !username.trim() ||
    !password ||
    username.length > 100 ||
    password.length > 200
  ) {
    return error(400, "bad_request", "Rol, kullanıcı adı ve parola gerekli.");
  }

  const key = await getSessionKey(process.env);
  const serviceKey = process.env.SERVICE_KEY;
  if (!key || !serviceKey) {
    console.error("Giriş kapalı: SERVICE_KEY veya oturum anahtarı (SESSION_SECRET/USER_SIGNING_KEY) eksik.");
    return error(503, "service_unavailable", "Giriş şu anda kullanılamıyor.");
  }

  const base = (process.env.API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");
  let upstream: Response;
  try {
    upstream = await fetch(`${base}/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-service-key": serviceKey },
      body: JSON.stringify({ role, username, password }),
      cache: "no-store",
    });
  } catch {
    return error(503, "service_unavailable", "AI servisine ulaşılamadı.");
  }

  if (upstream.status === 401) {
    return error(401, "unauthorized", "Kullanıcı adı veya parola hatalı.");
  }
  if (upstream.status === 429) {
    const retry = upstream.headers.get("retry-after");
    return error(429, "too_many_requests", "Çok fazla deneme yapıldı; lütfen biraz bekleyin.",
      retry ? { "retry-after": retry } : undefined);
  }
  if (!upstream.ok) {
    return error(upstream.status >= 500 ? 503 : 400, "login_failed", "Giriş tamamlanamadı.");
  }

  const data = (await upstream.json().catch(() => null)) as Record<string, unknown> | null;
  if (
    !data ||
    data.role !== role ||
    typeof data.account_id !== "string" ||
    !UUID.test(data.account_id) ||
    (role === "owner" && (typeof data.customer_id !== "string" || !UUID.test(data.customer_id)))
  ) {
    return error(503, "service_unavailable", "Giriş yanıtı geçersiz.");
  }

  const session: Session = {
    role,
    sub: data.account_id,
    cid: role === "owner" ? (data.customer_id as string) : null,
    name: typeof data.display_name === "string" ? data.display_name.slice(0, 200) : "",
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_S,
  };
  const token = await createSessionToken(session, key);
  (await cookies()).set(SESSION_COOKIE, token, sessionCookieOptions(process.env));
  return Response.json(
    { role, display_name: session.name, home: ROLE_HOME[role] },
    { headers: { "cache-control": "no-store" } },
  );
}
