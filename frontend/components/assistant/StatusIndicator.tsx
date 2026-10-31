import React from "react";
import type { StreamStage } from "@/lib/api/types";

interface StatusIndicatorProps {
  stage?: StreamStage | "yaziyor" | null;
  className?: string;
}

const STAGE_TEXT: Record<string, string> = {
  araniyor: "Tekne ve servis kayıtları aranıyor…",
  dogrulaniyor: "Kayıt kaynakları doğrulanıyor…",
  hazirlaniyor: "Miço Usta yanıtı yazıyor…",
  yaziyor: "Miço Usta yanıtı yazıyor…",
};

export function StatusIndicator({ stage, className = "" }: StatusIndicatorProps) {
  if (!stage) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2 text-sm text-slate-500 ${className}`}
    >
      <span className="flex items-center gap-1" aria-hidden="true">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-600 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-600 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-600" />
      </span>
      <span>{STAGE_TEXT[stage] ?? "Miço Usta yanıt hazırlıyor…"}</span>
    </div>
  );
}
