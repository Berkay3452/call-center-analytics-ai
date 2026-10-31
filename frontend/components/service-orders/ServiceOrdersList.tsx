"use client";

import { useState } from "react";
import Link from "next/link";
import type { ServiceOrderListItem } from "@/lib/api/types";
import {
  formatOrderCode,
  labelOf,
  REQUEST_CATEGORY_LABELS,
  SERVICE_ORDER_STATUS_LABELS,
  type RequestCategory,
  type ServiceOrderStatus,
} from "@/lib/types";
import { Badge, Button, Card, buttonClasses, cn, type Tone } from "@/components/ui";
import { TONE_BAR } from "@/components/ui/tone";
import { ServiceOrderDetailModal } from "./ServiceOrderDetailModal";
import { ServiceOrderStatusControl } from "./ServiceOrderStatusControl";

const STATUS_TONE: Record<ServiceOrderStatus, Tone> = {
  yeni_atandi: "brand",
  kesifte: "warning",
  onaylandi: "accent",
  devam_ediyor: "brand",
  tamamlandi: "success",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("tr-TR");
}

/** Servis emirleri kart listesi: nokta + başlık, alt bilgi, açıklama, etiketler, sağda durum ve eylemler. */
export function ServiceOrdersList({ orders }: { orders: ServiceOrderListItem[] }) {
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  // Durum ilerletilince rozet ve nokta hemen güncellensin
  const [statusOverride, setStatusOverride] = useState<Record<string, ServiceOrderStatus>>({});

  return (
    <>
      <ul className="space-y-3">
        {orders.map((order) => {
          const category = labelOf(REQUEST_CATEGORY_LABELS, order.category as RequestCategory);
          const status = statusOverride[order.id] ?? order.status;
          const tone = STATUS_TONE[status] ?? "neutral";
          const meta = [order.customer_name, formatDate(order.created_at), order.craftsman_name ?? "Usta atanmadı"];
          const tags = [category, order.marina, order.boat_model].filter((t): t is string => Boolean(t));

          return (
            <li key={order.id}>
              <Card className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 gap-3">
                  <span
                    aria-hidden="true"
                    className={cn("mt-2 h-2.5 w-2.5 shrink-0 rounded-full", TONE_BAR[tone])}
                  />
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-brand-800">
                      {category} — {order.boat_name}
                    </h2>
                    <p className="mt-0.5 text-sm text-slate-500">
                      {meta.join(" · ")}
                      <span className="ml-2 font-mono text-xs">{formatOrderCode(order.id)}</span>
                    </p>
                    {order.description && (
                      <p className="mt-2 text-sm text-slate-700">{order.description}</p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {tags.map((tag) => (
                        <Badge key={tag}>{tag}</Badge>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-start gap-3 sm:items-end">
                  <Badge tone={tone}>{SERVICE_ORDER_STATUS_LABELS[status] ?? status}</Badge>
                  <ServiceOrderStatusControl
                    orderId={order.id}
                    currentStatus={status}
                    onStatusUpdated={(u) => setStatusOverride((prev) => ({ ...prev, [order.id]: u.status }))}
                    compact
                  />
                  <div className="flex items-center gap-2">
                    {order.source_call_id && (
                      <Link
                        href={`/admin/calls/${order.source_call_id}`}
                        className={buttonClasses("ghost", "sm")}
                      >
                        Kaynak çağrı
                      </Link>
                    )}
                    <Button variant="secondary" size="sm" onClick={() => setSelectedOrderId(order.id)}>
                      Detay
                    </Button>
                  </div>
                </div>
              </Card>
            </li>
          );
        })}
      </ul>

      {selectedOrderId && (
        <ServiceOrderDetailModal
          orderId={selectedOrderId}
          onClose={() => setSelectedOrderId(null)}
          onStatusUpdated={(u) => setStatusOverride((prev) => ({ ...prev, [u.id]: u.status }))}
        />
      )}
    </>
  );
}
