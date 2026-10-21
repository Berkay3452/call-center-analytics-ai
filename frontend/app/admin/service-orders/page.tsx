import { Suspense } from "react";
import { redirect } from "next/navigation";
import Link from "next/link";
import { getServiceOrders } from "@/lib/api/client";
import type { ServiceOrderFilters } from "@/lib/api/types";
import {
  SERVICE_ORDER_STATUS_LABELS,
  type ServiceOrderStatus,
} from "@/lib/types";
import { ServiceOrdersTableSkeleton } from "@/components/skeletons";
import { Pagination } from "@/components/Pagination";
import { EmptyState } from "@/components/EmptyState";
import {
  ServiceOrdersTable,
  ServiceOrdersFilterBar,
} from "@/components/service-orders";
import { clampPageSize, lastPageIfOutOfRange, listUrl } from "@/lib/list-query";

export const metadata = { title: "Servis Emirleri | Miço Usta" };

interface ServiceOrdersPageProps {
  searchParams?: Promise<{
    page?: string;
    page_size?: string;
    status?: string;
    marina?: string;
    q?: string;
    date_from?: string;
    date_to?: string;
  }>;
}

const STATUS_TABS: { value: string; label: string; icon: string }[] = [
  { value: "all", label: "Tümü", icon: "📋" },
  { value: "yeni_atandi", label: SERVICE_ORDER_STATUS_LABELS.yeni_atandi, icon: "📥" },
  { value: "kesifte", label: SERVICE_ORDER_STATUS_LABELS.kesifte, icon: "🔍" },
  { value: "onaylandi", label: SERVICE_ORDER_STATUS_LABELS.onaylandi, icon: "✅" },
  { value: "devam_ediyor", label: SERVICE_ORDER_STATUS_LABELS.devam_ediyor, icon: "⚙️" },
  { value: "tamamlandi", label: SERVICE_ORDER_STATUS_LABELS.tamamlandi, icon: "🎉" },
];

export default async function ServiceOrdersPage({
  searchParams,
}: ServiceOrdersPageProps) {
  const params = searchParams ? await searchParams : {};
  const queryFilters: ServiceOrderFilters = {
    page: Math.max(1, Number(params?.page) || 1),
    page_size: clampPageSize(params?.page_size),
    status:
      params?.status && params.status !== "all"
        ? (params.status as ServiceOrderStatus)
        : undefined,
    marina: params?.marina?.trim() || undefined,
    q: params?.q?.trim() || undefined,
    date_from: params?.date_from?.trim() || undefined,
    date_to: params?.date_to?.trim() || undefined,
  };

  const hasActiveFilters = Boolean(
    queryFilters.status ||
      queryFilters.marina ||
      queryFilters.q ||
      queryFilters.date_from ||
      queryFilters.date_to,
  );

  const activeStatus = params?.status || "all";

  // Durum sekmesi için URL oluşturucu
  const getTabUrl = (statusValue: string) => {
    const nextFilters = {
      ...queryFilters,
      status: statusValue === "all" ? undefined : statusValue,
      page: 1,
    };
    return listUrl("/admin/service-orders", nextFilters, 1);
  };

  const suspenseKey = JSON.stringify(queryFilters);

  return (
    <div className="space-y-6">
      {/* Başlık ve Açıklama */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2.5">
            <span>Servis Emirleri</span>
            <span className="inline-flex items-center rounded-full bg-sky-100 dark:bg-sky-950/70 border border-sky-300 dark:border-sky-800 px-3 py-0.5 text-xs font-bold text-sky-800 dark:text-sky-300">
              İş Akışı & Takip
            </span>
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            CRM önerilerinden onaylanıp servis sürecine aktarılan iş emirleri
          </p>
        </div>

        <Link
          href="/admin/crm"
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 shadow-xs hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
        >
          <span>💡</span>
          <span>CRM Önerilerini Gör</span>
        </Link>
      </div>

      {/* Durum Sekmeleri */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
        {STATUS_TABS.map((tab) => {
          const isActive = activeStatus === tab.value;
          return (
            <Link
              key={tab.value}
              href={getTabUrl(tab.value)}
              className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 ${
                isActive
                  ? "bg-sky-700 text-white shadow-xs dark:bg-sky-600"
                  : "bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </Link>
          );
        })}
      </div>

      {/* Filtreleme Çubuğu */}
      <ServiceOrdersFilterBar />

      {/* Sayfalı Liste Alanı */}
      <Suspense key={suspenseKey} fallback={<ServiceOrdersTableSkeleton />}>
        <ServiceOrdersListContent
          filters={queryFilters}
          hasActiveFilters={hasActiveFilters}
        />
      </Suspense>
    </div>
  );
}

interface ServiceOrdersListContentProps {
  filters: ServiceOrderFilters;
  hasActiveFilters: boolean;
}

async function ServiceOrdersListContent({
  filters,
  hasActiveFilters,
}: ServiceOrdersListContentProps) {
  let data;
  let errorMsg: string | null = null;

  try {
    data = await getServiceOrders(filters);
  } catch (err: unknown) {
    errorMsg = err instanceof Error ? err.message : "Servis emirleri alınamadı.";
  }

  if (errorMsg) {
    return (
      <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 p-6 text-center shadow-xs">
        <p className="text-sm font-semibold text-red-800 dark:text-red-200">
          ⚠️ {errorMsg}
        </p>
        <p className="mt-1 text-xs text-red-700 dark:text-red-300">
          Servise ulaşılamıyor. Lütfen sayfayı yenileyin veya sistem yöneticinize danışın.
        </p>
      </div>
    );
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const page = data?.page ?? 1;
  const pageSize = data?.page_size ?? 20;

  // Sayfa aralık kontrolü: kayıt var ama istenen sayfa boş ise son sayfaya yönlendir (#108 kuralı)
  const lastPage = lastPageIfOutOfRange(items.length, total, page, pageSize);
  if (lastPage !== null) {
    redirect(listUrl("/admin/service-orders", filters, lastPage));
  }

  if (items.length === 0) {
    if (hasActiveFilters) {
      return (
        <EmptyState
          title="Filtrelere uyan servis emri bulunamadı"
          description="Arama kriterlerinizi değiştirerek veya filtreleri temizleyerek tekrar deneyebilirsiniz."
          icon="🔍"
          isFiltered={true}
        />
      );
    }

    // Hiç onaylanmış servis emri yoksa CRM sayfasına yönlendirme kartı (#114 GEREKSİNİMİ)
    return (
      <EmptyState
        title="Henüz onaylanmış öneri yok"
        description="CRM önerileri sayfasında yapay zekâ tarafından çıkarılan servis kayıtlarını onaylayarak burada servis emrine dönüştürebilirsiniz."
        icon="📋"
        isFiltered={false}
        actionLabel="CRM Önerilerine Git"
        actionHref="/admin/crm"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">
          Sayfa {page} / {Math.max(1, Math.ceil(total / pageSize))}
        </span>
        <span className="rounded-lg bg-sky-50 dark:bg-sky-950/50 px-3 py-1.5 text-xs font-semibold text-sky-800 dark:text-sky-300 border border-sky-200 dark:border-sky-800">
          {total} Toplam Servis Emri
        </span>
      </div>

      {/* Tablo */}
      <ServiceOrdersTable orders={items} />

      {/* Sayfalama */}
      <Pagination page={page} pageSize={pageSize} total={total} />
    </div>
  );
}
