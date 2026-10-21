"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { reanalyzeCall, getCallStatus } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { CallState } from "@/lib/api/types";
import { useFocusTrap } from "@/lib/use-focus-trap";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const STATE_INFO: Record<CallState, { percent: number; message: string; stageTitle: string }> = {
  beklemede: {
    percent: 15,
    message: "Çağrı sıraya alındı, analiz bekleniyor...",
    stageTitle: "1. Adım: Kuyrukta Bekliyor",
  },
  yaziya_cevriliyor: {
    percent: 40,
    message: "Ses dosyası metne dönüştürülüyor (STT)...",
    stageTitle: "2. Adım: Transkript Çıkarılıyor",
  },
  isleniyor: {
    percent: 70,
    message: "AI Agent'lar çağrıyı analiz ediyor (kategori, CRM, satış, özet)...",
    stageTitle: "3. Adım: Analiz Yapılıyor",
  },
  tamam: {
    percent: 100,
    message: "Analiz tamamlandı. Sayfa güncelleniyor...",
    stageTitle: "Tamamlandı: Analiz Başarılı!",
  },
  kismi: {
    percent: 100,
    message: "Analiz kısmen tamamlandı. Sayfa güncelleniyor...",
    stageTitle: "Tamamlandı: Kısmi Analiz",
  },
  basarisiz: {
    percent: 100,
    message: "Analiz başarısız oldu.",
    stageTitle: "Hata: Analiz Tamamlanamadı",
  },
};

export interface ReanalyzeButtonProps {
  callId: string;
  currentState?: CallState;
  variant?: "header" | "banner";
  className?: string;
}

export function ReanalyzeButton({
  callId,
  currentState,
  variant = "header",
  className = "",
}: ReanalyzeButtonProps) {
  const router = useRouter();

  // Mod ve görünüm durumları
  const [isOpen, setIsOpen] = useState(false);
  const [modalStage, setModalStage] = useState<"confirm" | "progress">("confirm");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Analiz canlı ilerleme durumu
  const [analysisState, setAnalysisState] = useState<CallState>("beklemede");
  const [progressPercent, setProgressPercent] = useState(15);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Tetikleyici buton referansı (focus return için)
  const triggerButtonRef = useRef<HTMLButtonElement | null>(null);

  // Polling iptal referansı
  const cancelledRef = useRef(false);

  // Unmount olduğunda polling durdur
  useEffect(() => {
    cancelledRef.current = false;
    return () => {
      cancelledRef.current = true;
    };
  }, []);

  const handleClose = React.useCallback(() => {
    if (isSubmitting && analysisState !== "basarisiz" && analysisState !== "tamam" && analysisState !== "kismi") {
      // Analiz arka planda devam eder, modalı kapat
      cancelledRef.current = true;
    }
    setIsOpen(false);
    setModalStage("confirm");
    setIsSubmitting(false);
    setErrorMessage(null);
  }, [isSubmitting, analysisState]);

  // Focus trap hook'u: Escape ile kapatma, Tab kilidi ve kapatıldığında butona odak iadesi
  const modalContainerRef = useFocusTrap<HTMLDivElement>({
    isOpen,
    onClose: handleClose,
    returnFocusRef: triggerButtonRef,
  });

  const handleStartReanalyze = async () => {
    // Çift tıklamayı engelle
    if (isSubmitting) return;

    setIsSubmitting(true);
    setModalStage("progress");
    setAnalysisState("beklemede");
    setProgressPercent(STATE_INFO.beklemede.percent);
    setStatusMessage("Yeniden analiz isteği gönderiliyor...");
    setErrorMessage(null);
    cancelledRef.current = false;

    try {
      // 1. POST /calls/{id}/analyze
      await reanalyzeCall(callId);

      setStatusMessage(STATE_INFO.beklemede.message);

      // 2. Canlı Polling: GET /calls/{id}/status
      const deadline = Date.now() + POLL_TIMEOUT_MS;
      let state: CallState = "beklemede";

      while (!cancelledRef.current) {
        await sleep(POLL_INTERVAL_MS);
        if (cancelledRef.current) break;

        const statusRes = await getCallStatus(callId);
        state = statusRes.state;
        setAnalysisState(state);
        setProgressPercent(STATE_INFO[state].percent);
        setStatusMessage(STATE_INFO[state].message);

        if (state === "tamam" || state === "kismi" || state === "basarisiz") {
          if (state === "basarisiz") {
            setErrorMessage(statusRes.error ?? "Analiz tamamlanamadı.");
          }
          break;
        }

        if (Date.now() > deadline) {
          throw new Error("Analiz beklenenden uzun sürdü. Lütfen sayfayı yenileyip kontrol edin.");
        }
      }

      // 3. Başarıyla bittiğinde sayfayı tazele
      if ((state === "tamam" || state === "kismi") && !cancelledRef.current) {
        await sleep(1000);
        if (!cancelledRef.current) {
          router.refresh();
          setIsOpen(false);
          setIsSubmitting(false);
        }
      }
    } catch (err: unknown) {
      if (cancelledRef.current) return;
      setAnalysisState("basarisiz");
      setProgressPercent(100);
      const msg = isApiError(err)
        ? err.message
        : err instanceof Error
        ? err.message
        : "Yeniden analiz başlatılamadı.";
      setErrorMessage(msg);
      setStatusMessage("Yeniden analiz başarısız oldu.");
    } finally {
      if (cancelledRef.current) {
        setIsSubmitting(false);
      }
    }
  };

  // Buton görünümü
  const isCallInProgress =
    currentState === "beklemede" ||
    currentState === "yaziya_cevriliyor" ||
    currentState === "isleniyor";

  // Eğer çağrı henüz analiz aşamasındaysa buton render edilmez
  if (isCallInProgress) {
    return null;
  }

  return (
    <>
      {/* Tetikleyici Buton */}
      {variant === "header" ? (
        <button
          ref={triggerButtonRef}
          type="button"
          onClick={() => {
            setIsOpen(true);
            setModalStage("confirm");
          }}
          disabled={isSubmitting}
          className={`inline-flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 active:scale-[0.98] transition-all shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 disabled:opacity-50 ${className}`}
          title="Çağrıyı yeniden analize gönder"
          aria-label="Çağrıyı yeniden analiz et"
        >
          <span className="text-sm" aria-hidden="true">🔄</span>
          <span>Yeniden Analiz Et</span>
        </button>
      ) : (
        <button
          ref={triggerButtonRef}
          type="button"
          onClick={() => {
            setIsOpen(true);
            setModalStage("confirm");
          }}
          disabled={isSubmitting}
          className={`inline-flex items-center gap-1.5 rounded-lg bg-amber-600 dark:bg-amber-700 text-white px-3 py-1 text-xs font-bold hover:bg-amber-700 dark:hover:bg-amber-600 transition-colors shadow-xs focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 disabled:opacity-50 ${className}`}
          title="Kısmi analizi tekrar tamamlat"
          aria-label="Kısmi analizi şimdi yeniden analiz et"
        >
          <span aria-hidden="true">⚡</span>
          <span>Şimdi Yeniden Analiz Et</span>
        </button>
      )}

      {/* Modal Diyaloğu */}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reanalyze-dialog-title"
        >
          <div
            ref={modalContainerRef}
            className="relative w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-2xl transition-all"
          >
            {/* 1. Aşama: Onay Diyaloğu */}
            {modalStage === "confirm" && (
              <div>
                <div className="flex items-center gap-3 mb-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-100 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300">
                    <span className="text-xl" aria-hidden="true">🔄</span>
                  </div>
                  <div>
                    <h2
                      id="reanalyze-dialog-title"
                      className="text-base font-bold text-slate-900 dark:text-slate-100"
                    >
                      Yeniden Analiz Başlatılsın mı?
                    </h2>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      Miço AI Analiz Motoru
                    </p>
                  </div>
                </div>

                <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed mb-6">
                  Bu işlem çağrı için yeni bir analiz sürümü oluşturacaktır. Devam etmek istiyor musunuz?
                </p>

                <div className="flex items-center justify-end gap-3 border-t border-slate-100 dark:border-slate-800 pt-4">
                  <button
                    type="button"
                    onClick={handleClose}
                    disabled={isSubmitting}
                    className="rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
                  >
                    Vazgeç
                  </button>
                  <button
                    type="button"
                    onClick={handleStartReanalyze}
                    disabled={isSubmitting}
                    className="inline-flex items-center gap-2 rounded-xl bg-sky-700 px-5 py-2 text-xs font-bold text-white shadow-xs hover:bg-sky-800 active:scale-[0.98] transition-all focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 disabled:opacity-50"
                  >
                    {isSubmitting ? (
                      <>
                        <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                        <span>Başlatılıyor...</span>
                      </>
                    ) : (
                      <span>Evet, Yeniden Analiz Et</span>
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* 2. Aşama: Canlı Durum & İlerleme Modalı */}
            {modalStage === "progress" && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    {analysisState === "beklemede" && (
                      <div className="h-4 w-4 rounded-full bg-amber-400 animate-ping" />
                    )}
                    {analysisState === "yaziya_cevriliyor" && (
                      <div className="h-4 w-4 rounded-full bg-indigo-500 animate-pulse" />
                    )}
                    {analysisState === "isleniyor" && (
                      <div className="h-4 w-4 rounded-full bg-sky-500 animate-spin" />
                    )}
                    {analysisState === "tamam" && (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 font-bold text-sm">
                        ✓
                      </div>
                    )}
                    {analysisState === "kismi" && (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 font-bold text-sm">
                        ⚠️
                      </div>
                    )}
                    {analysisState === "basarisiz" && (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-400 font-bold text-sm">
                        ✕
                      </div>
                    )}

                    <div>
                      <h3
                        id="reanalyze-dialog-title"
                        className="text-sm font-bold text-slate-900 dark:text-slate-100"
                      >
                        {STATE_INFO[analysisState]?.stageTitle ?? "Analiz Sürüyor"}
                      </h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {statusMessage}
                      </p>
                    </div>
                  </div>

                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                      analysisState === "tamam"
                        ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                        : analysisState === "basarisiz"
                        ? "bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800"
                        : analysisState === "kismi"
                        ? "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                        : "bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800"
                    }`}
                  >
                    {analysisState}
                  </span>
                </div>

                {/* İlerleme Çubuğu */}
                <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2.5 overflow-hidden mb-4">
                  <div
                    className={`h-2.5 rounded-full transition-all duration-500 ${
                      analysisState === "tamam"
                        ? "bg-emerald-500"
                        : analysisState === "basarisiz"
                        ? "bg-red-500"
                        : "bg-sky-600"
                    }`}
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>

                {/* Hata Mesajı */}
                {errorMessage && (
                  <div className="rounded-xl bg-red-50 dark:bg-red-950/40 p-4 border border-red-200 dark:border-red-900 text-xs text-red-700 dark:text-red-300 mb-4">
                    <p className="font-bold mb-1">Hata Oluştu:</p>
                    <p>{errorMessage}</p>
                  </div>
                )}

                {/* Kapat / İptal Aksiyonu */}
                <div className="flex items-center justify-end border-t border-slate-100 dark:border-slate-800 pt-3">
                  <button
                    type="button"
                    onClick={handleClose}
                    className="rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
                  >
                    {analysisState === "basarisiz" ? "Kapat" : "Arka Planda Sürdür"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
