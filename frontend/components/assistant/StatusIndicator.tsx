import React from "react";
import type { StreamStage } from "@/lib/api/types";

interface StatusIndicatorProps {
  stage?: StreamStage | "yaziyor" | null;
  className?: string;
}

export function StatusIndicator({ stage, className = "" }: StatusIndicatorProps) {
  if (!stage) return null;

  let text = "Miço Usta yanıt hazırlıyor…";
  let icon = (
    <span className="flex h-2 w-2 relative">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
      <span className="relative inline-flex rounded-full h-2 w-2 bg-sky-500"></span>
    </span>
  );

  if (stage === "araniyor") {
    text = "Tekne ve servis kayıtları aranıyor…";
    icon = (
      <svg
        className="w-3.5 h-3.5 animate-spin text-sky-700"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
        />
      </svg>
    );
  } else if (stage === "dogrulaniyor") {
    text = "Kayıt kaynakları ve veriler doğrulanıyor…";
    icon = (
      <svg
        className="w-3.5 h-3.5 animate-pulse text-indigo-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
        />
      </svg>
    );
  } else if (stage === "hazirlaniyor" || stage === "yaziyor") {
    text = "Miço Usta yanıtı yazıyor…";
    icon = (
      <div className="flex items-center gap-1 py-1" aria-hidden="true">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-700 animate-bounce [animation-delay:-0.3s]"></span>
        <span className="h-1.5 w-1.5 rounded-full bg-sky-700 animate-bounce [animation-delay:-0.15s]"></span>
        <span className="h-1.5 w-1.5 rounded-full bg-sky-700 animate-bounce"></span>
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2 rounded-full border border-sky-200 dark:border-sky-800 bg-sky-50/80 dark:bg-sky-950/60 px-3 py-1 text-xs font-medium text-sky-900 dark:text-sky-300 shadow-2xs backdrop-blur-xs transition-all ${className}`}
    >
      {icon}
      <span className="tracking-tight">{text}</span>
    </div>
  );
}
