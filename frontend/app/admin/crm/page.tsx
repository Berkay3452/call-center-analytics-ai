import { Suspense } from "react";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchCrmSuggestions } from "@/lib/api";
import type { CrmSuggestion } from "@/lib/types";
import { CrmSuggestionsSkeleton } from "@/components/skeletons";
import { CallsFilterBar } from "@/components/CallsFilterBar";
import { Pagination } from "@/components/Pagination";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/ui";
import { CrmSuggestionCard } from "@/components/crm";
import type { CallQueryFilters } from "@/lib/api/client";
import { clampPageSize, lastPageIfOutOfRange, listUrl } from "@/lib/list-query";

export const metadata = { title: "CRM Önerileri | Miço Usta" };

type TabStatus = "bekliyor" | "onaylandi" | "reddedildi";
const TABS: { status: TabStatus; label: string }[] = [
  { status: "bekliyor", label: "Bekliyor" },
  { status: "onaylandi", label: "Onaylandı" },
  { status: "reddedildi", label: "Reddedildi" },
];
const EMPTY_TEXT: Record<TabStatus, string> = {
  bekliyor: "Bekleyen öneri yok. Yeni çağrılar analiz edildikçe burada görünür.",
  onaylandi: "Henüz onaylanmış öneri yok.",
  reddedildi: "Henüz reddedilmiş öneri yok.",
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
    status: TABS.some((t) => t.status === params?.status) ? params?.status : "bekliyor",
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

  // Sekme sayıları (durum başına toplam kayıt)
  const counts: Record<TabStatus, number | null> = { bekliyor: null, onaylandi: null, reddedildi: null };
  await Promise.all(
    TABS.map(async (tab) => {
      try {
        counts[tab.status] = (await fetchCrmSuggestions({ status: tab.status, page_size: 1 })).total;
      } catch {
        // Servis kapalıysa sayı gösterilmez
      }
    }),
  );

  const suspenseKey = JSON.stringify(queryFilters);
  const activeStatus = queryFilters.status as TabStatus;

  const getStatusTabUrl = (tabStatus: TabStatus) =>
    listUrl("/admin/crm", { ...queryFilters, status: tabStatus, page: 1 }, 1);

  return (
    <div>
      <PageHeader
        title="CRM Önerileri"
        description="Çağrılardan çıkarılan servis kayıtlarını inceleyin; onaylarsanız servis emri açılır."
      />

      <nav aria-label="Öneri durumu" className="mb-4 flex flex-wrap gap-1 border-b border-slate-200 pb-3">
        {TABS.map((tab) => {
          const active = activeStatus === tab.status;
          return (
            <Link
              key={tab.status}
              href={getStatusTabUrl(tab.status)}
              aria-current={active ? "page" : undefined}
              className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-brand-700 text-white"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {tab.label}
              {counts[tab.status] !== null && <span className="ml-1.5 opacity-80">({counts[tab.status]})</span>}
            </Link>
          );
        })}
      </nav>

      {/* Arama ve Filtre Kontrolleri (#108, #113) */}
      <CallsFilterBar
        showCallType={false}
        showState={false}
        showStatus={false}
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
      <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-center">
        <p className="text-sm font-medium text-amber-800">CRM önerileri alınamadı: {errorMsg}</p>
        <p className="mt-1 text-xs text-amber-700">
          Servise ulaşılamıyor. Biraz sonra tekrar deneyin; sorun sürerse sistem yöneticinize başvurun.
        </p>
      </div>
    );
  }

  if (suggestions.length === 0) {
    return hasActiveFilters ? (
      <EmptyState
        title="Filtrelere uyan öneri bulunamadı"
        description="Arama terimini veya filtreleri değiştirip tekrar deneyin."
        isFiltered={true}
      />
    ) : (
      <EmptyState
        title="Öneri yok"
        description={EMPTY_TEXT[filters.status as TabStatus]}
        isFiltered={false}
      />
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        {total} öneri · Sayfa {page} / {Math.max(1, Math.ceil(total / pageSize))}
      </p>

      <div className="grid grid-cols-1 gap-4">
        {suggestions.map((s) => (
          <CrmSuggestionCard key={s.callId} suggestion={s} variant="list" />
        ))}
      </div>

      <Pagination page={page} pageSize={pageSize} total={total} />
    </div>
  );
}
