import type { Sentiment } from "@/lib/types";
import { SENTIMENT_LABELS } from "@/lib/types";
import { Badge, type Tone } from "@/components/ui";

const SENTIMENT_STYLE: Record<Sentiment, { tone: Tone; icon: string }> = {
  olumlu: { tone: "success", icon: "▲" },
  notr: { tone: "neutral", icon: "●" },
  olumsuz: { tone: "danger", icon: "▼" },
};

/**
 * Müşteri duygu rozeti (#335). Renk tek başına anlam taşımaz: simge ve metin birlikte verilir.
 * Duygu analizi yoksa (eski analiz veya analiz sürüyor) "Analiz edilmedi" gösterilir.
 */
export function SentimentBadge({
  sentiment,
  complaint,
}: {
  sentiment?: Sentiment | null;
  complaint?: boolean | null;
}) {
  if (!sentiment) {
    return (
      <span data-testid="sentiment-empty" className="text-xs text-slate-500">
        Analiz edilmedi
      </span>
    );
  }
  const style = SENTIMENT_STYLE[sentiment];
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Badge tone={style.tone} data-testid="sentiment-badge" data-sentiment={sentiment}>
        <span aria-hidden="true" className="mr-1 text-[9px]">
          {style.icon}
        </span>
        {SENTIMENT_LABELS[sentiment]}
      </Badge>
      {complaint && (
        <Badge tone="warning" data-testid="complaint-flag">
          <span aria-hidden="true" className="mr-1">
            ⚑
          </span>
          Şikâyet
        </Badge>
      )}
    </span>
  );
}
