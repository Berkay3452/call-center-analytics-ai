import { Suspense } from "react";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchCalls } from "@/lib/api";
import {
  ANALYSIS_STATUS_LABELS,
  CALL_TYPE_LABELS,
  EMPTY_LABEL,
  labelOf,
  LOSS_REASON_LABELS,
  URGENCY_LABELS,
  type AnalysisStatus,
  type Call,
  type CallType,
  type SalesOutcomeType,
  type Urgency,
} from "@/lib/types";
import { CallsTableSkeleton } from "@/components/skeletons";
import { CallsFilterBar } from "@/components/CallsFilterBar";
import { Pagination } from "@/components/Pagination";
import { EmptyState } from "@/components/EmptyState";
import type { CallQueryFilters } from "@/lib/api/client";
import { clampPageSize, lastPageIfOutOfRange, listUrl } from "@/lib/list-query";

export const metadata = { title: "Çağrılar | Miço Usta" };

const URGENCY_BADGE: Record<Urgency, string> = {
  acil: "bg-red-100 text-red-700 border-red-300 font-bold",
  yuksek: "bg-orange-100 text-orange-700 border-orange-200",
  normal: "bg-blue-50 text-blue-700 border-blue-200",
  dusuk: "bg-gray-100 text-gray-600 border-gray-200",
};

const CALL_TYPE_BADGE: Record<CallType, string> = {
  acil: "bg-red-50 text-red-700",
  servis: "bg-sky-50 text-sky-700",
  teklif: "bg-purple-50 text-purple-700",
  yeni_musteri: "bg-emerald-50 text-emerald-700",
  bilgi: "bg-gray-50 text-gray-600",
};

const ANALYSIS_STATUS_BADGE: Record<AnalysisStatus, string> = {
  tamam: "bg-emerald-50 text-emerald-700 border-emerald-200",
  kismi: "bg-amber-50 text-amber-700 border-amber-200",
  basarisiz: "bg-red-50 text-red-700 border-red-200",
};

const ANALYSIS_STATUS_ICON: Record<AnalysisStatus, string> = {
  tamam: "✓",
  kismi: "⚠",
  basarisiz: "✕",
};

const SALES_BADGE: Record<SalesOutcomeType, { icon: string; text: string; cls: string }> = {
  satisa_donustu: {
    icon: "✓",
    text: "Satışa Dönüştü",
    cls: "font-semibold text-emerald-700 bg-emerald-50",
  },
  kaybedildi: {
    icon: "✕",
    text: "Kaybedildi",
    cls: "font-semibold text-red-700 bg-red-50",
  },
  beklemede: {
    icon: "⏳",
    text: "Beklemede",
    cls: "font-medium text-amber-700 bg-amber-50",
  },
};

/** Satış durumu rozeti; kaybedilen çağrılarda kayıp nedeni de gösterilir ("Kaybedildi (Fiyat...)"). */
function SalesBadge({ sales }: { sales: Call["sales"] }) {
  const style = sales ? SALES_BADGE[sales.outcome] : undefined;
  if (!sales || !style) {
    return <span className="text-xs text-slate-500">{EMPTY_LABEL}</span>;
  }
  const reason =
    sales.outcome === "kaybedildi" && sales.lossReason
      ? ` (${labelOf(LOSS_REASON_LABELS, sales.lossReason)})`
      : "";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${style.cls}`}>
      {style.icon} {style.text}
      {reason}
    </span>
  );
}

function formatDuration(sec: number): string {
  if (sec === 0) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

interface CallsPageProps {
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

export default async function CallsPage({ searchParams }: CallsPageProps) {
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
      queryFilters.call_type ||
      queryFilters.request_category ||
      queryFilters.state ||
      queryFilters.marina ||
      queryFilters.date_from ||
      queryFilters.date_to,
  );

  const suspenseKey = JSON.stringify(queryFilters);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Çağrılar &amp; Analizler</h1>
          <p className="text-sm text-gray-500">
            Tüm marinalardan gelen sesli görüşmeler ve yapay zekâ analiz sonuçları
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/admin/calls/upload"
            className="inline-flex items-center gap-2 rounded-xl bg-sky-700 px-4 py-2.5 text-sm font-bold text-white shadow-xs hover:bg-sky-800 active:scale-[0.98] transition-all focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
          >
            <span aria-hidden="true">🎙️</span>
            <span>+ Yeni Çağrı Yükle</span>
          </Link>
        </div>
      </div>

      {/* Arama ve Filtre Kontrolleri (#108) */}
      <CallsFilterBar />

      {/* Çağrı Listesi Tablosu ve Sayfalama */}
      <Suspense key={suspenseKey} fallback={<CallsTableSkeleton />}>
        <CallsListContent filters={queryFilters} hasActiveFilters={hasActiveFilters} />
      </Suspense>
    </div>
  );
}

async function CallsListContent({
  filters,
  hasActiveFilters,
}: {
  filters: CallQueryFilters;
  hasActiveFilters: boolean;
}) {
  let calls: Call[] = [];
  let total = 0;
  let page = filters.page ?? 1;
  let pageSize = filters.page_size ?? 20;
  let errorMsg: string | null = null;

  try {
    const pageData = await fetchCalls(filters);
    calls = pageData.items;
    total = pageData.total;
    page = pageData.page;
    pageSize = pageData.page_size;
  } catch (err) {
    errorMsg = err instanceof Error ? err.message : "Çağrılar yüklenemedi";
  }

  // Aralık dışı sayfa (kayıt var ama bu sayfa boş): son sayfaya git, "kayıt yok" deme.
  const lastPage = errorMsg ? null : lastPageIfOutOfRange(calls.length, total, page, pageSize);
  if (lastPage !== null) redirect(listUrl("/admin/calls", filters, lastPage));

  if (errorMsg) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-center shadow-xs">
        <p className="text-sm font-semibold text-amber-800">
          ⚠️ Veriler alınırken bir sorun oluştu: {errorMsg}
        </p>
        <p className="mt-1 text-xs text-amber-700">
          Servise ulaşılamıyor. Lütfen biraz sonra tekrar deneyin; sorun sürerse sistem yöneticinize başvurun.
        </p>
      </div>
    );
  }

  if (calls.length === 0) {
    if (hasActiveFilters) {
      return (
        <EmptyState
          title="Filtrelere uyan çağrı bulunamadı"
          description="Arama kriterlerinizi değiştirerek veya filtreleri temizleyerek tekrar deneyebilirsiniz."
          isFiltered={true}
        />
      );
    }

    return (
      <EmptyState
        title="Çağrı Bulunamadı"
        description="Henüz sisteme kaydedilmiş bir çağrı bulunmuyor."
        isFiltered={false}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-xs">
        <table className="min-w-full divide-y divide-gray-200 text-left text-xs">
          <thead className="bg-gray-50">
            <tr>
              {["Arayan & Tekne", "Marina", "Çağrı Tipi", "Süre", "Aciliyet", "Analiz Durumu", "Satış Durumu", ""].map((h) => (
                <th
                  key={h}
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {calls.map((call) => (
              <tr key={call.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="text-sm font-semibold text-gray-900">{call.caller}</div>
                  <div className="text-xs text-gray-500">
                    {call.boatName || "Tekne belirtilmedi"}
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                  {call.location ?? EMPTY_LABEL}
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${call.callType ? CALL_TYPE_BADGE[call.callType] : "bg-gray-50 text-gray-600"}`}
                  >
                    {labelOf(CALL_TYPE_LABELS, call.callType)}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                  {formatDuration(call.durationSec)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span
                    className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${call.urgency ? URGENCY_BADGE[call.urgency] : "bg-gray-100 text-gray-600 border-gray-200"}`}
                  >
                    {call.urgency === "acil" && <span className="mr-1">🚨</span>}
                    {labelOf(URGENCY_LABELS, call.urgency)}
                  </span>
                </td>
                {/* Analiz Durumu Sütunu */}
                <td className="px-4 py-3 whitespace-nowrap">
                  {call.pendingState ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-2.5 py-0.5 text-xs font-semibold text-sky-700">
                      ⏳ {call.pendingState === "beklemede" ? "Sırada" : "İşleniyor"}
                    </span>
                  ) : (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${ANALYSIS_STATUS_BADGE[call.analysisStatus]}`}
                    >
                      {ANALYSIS_STATUS_ICON[call.analysisStatus]}{" "}
                      {labelOf(ANALYSIS_STATUS_LABELS, call.analysisStatus)}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm whitespace-nowrap">
                  <SalesBadge sales={call.sales} />
                </td>
                <td className="px-4 py-3 text-right text-sm whitespace-nowrap">
                  <Link
                    href={`/admin/calls/${call.id}`}
                    className="font-medium text-sky-700 hover:text-sky-800 hover:underline px-2 py-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
                  >
                    Detay &amp; CRM →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Sayfalama Kontrolleri (#108) */}
      <Pagination page={page} pageSize={pageSize} total={total} />
    </div>
  );
}
