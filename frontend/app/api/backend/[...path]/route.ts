/**
 * Tarayıcıdan AI servisine giden isteklerin vekil (proxy) uç noktası.
 *
 * Servis anahtarı (SERVICE_KEY) yalnızca bu sunucu tarafında bulunur; tarayıcı kodu hiçbir
 * zaman görmez. Yalnızca API sözleşmesindeki yollar (docs/api.md) iletilir.
 * Gerçek sistemde tekne sahibi kimliğini (X-User-Id) Miço Usta .NET uygulaması belirler;
 * geliştirmede arayüzün gönderdiği başlık olduğu gibi iletilir.
 */

import type { NextRequest } from "next/server";

// Yol → izinli HTTP yöntemleri (#271). Listede olmayan yöntem 405 döner.
const R: Array<[RegExp, readonly string[]]> = [
  [/^calls$/, ["GET", "POST"]],
  [/^calls\/[^/]+$/, ["GET"]],
  [/^calls\/[^/]+\/analyze$/, ["POST"]],
  [/^calls\/[^/]+\/status$/, ["GET"]],
  [/^calls\/[^/]+\/match$/, ["PUT"]],
  [/^calls\/[^/]+\/audio$/, ["GET", "HEAD"]],
  [/^calls\/audio$/, ["POST"]],
  [/^crm$/, ["GET"]],
  [/^crm\/[^/]+\/approve$/, ["POST"]],
  [/^crm\/[^/]+\/reject$/, ["POST"]],
  [/^crm\/suggestions\/[^/]+\/approve$/, ["POST"]],
  [/^crm\/suggestions\/[^/]+\/reject$/, ["POST"]],
  [/^crm\/suggestions\/[^/]+$/, ["GET"]],
  [/^crm\/[^/]+$/, ["GET"]],
  [/^service-orders$/, ["GET"]],
  [/^service-orders\/[^/]+$/, ["GET"]],
  [/^service-orders\/[^/]+\/status$/, ["PATCH"]],
  [/^analytics\/summary$/, ["GET"]],
  [/^chat\/.+$/, ["GET", "POST", "DELETE"]],
  [/^assistant\/.+$/, ["GET", "POST", "DELETE"]],
];

// Mock modunda veya servis kapalıyken dönecek geçerli minimal WAV ses verisi
const MOCK_WAV = Buffer.from(
  "UklGRjIAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YRAAAACAgICAgICAgICAgICAgICA",
  "base64",
);

async function forward(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await ctx.params;
  const joined = path.join("/");
  // Birden çok kural eşleşebilir (ör. calls/audio): izinli yöntemler birleşir.
  const methods = R.filter(([re]) => re.test(joined)).flatMap(([, m]) => m);
  if (methods.length === 0) {
    return Response.json(
      { error: { code: "not_found", message: "Bilinmeyen uç nokta.", details: {}, request_id: null } },
      { status: 404 },
    );
  }

  if (req.method !== "OPTIONS" && !methods.includes(req.method)) {
    return Response.json(
      {
        error: {
          code: "method_not_allowed",
          message: "Bu uç noktada bu yöntem desteklenmiyor.",
          details: {},
          request_id: null,
        },
      },
      { status: 405, headers: { allow: [...new Set(methods)].join(", ") } },
    );
  }

  const isAudioRequest = joined.startsWith("calls/") && joined.endsWith("/audio");

  // Mock modu açıksa ve ses isteniyorsa doğrudan örnek ses verisi dön
  if (isAudioRequest && process.env.NEXT_PUBLIC_USE_MOCKS === "true") {
    return new Response(MOCK_WAV, {
      status: 200,
      headers: {
        "content-type": "audio/wav",
        "content-length": String(MOCK_WAV.length),
        "accept-ranges": "bytes",
        "cache-control": "no-cache",
      },
    });
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
    "retry-after",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
  ]) {
    const v = upstream.headers.get(name);
    if (v) out.set(name, v);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
  forward as HEAD,
};
