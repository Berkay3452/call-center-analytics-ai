/**
 * Vekil rotanın backend'e ileteceği kimlik başlıkları (#372). Tarayıcıdan gelen hiçbir kimlik
 * başlığı kullanılmaz; her şey doğrulanmış oturumdan üretilir ve HMAC ile imzalanır.
 */

import { createHmac } from "node:crypto";
import type { Session } from "@/lib/server/session";

/** `<unix_zaman>.<hex(HMAC-SHA256(kimlik.rol.zaman))>`: backend `sign_user_id` ile aynı biçim. */
export function signUserId(userId: string, role: string, key: string, nowSec?: number): string {
  const ts = nowSec ?? Math.floor(Date.now() / 1000);
  const mac = createHmac("sha256", key).update(`${userId}.${role}.${ts}`).digest("hex");
  return `${ts}.${mac}`;
}

/** Sahip → müşteri kimliği, yönetici → hesap kimliği (denetim günlüğünde izlenebilir). */
export function identityHeaders(
  session: Session,
  signingKey: string | undefined,
  nowSec?: number,
): Record<string, string> {
  const userId = session.role === "owner" ? (session.cid as string) : session.sub;
  const headers: Record<string, string> = { "x-user-id": userId, "x-user-role": session.role };
  if (signingKey) headers["x-user-signature"] = signUserId(userId, session.role, signingKey, nowSec);
  return headers;
}
