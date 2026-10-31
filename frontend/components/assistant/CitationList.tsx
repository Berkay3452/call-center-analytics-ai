import React from "react";
import type { CitationCard as CitationCardType } from "@/lib/types";
import { CitationCard } from "./CitationCard";

interface CitationListProps {
  citations?: CitationCardType[] | null;
}

/** Kaynaklar varsayılan olarak kapalıdır; açılınca kartlar görünür. */
export function CitationList({ citations }: CitationListProps) {
  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <details className="mt-3 border-t border-slate-100 pt-2">
      <summary className="cursor-pointer text-xs font-medium text-brand-700">
        Kaynaklar ({citations.length})
      </summary>
      <div className="mt-2 grid gap-2" role="group" aria-label="Kaynak referansları">
        {citations.map((c, idx) => (
          <CitationCard key={c.recordId || `${c.sourceTitle}-${idx}`} citation={c} />
        ))}
      </div>
    </details>
  );
}
