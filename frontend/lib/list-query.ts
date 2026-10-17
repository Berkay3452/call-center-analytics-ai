import type { CallQueryFilters } from "@/lib/api/client";

/** API'nin kabul ettiği en büyük sayfa boyutu (`page_size` ≤ 100). */
export const MAX_PAGE_SIZE = 100;
export const DEFAULT_PAGE_SIZE = 20;

/** `?page_size=` değerini 1..MAX_PAGE_SIZE aralığına sıkıştırır; geçersizse varsayılan. */
export function clampPageSize(raw: string | undefined): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return DEFAULT_PAGE_SIZE;
  return Math.min(Math.floor(n), MAX_PAGE_SIZE);
}

/** Filtreleri koruyarak belirtilen sayfaya giden adres (boş filtreler yazılmaz). */
export function listUrl(path: string, filters: CallQueryFilters, page: number): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "" || key === "page") continue;
    params.set(key, String(value));
  }
  params.set("page", String(page));
  return `${path}?${params.toString()}`;
}

/** Kayıt var ama istenen sayfa son sayfanın ötesinde mi? (Son sayfa numarasını döner.) */
export function lastPageIfOutOfRange(
  itemCount: number,
  total: number,
  page: number,
  pageSize: number,
): number | null {
  if (itemCount > 0 || total <= 0 || page <= 1) return null;
  return Math.max(1, Math.ceil(total / pageSize));
}
