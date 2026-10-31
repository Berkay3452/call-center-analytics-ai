import React from "react";
import type { CitationCard as CitationCardType } from "@/lib/types";
import { Badge } from "@/components/ui";

interface CitationCardProps {
  citation: CitationCardType;
}

const KIND_LABELS: Record<string, string> = {
  service_record: "Servis Kaydı",
  boat_note: "Tekne Notu",
  expense: "Harcama",
  subscription: "Sözleşme / Marina",
};

export function CitationCard({ citation }: CitationCardProps) {
  const kindLabel = (citation.kind && KIND_LABELS[citation.kind]) || "Belge Kaydı";

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
      className="flex flex-col gap-1 rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs"
      role="region"
      aria-label={`Kaynak: ${citation.sourceTitle}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Badge>{kindLabel}</Badge>
          <span className="truncate font-medium text-slate-800" title={citation.sourceTitle}>
            {citation.sourceTitle}
          </span>
        </div>
        {formattedDate && <span className="shrink-0 text-slate-500">{formattedDate}</span>}
      </div>

      {citation.excerpt && (
        <blockquote className="border-l-2 border-slate-300 pl-2 text-slate-600">
          &ldquo;{citation.excerpt}&rdquo;
        </blockquote>
      )}

      {citation.callId && (
        <p className="text-slate-500">
          İlgili çağrı: <span className="font-mono">{citation.callId}</span>
        </p>
      )}
    </div>
  );
}
