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

  // A service source may repeat its record date at the start of its title.
  // Keep the descriptive title and a single labelled date below it.
  let title = citation.sourceTitle;
  const isoDate = citation.date?.split("T")[0];
  if (citation.kind === "service_record" && isoDate && /^\d{4}-\d{2}-\d{2}$/.test(isoDate)) {
    const parsed = new Date(`${isoDate}T00:00:00Z`);
    if (!Number.isNaN(parsed.getTime())) {
      const dateLabels = [
        isoDate, formattedDate,
        parsed.toLocaleDateString("tr-TR", { timeZone: "UTC", day: "numeric", month: "long", year: "numeric" }),
        parsed.toLocaleDateString("tr-TR", { timeZone: "UTC" }),
      ];
      for (const label of dateLabels) {
        if (label && title.toLocaleLowerCase("tr-TR").startsWith(label.toLocaleLowerCase("tr-TR"))) {
          title = title.slice(label.length).replace(/^[\s:·,–—-]+/, "").trim() || kindLabel;
          break;
        }
      }
    }
  }

  return (
    <div
      className="flex flex-col gap-1 rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs"
      role="region"
      aria-label={`Kaynak: ${title}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Badge>{kindLabel}</Badge>
          <span className="truncate font-medium text-slate-800" title={title}>
            {title}
          </span>
        </div>

      </div>

      {formattedDate && (
        <dl className="flex flex-wrap gap-x-1 text-slate-600">
          <dt>Kayıt tarihi:</dt>
          <dd><time dateTime={isoDate}>{formattedDate}</time></dd>
        </dl>
      )}

      {citation.excerpt && (
        <blockquote className="break-words border-l-2 border-slate-300 pl-2 text-slate-600 [overflow-wrap:anywhere]">
          &ldquo;{citation.excerpt}&rdquo;
        </blockquote>
      )}

      {citation.callId && (
        <p className="text-slate-500">
          İlgili çağrı: <span className="break-all font-mono">{citation.callId}</span>
        </p>
      )}
    </div>
  );
}
