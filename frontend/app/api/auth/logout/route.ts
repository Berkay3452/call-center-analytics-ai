/** Çıkış (#371): oturum çerezini siler. Yalnızca aynı kaynaktan gelen POST kabul edilir. */

import { cookies } from "next/headers";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, isSameOrigin } from "@/lib/server/session";

export async function POST(req: NextRequest): Promise<Response> {
  if (!isSameOrigin(req.headers.get("origin"), req.headers.get("host"))) {
    return Response.json({ error: { code: "forbidden", message: "İstek kaynağı geçersiz." } }, { status: 403 });
  }
  (await cookies()).delete(SESSION_COOKIE);
  return Response.json({ ok: true }, { headers: { "cache-control": "no-store" } });
}
