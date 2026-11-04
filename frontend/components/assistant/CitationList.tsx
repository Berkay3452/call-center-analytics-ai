import React from "react";
import type { CitationCard as CitationCardType } from "@/lib/types";
import { CitationCard } from "./CitationCard";

interface CitationListProps {
  citations?: CitationCardType[] | null;
}

/** Kaynaklar varsayılan olarak açıktır; kullanıcı klavyeyle de daraltabilir. */
export function CitationList({ citations }: CitationListProps) {
  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <details open className="mt-3 border-t border-slate-100 pt-2">
      <summary className="cursor-pointer rounded-sm text-xs font-medium text-brand-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500">
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
