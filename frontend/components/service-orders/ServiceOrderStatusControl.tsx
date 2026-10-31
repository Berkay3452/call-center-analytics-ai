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
            className="inline-flex items-center gap-2 rounded-xl bg-sky-700 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-sky-800 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
          >
            {isLoading ? (
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <span aria-hidden="true">➔</span>
            )}
            <span>
              {nextActionLabel} ({SERVICE_ORDER_STATUS_LABELS[nextStatus]})
            </span>
          </button>
        ) : (
          <div className="inline-flex items-center gap-2 rounded-xl bg-emerald-50 border border-emerald-200 px-3.5 py-1.5 text-xs font-bold text-emerald-800">
            <span aria-hidden="true">✓</span>
            <span>Servis Emri Tamamlandı</span>
          </div>
        )}

        {/* Seçici ile doğrudan bir sonraki adıma geçiş */}
        {nextStatus && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">veya:</span>
            <label htmlFor={`so-status-select-${orderId}`} className="sr-only">
              Servis emri durumunu değiştir
            </label>
            <select
              id={`so-status-select-${orderId}`}
              disabled={isLoading}
              value={status}
              aria-label="Servis emri durumunu değiştir"
              onChange={(e) => {
                const val = e.target.value as ServiceOrderStatus;
                if (val !== status) {
                  handleAdvanceStatus(val);
                }
              }}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 disabled:opacity-50"
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
        <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-xs text-red-700 flex items-start gap-2">
          <span className="font-bold flex-shrink-0" aria-hidden="true">✕</span>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
