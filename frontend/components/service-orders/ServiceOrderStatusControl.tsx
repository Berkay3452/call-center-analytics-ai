"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import type { ServiceOrderStatus } from "@/lib/types";
import {
  NEXT_SERVICE_ORDER_STATUS,
  NEXT_STATUS_ACTION_LABELS,
  SERVICE_ORDER_STATUS_LABELS,
} from "@/lib/types";
import { updateServiceOrderStatus } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { ServiceOrderDetail } from "@/lib/api/types";

interface ServiceOrderStatusControlProps {
  orderId: string;
  currentStatus: ServiceOrderStatus;
  onStatusUpdated?: (updated: ServiceOrderDetail) => void;
  className?: string;
}

export function ServiceOrderStatusControl({
  orderId,
  currentStatus,
  onStatusUpdated,
  className = "",
}: ServiceOrderStatusControlProps) {
  const router = useRouter();
  const [status, setStatus] = useState<ServiceOrderStatus>(currentStatus);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nextStatus = NEXT_SERVICE_ORDER_STATUS[status];
  const nextActionLabel = NEXT_STATUS_ACTION_LABELS[status];

  const handleAdvanceStatus = async (targetStatus: ServiceOrderStatus) => {
    if (isLoading) return;
    setIsLoading(true);
    setError(null);

    try {
      const updated = await updateServiceOrderStatus(orderId, targetStatus);
      setStatus(updated.status);
      onStatusUpdated?.(updated);
      router.refresh();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Durum güncellenirken bir hata oluştu.");
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Bilinmeyen bir hata oluştu.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex flex-wrap items-center gap-3">
        {nextStatus && nextActionLabel ? (
          <button
            type="button"
            disabled={isLoading}
            onClick={() => handleAdvanceStatus(nextStatus)}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-700 dark:bg-sky-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-sky-800 dark:hover:bg-sky-700 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            {isLoading ? (
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <span>➔</span>
            )}
            <span>
              {nextActionLabel} ({SERVICE_ORDER_STATUS_LABELS[nextStatus]})
            </span>
          </button>
        ) : (
          <div className="inline-flex items-center gap-2 rounded-xl bg-emerald-50 dark:bg-emerald-950/70 border border-emerald-200 dark:border-emerald-800 px-3.5 py-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300">
            <span>✓</span>
            <span>Servis Emri Tamamlandı</span>
          </div>
        )}

        {/* Seçici ile doğrudan bir sonraki adıma geçiş */}
        {nextStatus && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 dark:text-slate-400">veya:</span>
            <select
              disabled={isLoading}
              value={status}
              onChange={(e) => {
                const val = e.target.value as ServiceOrderStatus;
                if (val !== status) {
                  handleAdvanceStatus(val);
                }
              }}
              className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 shadow-xs focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
            >
              <option value={status} disabled>
                Mevcut: {SERVICE_ORDER_STATUS_LABELS[status]}
              </option>
              <option value={nextStatus}>
                Geç: {SERVICE_ORDER_STATUS_LABELS[nextStatus]}
              </option>
            </select>
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900 p-2.5 text-xs text-red-700 dark:text-red-300 flex items-start gap-2">
          <span className="font-bold flex-shrink-0">✕</span>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
