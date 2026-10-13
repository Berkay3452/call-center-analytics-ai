"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  createCall,
  createCallWithAudio,
  getCallStatus,
} from "@/lib/api/client";
import type { CallCreate, CallState } from "@/lib/api/types";

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

const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

/** Süreç aşamasına göre ilerleme çubuğu ve açıklama (yüzdeler yaklaşıktır). */
const STATE_INFO: Record<CallState, { percent: number; message: string }> = {
  beklemede: { percent: 15, message: "Çağrı sıraya alındı." },
  yaziya_cevriliyor: { percent: 40, message: "Ses dosyası metne dönüştürülüyor (STT)." },
  isleniyor: {
    percent: 70,
    message: "Agent'lar çağrıyı analiz ediyor (kategori, CRM alanları, satış, özet).",
  },
  tamam: { percent: 100, message: "Analiz tamamlandı. Sonuç ekranına aktarılıyorsunuz..." },
  kismi: {
    percent: 100,
    message: "Analiz kısmen tamamlandı; bazı alanlar boş kalabilir. Sonuca aktarılıyorsunuz...",
  },
  basarisiz: { percent: 100, message: "Analiz başarısız oldu." },
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const SAMPLE_TRANSCRIPT = `Temsilci: Miço Usta, buyurun.
Müşteri: Merhaba, Tuzla Marina'da teknem var. Motor çalışıyor ama gaz verdiğimde devir yükselmiyor.
Temsilci: Geçmiş olsun. Teknenin adını alabilir miyim?
Müşteri: Rüzgar. Yarın bir usta gelebilir mi?
Temsilci: Usta uygunluğuna bakıp sizi bilgilendireceğiz.`;

type UploadMode = "audio" | "transcript";

export default function CallUploadPage() {
  const router = useRouter();

  // Mod
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

  // Sürükle-bırak durumu
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Analiz durumu ve canlı akış
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [analysisState, setAnalysisState] = useState<CallState | null>(null);
  const [progressPercent, setProgressPercent] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [createdCallId, setCreatedCallId] = useState<string | null>(null);

  // Sayfadan çıkılınca sorgulama ve yönlendirme durur.
  const cancelled = useRef(false);
  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
    };
  }, []);

  // Dosya seçimi
  const handleFileChange = (file: File) => {
    if (file.size > MAX_AUDIO_BYTES) {
      setErrorMessage("Ses dosyası 25 MB'ı aşıyor. Daha küçük bir dosya seçin.");
      return;
    }
    setErrorMessage(null);
    setAudioFile(file);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setAudioUrl(URL.createObjectURL(file));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      handleFileChange(file);
    }
  };

  // Örnek veri doldur
  const fillSampleData = () => {
    setCustomerName("Burak Çelik");
    setCustomerPhone("+90 532 123 45 67");
    setBoatName("Rüzgar");
    setBoatModel("Jeanneau Merry Fisher 795");
    setMarina("Tuzla Marina");
    setTranscript(SAMPLE_TRANSCRIPT);
  };

  // Yükleme ve canlı analiz akışı
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (mode === "audio" && !audioFile) {
      setErrorMessage("Lütfen analiz edilecek bir ses dosyası seçin (.mp3, .wav, .m4a).");
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

      // Gerçek durumu sunucudan sorgula; bitene (tamam/kismi/basarisiz) kadar devam et.
      const deadline = Date.now() + POLL_TIMEOUT_MS;
      let state: CallState = "beklemede";
      while (!cancelled.current) {
        const res = await getCallStatus(callId);
        state = res.state;
        setAnalysisState(state);
        setProgressPercent(STATE_INFO[state].percent);
        setStatusMessage(STATE_INFO[state].message);
        if (state === "tamam" || state === "kismi" || state === "basarisiz") {
          if (state === "basarisiz") setErrorMessage(res.error ?? "Analiz tamamlanamadı.");
          break;
        }
        if (Date.now() > deadline) {
          throw new Error("Analiz beklenenden uzun sürdü. Çağrı listesinden sonucu kontrol edin.");
        }
        await sleep(POLL_INTERVAL_MS);
      }

      if (state !== "basarisiz" && !cancelled.current) {
        await sleep(1200);
        if (!cancelled.current) router.push(`/admin/calls/${callId}`);
      }
    } catch (err: unknown) {
      setAnalysisState("basarisiz");
      setProgressPercent(100);
      setErrorMessage(
        err instanceof Error ? err.message : "Analiz işlemi sırasında bir hata meydana geldi.",
      );
      setStatusMessage("Analiz başarısız oldu.");
    }
  };

  const handleRetry = () => {
    setIsSubmitting(false);
    setAnalysisState(null);
    setProgressPercent(0);
    setErrorMessage(null);
    setStatusMessage("");
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      {/* Üst Navigasyon & Başlık */}
      <div className="flex items-center justify-between">
        <div>
          <Link
            href="/admin/calls"
            className="inline-flex items-center text-sm font-medium text-sky-600 hover:text-sky-800 hover:underline mb-1"
          >
            ← Çağrı listesine dön
          </Link>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            Yeni Çağrı Yükleme & Analiz
          </h1>
          <p className="text-sm text-gray-500">
            Ses kaydı veya transkript metni yükleyin; Miço AI motoru CRM 7 temel alanı ve satış analizini çıkarsın.
          </p>
        </div>
      </div>

      {/* Analiz Devam Ediyor / Tamamlandı / Hata Durumu Modalı */}
      {isSubmitting && (
        <div className="rounded-2xl border border-sky-200 bg-white p-6 shadow-md transition-all">
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
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 font-bold text-sm">
                  ✓
                </div>
              )}
              {analysisState === "kismi" && (
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-amber-700 font-bold text-sm">
                  ⚠️
                </div>
              )}
              {analysisState === "basarisiz" && (
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-red-100 text-red-600 font-bold text-sm">
                  ✕
                </div>
              )}

              <div>
                <h3 className="text-base font-semibold text-gray-900">
                  {analysisState === "beklemede" && "1. Adım: Çağrı Sıraya Alındı"}
                  {analysisState === "yaziya_cevriliyor" && "2. Adım: Ses Metne Dönüştürülüyor (STT)"}
                  {analysisState === "isleniyor" && "3. Adım: AI Agent Analizleri Yürütülüyor"}
                  {analysisState === "tamam" && "Tamamlandı: Analiz Başarılı!"}
                  {analysisState === "kismi" && "Tamamlandı: Kısmi Analiz"}
                  {analysisState === "basarisiz" && "Hata: Analiz Tamamlanamadı"}
                </h3>
                <p className="text-xs text-gray-500">{statusMessage}</p>
              </div>
            </div>

            {/* Rozet */}
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider ${
                analysisState === "tamam"
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                  : analysisState === "basarisiz"
                  ? "bg-red-50 text-red-700 border border-red-200"
                  : analysisState === "kismi"
                  ? "bg-amber-50 text-amber-700 border border-amber-200"
                  : "bg-sky-50 text-sky-700 border border-sky-200"
              }`}
            >
              {analysisState}
            </span>
          </div>

          {/* İlerleme Çubuğu */}
          <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden mb-3">
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

          {/* Hata ve Yeniden Dene */}
          {errorMessage && (
            <div className="mt-4 rounded-lg bg-red-50 p-4 border border-red-200 text-sm text-red-700">
              <p className="font-semibold mb-1">Hata Oluştu:</p>
              <p>{errorMessage}</p>
              <button
                type="button"
                onClick={handleRetry}
                className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-700 transition-colors"
              >
                ← Yeniden Dene
              </button>
            </div>
          )}

          {/* Başarılı yönlendirme butonu */}
          {(analysisState === "tamam" || analysisState === "kismi") && createdCallId && (
            <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3">
              <span className="text-xs text-gray-400">Otomatik aktarılmazsa:</span>
              <Link
                href={`/admin/calls/${createdCallId}`}
                className="inline-flex items-center gap-1.5 text-xs font-bold text-sky-600 hover:text-sky-800 hover:underline"
              >
                Analiz Detayına Git →
              </Link>
            </div>
          )}
        </div>
      )}

      {/* Yükleme Formu */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Mod Seçimi Sekmeleri */}
        <div className="flex rounded-xl bg-gray-100 p-1.5 shadow-inner">
          <button
            type="button"
            onClick={() => setMode("audio")}
            className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all ${
              mode === "audio"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <span>🎙️</span>
            <span>Ses Dosyası Yükle (.mp3, .wav, .m4a)</span>
          </button>
          <button
            type="button"
            onClick={() => setMode("transcript")}
            className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all ${
              mode === "transcript"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <span>📝</span>
            <span>Transkript / Metin Yapıştır</span>
          </button>
        </div>

        {/* 1. Mod A: Ses Dosyası Yükleme Alanı */}
        {mode === "audio" && (
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-semibold text-gray-900 mb-2">
              Ses Dosyası Seçimi
            </h2>
            <p className="text-xs text-gray-500 mb-4">
              Santralden veya kayıt cihazından indirilen ses dosyasını yükleyin (Maksimum 25 MB).
            </p>

            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
                isDragging
                  ? "border-sky-500 bg-sky-50/50"
                  : audioFile
                  ? "border-emerald-400 bg-emerald-50/30"
                  : "border-gray-300 hover:border-gray-400 bg-gray-50"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/mp3,audio/wav,audio/m4a,audio/aac,audio/ogg,.mp3,.wav,.m4a,.aac"
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
                  <p className="text-sm font-semibold text-emerald-800">
                    Seçilen Dosya: {audioFile.name}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Boyut: {(audioFile.size / (1024 * 1024)).toFixed(2)} MB • Değiştirmek için tıklayın
                  </p>
                </div>
              ) : (
                <div>
                  <p className="text-sm font-medium text-gray-700">
                    Ses dosyasını buraya sürükleyin veya <span className="text-sky-600 font-bold underline">dosya seçin</span>
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    Desteklenenler: MP3, WAV, M4A, AAC (En fazla 25 MB)
                  </p>
                </div>
              )}
            </div>

            {/* Ses Önizleme Oynatıcısı */}
            {audioUrl && (
              <div className="mt-4 rounded-lg bg-gray-50 p-3 border border-gray-200 flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-600">Önizleme:</span>
                <audio controls src={audioUrl} className="h-8 max-w-sm" />
              </div>
            )}
          </div>
        )}

        {/* 2. Mod B: Transkript / Metin Yapıştırma */}
        {mode === "transcript" && (
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-base font-semibold text-gray-900">
                Görüşme Metni / Transkript
              </h2>
              <button
                type="button"
                onClick={fillSampleData}
                className="text-xs font-semibold text-sky-600 hover:text-sky-800 hover:underline"
              >
                + Örnek Tuzla Marina Transkripti Doldur
              </button>
            </div>
            <p className="text-xs text-gray-500 mb-3">
              Görüşmeyi satır satır &ldquo;Temsilci:&rdquo; ve &ldquo;Müşteri:&rdquo; formatında girebilirsiniz.
            </p>

            <textarea
              rows={8}
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder={`Temsilci: Miço Usta, buyurun.\nMüşteri: Merhaba, Tuzla Marina'da teknem var. Motor devir almıyor...`}
              className="w-full rounded-lg border border-gray-300 p-3 text-sm font-mono focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />

            <div className="mt-2 flex justify-between text-xs text-gray-400">
              <span>{transcript.split("\n").filter(Boolean).length} satır</span>
              <span>{transcript.length} karakter</span>
            </div>
          </div>
        )}

        {/* 3. İsteğe Bağlı Çağrı ve Tekne Bilgileri */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
          <h2 className="text-base font-semibold text-gray-900 border-b pb-2">
            Çağrı & Müşteri Bilgileri <span className="text-xs font-normal text-gray-500">(İsteğe Bağlı)</span>
          </h2>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-semibold uppercase text-gray-600 mb-1">
                Müşteri Adı Soyadı
              </label>
              <input
                type="text"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                placeholder="Örn: Burak Çelik"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-gray-600 mb-1">
                Müşteri Telefonu
              </label>
              <input
                type="text"
                value={customerPhone}
                onChange={(e) => setCustomerPhone(e.target.value)}
                placeholder="Örn: +90 532 123 45 67"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-gray-600 mb-1">
                Tekne Adı
              </label>
              <input
                type="text"
                value={boatName}
                onChange={(e) => setBoatName(e.target.value)}
                placeholder="Örn: Rüzgar"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-gray-600 mb-1">
                Tekne Modeli
              </label>
              <input
                type="text"
                value={boatModel}
                onChange={(e) => setBoatModel(e.target.value)}
                placeholder="Örn: Jeanneau Merry Fisher 795"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-gray-600 mb-1">
                Marina / Lokasyon
              </label>
              <select
                value={marina}
                onChange={(e) => setMarina(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 bg-white"
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

        {/* Gönder / Analizi Başlat Butonu */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <Link
            href="/admin/calls"
            className="rounded-xl border border-gray-300 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
          >
            İptal
          </Link>
          <button
            type="submit"
            disabled={isSubmitting}
            className={`rounded-xl px-6 py-2.5 text-sm font-bold text-white shadow-sm transition-all ${
              isSubmitting
                ? "bg-sky-400 cursor-not-allowed opacity-75"
                : "bg-sky-600 hover:bg-sky-700 active:scale-[0.98]"
            }`}
          >
            {isSubmitting ? "Analiz Ediliyor..." : "⚡ Analizi Başlat"}
          </button>
        </div>
      </form>
    </div>
  );
}
