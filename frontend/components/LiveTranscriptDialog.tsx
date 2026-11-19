"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button } from "@/components/ui";
import { useFocusTrap } from "@/lib/use-focus-trap";
import { useTranscriptStream } from "@/lib/use-transcript-stream";
import {
  SPEAKER_LABEL,
  formatMs,
  groupTurns,
  type LiveStatus,
} from "@/lib/transcript-live";

const STATUS_INFO: Record<LiveStatus, { label: string; tone: "brand" | "success" | "danger" | "warning" | "neutral" }> = {
  baglaniyor: { label: "Bağlanıyor…", tone: "neutral" },
  canli: { label: "Canlı", tone: "brand" },
  bitti: { label: "Tamamlandı", tone: "success" },
  hata: { label: "Yazıya çevirme başarısız", tone: "danger" },
  kopuk: { label: "Canlı akış yok", tone: "warning" },
  zaman_asimi: { label: "Süre doldu", tone: "warning" },
};

const STICK_THRESHOLD_PX = 48;

/**
 * Yazıya çevirme (2. adım) sürerken açılan pop-up: cümleler konuşmacıya göre (temsilci solda,
 * müşteri sağda) canlı yazılır (#326). Bileşen yalnızca açıkken bağlanır; kapatılıp yeniden
 * açılınca sunucu akışı baştan oynatır, kaçırılan cümle olmaz. Akış yoksa/koparsa çağrı analizi
 * etkilenmez; yazıya çevirme arka planda sürer ve metin çağrı detayında görünür.
 */
export function LiveTranscriptDialog({
  callId,
  onClose,
}: {
  callId: string;
  onClose: () => void;
}) {
  const { segments, status } = useTranscriptStream(callId, true);
  const turns = useMemo(() => groupTurns(segments), [segments]);
  const modalRef = useFocusTrap<HTMLDivElement>({ isOpen: true, onClose });
  const logRef = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(true);

  const scrollToBottom = useCallback(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    setStuck(true);
  }, []);

  // Yeni cümle gelince, kullanıcı yukarı kaydırmadıysa en alta kaydır.
  useEffect(() => {
    if (stuck && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [turns, stuck]);

  const info = STATUS_INFO[status];
  const live = status === "canli" || status === "baglaniyor";

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="live-transcript-title"
    >
      <div
        ref={modalRef}
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-slate-200 bg-white shadow-lg"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 p-5">
          <div>
            <h2 id="live-transcript-title" className="text-base font-bold text-slate-900">
              Canlı yazıya çevirme
            </h2>
            <p className="mt-0.5 text-sm text-slate-500">
              Konuşma metne dönüştükçe burada görünür; temsilci solda, müşteri sağda.
            </p>
          </div>
          <Badge tone={info.tone}>{info.label}</Badge>
        </div>

        <div className="relative min-h-[16rem] flex-1 overflow-hidden">
          <div
            ref={logRef}
            role="log"
            aria-live="polite"
            aria-label="Canlı transkript"
            tabIndex={0}
            onScroll={(e) => {
              const el = e.currentTarget;
              setStuck(el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD_PX);
            }}
            className="h-full max-h-[50vh] space-y-3 overflow-y-auto p-5"
          >
            {turns.length === 0 && (
              <p className="py-8 text-center text-sm text-slate-500">
                {status === "kopuk"
                  ? "Canlı akışa bağlanılamadı."
                  : status === "hata"
                    ? "Yazıya çevirme başarısız oldu."
                    : "Konuşma bekleniyor…"}
              </p>
            )}
            {turns.map((turn) => {
              const isRep = turn.speaker === "rep";
              return (
                <div
                  key={`${turn.start_ms}-${turn.speaker}`}
                  className={`flex ${isRep ? "justify-start" : "justify-end"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                      isRep
                        ? "rounded-bl-sm border border-slate-200 bg-slate-50 text-slate-800"
                        : "rounded-br-sm border border-brand-200 bg-brand-50 text-brand-900"
                    }`}
                  >
                    <p className="mb-0.5 text-xs font-semibold text-slate-500">
                      {SPEAKER_LABEL[turn.speaker]} · {formatMs(turn.start_ms)}
                    </p>
                    <p className="whitespace-pre-wrap break-words">{turn.text}</p>
                  </div>
                </div>
              );
            })}
            {live && turns.length > 0 && (
              <p className="flex items-center gap-1 text-xs text-slate-400" aria-hidden="true">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
                yazılıyor…
              </p>
            )}
          </div>
          {!stuck && turns.length > 0 && (
            <button
              type="button"
              onClick={scrollToBottom}
              className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-slate-300 bg-white px-3 py-1 text-xs shadow"
            >
              En alta git ↓
            </button>
          )}
        </div>

        <div className="space-y-2 border-t border-slate-200 p-5">
          {status === "kopuk" && (
            <p role="status" className="text-sm text-amber-800">
              Canlı akış kullanılamıyor. Yazıya çevirme arka planda sürer; bitince metin çağrı
              detayında görünür.
            </p>
          )}
          {status === "zaman_asimi" && (
            <p role="status" className="text-sm text-amber-800">
              Canlı izleme süresi doldu. Sonuç çağrı detayında görünecek.
            </p>
          )}
          {status === "hata" && (
            <p role="alert" className="text-sm text-red-700">
              Yazıya çevirme tamamlanamadı. Ayrıntı için çağrı durumuna bakın.
            </p>
          )}
          <div className="flex justify-end">
            <Button variant={status === "bitti" ? "primary" : "secondary"} onClick={onClose}>
              {live ? "Arka planda sürdür" : "Kapat"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
