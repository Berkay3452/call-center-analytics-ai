import React from "react";
import type { CitationCard as CitationCardType } from "@/lib/types";

interface CitationCardProps {
  citation: CitationCardType;
}

const KIND_LABELS: Record<string, { label: string; bg: string; text: string; border: string }> = {
  service_record: {
    label: "Servis Kaydı",
    bg: "bg-sky-50",
    text: "text-sky-700",
    border: "border-sky-200",
  },
  boat_note: {
    label: "Tekne Notu",
    bg: "bg-indigo-50",
    text: "text-indigo-700",
    border: "border-indigo-200",
  },
  expense: {
    label: "Harcama",
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    border: "border-emerald-200",
  },
  subscription: {
    label: "Sözleşme / Marina",
    bg: "bg-amber-50",
    text: "text-amber-700",
    border: "border-amber-200",
  },
};

export function CitationCard({ citation }: CitationCardProps) {
  const kindConfig = (citation.kind && KIND_LABELS[citation.kind]) || {
    label: "Belge Kaydı",
    bg: "bg-slate-100",
    text: "text-slate-700",
    border: "border-slate-200",
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
      className="group relative flex flex-col gap-1.5 rounded-lg border border-slate-200 bg-white/90 p-2.5 text-xs shadow-xs hover:border-sky-300 hover:shadow-xs transition-all"
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
          <span className="font-semibold text-slate-800 truncate" title={citation.sourceTitle}>
            {citation.sourceTitle}
          </span>
        </div>
        {formattedDate && (
          <span className="text-[11px] font-medium text-slate-500 shrink-0">
            {formattedDate}
          </span>
        )}
      </div>

      {citation.excerpt && (
        <blockquote className="mt-0.5 border-l-2 border-sky-300 pl-2 text-[11px] text-slate-600 italic leading-snug">
          &ldquo;{citation.excerpt}&rdquo;
        </blockquote>
      )}

      {citation.callId && (
        <div className="mt-1 flex items-center gap-1 text-[10px] text-slate-400">
          <span>İlgili Çağrı:</span>
          <span className="font-mono text-slate-600">{citation.callId}</span>
        </div>
      )}
    </div>
  );
}
