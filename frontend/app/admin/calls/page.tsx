import { Suspense } from "react";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchCalls } from "@/lib/api";
import {
  ANALYSIS_STATUS_LABELS,
  ANALYSIS_STATUS_TONE,
  CALL_TYPE_LABELS,
  EMPTY_LABEL,
  labelOf,
  LOSS_REASON_LABELS,
  URGENCY_LABELS,
  type Call,
  type SalesOutcomeType,
  type Urgency,
} from "@/lib/types";
import {
  Badge,
  buttonClasses,
  PageHeader,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
  type Tone,
} from "@/components/ui";
import { CallsTableSkeleton } from "@/components/skeletons";
import { CallsFilterBar } from "@/components/CallsFilterBar";
import { Pagination } from "@/components/Pagination";
import { EmptyState } from "@/components/EmptyState";
import type { CallQueryFilters } from "@/lib/api/client";
import { clampPageSize, lastPageIfOutOfRange, listUrl } from "@/lib/list-query";

export const metadata = { title: "Çağrılar | Miço Usta" };

const URGENCY_TONE: Record<Urgency, Tone> = {
  acil: "danger",
  yuksek: "warning",
  normal: "brand",
  dusuk: "neutral",
};

const SALES_TONE: Record<SalesOutcomeType, { text: string; tone: Tone }> = {
  satisa_donustu: { text: "Satışa dönüştü", tone: "success" },
  kaybedildi: { text: "Kaybedildi", tone: "danger" },
  beklemede: { text: "Beklemede", tone: "warning" },
};

/** Satış durumu rozeti; kaybedilen çağrılarda kayıp nedeni de gösterilir. */
function SalesBadge({ sales }: { sales: Call["sales"] }) {
  const style = sales ? SALES_TONE[sales.outcome] : undefined;
  if (!sales || !style) {
    return <span className="text-xs text-slate-500">{EMPTY_LABEL}</span>;
  }
  const reason =
    sales.outcome === "kaybedildi" && sales.lossReason
      ? ` (${labelOf(LOSS_REASON_LABELS, sales.lossReason)})`
      : "";
  return (
    <Badge tone={style.tone}>
      {style.text}
      {reason}
    </Badge>
  );
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
      <PageHeader
        title="Çağrılar"
        description="Sesli görüşmeler ve yapay zekâ analiz sonuçları"
        actions={
          <Link href="/admin/calls/upload" className={buttonClasses("primary")}>
            Yeni çağrı yükle
          </Link>
        }
      />

      {/* Arama ve Filtre Kontrolleri (#108) */}
      <CallsFilterBar compact showCallType={false} />

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
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-center">
        <p className="text-sm font-semibold text-amber-800">
          Veriler alınırken bir sorun oluştu: {errorMsg}
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
      <Table>
        <THead>
          <tr>
            <Th>Müşteri</Th>
            <Th>Marina</Th>
            <Th>Kategori</Th>
            <Th>Aciliyet</Th>
            <Th>Durum</Th>
            <Th>Satış</Th>
            <Th>
              <span className="sr-only">Eylem</span>
            </Th>
          </tr>
        </THead>
        <TBody>
          {calls.map((call) => (
            <Tr key={call.id}>
              <Td className="whitespace-nowrap">
                <div className="font-semibold text-brand-800">{call.caller}</div>
                <div className="text-xs text-slate-500">{call.boatName || "Tekne belirtilmedi"}</div>
              </Td>
              <Td className="whitespace-nowrap">{call.location ?? EMPTY_LABEL}</Td>
              <Td className="whitespace-nowrap">{labelOf(CALL_TYPE_LABELS, call.callType)}</Td>
              <Td className="whitespace-nowrap">
                <Badge tone={call.urgency ? URGENCY_TONE[call.urgency] : "neutral"}>
                  {labelOf(URGENCY_LABELS, call.urgency)}
                </Badge>
              </Td>
              <Td className="whitespace-nowrap">
                {call.pendingState ? (
                  <Badge tone="brand">{call.pendingState === "beklemede" ? "Sırada" : "İşleniyor"}</Badge>
                ) : (
                  <Badge tone={ANALYSIS_STATUS_TONE[call.analysisStatus]}>
                    {labelOf(ANALYSIS_STATUS_LABELS, call.analysisStatus)}
                  </Badge>
                )}
              </Td>
              <Td className="whitespace-nowrap">
                <SalesBadge sales={call.sales} />
              </Td>
              <Td className="whitespace-nowrap text-right">
                <Link
                  href={`/admin/calls/${call.id}`}
                  className="font-medium text-brand-700 hover:underline"
                >
                  Detay
                </Link>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>

      {/* Sayfalama Kontrolleri (#108) */}
      <Pagination page={page} pageSize={pageSize} total={total} />
    </div>
  );
}
