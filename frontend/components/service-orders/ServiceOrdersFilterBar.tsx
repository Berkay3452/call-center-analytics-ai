"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState, useTransition } from "react";
import { MARINA_OPTIONS } from "@/lib/types";

interface ServiceOrdersFilterBarProps {
  className?: string;
  placeholder?: string;
}

export function ServiceOrdersFilterBar({
  className = "",
  placeholder = "Kod (SO-...), müşteri, tekne veya açıklama ara...",
}: ServiceOrdersFilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const urlQ = searchParams.get("q") ?? "";
  const urlMarina = searchParams.get("marina") ?? "";

  const [searchVal, setSearchVal] = useState(urlQ);

  const updateParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(searchParams.toString());
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      // Filtre değişince sayfa 1'e döner
      next.delete("page");

      startTransition(() => {
        const query = next.toString();
        router.push(query ? `${pathname}?${query}` : pathname);
      });
    },
    [pathname, router, searchParams],
  );

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateParam("q", searchVal.trim());
  };

  const handleReset = () => {
    setSearchVal("");
    const next = new URLSearchParams(searchParams.toString());
    next.delete("q");
    next.delete("marina");
    next.delete("date_from");
    next.delete("date_to");
    next.delete("page");

    startTransition(() => {
      const query = next.toString();
      router.push(query ? `${pathname}?${query}` : pathname);
    });
  };

  const hasFilters = Boolean(urlQ || urlMarina);

  return (
    <div
      className={`rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 shadow-xs ${className}`}
    >
      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3"
      >
        {/* Arama Alanı */}
        <div className="relative flex-1">
          <span
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 select-none text-xs"
            aria-hidden="true"
          >
            🔍
          </span>
          <label htmlFor="so-filter-q" className="sr-only">
            Servis emri arama
          </label>
          <input
            id="so-filter-q"
            type="text"
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            placeholder={placeholder}
            aria-label="Servis emri ara"
            className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 pl-8 pr-3 py-1.5 text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
          />
        </div>

        {/* Marina Filtresi */}
        <div className="w-full sm:w-48">
          <label htmlFor="so-filter-marina" className="sr-only">
            Marina filtresi
          </label>
          <select
            id="so-filter-marina"
            value={urlMarina}
            onChange={(e) => updateParam("marina", e.target.value)}
            aria-label="Marina filtresi"
            className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 px-2.5 py-1.5 text-xs text-slate-700 dark:text-slate-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
          >
            <option value="">Tüm Marinalar</option>
            {MARINA_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        {/* Ara & Temizle Butonları */}
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={isPending}
            className="rounded-lg bg-sky-700 dark:bg-sky-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-sky-800 dark:hover:bg-sky-700 transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 disabled:opacity-50"
          >
            {isPending ? "..." : "Ara"}
          </button>

          {hasFilters && (
            <button
              type="button"
              onClick={handleReset}
              disabled={isPending}
              aria-label="Filtreleri temizle"
              className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
            >
              Temizle
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
