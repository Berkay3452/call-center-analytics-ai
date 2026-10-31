"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";
import {
  CALL_TYPE_LABELS,
  MARINA_OPTIONS,
  REQUEST_CATEGORY_LABELS,
  URGENCY_LABELS,
  type CallType,
  type RequestCategory,
  type Urgency,
} from "@/lib/types";

const STATE_OPTIONS: { value: string; label: string }[] = [
  { value: "beklemede", label: "⏳ Sırada (Beklemede)" },
  { value: "yaziya_cevriliyor", label: "Yazıya Çevriliyor" },
  { value: "isleniyor", label: "İşleniyor" },
  { value: "tamam", label: "✓ Tamamlandı" },
  { value: "kismi", label: "Kısmi" },
  { value: "basarisiz", label: "✕ Başarısız / Hata" },
];

export interface CallsFilterBarProps {
  showCallType?: boolean;
  showState?: boolean;
  showStatus?: boolean;
  className?: string;
  placeholder?: string;
}

export function CallsFilterBar({
  showCallType = true,
  showState = true,
  showStatus = false,
  className = "",
  placeholder = "Müşteri adı, tekne adı veya marina ara...",
}: CallsFilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const urlQ = searchParams.get("q") ?? "";
  const urlUrgency = searchParams.get("urgency") ?? "";
  const urlCallType = searchParams.get("call_type") ?? "";
  const urlRequestCategory = searchParams.get("request_category") ?? "";
  const urlState = searchParams.get("state") ?? "";
  const urlStatus = searchParams.get("status") ?? "";
  const urlMarina = searchParams.get("marina") ?? "";
  const urlDateFrom = searchParams.get("date_from") ?? "";
  const urlDateTo = searchParams.get("date_to") ?? "";

  const [prevUrlQ, setPrevUrlQ] = useState(urlQ);
  const [searchVal, setSearchVal] = useState(urlQ);

  // URL dışarıdan veya reset ile değiştiğinde yerel input değerini güncelle
  if (prevUrlQ !== urlQ) {
    setPrevUrlQ(urlQ);
    setSearchVal(urlQ);
  }

  // Tek bir veya birden fazla filtreyi URL parametrelerine uygula, page=1 yap
  const applyFilterChanges = useCallback(
    (updates: Record<string, string | null | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());

      for (const [key, val] of Object.entries(updates)) {
        if (val && val !== "all") {
          params.set(key, val);
        } else {
          params.delete(key);
        }
      }

      // Herhangi bir filtre değiştiğinde 1. sayfaya dön
      params.set("page", "1");

      const query = params.toString();
      startTransition(() => {
        router.push(query ? `${pathname}?${query}` : pathname);
      });
    },
    [pathname, router, searchParams],
  );

  // Arama metni için 300ms debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchVal.trim() !== urlQ) {
        applyFilterChanges({ q: searchVal.trim() || null });
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchVal, urlQ, applyFilterChanges]);

  // Aktif filtre kontrolü
  const hasActiveFilters = Boolean(
    urlQ ||
      urlUrgency ||
      urlCallType ||
      urlRequestCategory ||
      urlState ||
      urlStatus ||
      urlMarina ||
      urlDateFrom ||
      urlDateTo,
  );

  const handleReset = () => {
    setSearchVal("");
    const params = new URLSearchParams(searchParams.toString());
    const filterKeys = [
      "q",
      "urgency",
      "call_type",
      "request_category",
      "state",
      "marina",
      "date_from",
      "date_to",
      "status",
    ];
    filterKeys.forEach((key) => params.delete(key));
    params.set("page", "1");

    const query = params.toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname);
    });
  };

  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-xs space-y-3.5 transition-colors ${className}`}
    >
      {/* 1. Satır: Arama Kutusu ve Yükleme Göstergesi */}
      <div className="relative flex items-center">
        <label htmlFor="calls-filter-search-input" className="sr-only">
          Arama kutusu
        </label>
        <input
          id="calls-filter-search-input"
          type="text"
          value={searchVal}
          onChange={(e) => setSearchVal(e.target.value)}
          placeholder={placeholder}
          aria-label="Arama kutusu"
          className="w-full rounded-xl border border-slate-300 bg-slate-50/70 pl-10 pr-10 py-2.5 text-sm text-slate-900 placeholder-slate-400 shadow-xs focus:bg-white focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
        />
        {searchVal && (
          <button
            type="button"
            onClick={() => {
              setSearchVal("");
              applyFilterChanges({ q: null });
            }}
            aria-label="Aramayı temizle"
            className="absolute right-3.5 text-xs text-slate-400 hover:text-slate-600 p-1 rounded-full hover:bg-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
          >
            ✕
          </button>
        )}
      </div>

      {/* 2. Satır: Filtre Seçiciler */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-2.5 items-center">
        {/* Marina Seçici */}
        <div>
          <label className="sr-only" htmlFor="filter-marina">
            Marina
          </label>
          <select
            id="filter-marina"
            value={urlMarina || "all"}
            onChange={(e) => applyFilterChanges({ marina: e.target.value })}
            disabled={isPending}
            aria-label="Marina filtresi"
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
          >
            <option value="all">Tüm Marinalar</option>
            {MARINA_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        {/* Aciliyet Seçici */}
        <div>
          <label className="sr-only" htmlFor="filter-urgency">
            Aciliyet
          </label>
          <select
            id="filter-urgency"
            value={urlUrgency || "all"}
            onChange={(e) => applyFilterChanges({ urgency: e.target.value })}
            disabled={isPending}
            aria-label="Aciliyet seviyesi"
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
          >
            <option value="all">Aciliyet (Tümü)</option>
            {(Object.keys(URGENCY_LABELS) as Urgency[]).map((u) => (
              <option key={u} value={u}>
                {URGENCY_LABELS[u]}
              </option>
            ))}
          </select>
        </div>

        {/* Çağrı Tipi Seçici */}
        {showCallType && (
          <div>
            <label className="sr-only" htmlFor="filter-call-type">
              Çağrı Tipi
            </label>
            <select
              id="filter-call-type"
              value={urlCallType || "all"}
              onChange={(e) => applyFilterChanges({ call_type: e.target.value })}
              disabled={isPending}
              aria-label="Çağrı tipi"
              className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
            >
              <option value="all">Çağrı Tipi (Tümü)</option>
              {(Object.keys(CALL_TYPE_LABELS) as CallType[]).map((t) => (
                <option key={t} value={t}>
                  {CALL_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Talep Kategorisi Seçici */}
        <div>
          <label className="sr-only" htmlFor="filter-category">
            Talep Kategorisi
          </label>
          <select
            id="filter-category"
            value={urlRequestCategory || "all"}
            onChange={(e) => applyFilterChanges({ request_category: e.target.value })}
            disabled={isPending}
            aria-label="Talep kategorisi"
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
          >
            <option value="all">Kategori (Tümü)</option>
            {(Object.keys(REQUEST_CATEGORY_LABELS) as RequestCategory[]).map((c) => (
              <option key={c} value={c}>
                {REQUEST_CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>
        </div>

        {/* Analiz Durumu Seçici */}
        {showState && (
          <div>
            <label className="sr-only" htmlFor="filter-state">
              Analiz Durumu
            </label>
            <select
              id="filter-state"
              value={urlState || "all"}
              onChange={(e) => applyFilterChanges({ state: e.target.value })}
              disabled={isPending}
              aria-label="Analiz durumu"
              className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
            >
              <option value="all">Durum (Tümü)</option>
              {STATE_OPTIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* CRM İnceleme Durumu Seçici (#113) */}
        {showStatus && (
          <div>
            <label className="sr-only" htmlFor="filter-status">
              İnceleme Durumu
            </label>
            <select
              id="filter-status"
              value={urlStatus || "all"}
              onChange={(e) => applyFilterChanges({ status: e.target.value })}
              disabled={isPending}
              aria-label="İnceleme durumu"
              className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
            >
              <option value="all">İnceleme (Tümü)</option>
              <option value="bekliyor">⏳ Bekliyor</option>
              <option value="onaylandi">✓ Onaylandı</option>
              <option value="reddedildi">✕ Reddedildi</option>
            </select>
          </div>
        )}

        {/* Başlangıç Tarihi */}
        <div>
          <label className="sr-only" htmlFor="filter-date-from">
            Başlangıç Tarihi
          </label>
          <input
            id="filter-date-from"
            type="date"
            value={urlDateFrom}
            onChange={(e) => applyFilterChanges({ date_from: e.target.value || null })}
            disabled={isPending}
            title="Başlangıç tarihi (dahil)"
            aria-label="Başlangıç tarihi"
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
          />
        </div>

        {/* Bitiş Tarihi */}
        <div>
          <label className="sr-only" htmlFor="filter-date-to">
            Bitiş Tarihi
          </label>
          <input
            id="filter-date-to"
            type="date"
            value={urlDateTo}
            onChange={(e) => applyFilterChanges({ date_to: e.target.value || null })}
            disabled={isPending}
            title="Bitiş tarihi (dahil)"
            aria-label="Bitiş tarihi"
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 transition-colors"
          />
        </div>
      </div>

      {/* 3. Satır: Aktif Filtre İpuçları ve Temizle Butonu */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <div className="flex items-center gap-2">
          {isPending && (
            <span className="inline-flex items-center gap-1.5 text-xs text-sky-600 animate-pulse font-medium">
              <span>⏳</span> Filtreler uygulanıyor...
            </span>
          )}
        </div>

        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleReset}
            disabled={isPending}
            className="inline-flex items-center gap-1 px-3 py-1 text-xs font-semibold rounded-lg text-slate-600 hover:text-red-700 hover:bg-red-50 border border-slate-200 transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2"
          >
            <span>✕</span> Filtreleri Temizle
          </button>
        )}
      </div>
    </div>
  );
}
