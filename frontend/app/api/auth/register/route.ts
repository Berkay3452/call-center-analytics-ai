/**
 * Kaydol (#384): tarayıcıdan gelen müşteri bilgilerini backend `/auth/register` ucuna iletir.
 *
 * Servis anahtarı yalnızca bu sunucuda bulunur. Başarılıysa giriş ucuyla aynı yolla imzalı,
 * `httpOnly` oturum çerezi kurulur (kullanıcı kaydolur kaydolmaz girmiş olur). Rol ve müşteri
 * kimliği istekten ALINMAZ: hesap her zaman tekne sahibidir. Parola hiçbir yerde saklanmaz.
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
const FIELDS = ["first_name", "last_name", "phone", "email", "password", "password_confirm"] as const;

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
  const raw = (input ?? {}) as Record<string, unknown>;
  const body: Record<string, string> = {};
  for (const field of FIELDS) {
    const value = raw[field];
    if (typeof value !== "string" || !value || value.length > 200) {
      return error(400, "bad_request", "Tüm alanlar gerekli.");
    }
    body[field] = value; // yalnızca bilinen alanlar iletilir (rol/müşteri kimliği taşınmaz)
  }

  const key = await getSessionKey(process.env);
  const serviceKey = process.env.SERVICE_KEY;
  if (!key || !serviceKey) {
    console.error("Kayıt kapalı: SERVICE_KEY veya oturum anahtarı (SESSION_SECRET/USER_SIGNING_KEY) eksik.");
    return error(503, "service_unavailable", "Kayıt şu anda kullanılamıyor.");
  }

  const base = (process.env.API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");
  let upstream: Response;
  try {
    upstream = await fetch(`${base}/auth/register`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-service-key": serviceKey },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return error(503, "service_unavailable", "AI servisine ulaşılamadı.");
  }

  if (upstream.status === 429) {
    const retry = upstream.headers.get("retry-after");
    return error(429, "too_many_requests", "Çok fazla kayıt denemesi; lütfen daha sonra tekrar deneyin.",
      retry ? { "retry-after": retry } : undefined);
  }
  if (upstream.status === 409 || upstream.status === 422) {
    // Sunucunun Türkçe, kullanıcıya dönük iletisi korunur (hesabın varlığı vurgulanmaz).
    const data = (await upstream.json().catch(() => null)) as { error?: { message?: unknown } } | null;
    const message = typeof data?.error?.message === "string" ? data.error.message.slice(0, 300) : "Kayıt tamamlanamadı.";
    return error(upstream.status, upstream.status === 409 ? "conflict" : "validation_error", message);
  }
  if (!upstream.ok) {
    return error(upstream.status >= 500 ? 503 : 400, "register_failed", "Kayıt tamamlanamadı.");
  }

  const data = (await upstream.json().catch(() => null)) as Record<string, unknown> | null;
  if (
    !data ||
    data.role !== "owner" ||
    typeof data.account_id !== "string" ||
    !UUID.test(data.account_id) ||
    typeof data.customer_id !== "string" ||
    !UUID.test(data.customer_id)
  ) {
    return error(503, "service_unavailable", "Kayıt yanıtı geçersiz.");
  }

  const session: Session = {
    role: "owner",
    sub: data.account_id,
    cid: data.customer_id,
    name: typeof data.display_name === "string" ? data.display_name.slice(0, 200) : "",
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_S,
  };
  const token = await createSessionToken(session, key);
  (await cookies()).set(SESSION_COOKIE, token, sessionCookieOptions(process.env));
  return Response.json(
    { role: "owner", display_name: session.name, home: ROLE_HOME.owner },
    { status: 201, headers: { "cache-control": "no-store" } },
  );
}
