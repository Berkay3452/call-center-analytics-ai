/**
 * Rota koruması (#372): oturumsuz kimse panellere ya da vekil API'ye ulaşamaz; roller kendi
 * alanında kalır. Her istekte oturum çerezi imzası ve süresi doğrulanır (bkz. `lib/server/session`).
 *
 * - Oturum yok: sayfalar `/login?next=...`e yönlenir, `/api/backend/*` 401 JSON döner.
 * - Yönetici `/owner/*`e, tekne sahibi `/admin/*`e giremez: kendi ana sayfasına yönlenir.
 * - Oturumlu kullanıcı `/login` veya `/` açarsa rolünün ana sayfasına gider.
 *
 * Asıl yetki yine backend'dedir (rol ve sahip denetimi); bu katman kullanıcıya erken, doğru
 * yönlendirme verir ve yetkisiz isteğin vekile bile girmesini önler.
 */

import { NextResponse, type NextRequest } from "next/server";
import { ROLE_HOME, SESSION_COOKIE, getSessionKey, verifySessionToken } from "@/lib/server/session";

function unauthorizedApi(): Response {
  return Response.json(
    { error: { code: "unauthorized", message: "Oturum gerekli.", details: {}, request_id: null } },
    { status: 401, headers: { "cache-control": "no-store" } },
  );
}

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const key = await getSessionKey(process.env);
  const session = key ? await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value, key) : null;

  // Giriş/çıkış uçları herkese açıktır (oturumu kuran/silen uçlardır).
  if (pathname.startsWith("/api/auth/")) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return session ? NextResponse.next() : unauthorizedApi();
  }

  if (!session) {
    if (pathname === "/login") return NextResponse.next();
    const url = new URL("/login", request.url);
    if (pathname.startsWith("/admin") || pathname.startsWith("/owner")) {
      url.searchParams.set("next", `${pathname}${search}`);
    }
    return NextResponse.redirect(url);
  }

  const home = ROLE_HOME[session.role];
  const wrongArea =
    (pathname.startsWith("/admin") && session.role !== "admin") ||
    (pathname.startsWith("/owner") && session.role !== "owner");
  if (pathname === "/login" || pathname === "/" || wrongArea) {
    return NextResponse.redirect(new URL(home, request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Statik dosyalar ve görseller hariç her yol (bkz. Next `proxy` matcher belgesi).
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|gif|webp|ico|txt|xml)$).*)"],
};
