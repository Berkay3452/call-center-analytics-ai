"use client";

import { useEffect, useRef, useState, useCallback, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  createCall,
  createCallWithAudio,
  getCallStatus,
} from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { CallCreate, CallState, CallStatus } from "@/lib/api/types";

const MARINA_OPTIONS = [
  "Tuzla Marina",
  "Kalamış Marina",
  "Marinturk İstanbul City Port (Pendik)",
  "Ataköy Marina",
  "Setur Yalova Marina",
  "D-Marin Turgutreis (Bodrum)",
  "Marmaris Yacht Marina",
  "Göcek D-Marin",
  "Diğer",
];

const ALLOWED_AUDIO_EXTENSIONS = [
  "wav",
  "mp3",
  "m4a",
  "ogg",
  "flac",
  "aac",
  "webm",
];
const ALLOWED_AUDIO_ACCEPT = ALLOWED_AUDIO_EXTENSIONS.map((e) => `.${e}`).join(",");
const MAX_AUDIO_BYTES = 25 * 1024 * 1024; // 25 MB
const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;
const AUTO_REDIRECT_MS = 3000;

/** Süreç aşamasına göre ilerleme çubuğu yüzdesi ve açıklama. */
const STATE_INFO: Record<
  CallState,
  { percent: number; label: string; description: string }
> = {
  beklemede: {
    percent: 15,
    label: "Yüklendi",
    description: "Çağrı kaydı sıraya alındı.",
  },
  yaziya_cevriliyor: {
    percent: 50,
    label: "Yazıya Çevriliyor (STT)",
    description: "Ses dosyası metne dönüştürülüyor...",
  },
  isleniyor: {
    percent: 78,
    label: "Analiz Ediliyor (Agent)",
    description:
      "AI Agent'lar çağrıyı analiz ediyor (kategori, CRM, satış, özet)...",
  },
  tamam: {
    percent: 100,
    label: "Tamamlandı",
    description: "Analiz başarıyla tamamlandı.",
  },
  kismi: {
    percent: 100,
    label: "Kısmi Tamamlandı",
    description: "Analiz kısmen tamamlandı. Bazı alanlar üretilemedi.",
  },
  basarisiz: {
    percent: 100,
    label: "Hata",
    description: "Analiz tamamlanamadı.",
  },
};

/** Pipeline'da sıralı gösterilen adımlar */
const PIPELINE_STEPS: CallState[] = [
  "beklemede",
  "yaziya_cevriliyor",
  "isleniyor",
  "tamam",
];

const SAMPLE_TRANSCRIPT = `Temsilci: Miço Usta, buyurun.
Müşteri: Merhaba, Tuzla Marina'da teknem var. Motor çalışıyor ama gaz verdiğimde devir yükselmiyor.
Temsilci: Geçmiş olsun. Teknenin adını alabilir miyim?
Müşteri: Rüzgar. Yarın bir usta gelebilir mi?
Temsilci: Usta uygunluğuna bakıp sizi bilgilendireceğiz.`;

type UploadMode = "audio" | "transcript";

/** 409 durumunda mevcut çağrının bilgisi */
interface ConflictInfo {
  callId: string;
}

/** Backend hata kodunu Türkçe mesaja çevirir */
function resolveServerError(err: unknown): {
  message: string;
  conflict?: ConflictInfo;
} {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      const callId =
        typeof err.details?.call_id === "string" ? err.details.call_id : null;
      return {
        message: "Bu ses kaydı daha önce yüklenmiş.",
        conflict: callId ? { callId } : undefined,
      };
    }
    if (err.status === 413) {
      return {
        message:
          "Dosya boyutu sunucu sınırını aşıyor (maksimum 25 MB).",
      };
    }
    if (err.status === 415) {
      return {
        message:
          "Desteklenmeyen dosya formatı. Lütfen geçerli bir ses dosyası yükleyin.",
      };
    }
    if (err.status === 503) {
      return {
        message:
          "Analiz servisi veya kuyruk geçici olarak meşgul. Lütfen birazdan tekrar deneyin.",
      };
    }
    return { message: err.message };
  }
  if (err instanceof Error) return { message: err.message };
  return {
    message:
      "Analiz işlemi sırasında beklenmeyen bir hata meydana geldi.",
  };
}

/** İstemci tarafı dosya doğrulama — null: geçerli, string: hata mesajı */
function validateAudioFile(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ALLOWED_AUDIO_EXTENSIONS.includes(ext)) {
    return `Desteklenmeyen format: .${ext}. İzin verilen formatlar: ${ALLOWED_AUDIO_EXTENSIONS.map((e) => `.${e}`).join(", ")}.`;
  }
  if (file.size > MAX_AUDIO_BYTES) {
    return `Dosya boyutu ${(file.size / (1024 * 1024)).toFixed(1)} MB. Maksimum izin verilen boyut 25 MB'dır.`;
  }
  return null;
}

function CallUploadContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // URL'deki ?call_id= — bileşen ilk render'da bir kez okunur
  const initialUrlCallId = searchParams.get("call_id");

  // Sekme
  const [mode, setMode] = useState<UploadMode>("audio");

  // Form alanları
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [boatName, setBoatName] = useState("");
  const [boatModel, setBoatModel] = useState("");
  const [marina, setMarina] = useState("");
  const [transcript, setTranscript] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  // Sürükle-bırak
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Analiz durumu — URL call_id varsa başlangıçta uygun değerlerle başlat
  const [isSubmitting, setIsSubmitting] = useState(() => !!initialUrlCallId);
  const [analysisState, setAnalysisState] = useState<CallState | null>(
    () => (initialUrlCallId ? "beklemede" : null),
  );
  const [progressPercent, setProgressPercent] = useState(() =>
    initialUrlCallId ? STATE_INFO.beklemede.percent : 0,
  );
  const [statusMessage, setStatusMessage] = useState(() =>
    initialUrlCallId ? STATE_INFO.beklemede.description : "",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [conflictInfo, setConflictInfo] = useState<ConflictInfo | null>(null);
  const [createdCallId, setCreatedCallId] = useState<string | null>(
    () => initialUrlCallId,
  );
  const [backendError, setBackendError] = useState<string | null>(null);

  // Polling temizlik referansları
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelled = useRef(false);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current !== null) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  // Sayfadan ayrılınca interval ve timer temizliği
  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      if (redirectTimerRef.current !== null) {
        clearTimeout(redirectTimerRef.current);
        redirectTimerRef.current = null;
      }
    };
  }, []);

  const startPolling = useCallback(
    (callId: string) => {
      stopPolling();
      const deadline = Date.now() + POLL_TIMEOUT_MS;

      const poll = async () => {
        if (cancelled.current) {
          stopPolling();
          return;
        }
        try {
          const res: CallStatus = await getCallStatus(callId);
          const state = res.state;

          if (cancelled.current) return;
          setAnalysisState(state);
          setProgressPercent(STATE_INFO[state].percent);
          setStatusMessage(STATE_INFO[state].description);

          if (
            state === "tamam" ||
            state === "kismi" ||
            state === "basarisiz"
          ) {
            stopPolling();
            if (state === "basarisiz") {
              setBackendError(
                res.error ??
                  "Analiz tamamlanamadı. Backend hata detayı mevcut değil.",
              );
            }
            if (state === "tamam" && !cancelled.current) {
              redirectTimerRef.current = setTimeout(() => {
                if (!cancelled.current) {
                  router.push(`/admin/calls/${callId}`);
                }
              }, AUTO_REDIRECT_MS);
            }
            return;
          }

          if (Date.now() > deadline) {
            stopPolling();
            setAnalysisState("basarisiz");
            setProgressPercent(100);
            setErrorMessage(
              "Analiz beklenenden uzun sürdü. Çağrı listesinden sonucu kontrol edebilirsiniz.",
            );
            setStatusMessage("Zaman aşımı.");
          }
        } catch (err: unknown) {
          if (cancelled.current) return;
          stopPolling();
          const { message } = resolveServerError(err);
          setAnalysisState("basarisiz");
          setProgressPercent(100);
          setErrorMessage(message);
          setStatusMessage("Durum sorgulanamadı.");
        }
      };

      void poll();
      pollIntervalRef.current = setInterval(() => void poll(), POLL_INTERVAL_MS);
    },
    [router, stopPolling],
  );

  // URL'de ?call_id=... varsa sayfa açılışında doğrudan izlemeye bağlan.
  // Tüm state'ler lazy initializer ile zaten ayarlı; burada sadece polling başlatılır.
  const urlCallIdConnected = useRef(false);
  useEffect(() => {
    if (urlCallIdConnected.current) return;
    if (!initialUrlCallId) return;
    urlCallIdConnected.current = true;
    startPolling(initialUrlCallId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Dosya seçimi — istemci tarafı doğrulama
  const handleFileChange = (file: File) => {
    const validationError = validateAudioFile(file);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }
    setErrorMessage(null);
    setConflictInfo(null);
    setAudioFile(file);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(URL.createObjectURL(file));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const fillSampleData = () => {
    setCustomerName("Burak Çelik");
    setCustomerPhone("+90 532 123 45 67");
    setBoatName("Rüzgar");
    setBoatModel("Jeanneau Merry Fisher 795");
    setMarina("Tuzla Marina");
    setTranscript(SAMPLE_TRANSCRIPT);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setConflictInfo(null);
    setBackendError(null);

    if (mode === "audio" && !audioFile) {
      setErrorMessage("Lütfen analiz edilecek bir ses dosyası seçin.");
      return;
    }
    if (mode === "transcript" && !transcript.trim()) {
      setErrorMessage("Lütfen transkript veya görüşme metnini girin.");
      return;
    }

    setIsSubmitting(true);
    setAnalysisState("beklemede");
    setProgressPercent(STATE_INFO.beklemede.percent);
    setStatusMessage("Çağrı kaydı oluşturuluyor ve sunucuya iletiliyor...");

    try {
      let callId: string;

      if (mode === "audio" && audioFile) {
        const formData = new FormData();
        formData.append("file", audioFile);
        formData.append("started_at", new Date().toISOString());
        if (customerName) formData.append("customer_name", customerName);
        if (customerPhone) formData.append("customer_phone", customerPhone);
        if (boatName) formData.append("boat_name", boatName);
        if (boatModel) formData.append("boat_model", boatModel);
        if (marina) formData.append("marina", marina);
        callId = (await createCallWithAudio(formData)).call_id;
      } else {
        const payload: CallCreate = {
          started_at: new Date().toISOString(),
          customer_name: customerName || null,
          customer_phone: customerPhone || null,
          boat_name: boatName || null,
          boat_model: boatModel || null,
          marina: marina || null,
          transcript: transcript.trim() || null,
        };
        callId = (await createCall(payload)).call_id;
      }

      setCreatedCallId(callId);
      startPolling(callId);
    } catch (err: unknown) {
      const { message, conflict } = resolveServerError(err);
      setIsSubmitting(false);
      setAnalysisState(null);
      setProgressPercent(0);
      setStatusMessage("");
      setErrorMessage(message);
      if (conflict) setConflictInfo(conflict);
    }
  };

  const handleRetry = () => {
    stopPolling();
    if (redirectTimerRef.current !== null) {
      clearTimeout(redirectTimerRef.current);
      redirectTimerRef.current = null;
    }
    setIsSubmitting(false);
    setAnalysisState(null);
    setProgressPercent(0);
    setErrorMessage(null);
    setConflictInfo(null);
    setBackendError(null);
    setStatusMessage("");
    setCreatedCallId(null);
  };

  /** Yüklendi → STT → Agent → Tamamlandı adım göstergesi */
  const renderPipelineSteps = () => {
    const currentIdx = analysisState
      ? PIPELINE_STEPS.indexOf(analysisState as CallState)
      : -1;
    const isFailed = analysisState === "basarisiz";

    return (
      <div className="flex items-start gap-0 mt-5 mb-3">
        {PIPELINE_STEPS.map((step, idx) => {
          const info = STATE_INFO[step];
          const isDone = !isFailed && currentIdx > idx;
          const isActive = !isFailed && currentIdx === idx;

          return (
            <div key={step} className="flex items-center flex-1 min-w-0">
              <div className="flex flex-col items-center flex-shrink-0 w-16">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-all duration-300 ${
                    isDone
                      ? "bg-emerald-500 text-white"
                      : isActive && isFailed
                      ? "bg-red-500 text-white"
                      : isActive
                      ? "bg-sky-600 text-white ring-2 ring-sky-300 animate-pulse"
                      : isFailed
                      ? "bg-gray-200 dark:bg-slate-700 text-gray-400 dark:text-slate-500"
                      : "bg-gray-200 dark:bg-slate-700 text-gray-400 dark:text-slate-500"
                  }`}
                >
                  {isDone ? "✓" : idx + 1}
                </div>
                <span
                  className={`mt-1 text-[9px] font-medium text-center leading-tight ${
                    isDone
                      ? "text-emerald-600 dark:text-emerald-400"
                      : isActive
                      ? "text-sky-700 dark:text-sky-400"
                      : "text-gray-400 dark:text-slate-500"
                  }`}
                >
                  {info.label}
                </span>
              </div>
              {idx < PIPELINE_STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-1 mb-4 transition-all duration-500 ${
                    isDone ? "bg-emerald-400" : "bg-gray-200 dark:bg-slate-700"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      {/* Başlık */}
      <div className="flex items-center justify-between">
        <div>
          <Link
            href="/admin/calls"
            className="inline-flex items-center text-sm font-medium text-sky-700 dark:text-sky-400 hover:text-sky-800 dark:hover:text-sky-300 hover:underline mb-1"
          >
            ← Çağrı listesine dön
          </Link>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-slate-100">
            Yeni Çağrı Yükleme &amp; Analiz
          </h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            Ses kaydı veya transkript metni yükleyin; Miço AI motoru CRM 7
            temel alanı ve satış analizini çıkarsın.
          </p>
        </div>
      </div>

      {/* Bilgi bandı */}
      <div className="rounded-lg bg-sky-50 dark:bg-sky-950/30 border border-sky-200 dark:border-sky-800 px-4 py-2.5 text-xs text-sky-800 dark:text-sky-300 flex items-start gap-2">
        <span className="mt-0.5 flex-shrink-0">ℹ️</span>
        <span>
          <strong>Ses yükleme:</strong> WAV, MP3, M4A, OGG, FLAC, AAC, WEBM —
          maksimum 25 MB. Dosya seçildiğinde uzantı ve boyut istemci tarafında
          otomatik kontrol edilir.
        </span>
      </div>

      {/* 409 Conflict uyarısı */}
      {conflictInfo && (
        <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 p-5">
          <div className="flex items-start gap-3">
            <span className="text-xl flex-shrink-0">⚠️</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-1">
                Bu ses kaydı daha önce yüklenmiş.
              </p>
              <p className="text-xs text-amber-700 dark:text-amber-400 mb-3">
                Aynı ses dosyası sistemde zaten mevcut. Mevcut çağrının
                detaylarını inceleyebilirsiniz.
              </p>
              <Link
                href={`/admin/calls/${conflictInfo.callId}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 transition-colors"
              >
                Mevcut Çağrıyı Görüntüle: /admin/calls/{conflictInfo.callId} →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Analiz İzleme Paneli */}
      {isSubmitting && (
        <div className="rounded-2xl border border-sky-200 dark:border-sky-900/60 bg-white dark:bg-slate-900 p-6 shadow-md">
          {/* Başlık satırı */}
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-3">
              {(analysisState === "beklemede" ||
                analysisState === "yaziya_cevriliyor" ||
                analysisState === "isleniyor") && (
                <div className="h-5 w-5 rounded-full border-2 border-sky-600 border-t-transparent animate-spin flex-shrink-0" />
              )}
              {analysisState === "tamam" && (
                <span className="text-2xl flex-shrink-0">✅</span>
              )}
              {analysisState === "kismi" && (
                <span className="text-2xl flex-shrink-0">⚠️</span>
              )}
              {analysisState === "basarisiz" && (
                <span className="text-2xl flex-shrink-0">❌</span>
              )}

              <div>
                <h3 className="text-base font-semibold text-gray-900 dark:text-slate-100">
                  {analysisState === "beklemede" &&
                    "1. Adım: Çağrı Sıraya Alındı"}
                  {analysisState === "yaziya_cevriliyor" &&
                    "2. Adım: Ses Metne Dönüştürülüyor (STT)"}
                  {analysisState === "isleniyor" &&
                    "3. Adım: AI Agent Analizleri Yürütülüyor"}
                  {analysisState === "tamam" &&
                    "Analiz Başarıyla Tamamlandı"}
                  {analysisState === "kismi" && "Kısmi Analiz Tamamlandı"}
                  {analysisState === "basarisiz" &&
                    "Hata: Analiz Tamamlanamadı"}
                </h3>
                <p className="text-xs text-gray-500 dark:text-slate-400">
                  {statusMessage}
                </p>
              </div>
            </div>

            {/* Durum rozeti */}
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider flex-shrink-0 ${
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

          {/* Pipeline adım göstergesi */}
          {renderPipelineSteps()}

          {/* İlerleme çubuğu */}
          <div className="w-full bg-gray-100 dark:bg-slate-800 rounded-full h-2.5 overflow-hidden mb-5">
            <div
              className={`h-2.5 rounded-full transition-all duration-700 ${
                analysisState === "tamam"
                  ? "bg-emerald-500"
                  : analysisState === "basarisiz"
                  ? "bg-red-500"
                  : analysisState === "kismi"
                  ? "bg-amber-500"
                  : "bg-sky-600"
              }`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          {/* tamam — başarı ve otomatik yönlendirme */}
          {analysisState === "tamam" && createdCallId && (
            <div className="rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 p-4">
              <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-300 mb-1">
                🎉 Analiz Başarıyla Tamamlandı
              </p>
              <p className="text-xs text-emerald-700 dark:text-emerald-400 mb-3">
                {AUTO_REDIRECT_MS / 1000} saniye içinde otomatik olarak çağrı
                detayına yönlendirileceksiniz.
              </p>
              <Link
                href={`/admin/calls/${createdCallId}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 transition-colors"
              >
                Sonucu Aç →
              </Link>
            </div>
          )}

          {/* kismi — uyarı */}
          {analysisState === "kismi" && createdCallId && (
            <div className="rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 p-4">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-1">
                Analiz kısmen tamamlandı. Bazı alanlar üretilemedi.
              </p>
              <p className="text-xs text-amber-700 dark:text-amber-400 mb-3">
                Mevcut sonuçları görmek ve eksik alanları incelemek için çağrı
                detayına gidebilirsiniz.
              </p>
              <Link
                href={`/admin/calls/${createdCallId}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 transition-colors"
              >
                Çağrı Detayına Git →
              </Link>
            </div>
          )}

          {/* basarisiz — hata + backend detayı + yeniden dene */}
          {analysisState === "basarisiz" && (
            <div className="rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 p-4">
              <p className="text-sm font-semibold text-red-800 dark:text-red-300 mb-1">
                Hata Oluştu
              </p>
              {errorMessage && (
                <p className="text-xs text-red-700 dark:text-red-400 mb-2">
                  {errorMessage}
                </p>
              )}
              {backendError && (
                <p className="text-xs text-red-600 dark:text-red-500 mb-3 font-mono bg-red-100 dark:bg-red-950/50 rounded p-2 whitespace-pre-wrap">
                  Detay: {backendError}
                </p>
              )}
              <button
                type="button"
                onClick={handleRetry}
                className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-xs font-bold text-white hover:bg-red-700 transition-colors"
              >
                ← Yeniden Dene
              </button>
            </div>
          )}
        </div>
      )}

      {/* Yükleme formu — sadece işlem yokken */}
      {!isSubmitting && (
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Sekme seçimi */}
          <div className="flex rounded-xl bg-gray-100 dark:bg-slate-800/80 p-1.5 shadow-inner border border-gray-200 dark:border-slate-700">
            <button
              type="button"
              onClick={() => setMode("audio")}
              className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all ${
                mode === "audio"
                  ? "bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 shadow-sm"
                  : "text-gray-600 dark:text-slate-400 hover:text-gray-900 dark:hover:text-slate-200"
              }`}
            >
              <span>🎙️</span>
              <span>Ses Dosyası Yükle</span>
            </button>
            <button
              type="button"
              onClick={() => setMode("transcript")}
              className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all ${
                mode === "transcript"
                  ? "bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 shadow-sm"
                  : "text-gray-600 dark:text-slate-400 hover:text-gray-900 dark:hover:text-slate-200"
              }`}
            >
              <span>📝</span>
              <span>Metin / Transkript Yükle</span>
            </button>
          </div>

          {/* Ses Yükleme */}
          {mode === "audio" && (
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100 mb-1">
                Ses Dosyası Seçimi
              </h2>
              <p className="text-xs text-gray-500 dark:text-slate-400 mb-4">
                Santralden veya kayıt cihazından indirilen ses dosyasını
                yükleyin. Desteklenen formatlar:{" "}
                <strong>WAV, MP3, M4A, OGG, FLAC, AAC, WEBM</strong> —
                maksimum <strong>25 MB</strong>.
              </p>

              {/* Sürükle-bırak alanı */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
                  isDragging
                    ? "border-sky-500 bg-sky-50/50 dark:bg-sky-950/30"
                    : audioFile
                    ? "border-emerald-400 dark:border-emerald-600 bg-emerald-50/30 dark:bg-emerald-950/30"
                    : "border-gray-300 dark:border-slate-700 hover:border-gray-400 dark:hover:border-slate-600 bg-gray-50 dark:bg-slate-800/50"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ALLOWED_AUDIO_ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileChange(e.target.files[0]);
                    }
                  }}
                />
                <div className="text-4xl mb-3">{audioFile ? "🎵" : "☁️"}</div>
                {audioFile ? (
                  <div>
                    <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                      Seçilen Dosya: {audioFile.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">
                      Boyut: {(audioFile.size / (1024 * 1024)).toFixed(2)} MB •
                      Değiştirmek için tıklayın
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm font-medium text-gray-700 dark:text-slate-200">
                      Ses dosyasını buraya sürükleyin veya{" "}
                      <span className="text-sky-700 dark:text-sky-400 font-bold underline">
                        dosya seçin
                      </span>
                    </p>
                    <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                      WAV, MP3, M4A, OGG, FLAC, AAC, WEBM — en fazla 25 MB
                    </p>
                  </div>
                )}
              </div>

              {/* İstemci doğrulama hatası */}
              {errorMessage && (
                <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 px-4 py-3 text-xs text-red-700 dark:text-red-300">
                  <span className="flex-shrink-0 font-bold">❌</span>
                  <span>{errorMessage}</span>
                </div>
              )}

              {/* Ses önizleme */}
              {audioUrl && (
                <div className="mt-4 rounded-lg bg-gray-50 dark:bg-slate-800/80 p-3 border border-gray-200 dark:border-slate-700 flex items-center justify-between gap-4">
                  <span className="text-xs font-semibold text-gray-600 dark:text-slate-300 flex-shrink-0">
                    Önizleme:
                  </span>
                  <audio controls src={audioUrl} className="h-8 flex-1 min-w-0" />
                </div>
              )}
            </div>
          )}

          {/* Transkript Yükleme */}
          {mode === "transcript" && (
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">
                  Görüşme Metni / Transkript
                </h2>
                <button
                  type="button"
                  onClick={fillSampleData}
                  className="text-xs font-semibold text-sky-700 dark:text-sky-400 hover:text-sky-800 dark:hover:text-sky-300 hover:underline"
                >
                  + Örnek Tuzla Marina Transkripti Doldur
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-slate-400 mb-3">
                Görüşmeyi satır satır &ldquo;Temsilci:&rdquo; ve
                &ldquo;Müşteri:&rdquo; formatında girebilirsiniz.
              </p>
              <textarea
                rows={8}
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder={`Temsilci: Miço Usta, buyurun.\nMüşteri: Merhaba, Tuzla Marina'da teknem var. Motor devir almıyor...`}
                className="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 text-sm font-mono text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:border-sky-500 dark:focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
              <div className="mt-2 flex justify-between text-xs text-gray-500 dark:text-slate-400">
                <span>
                  {transcript.split("\n").filter(Boolean).length} satır
                </span>
                <span>{transcript.length} karakter</span>
              </div>
              {errorMessage && (
                <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 px-4 py-3 text-xs text-red-700 dark:text-red-300">
                  <span className="flex-shrink-0 font-bold">❌</span>
                  <span>{errorMessage}</span>
                </div>
              )}
            </div>
          )}

          {/* İsteğe bağlı müşteri / tekne bilgileri */}
          <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm space-y-4">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100 border-b border-gray-200 dark:border-slate-800 pb-2">
                Çağrı &amp; Müşteri Bilgileri{" "}
                <span className="text-xs font-normal text-gray-500 dark:text-slate-400">
                  (İsteğe Bağlı)
                </span>
              </h2>
              <p className="text-xs text-sky-700 dark:text-sky-400 mt-2 flex items-start gap-1">
                <span className="flex-shrink-0 mt-0.5">💡</span>
                <span>
                  Boş bırakılırsa konuşma içeriğinden yapay zeka tarafından
                  otomatik tespit edilir.
                </span>
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-xs font-semibold uppercase text-gray-600 dark:text-slate-300 mb-1">
                  Müşteri Adı Soyadı
                </label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  placeholder="Örn: Burak Çelik"
                  className="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:border-sky-500 dark:focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-gray-600 dark:text-slate-300 mb-1">
                  Müşteri Telefonu
                </label>
                <input
                  type="text"
                  value={customerPhone}
                  onChange={(e) => setCustomerPhone(e.target.value)}
                  placeholder="Örn: +90 532 123 45 67"
                  className="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:border-sky-500 dark:focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-gray-600 dark:text-slate-300 mb-1">
                  Tekne Adı
                </label>
                <input
                  type="text"
                  value={boatName}
                  onChange={(e) => setBoatName(e.target.value)}
                  placeholder="Örn: Rüzgar"
                  className="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:border-sky-500 dark:focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-gray-600 dark:text-slate-300 mb-1">
                  Tekne Modeli
                </label>
                <input
                  type="text"
                  value={boatModel}
                  onChange={(e) => setBoatModel(e.target.value)}
                  placeholder="Örn: Jeanneau Merry Fisher 795"
                  className="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:border-sky-500 dark:focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-xs font-semibold uppercase text-gray-600 dark:text-slate-300 mb-1">
                  Marina / Lokasyon
                </label>
                <select
                  value={marina}
                  onChange={(e) => setMarina(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-gray-900 dark:text-slate-100 focus:border-sky-500 dark:focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-500"
                >
                  <option value="">Seçiniz (isteğe bağlı)</option>
                  {MARINA_OPTIONS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Gönder */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <Link
              href="/admin/calls"
              className="rounded-xl border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-5 py-2.5 text-sm font-semibold text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors"
            >
              İptal
            </Link>
            <button
              type="submit"
              className="rounded-xl px-6 py-2.5 text-sm font-bold text-white shadow-sm transition-all bg-sky-700 hover:bg-sky-800 active:scale-[0.98]"
            >
              ⚡ Analizi Başlat
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function CallUploadPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-gray-400">Yükleniyor...</div>}>
      <CallUploadContent />
    </Suspense>
  );
}
