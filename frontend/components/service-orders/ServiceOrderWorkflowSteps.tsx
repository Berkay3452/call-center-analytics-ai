import React from "react";
import type { ServiceOrderStatus } from "@/lib/types";
import {
  SERVICE_ORDER_STATUS_ORDER,
  SERVICE_ORDER_STATUS_LABELS,
} from "@/lib/types";

interface ServiceOrderWorkflowStepsProps {
  currentStatus: ServiceOrderStatus;
  createdAt?: string;
  completedAt?: string | null;
  className?: string;
}

const STEP_ICONS: Record<ServiceOrderStatus, string> = {
  yeni_atandi: "1",
  kesifte: "2",
  onaylandi: "3",
  devam_ediyor: "4",
  tamamlandi: "5",
};

export function ServiceOrderWorkflowSteps({
  currentStatus,
  createdAt,
  completedAt,
  className = "",
}: ServiceOrderWorkflowStepsProps) {
  const currentIndex = SERVICE_ORDER_STATUS_ORDER.indexOf(currentStatus);

  return (
    <div className={`w-full py-2 ${className}`}>
      <div className="relative flex items-center justify-between">
        {/* Arka plan çizgisi */}
        <div className="absolute left-6 right-6 top-1/2 -translate-y-1/2 h-1 bg-slate-200 -z-0" />
        {/* Tamamlanan ilerleme çizgisi */}
        <div
          className="absolute left-6 top-1/2 -translate-y-1/2 h-1 bg-sky-600 transition-all duration-300 -z-0"
          style={{
            width: `${Math.max(
              0,
              (currentIndex / (SERVICE_ORDER_STATUS_ORDER.length - 1)) * 100,
            )}%`,
          }}
        />

        {SERVICE_ORDER_STATUS_ORDER.map((step, idx) => {
          const isDone = idx < currentIndex;
          const isCurrent = idx === currentIndex;

          return (
            <div key={step} className="flex flex-col items-center relative z-10">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-all shadow-xs ${
                  isDone
                    ? "bg-sky-600 text-white"
                    : isCurrent
                      ? "bg-white text-sky-600 border-2 border-sky-600 ring-4 ring-sky-100"
                      : "bg-slate-100 text-slate-400 border border-slate-200"
                }`}
              >
                {isDone ? (
                  <span className="text-sm">✓</span>
                ) : (
                  <span>{STEP_ICONS[step]}</span>
                )}
              </div>

              <span
                className={`mt-2 text-xs font-semibold whitespace-nowrap ${
                  isCurrent
                    ? "text-sky-700 font-bold"
                    : isDone
                      ? "text-slate-700"
                      : "text-slate-400"
                }`}
              >
                {SERVICE_ORDER_STATUS_LABELS[step]}
              </span>

              {isCurrent && (
                <span className="text-[10px] font-medium text-sky-600">
                  {step === "tamamlandi" && completedAt ? (
                    new Date(completedAt).toLocaleDateString("tr-TR")
                  ) : step === "yeni_atandi" && createdAt ? (
                    new Date(createdAt).toLocaleDateString("tr-TR")
                  ) : (
                    "Aktif Aşama"
                  )}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
