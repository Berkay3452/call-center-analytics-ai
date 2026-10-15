/**
 * Tarayıcıdan AI servisine giden isteklerin vekil (proxy) uç noktası.
 *
 * Servis anahtarı (SERVICE_KEY) yalnızca bu sunucu tarafında bulunur; tarayıcı kodu hiçbir
 * zaman görmez. Yalnızca API sözleşmesindeki yollar (docs/api.md) iletilir.
 * Gerçek sistemde tekne sahibi kimliğini (X-User-Id) Miço Usta .NET uygulaması belirler;
 * geliştirmede arayüzün gönderdiği başlık olduğu gibi iletilir.
 */

import type { NextRequest } from "next/server";

const ALLOWED = [
  /^calls(\/[^/]+(\/(analyze|status|audio))?)?$/,
  /^calls\/audio$/,
  /^crm$/,
  /^analytics\/summary$/,
  /^chat\/.+$/,
  /^assistant\/.+$/,
];

async function forward(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!ALLOWED.some((re) => re.test(joined))) {
    return Response.json(
      { error: { code: "not_found", message: "Bilinmeyen uç nokta.", details: {}, request_id: null } },
      { status: 404 },
    );
  }

  const base = (process.env.API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");
  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const userId = req.headers.get("x-user-id");
  if (userId) headers.set("x-user-id", userId);
  const range = req.headers.get("range");
  if (range) headers.set("range", range);
  const key = process.env.SERVICE_KEY;
  if (key) headers.set("x-service-key", key);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(`${base}/${joined}${req.nextUrl.search}`, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      cache: "no-store",
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "service_unavailable",
          message: "AI servisine ulaşılamadı.",
          details: {},
          request_id: null,
        },
      },
      { status: 503 },
    );
  }

  // Akışlı cevap (SSE) ve ses dosyası (Range) dahil gövde olduğu gibi aktarılır.
  const out = new Headers();
  for (const name of [
    "content-type",
    "x-request-id",
    "cache-control",
    "accept-ranges",
    "content-range",
    "content-length",
  ]) {
    const v = upstream.headers.get(name);
    if (v) out.set(name, v);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as DELETE };
