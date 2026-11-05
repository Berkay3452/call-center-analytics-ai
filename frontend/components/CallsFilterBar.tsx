"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, useTransition, type ReactNode } from "react";
import {
  CALL_TYPE_LABELS,
  MARINA_OPTIONS,
  REQUEST_CATEGORY_LABELS,
  URGENCY_LABELS,
  type CallType,
  type RequestCategory,
  type Urgency,
} from "@/lib/types";
import { Button, Input, Select } from "@/components/ui";

const STATE_OPTIONS: { value: string; label: string }[] = [
  { value: "beklemede", label: "Sırada" },
  { value: "yaziya_cevriliyor", label: "Yazıya çevriliyor" },
  { value: "isleniyor", label: "İşleniyor" },
  { value: "tamam", label: "Tamamlandı" },
  { value: "kismi", label: "Kısmi" },
  { value: "basarisiz", label: "Başarısız" },
];

export interface CallsFilterBarProps {
  /** Sade görünüm: arama, marina, aciliyet, kategori ve durum (tarihler gizlenir). */
  compact?: boolean;
  crmLayout?: boolean;
  children?: ReactNode;
  showCallType?: boolean;
  showState?: boolean;
  showStatus?: boolean;
  className?: string;
  placeholder?: string;
}

export function CallsFilterBar({
  compact = false,
  crmLayout = false,
  children,
  showCallType = true,
  showState = true,
  showStatus = false,
  className = "",
  placeholder = "Müşteri adı, tekne adı veya marina ara...",
}: CallsFilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [dateError, setDateError] = useState<string | null>(null);
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

      const from = params.get("date_from");
      const to = params.get("date_to");
      if (from && to && to < from) {
        setDateError("Bitiş tarihi başlangıç tarihinden önce olamaz.");
        return;
      }
      setDateError(null);

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
    setDateError(null);
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

  const sel = compact || crmLayout ? "w-full min-w-0" : "w-auto min-w-40";
  const categoryFilter = (
    <>
      <label className="sr-only" htmlFor="filter-category">
        Talep Kategorisi
      </label>
      <Select
        id="filter-category"
        value={urlRequestCategory || "all"}
        onChange={(e) => applyFilterChanges({ request_category: e.target.value })}
        disabled={isPending}
        aria-label="Talep kategorisi"
        className={sel}
      >
        <option value="all">Kategori (tümü)</option>
        {(Object.keys(REQUEST_CATEGORY_LABELS) as RequestCategory[]).map((c) => (
          <option key={c} value={c}>
            {REQUEST_CATEGORY_LABELS[c]}
          </option>
        ))}
      </Select>
    </>
  );

  return (
    <div role="search" aria-label={crmLayout ? "CRM filtreleri" : "Çağrı filtreleri"} className={`rounded-xl border border-slate-200 bg-white p-4 ${crmLayout ? "grid grid-cols-1 items-end gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6" : "space-y-3"} ${className}`}>
      {children}
      <div className={crmLayout ? "contents" : compact ? "grid grid-cols-1 items-center gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6" : "flex flex-wrap items-center gap-2"}>
        <label htmlFor="calls-filter-search-input" className="sr-only">
          Arama kutusu
        </label>
        <div className={compact || crmLayout ? "relative min-w-0" : "relative min-w-60 flex-1"}>
          <Input
            id="calls-filter-search-input"
            type="search"
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            placeholder={placeholder}
            aria-label="Arama kutusu"
          />
        </div>

        <label className="sr-only" htmlFor="filter-marina">
          Marina
        </label>
        <Select
          id="filter-marina"
          value={urlMarina || "all"}
          onChange={(e) => applyFilterChanges({ marina: e.target.value })}
          disabled={isPending}
          aria-label="Marina filtresi"
          className={sel}
        >
          <option value="all">Tüm marinalar</option>
          {MARINA_OPTIONS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>

        <label className="sr-only" htmlFor="filter-urgency">
          Aciliyet
        </label>
        <Select
          id="filter-urgency"
          value={urlUrgency || "all"}
          onChange={(e) => applyFilterChanges({ urgency: e.target.value })}
          disabled={isPending}
          aria-label="Aciliyet seviyesi"
          className={sel}
        >
          <option value="all">Aciliyet (tümü)</option>
          {(Object.keys(URGENCY_LABELS) as Urgency[]).map((u) => (
            <option key={u} value={u}>
              {URGENCY_LABELS[u]}
            </option>
          ))}
        </Select>

        {showState && (
          <>
            <label className="sr-only" htmlFor="filter-state">
              Analiz Durumu
            </label>
            <Select
              id="filter-state"
              value={urlState || "all"}
              onChange={(e) => applyFilterChanges({ state: e.target.value })}
              disabled={isPending}
              aria-label="Analiz durumu"
              className={sel}
            >
              <option value="all">Durum (tümü)</option>
              {STATE_OPTIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </>
        )}

        {compact && categoryFilter}

        {hasActiveFilters && (
          <Button variant="ghost" onClick={handleReset} disabled={isPending}>
            Temizle
          </Button>
        )}
      </div>

      {!compact && (
        <div className={crmLayout ? "contents" : "flex flex-wrap items-center gap-2"}>
          {showCallType && (
            <>
              <label className="sr-only" htmlFor="filter-call-type">
                Çağrı Tipi
              </label>
              <Select
                id="filter-call-type"
                value={urlCallType || "all"}
                onChange={(e) => applyFilterChanges({ call_type: e.target.value })}
                disabled={isPending}
                aria-label="Çağrı tipi"
                className={sel}
              >
                <option value="all">Çağrı tipi (tümü)</option>
                {(Object.keys(CALL_TYPE_LABELS) as CallType[]).map((t) => (
                  <option key={t} value={t}>
                    {CALL_TYPE_LABELS[t]}
                  </option>
                ))}
              </Select>
            </>
          )}

          {categoryFilter}

          {showStatus && (
            <>
              <label className="sr-only" htmlFor="filter-status">
                İnceleme Durumu
              </label>
              <Select
                id="filter-status"
                value={urlStatus || "all"}
                onChange={(e) => applyFilterChanges({ status: e.target.value })}
                disabled={isPending}
                aria-label="İnceleme durumu"
                className={sel}
              >
                <option value="all">İnceleme (tümü)</option>
                <option value="bekliyor">Bekliyor</option>
                <option value="onaylandi">Onaylandı</option>
                <option value="reddedildi">Reddedildi</option>
              </Select>
            </>
          )}

          <div className="min-w-0">
            <label className="mb-1 block text-xs font-medium text-slate-700" htmlFor="filter-date-from">
              Başlangıç tarihi
            </label>
            <Input
              id="filter-date-from"
              type="date"
              lang="tr"
              placeholder="gg.aa.yyyy"
              value={urlDateFrom}
              max={urlDateTo || undefined}
              onChange={(e) => applyFilterChanges({ date_from: e.target.value || null })}
              disabled={isPending}
              aria-label="Başlangıç tarihi"
              aria-describedby="filter-date-format filter-date-error"
              className={crmLayout ? "w-full min-w-0" : "w-auto"}
            />
          </div>
          <div className="min-w-0">
            <label className="mb-1 block text-xs font-medium text-slate-700" htmlFor="filter-date-to">
              Bitiş tarihi
            </label>
            <Input
              id="filter-date-to"
              type="date"
              lang="tr"
              placeholder="gg.aa.yyyy"
              value={urlDateTo}
              min={urlDateFrom || undefined}
              onChange={(e) => applyFilterChanges({ date_to: e.target.value || null })}
              disabled={isPending}
              aria-label="Bitiş tarihi"
              aria-describedby="filter-date-format filter-date-error"
              className={crmLayout ? "w-full min-w-0" : "w-auto"}
            />
          </div>
          <p id="filter-date-format" className={crmLayout ? "col-span-full text-xs text-slate-500" : "text-xs text-slate-500"}>
            Tarih biçimi: gg.aa.yyyy
          </p>
          <p id="filter-date-error" role={dateError ? "alert" : undefined} className={crmLayout ? "col-span-full text-xs text-red-700 empty:hidden" : "text-xs text-red-700 empty:hidden"}>
            {dateError}
          </p>
        </div>
      )}
    </div>
  );
}
