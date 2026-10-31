"use client";

import { useEffect, useRef, useState, useCallback, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  createCall,
  analyzeCall,
  createCallWithAudio,
  getCallStatus,
} from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { CallCreate, CallState, CallStatus } from "@/lib/api/types";
import { MARINA_OPTIONS } from "@/lib/types";
import {
  Badge,
  Button,
  buttonClasses,
  Card,
  Field,
  Input,
  PageHeader,
  ProgressBar,
  Select,
  Textarea,
  type Tone,
} from "@/components/ui";

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
    label: "Yazıya çevriliyor",
    description: "Ses dosyası metne dönüştürülüyor...",
  },
  isleniyor: {
    percent: 78,
    label: "Analiz",
    description:
      "Çağrı analiz ediliyor: kategori, CRM alanları, satış ve özet çıkarılıyor...",
  },
  tamam: {
    percent: 100,
    label: "Tamam",
    description: "Analiz başarıyla tamamlandı.",
  },
  kismi: {
    percent: 100,
    label: "Kısmi tamam",
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

/** İstek kimliği varsa mesaja eklenir; destek ekibi kaydı bu kimlikle bulur. */
function withRequestId(message: string, requestId: string | null | undefined): string {
  return requestId ? `${message} (İstek kimliği: ${requestId})` : message;
}

/** Backend hata kodunu neden ve yapılacak işle birlikte Türkçe mesaja çevirir */
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
        message: withRequestId(
          "Dosya sunucu sınırını (25 MB) aşıyor. Daha kısa bir kayıt seçin veya sesi sıkıştırıp tekrar yükleyin.",
          err.requestId,
        ),
      };
    }
    if (err.status === 415) {
      return {
        message: withRequestId(
          "Bu dosya biçimi desteklenmiyor. WAV, MP3, M4A, OGG, FLAC, AAC veya WEBM biçiminde bir ses dosyası seçin.",
          err.requestId,
        ),
      };
    }
    if (err.status === 503) {
      return {
        message: withRequestId(
          "Analiz servisi şu an meşgul. Birkaç dakika sonra tekrar deneyin.",
          err.requestId,
        ),
      };
    }
    return {
      message: withRequestId(
        `${err.message} Sorun sürerse istek kimliğini yöneticinize iletin.`,
        err.requestId,
      ),
    };
  }
  if (err instanceof Error) {
    return {
      message: `${err.message} Sunucuya ulaşılamadıysa bağlantınızı kontrol edip tekrar deneyin.`,
    };
  }
  return {
    message:
      "Yükleme tamamlanamadı. Bağlantınızı kontrol edip tekrar deneyin; sorun sürerse yöneticinize haber verin.",
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
                  "Analiz tamamlanamadı. Ayrıntı alınamadı.",
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

  // URL'de ?call_id=... varsa sayfa açılışında doğrudan izlemeye bağlan. Tüm state'ler lazy
  // initializer ile zaten ayarlı. Effect tekrar çalıştırılabilir olmalı (React Strict Mode
  // geliştirmede mount → cleanup → mount yapar; cleanup izlemeyi durdurduğu için yeniden başlar).
  useEffect(() => {
    if (!initialUrlCallId) return;
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
      // Sayfa yenilenirse veya kullanıcı geri dönerse izleme aynı çağrıdan devam eder.
      router.replace(`/admin/calls/upload?call_id=${callId}`);
      startPolling(callId);
    } catch (err: unknown) {
      const { message, conflict } = resolveServerError(err);
      setIsSubmitting(false);
      setAnalysisState(null);
      setProgressPercent(0);
      setStatusMessage("");
      setErrorMessage(message);
      if (conflict) {
        setConflictInfo(conflict);
        redirectTimerRef.current = setTimeout(() => {
          if (!cancelled.current) router.push(`/admin/calls/${conflict.callId}`);
        }, 1500);
      }
    }
  };

  /** Otomatik yönlendirmeyi iptal eder; kullanıcı sayfada kalır. */
  const [redirectCancelled, setRedirectCancelled] = useState(false);
  const cancelRedirect = () => {
    if (redirectTimerRef.current !== null) {
      clearTimeout(redirectTimerRef.current);
      redirectTimerRef.current = null;
    }
    setRedirectCancelled(true);
  };

  /** Başarısız çağrıyı aynı kayıt üzerinde yeniden analize gönderir. */
  const handleReanalyze = async () => {
    if (!createdCallId) return;
    setBackendError(null);
    setErrorMessage(null);
    setAnalysisState("beklemede");
    setProgressPercent(STATE_INFO.beklemede.percent);
    setStatusMessage("Yeniden analiz isteği gönderiliyor...");
    try {
      await analyzeCall(createdCallId);
      startPolling(createdCallId);
    } catch (err: unknown) {
      const { message } = resolveServerError(err);
      setAnalysisState("basarisiz");
      setProgressPercent(100);
      setErrorMessage(message);
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
    setRedirectCancelled(false);
    router.replace("/admin/calls/upload");
  };

  /** Yüklendi → Yazıya çevriliyor → Analiz → Tamam: tek şerit adım göstergesi */
  const renderPipelineSteps = () => {
    const currentIdx = analysisState ? PIPELINE_STEPS.indexOf(analysisState) : -1;
    const isFailed = analysisState === "basarisiz";

    return (
      <ol className="mb-4 flex items-center gap-2 text-sm" aria-label="Analiz adımları">
        {PIPELINE_STEPS.map((step, idx) => {
          const isDone = !isFailed && currentIdx > idx;
          const isActive = !isFailed && currentIdx === idx;
          return (
            <li
              key={step}
              aria-current={isActive ? "step" : undefined}
              className={`flex flex-1 items-center gap-2 rounded-lg border px-3 py-2 ${
                isDone
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : isActive
                    ? "border-brand-200 bg-brand-50 font-medium text-brand-800"
                    : "border-slate-200 bg-white text-slate-500"
              }`}
            >
              <span className="text-xs font-semibold">{isDone ? "✓" : idx + 1}</span>
              <span className="truncate">{STATE_INFO[step].label}</span>
            </li>
          );
        })}
      </ol>
    );
  };

  const stateTone: Tone =
    analysisState === "tamam"
      ? "success"
      : analysisState === "basarisiz"
        ? "danger"
        : analysisState === "kismi"
          ? "warning"
          : "brand";

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-12">
      <Link href="/admin/calls" className="inline-block text-sm font-medium text-brand-700 hover:underline">
        ← Çağrı listesine dön
      </Link>
      <PageHeader
        title="Çağrı Yükle"
        description="Ses kaydı veya görüşme metni yükleyin; CRM alanları ve satış analizi otomatik çıkarılır."
      />

      {/* Aynı ses ikinci kez yüklendi: mevcut çağrıya yönlendirilir */}
      {conflictInfo && (
        <Card className="border-amber-300 bg-amber-50" role="status">
          <p className="text-sm font-semibold text-amber-900">Bu ses kaydı daha önce yüklenmiş.</p>
          <p className="mt-1 text-sm text-amber-800">
            Aynı dosya sistemde zaten var; mevcut çağrıya yönlendiriliyorsunuz.
          </p>
          <Link
            href={`/admin/calls/${conflictInfo.callId}`}
            className={buttonClasses("primary", "md", "mt-3")}
          >
            Mevcut çağrıyı aç
          </Link>
        </Card>
      )}

      {/* Analiz izleme: tek şerit */}
      {isSubmitting && (
        <Card>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-brand-800">
                {analysisState === "tamam"
                  ? "Analiz tamamlandı"
                  : analysisState === "kismi"
                    ? "Analiz kısmen tamamlandı"
                    : analysisState === "basarisiz"
                      ? "Analiz tamamlanamadı"
                      : "Analiz sürüyor"}
              </h2>
              <p className="mt-0.5 text-sm text-slate-500">{statusMessage}</p>
            </div>
            {analysisState && (
              <Badge tone={stateTone}>{STATE_INFO[analysisState].label}</Badge>
            )}
          </div>

          {renderPipelineSteps()}
          <ProgressBar
            value={progressPercent}
            tone={stateTone}
            label="Analiz ilerlemesi"
            className="mb-5"
          />

          {analysisState === "tamam" && createdCallId && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-sm text-emerald-800">
                {redirectCancelled
                  ? "Otomatik yönlendirme iptal edildi."
                  : `${AUTO_REDIRECT_MS / 1000} saniye içinde çağrı detayına yönlendirileceksiniz.`}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link href={`/admin/calls/${createdCallId}`} className={buttonClasses("primary")}>
                  Sonucu aç
                </Link>
                {!redirectCancelled && (
                  <Button variant="secondary" onClick={cancelRedirect}>
                    Burada kal
                  </Button>
                )}
              </div>
            </div>
          )}

          {analysisState === "kismi" && createdCallId && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm text-amber-900">
                Bazı alanlar üretilemedi. Eksikleri görmek için çağrı detayına gidin.
              </p>
              <Link
                href={`/admin/calls/${createdCallId}`}
                className={buttonClasses("primary", "md", "mt-3")}
              >
                Çağrı detayına git
              </Link>
            </div>
          )}

          {analysisState === "basarisiz" && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4" role="alert">
              {errorMessage && <p className="text-sm text-red-800">{errorMessage}</p>}
              {backendError && (
                <p className="mt-2 whitespace-pre-wrap rounded bg-red-100 p-2 font-mono text-xs text-red-700">
                  Ayrıntı: {backendError}
                </p>
              )}
              <p className="mt-2 text-sm text-red-800">
                Aynı çağrıyı yeniden analiz etmeyi deneyebilir veya yeni bir yükleme başlatabilirsiniz.
                Sorun sürerse istek kimliğini yöneticinize iletin.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {createdCallId && (
                  <Button onClick={() => void handleReanalyze()}>Yeniden analiz et</Button>
                )}
                <Button variant="secondary" onClick={handleRetry}>
                  Yeni yükleme
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Yükleme formu — yalnızca işlem yokken */}
      {!isSubmitting && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div role="tablist" aria-label="Yükleme türü" className="flex gap-1 rounded-lg bg-slate-100 p-1">
            {(
              [
                ["audio", "Ses dosyası"],
                ["transcript", "Metin / transkript"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={mode === value}
                onClick={() => setMode(value)}
                className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                  mode === value ? "bg-white text-brand-800" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {mode === "audio" && (
            <Card>
              <div
                role="button"
                tabIndex={0}
                aria-label="Ses dosyası seç veya sürükle bırak"
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
                  isDragging
                    ? "border-brand-500 bg-brand-50"
                    : audioFile
                      ? "border-emerald-400 bg-emerald-50"
                      : "border-slate-300 bg-slate-50 hover:border-slate-400"
                }`}
              >
                <input
                  id="upload-audio-file"
                  ref={fileInputRef}
                  type="file"
                  accept={ALLOWED_AUDIO_ACCEPT}
                  className="hidden"
                  aria-label="Ses dosyası yükle"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileChange(e.target.files[0]);
                    }
                  }}
                />
                {audioFile ? (
                  <>
                    <p className="text-base font-semibold text-emerald-800">{audioFile.name}</p>
                    <p className="mt-1 text-sm text-slate-500">
                      {(audioFile.size / (1024 * 1024)).toFixed(2)} MB · değiştirmek için tıklayın
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-base font-medium text-brand-800">
                      Ses dosyasını buraya sürükleyin veya{" "}
                      <span className="underline">dosya seçin</span>
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      WAV, MP3, M4A, OGG, FLAC, AAC, WEBM — en fazla 25 MB
                    </p>
                  </>
                )}
              </div>

              {errorMessage && (
                <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </p>
              )}

              {audioUrl && (
                <div className="mt-4 flex items-center gap-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <span className="shrink-0 text-sm font-medium text-slate-600">Önizleme</span>
                  <audio controls src={audioUrl} className="h-8 min-w-0 flex-1" />
                </div>
              )}
            </Card>
          )}

          {mode === "transcript" && (
            <Card>
              <div className="mb-2 flex items-center justify-between gap-3">
                <label htmlFor="upload-transcript" className="text-sm font-medium text-slate-700">
                  Görüşme metni
                </label>
                <Button variant="ghost" size="sm" onClick={fillSampleData}>
                  Örnek metin doldur
                </Button>
              </div>
              <Textarea
                id="upload-transcript"
                rows={10}
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder={`Temsilci: Miço Usta, buyurun.\nMüşteri: Merhaba, Tuzla Marina'da teknem var. Motor devir almıyor...`}
                className="font-mono"
              />
              <p className="mt-2 text-xs text-slate-500">
                Satırları &ldquo;Temsilci:&rdquo; ve &ldquo;Müşteri:&rdquo; ile başlatabilirsiniz ·{" "}
                {transcript.split("\n").filter(Boolean).length} satır, {transcript.length} karakter
              </p>
              {errorMessage && (
                <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </p>
              )}
            </Card>
          )}

          <details className="rounded-xl border border-slate-200 bg-white">
            <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-brand-800">
              Müşteri bilgisi ekle (isteğe bağlı)
            </summary>
            <div className="space-y-4 border-t border-slate-100 p-5">
              <p className="text-sm text-slate-500">
                Boş bırakılırsa konuşma içeriğinden yapay zekâ tarafından otomatik tespit edilir.
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field id="upload-customer-name" label="Müşteri adı soyadı">
                  <Input
                    id="upload-customer-name"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    placeholder="Örn: Burak Çelik"
                  />
                </Field>
                <Field id="upload-customer-phone" label="Müşteri telefonu">
                  <Input
                    id="upload-customer-phone"
                    value={customerPhone}
                    onChange={(e) => setCustomerPhone(e.target.value)}
                    placeholder="Örn: +90 532 123 45 67"
                  />
                </Field>
                <Field id="upload-boat-name" label="Tekne adı">
                  <Input
                    id="upload-boat-name"
                    value={boatName}
                    onChange={(e) => setBoatName(e.target.value)}
                    placeholder="Örn: Rüzgar"
                  />
                </Field>
                <Field id="upload-boat-model" label="Tekne modeli">
                  <Input
                    id="upload-boat-model"
                    value={boatModel}
                    onChange={(e) => setBoatModel(e.target.value)}
                    placeholder="Örn: Jeanneau Merry Fisher 795"
                  />
                </Field>
                <Field id="upload-marina" label="Marina" className="sm:col-span-2">
                  <Select id="upload-marina" value={marina} onChange={(e) => setMarina(e.target.value)}>
                    <option value="">Seçiniz (isteğe bağlı)</option>
                    {MARINA_OPTIONS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            </div>
          </details>

          <div className="flex items-center justify-end gap-3">
            <Link href="/admin/calls" className={buttonClasses("secondary")}>
              İptal
            </Link>
            <Button type="submit">Analizi başlat</Button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function CallUploadPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-500">Yükleniyor...</div>}>
      <CallUploadContent />
    </Suspense>
  );
}
