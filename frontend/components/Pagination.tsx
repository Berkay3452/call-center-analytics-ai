"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  className?: string;
}

export function Pagination({
  page,
  pageSize,
  total,
  className = "",
}: PaginationProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(Math.max(1, page), totalPages);

  const startRecord = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endRecord = Math.min(currentPage * pageSize, total);

  const goToPage = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages || newPage === currentPage || isPending) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(newPage));
    // page_size belirtilmişse koru
    if (pageSize !== 20) {
      params.set("page_size", String(pageSize));
    }
    const query = params.toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname);
      if (typeof window !== "undefined") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    });
  };

  // Sayfa butonları hesaplama (örn. 1, 2, ..., totalPages)
  const getPageNumbers = () => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages: (number | "dots")[] = [];
    if (currentPage <= 4) {
      pages.push(1, 2, 3, 4, 5, "dots", totalPages);
    } else if (currentPage >= totalPages - 3) {
      pages.push(1, "dots", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
    } else {
      pages.push(1, "dots", currentPage - 1, currentPage, currentPage + 1, "dots", totalPages);
    }
    return pages;
  };

  if (total === 0) {
    return null;
  }

  const pages = getPageNumbers();

  return (
    <nav
      aria-label="Sayfalama"
      className={`flex flex-col sm:flex-row items-center justify-between gap-4 py-4 px-2 ${className}`}
    >
      {/* Kayıt Göstergesi */}
      <div className="text-xs text-slate-600 font-medium">
        Toplam <span className="font-semibold text-slate-900">{total}</span> kayıttan{" "}
        <span className="font-semibold text-slate-900">
          {startRecord}-{endRecord}
        </span>{" "}
        arası gösteriliyor
      </div>

      {/* Sayfa Kontrolleri (yalnızca birden fazla sayfa varsa veya kontroller görünür) */}
      {totalPages > 1 && (
        <div className="inline-flex items-center gap-1">
          {/* Önceki Butonu */}
          <button
            type="button"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1 || isPending}
            aria-label="Önceki sayfaya git"
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-300 bg-white text-slate-700 shadow-xs hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
          >
            ‹ Önceki
          </button>

          {/* Sayfa Numaraları */}
          <div className="hidden sm:inline-flex items-center gap-1">
            {pages.map((p, idx) => {
              if (p === "dots") {
                return (
                  <span
                    key={`dots-${idx}`}
                    className="px-2 py-1 text-xs text-slate-400 select-none"
                    aria-hidden="true"
                  >
                    …
                  </span>
                );
              }
              const isCurrent = p === currentPage;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => goToPage(p)}
                  disabled={isPending}
                  aria-label={`Sayfa ${p}`}
                  aria-current={isCurrent ? "page" : undefined}
                  className={`min-w-8 h-8 inline-flex items-center justify-center px-2 text-xs font-semibold rounded-lg transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 ${
                    isCurrent
                      ? "bg-sky-700 text-white shadow-xs"
                      : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {p}
                </button>
              );
            })}
          </div>

          {/* Mobil için sade sayfa göstergesi */}
          <span className="sm:hidden text-xs font-medium text-slate-600 px-2">
            {currentPage} / {totalPages}
          </span>

          {/* Sonraki Butonu */}
          <button
            type="button"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= totalPages || isPending}
            aria-label="Sonraki sayfaya git"
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-300 bg-white text-slate-700 shadow-xs hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
          >
            Sonraki ›
          </button>
        </div>
      )}
    </nav>
  );
}
