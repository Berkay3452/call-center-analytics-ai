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
import { Button } from "@/components/ui";
import type { ServiceOrderDetail } from "@/lib/api/types";

interface ServiceOrderStatusControlProps {
  orderId: string;
  currentStatus: ServiceOrderStatus;
  onStatusUpdated?: (updated: ServiceOrderDetail) => void;
  className?: string;
  /** Kart içinde küçük düğme kullanır. */
  compact?: boolean;
}

export function ServiceOrderStatusControl({
  orderId,
  currentStatus,
  onStatusUpdated,
  className = "",
  compact = false,
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
    <div className={`space-y-2 ${className}`}>
      {nextStatus && nextActionLabel ? (
        <Button size={compact ? "sm" : "md"} disabled={isLoading} onClick={() => handleAdvanceStatus(nextStatus)}>
          {isLoading ? "Güncelleniyor…" : `${nextActionLabel} → ${SERVICE_ORDER_STATUS_LABELS[nextStatus]}`}
        </Button>
      ) : (
        <p className="text-sm font-medium text-emerald-700">Servis emri tamamlandı</p>
      )}

      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
