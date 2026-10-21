"use client";

import React, { useState } from "react";
import Link from "next/link";
import type { ServiceOrderDetail, ServiceOrderListItem } from "@/lib/api/types";
import {
  formatOrderCode,
  labelOf,
  REQUEST_CATEGORY_LABELS,
  type RequestCategory,
} from "@/lib/types";
import { ServiceOrderStatusBadge } from "./ServiceOrderStatusBadge";
import { ServiceOrderDetailModal } from "./ServiceOrderDetailModal";

interface ServiceOrdersTableProps {
  orders: ServiceOrderListItem[];
  onOrderUpdated?: (updated: ServiceOrderDetail) => void;
}

export function ServiceOrdersTable({
  orders,
  onOrderUpdated,
}: ServiceOrdersTableProps) {
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleOpenDetail = (id: string) => {
    setSelectedOrderId(id);
    setIsModalOpen(true);
  };

  const handleCloseDetail = () => {
    setIsModalOpen(false);
    setSelectedOrderId(null);
  };

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/75 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 font-bold uppercase tracking-wider">
              <th scope="col" className="px-4 py-3.5 whitespace-nowrap">
                Kod
              </th>
              <th scope="col" className="px-4 py-3.5 whitespace-nowrap">
                Müşteri
              </th>
              <th scope="col" className="px-4 py-3.5 whitespace-nowrap">
                Tekne & Marina
              </th>
              <th scope="col" className="px-4 py-3.5 whitespace-nowrap">
                Kategori
              </th>
              <th scope="col" className="px-4 py-3.5">
                Açıklama
              </th>
              <th scope="col" className="px-4 py-3.5 whitespace-nowrap">
                Durum
              </th>
              <th scope="col" className="px-4 py-3.5 whitespace-nowrap">
                Kaynak Çağrı
              </th>
              <th scope="col" className="px-4 py-3.5 text-right whitespace-nowrap">
                İşlem
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
            {orders.map((order) => {
              const code = formatOrderCode(order.id);
              const categoryLabel = labelOf(
                REQUEST_CATEGORY_LABELS,
                order.category as RequestCategory,
              );

              return (
                <tr
                  key={order.id}
                  className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors group cursor-pointer"
                  onClick={() => handleOpenDetail(order.id)}
                >
                  {/* Kod */}
                  <td className="px-4 py-3 font-mono font-bold text-sky-700 dark:text-sky-400 whitespace-nowrap">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenDetail(order.id);
                      }}
                      className="hover:underline focus:outline-none focus:ring-1 focus:ring-sky-500 rounded"
                    >
                      {code}
                    </button>
                  </td>

                  {/* Müşteri */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="font-semibold text-slate-900 dark:text-slate-100">
                      {order.customer_name}
                    </div>
                    {order.customer_phone && (
                      <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400">
                        {order.customer_phone}
                      </div>
                    )}
                  </td>

                  {/* Tekne & Marina */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="font-medium text-slate-800 dark:text-slate-200">
                      {order.boat_name}
                      {order.boat_model && (
                        <span className="text-slate-500 dark:text-slate-400 text-[11px] ml-1">
                          ({order.boat_model})
                        </span>
                      )}
                    </div>
                    {order.marina && (
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        📍 {order.marina}
                      </div>
                    )}
                  </td>

                  {/* Kategori */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="inline-flex items-center rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                      {categoryLabel}
                    </span>
                  </td>

                  {/* Açıklama */}
                  <td className="px-4 py-3 max-w-xs">
                    <p
                      className="truncate text-slate-600 dark:text-slate-300"
                      title={order.description || ""}
                    >
                      {order.description || "—"}
                    </p>
                  </td>

                  {/* Durum Rozeti */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <ServiceOrderStatusBadge status={order.status} />
                  </td>

                  {/* Kaynak Çağrı */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    {order.source_call_id ? (
                      <Link
                        href={`/admin/calls/${order.source_call_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-sky-50 dark:bg-sky-950/60 border border-sky-200 dark:border-sky-800/80 px-2.5 py-1 text-[11px] font-semibold text-sky-700 dark:text-sky-300 hover:bg-sky-100 dark:hover:bg-sky-900/60 transition-colors"
                      >
                        <span>📞</span>
                        <span>Çağrı Detayı</span>
                      </Link>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500">—</span>
                    )}
                  </td>

                  {/* İşlem */}
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenDetail(order.id);
                      }}
                      className="inline-flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 px-2.5 py-1 text-xs font-semibold text-slate-700 dark:text-slate-200 transition-colors"
                    >
                      <span>İncele</span>
                      <span>➔</span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Detay Modalı */}
      {isModalOpen && selectedOrderId && (
        <ServiceOrderDetailModal
          orderId={selectedOrderId}
          onClose={handleCloseDetail}
          onStatusUpdated={onOrderUpdated}
        />
      )}
    </>
  );
}
