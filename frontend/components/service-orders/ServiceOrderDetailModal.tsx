"use client";

import React, { useEffect, useState } from "react";
import type { ServiceOrderDetail } from "@/lib/api/types";
import { getServiceOrderById } from "@/lib/api/client";
import { ServiceOrderDetailSkeleton } from "@/components/skeletons";
import { ServiceOrderDetailCard } from "./ServiceOrderDetailCard";
import { useFocusTrap } from "@/lib/use-focus-trap";

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

  // Focus trap & Escape hook: Tab tuşunu kilitler, Escape ile kapatır ve odağı açan elemana iade eder
  const modalContainerRef = useFocusTrap<HTMLDivElement>({
    isOpen: true,
    onClose,
  });

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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-label="Servis Emri Detay Modalı"
    >
      {/* Karartma arka planı */}
      <div
        className="fixed inset-0 bg-slate-900/60  transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal gövdesi */}
      <div
        ref={modalContainerRef}
        className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white border border-slate-200 p-6 shadow-lg z-10 transition-all"
      >
        {/* Kapat butonu */}
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500 hover:bg-slate-200 transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
          aria-label="Kapat"
        >
          ✕
        </button>

        {loading && <ServiceOrderDetailSkeleton />}

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center space-y-3">
            <span className="text-3xl" aria-hidden="true">⚠️</span>
            <p className="text-sm font-semibold text-red-800">
              {error}
            </p>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-bold text-white hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
            >
              Kapat
            </button>
          </div>
        )}

        {!loading && !error && order && (
          <ServiceOrderDetailCard
            order={order}
            onStatusUpdated={onStatusUpdated}
          />
        )}
      </div>
    </div>
  );
}
