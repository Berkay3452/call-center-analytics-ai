import React from "react";
import type { ServiceOrderStatus } from "@/lib/types";
import {
  SERVICE_ORDER_STATUS_BADGE,
  SERVICE_ORDER_STATUS_LABELS,
} from "@/lib/types";

interface ServiceOrderStatusBadgeProps {
  status: ServiceOrderStatus;
  className?: string;
  /** Eski çağrılarla uyum için korunur; rozet artık emoji göstermez. */
  showIcon?: boolean;
}

export function ServiceOrderStatusBadge({
  status,
  className = "",
}: ServiceOrderStatusBadgeProps) {
  const badgeCls =
    SERVICE_ORDER_STATUS_BADGE[status] ??
    "bg-slate-100 text-slate-700 border-slate-200";
  const label = SERVICE_ORDER_STATUS_LABELS[status] ?? status;

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${badgeCls} ${className}`}
    >
      {label}
    </span>
  );
}
