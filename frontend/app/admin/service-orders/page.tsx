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
import { PageHeader, buttonClasses } from "@/components/ui";
import {
  ServiceOrdersList,
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

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "all", label: "Tümü" },
  { value: "yeni_atandi", label: SERVICE_ORDER_STATUS_LABELS.yeni_atandi },
  { value: "kesifte", label: SERVICE_ORDER_STATUS_LABELS.kesifte },
  { value: "onaylandi", label: SERVICE_ORDER_STATUS_LABELS.onaylandi },
  { value: "devam_ediyor", label: SERVICE_ORDER_STATUS_LABELS.devam_ediyor },
  { value: "tamamlandi", label: SERVICE_ORDER_STATUS_LABELS.tamamlandi },
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
    <div>
      <PageHeader
        title="Servis Emirleri"
        description="CRM önerilerinden onaylanıp servise aktarılan iş emirleri."
        actions={
          <Link href="/admin/crm" className={buttonClasses("secondary", "sm")}>
            CRM önerilerine git
          </Link>
        }
      />

      <nav aria-label="Servis emri durumu" className="mb-4 flex flex-wrap gap-1 border-b border-slate-200 pb-3">
        {STATUS_TABS.map((tab) => {
          const isActive = activeStatus === tab.value;
          return (
            <Link
              key={tab.value}
              href={getTabUrl(tab.value)}
              aria-current={isActive ? "page" : undefined}
              className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-brand-700 text-white"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

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
      <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-sm font-medium text-red-800">{errorMsg}</p>
        <p className="mt-1 text-xs text-red-700">
          Servise ulaşılamıyor. Sayfayı yenileyin veya sistem yöneticinize danışın.
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
          isFiltered={true}
        />
      );
    }

    // Hiç onaylanmış servis emri yoksa CRM sayfasına yönlendirme kartı (#114 GEREKSİNİMİ)
    return (
      <EmptyState
        title="Henüz onaylanmış öneri yok"
        description="CRM önerileri sayfasında yapay zekâ tarafından çıkarılan servis kayıtlarını onaylayarak burada servis emrine dönüştürebilirsiniz."
        isFiltered={false}
        actionLabel="CRM Önerilerine Git"
        actionHref="/admin/crm"
      />
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        {total} servis emri · Sayfa {page} / {Math.max(1, Math.ceil(total / pageSize))}
      </p>

      <ServiceOrdersList orders={items} />

      {/* Sayfalama */}
      <Pagination page={page} pageSize={pageSize} total={total} />
    </div>
  );
}
