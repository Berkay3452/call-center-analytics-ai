import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

/**
 * Güvenlik başlıkları (#271). Tarayıcı yalnızca kendi kaynağına (`'self'`) bağlanır: API çağrıları
 * `/api/backend` vekili üzerinden gider, dış alan adı yoktur.
 *
 * `'unsafe-inline'` script için gerekli: Next.js satır içi başlatma betikleri yazar ve nonce'lu CSP
 * tüm sayfaları dinamik render etmeyi gerektirir (bu projede `cacheComponents` açık). Sıkılaştırma
 * (nonce) docs/guvenlik_mimarisi.md'de kalan risk olarak kayıtlıdır.
 * Geliştirmede HMR için `'unsafe-eval'` ve `ws:` eklenir; üretimde yoktur.
 */
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' blob: data:",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  // HSTS yalnızca canlıda (HTTPS): yerel http geliştirmeyi kilitlemesin.
  ...(isDev
    ? []
    : [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]),
];

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  experimental: {
    // `proxy.ts` çalışan isteklerde gövde varsayılan 10 MB'ta kesilir; ses yükleme sınırı 25 MB (#390).
    // Pay, çok parçalı form başlıkları ve alanları içindir.
    proxyClientMaxBodySize: "26mb",
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
