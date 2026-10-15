import React from "react";
import type { CitationCard as CitationCardType } from "@/lib/types";
import { CitationCard } from "./CitationCard";

interface CitationListProps {
  citations?: CitationCardType[] | null;
}

export function CitationList({ citations }: CitationListProps) {
  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2" role="group" aria-label="Kaynak Referansları">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
        <svg
          className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <span>Doğrulanan Kaynaklar ({citations.length})</span>
      </div>
      <div className="grid gap-2">
        {citations.map((c, idx) => (
          <CitationCard key={c.recordId || `${c.sourceTitle}-${idx}`} citation={c} />
        ))}
      </div>
    </div>
  );
}
