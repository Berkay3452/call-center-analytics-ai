import { Suspense } from "react";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchCrmSuggestions } from "@/lib/api";
import {
  EMPTY_LABEL,
  labelOf,
  NEXT_ACTION_LABELS,
  REQUEST_CATEGORY_LABELS,
  SERVICE_MODE_LABELS,
  URGENCY_LABELS,
  type CrmSuggestion,
  type Urgency,
} from "@/lib/types";
import { CrmSuggestionsSkeleton } from "@/components/skeletons";
import { CallsFilterBar } from "@/components/CallsFilterBar";
import { Pagination } from "@/components/Pagination";
import { EmptyState } from "@/components/EmptyState";
import type { CallQueryFilters } from "@/lib/api/client";
import { clampPageSize, lastPageIfOutOfRange, listUrl } from "@/lib/list-query";

export const metadata = { title: "CRM Kayıt Önerileri | Miço Usta" };

const URGENCY_BADGE: Record<Urgency, string> = {
  acil: "bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-300 dark:border-red-800 font-bold",
  yuksek: "bg-orange-100 dark:bg-orange-950/60 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-800",
  normal: "bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800",
  dusuk: "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700",
};

interface CrmPageProps {
  searchParams?: Promise<{
    page?: string;
    page_size?: string;
    q?: string;
    urgency?: string;
    call_type?: string;
    request_category?: string;
    state?: string;
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
    marina: params?.marina?.trim() || undefined,
    date_from: params?.date_from?.trim() || undefined,
    date_to: params?.date_to?.trim() || undefined,
  };

  const hasActiveFilters = Boolean(
    queryFilters.q ||
      queryFilters.urgency ||
      queryFilters.request_category ||
      queryFilters.marina ||
      queryFilters.date_from ||
      queryFilters.date_to,
  );

  const suspenseKey = JSON.stringify(queryFilters);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            CRM Kayıt ve Servis Emri Önerileri
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Çağrılardan yapay zekâ tarafından otomatik çıkarılan 7 alanlı servis kayıtları
          </p>
        </div>
      </div>

      {/* Arama ve Filtre Kontrolleri (#108) */}
      <CallsFilterBar
        showCallType={false}
        showState={false}
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

      <div className="grid grid-cols-1 gap-5">
        {suggestions.map((s) => (
          <div
            key={s.callId}
            className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs transition-all hover:border-sky-300 dark:hover:border-sky-500"
          >
            {/* Üst Kısım: Arayan, Tekne, Aciliyet ve Buton */}
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">{s.caller}</h2>
                  {s.boatName && (
                    <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                      • {s.boatName}
                    </span>
                  )}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <span>📍 {s.location ?? EMPTY_LABEL}</span>
                  <span>•</span>
                  <span>Çağrı ID: {s.callId}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${s.urgency ? URGENCY_BADGE[s.urgency] : "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700"}`}
                >
                  {s.urgency === "acil" && <span className="mr-1">🚨</span>}
                  {labelOf(URGENCY_LABELS, s.urgency)}
                </span>
                <Link
                  href={`/admin/calls/${s.callId}`}
                  className="rounded-lg bg-sky-700 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-sky-800 transition-colors shadow-xs focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  İncele &amp; Onayla →
                </Link>
              </div>
            </div>

            {/* 7 CRM Alanı Izgara Görünümü */}
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-transparent dark:border-slate-800/50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  1. Müşteri Talebi (Kategori)
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {labelOf(REQUEST_CATEGORY_LABELS, s.requestCategory)}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-transparent dark:border-slate-800/50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  2. Lokasyon / Marina
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {s.location ?? EMPTY_LABEL}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-transparent dark:border-slate-800/50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  3. Problem Tanımı
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200 line-clamp-2">
                  {s.problem ?? EMPTY_LABEL}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-transparent dark:border-slate-800/50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  4. Hizmet Biçimi
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {labelOf(SERVICE_MODE_LABELS, s.serviceMode)}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-transparent dark:border-slate-800/50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  6. Potansiyel İş
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {s.potentialJob ?? EMPTY_LABEL}
                </p>
              </div>

              <div className="rounded-lg bg-sky-50 dark:bg-sky-950/40 border border-sky-100 dark:border-sky-900/60 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-sky-700 dark:text-sky-400">
                  7. Sonraki Aksiyon / Servis Emri
                </span>
                <p className="mt-0.5 text-xs font-bold text-sky-900 dark:text-sky-200">
                  {labelOf(NEXT_ACTION_LABELS, s.nextAction)}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Sayfalama Kontrolleri (#108) */}
      <Pagination page={page} pageSize={pageSize} total={total} />
    </div>
  );
}
