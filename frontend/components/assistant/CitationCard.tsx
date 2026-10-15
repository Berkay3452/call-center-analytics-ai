import React from "react";
import type { CitationCard as CitationCardType } from "@/lib/types";

interface CitationCardProps {
  citation: CitationCardType;
}

const KIND_LABELS: Record<string, { label: string; bg: string; text: string; border: string }> = {
  service_record: {
    label: "Servis Kaydı",
    bg: "bg-sky-50 dark:bg-sky-950/50",
    text: "text-sky-700 dark:text-sky-300",
    border: "border-sky-200 dark:border-sky-800",
  },
  boat_note: {
    label: "Tekne Notu",
    bg: "bg-indigo-50 dark:bg-indigo-950/50",
    text: "text-indigo-700 dark:text-indigo-300",
    border: "border-indigo-200 dark:border-indigo-800",
  },
  expense: {
    label: "Harcama",
    bg: "bg-emerald-50 dark:bg-emerald-950/50",
    text: "text-emerald-700 dark:text-emerald-300",
    border: "border-emerald-200 dark:border-emerald-800",
  },
  subscription: {
    label: "Sözleşme / Marina",
    bg: "bg-amber-50 dark:bg-amber-950/50",
    text: "text-amber-700 dark:text-amber-300",
    border: "border-amber-200 dark:border-amber-800",
  },
};

export function CitationCard({ citation }: CitationCardProps) {
  const kindConfig = (citation.kind && KIND_LABELS[citation.kind]) || {
    label: "Belge Kaydı",
    bg: "bg-slate-100 dark:bg-slate-800",
    text: "text-slate-700 dark:text-slate-300",
    border: "border-slate-200 dark:border-slate-700",
  };

  // Tarih biçimlendirme
  let formattedDate = citation.date;
  if (citation.date && citation.date.includes("-")) {
    const parts = citation.date.split("T")[0].split("-");
    if (parts.length === 3) {
      formattedDate = `${parts[2]}.${parts[1]}.${parts[0]}`;
    }
  }

  return (
    <div
      className="group relative flex flex-col gap-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 p-2.5 text-xs shadow-xs hover:border-sky-300 dark:hover:border-sky-500 hover:shadow-xs transition-all"
      role="region"
      aria-label={`Kaynak: ${citation.sourceTitle}`}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border ${kindConfig.bg} ${kindConfig.text} ${kindConfig.border}`}
          >
            {kindConfig.label}
          </span>
          <span className="font-semibold text-slate-800 dark:text-slate-200 truncate" title={citation.sourceTitle}>
            {citation.sourceTitle}
          </span>
        </div>
        {formattedDate && (
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 shrink-0">
            {formattedDate}
          </span>
        )}
      </div>

      {citation.excerpt && (
        <blockquote className="mt-0.5 border-l-2 border-sky-300 dark:border-sky-600 pl-2 text-[11px] text-slate-600 dark:text-slate-300 italic leading-snug">
          &ldquo;{citation.excerpt}&rdquo;
        </blockquote>
      )}

      {citation.callId && (
        <div className="mt-1 flex items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500">
          <span>İlgili Çağrı:</span>
          <span className="font-mono text-slate-600 dark:text-slate-300">{citation.callId}</span>
        </div>
      )}
    </div>
  );
}
