"use client";

import { useCallback, useRef, useState } from "react";
import { reanalyzeCall } from "@/lib/api/client";
import type { CallState } from "@/lib/api/types";
import { useFocusTrap } from "@/lib/use-focus-trap";
import { analysisIsRunning, analysisStage, AnalysisSpinner, useAnalysis } from "@/components/AnalysisTracker";

export interface ReanalyzeButtonProps {
  callId: string;
  currentState?: CallState;
  variant?: "header" | "banner";
  className?: string;
}

export function ReanalyzeButton({ callId, currentState = "tamam", variant = "header", className = "" }: ReanalyzeButtonProps) {
  const { status, track, connectionError } = useAnalysis({ call_id: callId, state: currentState });
  const running = analysisIsRunning(status.state);
  const [isOpen, setIsOpen] = useState(false);
  const [progress, setProgress] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setIsOpen(false), []);
  const modalRef = useFocusTrap<HTMLDivElement>({ isOpen, onClose: close, returnFocusRef: triggerRef });

  const start = async () => {
    if (submitting || running) return;
    setSubmitting(true);
    setProgress(true);
    setError(null);
    try {
      const accepted = await reanalyzeCall(callId);
      track({ call_id: callId, state: accepted.state, stage: accepted.stage, updated_at: accepted.updated_at });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Yeniden analiz başlatılamadı.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        disabled={submitting || running}
        aria-label={running ? "Analiz sürüyor" : variant === "header" ? "Çağrıyı yeniden analiz et" : "Kısmi analizi şimdi yeniden analiz et"}
        title={running ? "Analiz sürüyor" : "Çağrıyı yeniden analize gönder"}
        onClick={() => { if (!running) { setProgress(false); setError(null); setIsOpen(true); } }}
        className={`inline-flex items-center gap-2 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-amber-700 focus-visible:ring-2 focus-visible:ring-amber-500 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      >
        {(running || submitting) && <AnalysisSpinner />}
        {running ? "Analiz sürüyor" : submitting ? "Başlatılıyor…" : variant === "header" ? "Yeniden Analiz Et" : "Şimdi Yeniden Analiz Et"}
      </button>
      {isOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/60 p-4" role="dialog" aria-modal="true" aria-labelledby="reanalyze-dialog-title">
          <div ref={modalRef} className="w-full max-w-md space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-lg">
            <h2 id="reanalyze-dialog-title" className="font-bold text-slate-900">{progress ? "Analiz durumu" : "Yeniden Analiz Başlatılsın mı?"}</h2>
            {!progress ? (
              <>
                <p className="text-sm text-slate-600">Bu işlem çağrı için yeni bir analiz sürümü oluşturacaktır. Devam etmek istiyor musunuz?</p>
                <div className="flex justify-end gap-3">
                  <button type="button" onClick={close}>Vazgeç</button>
                  <button type="button" onClick={() => void start()} className="rounded-lg bg-brand-700 px-4 py-2 text-sm text-white">Evet, Yeniden Analiz Et</button>
                </div>
              </>
            ) : (
              <>
                <p className="flex items-center gap-2 text-sm">{(submitting || running) && <AnalysisSpinner />}{submitting ? "İstek gönderiliyor…" : running ? analysisStage(status) : status.state === "tamam" ? "Analiz tamamlandı" : status.state === "kismi" ? "Analiz kısmen tamamlandı" : "Analiz tamamlanamadı"}</p>
                {(error || connectionError || status.error) && <p role="alert" className="text-sm text-red-700">{error || connectionError || status.error}</p>}
                <div className="flex justify-end">
                  <button type="button" onClick={close} className="rounded-lg border border-slate-300 px-4 py-2 text-sm">{submitting || running ? "Arka planda sürdür" : "Kapat"}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
