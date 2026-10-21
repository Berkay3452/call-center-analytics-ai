"use client";

import React, { useEffect, useState } from "react";
import type { ServiceOrderDetail } from "@/lib/api/types";
import { getServiceOrderById } from "@/lib/api/client";
import { ServiceOrderDetailSkeleton } from "@/components/skeletons";
import { ServiceOrderDetailCard } from "./ServiceOrderDetailCard";

interface ServiceOrderDetailModalProps {
  orderId: string;
  onClose: () => void;
  onStatusUpdated?: (updated: ServiceOrderDetail) => void;
}

export function ServiceOrderDetailModal({
  orderId,
  onClose,
  onStatusUpdated,
}: ServiceOrderDetailModalProps) {
  const [order, setOrder] = useState<ServiceOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    getServiceOrderById(orderId)
      .then((data) => {
        if (isMounted) {
          setOrder(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(
            err instanceof Error ? err.message : "Servis emri detayı yüklenemedi.",
          );
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [orderId]);

  // ESC tuşuyla kapatma
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      {/* Karartma arka planı */}
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal gövdesi */}
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 shadow-2xl z-10 transition-all">
        {/* Kapat butonu */}
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500"
          aria-label="Kapat"
        >
          ✕
        </button>

        {loading && <ServiceOrderDetailSkeleton />}

        {error && (
          <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-6 text-center space-y-3">
            <span className="text-3xl">⚠️</span>
            <p className="text-sm font-semibold text-red-800 dark:text-red-200">
              {error}
            </p>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-bold text-white hover:bg-slate-700"
            >
              Kapat
            </button>
          </div>
        )}

        {!loading && !error && order && (
          <ServiceOrderDetailCard
            order={order}
            onStatusUpdated={(updated) => {
              setOrder(updated);
              onStatusUpdated?.(updated);
            }}
          />
        )}
      </div>
    </div>
  );
}
