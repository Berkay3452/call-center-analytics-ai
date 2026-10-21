import React from "react";
import type { ServiceOrderStatus } from "@/lib/types";
import {
  SERVICE_ORDER_STATUS_BADGE,
  SERVICE_ORDER_STATUS_LABELS,
} from "@/lib/types";

interface ServiceOrderStatusBadgeProps {
  status: ServiceOrderStatus;
  className?: string;
  showIcon?: boolean;
}

const STATUS_ICONS: Record<ServiceOrderStatus, string> = {
  yeni_atandi: "📥",
  kesifte: "🔍",
  onaylandi: "✅",
  devam_ediyor: "⚙️",
  tamamlandi: "🎉",
};

export function ServiceOrderStatusBadge({
  status,
  className = "",
  showIcon = true,
}: ServiceOrderStatusBadgeProps) {
  const badgeCls =
    SERVICE_ORDER_STATUS_BADGE[status] ??
    "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700";
  const label = SERVICE_ORDER_STATUS_LABELS[status] ?? status;
  const icon = STATUS_ICONS[status] ?? "•";

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border transition-colors ${badgeCls} ${className}`}
    >
      {showIcon && <span className="text-[11px] leading-none select-none">{icon}</span>}
      <span>{label}</span>
    </span>
  );
}
