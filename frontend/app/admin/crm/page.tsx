import { Suspense } from "react";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchCrmSuggestions } from "@/lib/api";
import type { CrmSuggestion } from "@/lib/types";
import { CrmSuggestionsSkeleton } from "@/components/skeletons";
import { CallsFilterBar } from "@/components/CallsFilterBar";
import { Pagination } from "@/components/Pagination";
import { EmptyState } from "@/components/EmptyState";
import { CrmSuggestionCard } from "@/components/crm";
import type { CallQueryFilters } from "@/lib/api/client";
import { clampPageSize, lastPageIfOutOfRange, listUrl } from "@/lib/list-query";

export const metadata = { title: "CRM Kayıt Önerileri | Miço Usta" };

interface CrmPageProps {
  searchParams?: Promise<{
    page?: string;
    page_size?: string;
    q?: string;
    urgency?: string;
    call_type?: string;
    request_category?: string;
    state?: string;
    status?: string;
    marina?: string;
    date_from?: string;
    date_to?: string;
  }>;
}

export default async function CrmPage({ searchParams }: CrmPageProps) {
  const params = searchParams ? await searchParams : {};
  const queryFilters: CallQueryFilters = {
    page: Math.max(1, Number(params?.page) || 1),
    page_size: clampPageSize(params?.page_size),
    q: params?.q?.trim() || undefined,
    urgency: params?.urgency?.trim() || undefined,
    call_type: params?.call_type?.trim() || undefined,
    request_category: params?.request_category?.trim() || undefined,
    state: params?.state?.trim() || undefined,
    status: params?.status?.trim() || undefined,
    marina: params?.marina?.trim() || undefined,
    date_from: params?.date_from?.trim() || undefined,
    date_to: params?.date_to?.trim() || undefined,
  };

  const hasActiveFilters = Boolean(
    queryFilters.q ||
      queryFilters.urgency ||
      queryFilters.request_category ||
      queryFilters.status ||
      queryFilters.marina ||
      queryFilters.date_from ||
      queryFilters.date_to,
  );

  // Bekleyen öneri sayısını bağımsız dinamik sorguyla al (#113)
  let pendingCount: number | null = null;
  try {
    const pendingRes = await fetchCrmSuggestions({ status: "bekliyor", page_size: 1 });
    pendingCount = pendingRes.total;
  } catch {
    // Servis kapalıysa fallback
  }

  const suspenseKey = JSON.stringify(queryFilters);

  // Hızlı durum sekmeleri için URL oluşturucu
  const getStatusTabUrl = (tabStatus?: string) => {
    const nextFilters: CallQueryFilters = {
      ...queryFilters,
      status: tabStatus,
      page: 1,
    };
    return listUrl("/admin/crm", nextFilters, 1);
  };

  const activeStatus = queryFilters.status ?? "all";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2.5">
            <span>CRM Kayıt ve Servis Emri Önerileri</span>
            {pendingCount !== null && (
              <span className="inline-flex items-center rounded-full bg-amber-100 dark:bg-amber-950/70 border border-amber-300 dark:border-amber-800 px-3 py-0.5 text-xs font-bold text-amber-800 dark:text-amber-300">
                ⏳ {pendingCount} Bekleyen Öneri
              </span>
            )}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Çağrılardan yapay zekâ tarafından otomatik çıkarılan 7 alanlı servis kayıtları
          </p>
        </div>
      </div>

      {/* Hızlı CRM Durum Sekmeleri (#113) */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
        <Link
          href={getStatusTabUrl(undefined)}
          className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 ${
            activeStatus === "all"
              ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 shadow-xs"
              : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          Tüm Kayıtlar
        </Link>
        <Link
          href={getStatusTabUrl("bekliyor")}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 ${
            activeStatus === "bekliyor"
              ? "bg-amber-600 text-white shadow-xs"
              : "text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 hover:bg-amber-100 dark:hover:bg-amber-900/60"
          }`}
        >
          <span>⏳</span>
          <span>Bekliyor</span>
          {pendingCount !== null && (
            <span className="ml-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-900 dark:bg-amber-900 dark:text-amber-100">
              {pendingCount}
            </span>
          )}
        </Link>
        <Link
          href={getStatusTabUrl("onaylandi")}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 ${
            activeStatus === "onaylandi"
              ? "bg-emerald-600 text-white shadow-xs"
              : "text-emerald-800 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 hover:bg-emerald-100 dark:hover:bg-emerald-900/60"
          }`}
        >
          <span>✓</span>
          <span>Onaylandı</span>
        </Link>
        <Link
          href={getStatusTabUrl("reddedildi")}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 ${
            activeStatus === "reddedildi"
              ? "bg-red-600 text-white shadow-xs"
              : "text-red-800 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 hover:bg-red-100 dark:hover:bg-red-900/60"
          }`}
        >
          <span>✕</span>
          <span>Reddedildi</span>
        </Link>
      </div>

      {/* Arama ve Filtre Kontrolleri (#108, #113) */}
      <CallsFilterBar
        showCallType={false}
        showState={false}
        showStatus={true}
        placeholder="Müşteri, tekne veya problem ara..."
      />

      {/* CRM Listesi ve Sayfalama */}
      <Suspense key={suspenseKey} fallback={<CrmSuggestionsSkeleton />}>
        <CrmContent filters={queryFilters} hasActiveFilters={hasActiveFilters} />
      </Suspense>
    </div>
  );
}

async function CrmContent({
  filters,
  hasActiveFilters,
}: {
  filters: CallQueryFilters;
  hasActiveFilters: boolean;
}) {
  let suggestions: CrmSuggestion[] = [];
  let total = 0;
  let page = filters.page ?? 1;
  let pageSize = filters.page_size ?? 20;
  let errorMsg: string | null = null;

  try {
    const pageData = await fetchCrmSuggestions(filters);
    suggestions = pageData.items;
    total = pageData.total;
    page = pageData.page;
    pageSize = pageData.page_size;
  } catch (err) {
    errorMsg = err instanceof Error ? err.message : "CRM önerileri yüklenemedi";
  }

  // Aralık dışı sayfa (kayıt var ama bu sayfa boş): son sayfaya git, "kayıt yok" deme.
  const lastPage = errorMsg ? null : lastPageIfOutOfRange(suggestions.length, total, page, pageSize);
  if (lastPage !== null) redirect(listUrl("/admin/crm", filters, lastPage));

  if (errorMsg) {
    return (
      <div className="rounded-xl border border-amber-200 dark:border-amber-800/60 bg-amber-50 dark:bg-amber-950/30 p-6 text-center shadow-xs">
        <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
          ⚠️ CRM kayıtları alınamadı: {errorMsg}
        </p>
        <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
          Servise ulaşılamıyor. Lütfen biraz sonra tekrar deneyin; sorun sürerse sistem yöneticinize başvurun.
        </p>
      </div>
    );
  }

  if (suggestions.length === 0) {
    if (hasActiveFilters) {
      return (
        <EmptyState
          title="Filtrelere uyan CRM önerisi bulunamadı"
          description="Arama teriminizi veya filtre seçimlerinizi değiştirerek tekrar deneyebilirsiniz."
          icon="🔍"
          isFiltered={true}
        />
      );
    }

    return (
      <EmptyState
        title="CRM Önerisi Bulunamadı"
        description="Henüz bekleyen bir CRM önerisi bulunmuyor."
        icon="⚓"
        isFiltered={false}
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">
          Sayfa {page} / {Math.max(1, Math.ceil(total / pageSize))}
        </span>
        <span className="rounded-lg bg-sky-50 dark:bg-sky-950/50 px-3 py-1.5 text-xs font-semibold text-sky-800 dark:text-sky-300 border border-sky-200 dark:border-sky-800">
          {total} Toplam Öneri
        </span>
      </div>

      {/* İnteraktif Kart Listesi (#113: Onayla, Reddet, Düzenle) */}
      <div className="grid grid-cols-1 gap-5">
        {suggestions.map((s) => (
          <CrmSuggestionCard key={s.callId} suggestion={s} variant="list" />
        ))}
      </div>

      {/* Sayfalama Kontrolleri (#108) */}
      <Pagination page={page} pageSize={pageSize} total={total} />
    </div>
  );
}
