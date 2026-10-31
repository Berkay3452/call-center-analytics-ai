import { Suspense } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getCallById, getCalls } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type {
  CallDetail,
  CallType,
  SalesOutcomeType,
  LossReason,
} from "@/lib/api/types";
import { PlaceholderCard } from "@/components/PlaceholderCard";
import { CallDetailSkeleton } from "@/components/skeletons";
import { AudioPlayer } from "@/components/AudioPlayer";
import { ReanalyzeButton } from "@/components/ReanalyzeButton";
import { CrmSuggestionCard } from "@/components/crm";
import {
  CALL_TYPE_LABELS,
  labelOf,
  LOSS_REASON_LABELS,
  SALES_OUTCOME_LABELS,
} from "@/lib/types";
import mockCallsList from "@/mocks/cagri_listesi.json";

interface Props {
  params: Promise<{ id: string }>;
}

export async function generateStaticParams() {
  try {
    const res = await getCalls();
    if (res?.items && res.items.length > 0) {
      return res.items.map((c) => ({ id: c.id }));
    }
  } catch {
    // Derleme anında backend kapalıysa güvenli mock fallback
  }
  return mockCallsList.items.map((c) => ({ id: c.id }));
}

export async function generateMetadata({ params }: Props) {
  try {
    const { id } = await params;
    return { title: `Çağrı Analizi ${id} | Miço Usta` };
  } catch {
    return { title: "Çağrı Analizi | Miço Usta" };
  }
}

const SALES_OUTCOME_BADGE: Record<SalesOutcomeType, string> = {
  satisa_donustu: "bg-emerald-50 text-emerald-700 border-emerald-300",
  kaybedildi: "bg-red-50 text-red-700 border-red-300",
  beklemede: "bg-amber-50 text-amber-700 border-amber-300",
};

/**
 * Konuşma metnindeki "rep: ...", "customer: ...", "Temsilci: ..." vb. önekleri temizler.
 */
function cleanSpeakerPrefix(text: string): string {
  return text.replace(/^(rep|customer|temsilci|müşteri|musteri)\s*:\s*/i, "").trim();
}

/**
 * Milisaniyeyi "dk:sn" biçimine çevirir.
 */
function formatMs(ms: number | null | undefined): string | null {
  if (ms == null) return null;
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function CallDetailPage({ params }: Props) {
  return (
    <Suspense fallback={<CallDetailSkeleton />}>
      <CallDetailContent params={params} />
    </Suspense>
  );
}

async function CallDetailContent({ params }: Props) {
  const { id } = await params;
  let call: CallDetail | null = null;

  try {
    call = await getCallById(id);
  } catch (err) {
    if (isApiError(err) && err.status === 404) notFound();
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 shadow-sm">
        <h2 className="text-base font-bold text-red-900">Çağrı Detayı Yüklenemedi</h2>
        <p className="mt-1 text-sm text-red-700">
          {err instanceof Error
            ? err.message
            : "Sunucuya bağlanılamadı. Ağ bağlantınızı veya backend durumunu kontrol edin."}
        </p>
        <Link
          href="/admin/calls"
          className="mt-4 inline-block text-xs font-semibold text-sky-700 hover:underline px-2 py-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
        >
          ← Çağrı listesine dön
        </Link>
      </div>
    );
  }

  if (!call) notFound();

  const crm = call.analysis?.crm;
  const sales = call.analysis?.sales;
  const summary = call.analysis?.summary;
  const classification = call.analysis?.classification;
  const durationSec = call.duration_s ?? 0;

  // Aciliyet çıkarılamadıysa nötr renk kullanılır.
  const urgency = crm?.urgency;
  const callType = classification?.call_type;
  const inProgress =
    call.state === "beklemede" || call.state === "yaziya_cevriliyor" || call.state === "isleniyor";
  const analysisStatus = call.analysis?.status ?? (call.state === "basarisiz" ? "basarisiz" : "kismi");

  // Gerçek Analiz Güveni: yalnızca classification.confidence varsa gösterilir
  const rawConfidence = classification?.confidence;
  const confidencePercent =
    rawConfidence != null
      ? Math.round(rawConfidence <= 1 ? rawConfidence * 100 : rawConfidence)
      : null;

  // Kısmi analiz veya analiz hataları ayrıştırma
  const rawErrors = call.analysis?.errors;
  const errorEntries: Array<{ section: string; message: string; detail?: string }> = [];

  if (rawErrors) {
    if (Array.isArray(rawErrors)) {
      rawErrors.forEach((err, idx) => {
        if (typeof err === "string") {
          errorEntries.push({ section: `Bölüm ${idx + 1}`, message: "Bu bölüm üretilemedi.", detail: err });
        } else if (typeof err === "object" && err !== null) {
          const anyErr = err as Record<string, unknown>;
          errorEntries.push({
            section: String(anyErr.section || anyErr.field || `Hata ${idx + 1}`),
            message: "Bu bölüm üretilemedi.",
            detail: String(anyErr.message || anyErr.error || JSON.stringify(err)),
          });
        }
      });
    } else if (typeof rawErrors === "object") {
      Object.entries(rawErrors).forEach(([key, val]) => {
        // Backend `analysis.errors` anahtarları ajan adlarıdır.
        const sectionMap: Record<string, string> = {
          call_classifier: "Çağrı Sınıflandırma",
          crm_extraction: "CRM Çıkarımı",
          sales_analyzer: "Satış Analizi",
          summarizer: "Görüşme Özeti",
          classification: "Çağrı Sınıflandırma",
          crm: "CRM Çıkarımı",
          sales: "Satış Analizi",
          summary: "Görüşme Özeti",
        };
        const sectionName = sectionMap[key] || key;
        errorEntries.push({ section: sectionName, message: "Bu bölüm üretilemedi.", detail: String(val) });
      });
    }
  }

  const isPartial = analysisStatus === "kismi" || errorEntries.length > 0;

  // Transkript segmentleri (Öncelikle segments dizisi, yoksa raw text)
  const segments = (call.transcript?.segments && call.transcript.segments.length > 0)
    ? call.transcript.segments.map((seg, idx) => {
        const isCustomer = seg.speaker === "customer";
        const cleanText = cleanSpeakerPrefix(seg.text);
        const timeFormatted = formatMs(seg.start_ms);
        return {
          id: idx,
          isCustomer,
          text: cleanText,
          time: timeFormatted,
        };
      })
    : (call.transcript?.text
        ? call.transcript.text
            .split("\n")
            .filter((l) => l.trim().length > 0)
            .map((line, idx) => {
              const isCustomer = /^(müşteri|musteri|customer)\s*:/i.test(line);
              const cleanText = cleanSpeakerPrefix(line);
              return {
                id: idx,
                isCustomer,
                text: cleanText,
                time: null,
              };
            })
        : []);

  return (
    <div className="space-y-6">
      {/* Üst Bar / Geri Dönüş */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/admin/calls"
          className="text-sm font-medium text-sky-700 hover:underline px-2 py-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
        >
          ← Çağrı listesine dön
        </Link>

        <div className="flex flex-wrap items-center gap-2">
          {inProgress && (
            <span className="inline-flex items-center rounded-md bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-800 border border-sky-200">
              ⏳ Analiz sürüyor
            </span>
          )}
          {!inProgress && analysisStatus === "kismi" && (
            <span className="inline-flex items-center rounded-md bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 border border-amber-200">
              ⚠️ Kısmi Analiz
            </span>
          )}
          {!inProgress && analysisStatus === "basarisiz" && (
            <span className="inline-flex items-center rounded-md bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-800 border border-red-200">
              ✕ Analiz Başarısız
            </span>
          )}
          {!inProgress && analysisStatus === "tamam" && (
            <span className="inline-flex items-center rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800 border border-emerald-200">
              ✓ Analiz Tamamlandı
            </span>
          )}
          {urgency === "acil" && (
            <span className="inline-flex items-center rounded-md bg-red-100 px-2.5 py-1 text-xs font-bold text-red-700 border border-red-300 animate-pulse">
              🚨 ACİL SERVİS
            </span>
          )}
          {callType && (
            <span className="inline-flex rounded-md bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700 border border-transparent">
              {labelOf(CALL_TYPE_LABELS, callType as CallType)}
            </span>
          )}
          {/* Yeniden Analiz Et Butonu (#110) */}
          <ReanalyzeButton callId={call.id} currentState={call.state} variant="header" />
        </div>
      </div>

      {/* Kısmi Analiz & Hata Durumu Uyarısı */}
      {isPartial && !inProgress && (
        <div className="rounded-xl border border-amber-300 bg-amber-50/90 p-4 shadow-sm">
          <div className="flex items-start gap-3">
            <span className="text-xl" aria-hidden="true">⚠️</span>
            <div className="flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-amber-900">
                  Kısmi Analiz — Bazı Alanlar Üretilemedi
                </h3>
                <ReanalyzeButton callId={call.id} currentState={call.state} variant="banner" />
              </div>
              <p className="mt-0.5 text-xs text-amber-800">
                Bu görüşmenin analizinde bazı bölümler üretilemedi; diğer bölümlerin sonuçları geçerlidir.
              </p>
              {errorEntries.length > 0 ? (
                <ul className="mt-2.5 space-y-1 rounded-lg bg-amber-100/70 p-2.5 text-xs text-amber-950 border border-amber-200">
                  {errorEntries.map((e, idx) => (
                    <li key={idx} className="flex items-baseline gap-1.5" title={e.detail}>
                      <span className="font-bold">• {e.section}:</span>
                      <span>{e.message}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-amber-700 italic">
                  Eksik alan uyarısı: Bazı analiz parametreleri tespit edilemediğinden kısmi kayıt oluşturuldu.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Başlık ve Temel Bilgiler */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {call.customer_name ?? "İsimsiz Müşteri"} — {call.boat_name || "Tekne Bilgisi Yok"}
            </h1>
            <p className="mt-1 text-xs text-gray-500">
              {call.customer_phone ?? "Telefon Yok"} • {call.boat_model || "Model Belirtilmedi"} • {call.marina ?? "Marina Belirtilmedi"} •{" "}
              {new Date(call.started_at).toLocaleString("tr-TR", { timeZone: "Europe/Istanbul" })}
            </p>
          </div>
          {/* Gerçek Analiz Güveni */}
          {confidencePercent !== null && (
            <div className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-1.5 border border-emerald-200">
              <span className="text-xs text-emerald-800 font-medium">Analiz Güveni:</span>
              <span className="text-sm font-bold text-emerald-700">
                %{confidencePercent}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 2 Kolonlu Düzen */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* SOL: Ses Oynatıcı, Transkript, Özet & Satış Analizi (7 Kolon) */}
        <div className="space-y-6 lg:col-span-7">
          {/* Gerçek HTML5 Ses Oynatıcı (#89) */}
          <AudioPlayer
            key={call.id}
            callId={call.id}
            hasAudio={Boolean(call.has_audio)}
            durationSec={durationSec}
          />

          {/* Transkript Konuşma Balonları */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-600">
                Konuşma Transkripti (Ayrıştırılmış)
              </h2>
              <span className="text-xs text-gray-500">
                {segments.length} segment
              </span>
            </div>

            {segments.length > 0 ? (
              <div className="space-y-3">
                {segments.map((seg) => (
                  <div
                    key={seg.id}
                    className={`flex ${seg.isCustomer ? "justify-start" : "justify-end"}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl p-3 text-sm shadow-sm ${
                        seg.isCustomer
                          ? "bg-slate-100 text-slate-800 rounded-tl-sm border border-slate-200"
                          : "bg-sky-700 text-white rounded-tr-sm"
                      }`}
                    >
                      <div
                        className={`mb-1 flex items-center justify-between gap-3 text-[11px] font-bold ${
                          seg.isCustomer ? "text-slate-600" : "text-sky-100"
                        }`}
                      >
                        <span>
                          {seg.isCustomer ? "⚓ Müşteri" : "🛠 Temsilci (Miço Usta)"}
                        </span>
                        {seg.time && (
                          <span className="font-mono text-[10px] font-normal">
                            {seg.time}
                          </span>
                        )}
                      </div>
                      <p className="leading-relaxed whitespace-pre-wrap">{seg.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg bg-gray-50 p-6 text-center text-sm text-gray-500">
                Ses kaydı transkripti henüz oluşturulmadı (cevapsız çağrı veya işleniyor).
              </div>
            )}
          </div>

          {/* AI Görüşme Özeti */}
          <PlaceholderCard title="AI Görüşme Özeti & Önemli Noktalar">
            <p className="text-sm text-gray-800 leading-relaxed">
              {summary?.summary ?? (inProgress ? "Özet hazırlanıyor..." : "Bu görüşme için özet üretilemedi.")}
            </p>
            {summary?.key_points && summary.key_points.length > 0 && (
              <ul className="mt-3 list-inside list-disc space-y-1 text-xs text-gray-600">
                {summary.key_points.map((point, i) => (
                  <li key={i}>{point}</li>
                ))}
              </ul>
            )}
          </PlaceholderCard>

          {/* Satış Analizi Kartı */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 pb-3 mb-4">
              <div>
                <h2 className="text-base font-bold text-gray-900">
                  Satış Analizi
                </h2>
                <p className="text-xs text-gray-500">
                  Yapay zekâ destekli satış dönüşüm ve kayıp analizi
                </p>
              </div>

              {sales?.outcome && (
                <span
                  className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-bold ${SALES_OUTCOME_BADGE[sales.outcome] || "bg-gray-100 text-gray-700"}`}
                >
                  {sales.outcome === "satisa_donustu" && "✓ "}
                  {sales.outcome === "kaybedildi" && "✕ "}
                  {sales.outcome === "beklemede" && "⏳ "}
                  {labelOf(SALES_OUTCOME_LABELS, sales.outcome)}
                </span>
              )}
            </div>

            {sales ? (
              <div className="space-y-3.5">
                {/* Sonuç Özeti */}
                <div className="rounded-lg bg-slate-50 border border-slate-100 p-3">
                  <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Satış Durumu
                  </span>
                  <p className="mt-0.5 text-sm font-semibold text-slate-900">
                    {labelOf(SALES_OUTCOME_LABELS, sales.outcome)}
                  </p>
                </div>

                {/* Kayıp Nedeni */}
                {(sales.outcome === "kaybedildi" || sales.loss_reason) && (
                  <div className="rounded-lg bg-red-50 border border-red-200 p-3">
                    <span className="block text-[11px] font-bold uppercase tracking-wider text-red-700">
                      Kayıp Nedeni
                    </span>
                    <p className="mt-0.5 text-sm font-bold text-red-900">
                      {labelOf(LOSS_REASON_LABELS, sales.loss_reason as LossReason | null | undefined)}
                    </p>
                  </div>
                )}

                {/* Dayanak / Alıntılar */}
                {sales.evidence && (
                  <div className="rounded-lg bg-amber-50/70 border border-amber-200/80 p-3">
                    <span className="block text-[11px] font-bold uppercase tracking-wider text-amber-800 mb-1">
                      📌 Satış Analizi Dayanağı &amp; Alıntılar
                    </span>
                    <p className="text-xs text-amber-950 leading-relaxed italic">
                      &ldquo;{sales.evidence}&rdquo;
                    </p>
                  </div>
                )}

                {/* Satış Analiz Güveni */}
                {sales.confidence != null && (
                  <div className="flex items-center justify-between text-xs text-gray-500 pt-2 border-t border-gray-100">
                    <span>Satış Analizi Güveni:</span>
                    <span className="font-semibold text-emerald-700">
                      %{Math.round(sales.confidence <= 1 ? sales.confidence * 100 : sales.confidence)}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-lg bg-gray-50 p-4 text-center text-xs text-gray-500">
                Bu çağrı için henüz satış analizi oluşturulmadı.
              </div>
            )}
          </div>
        </div>

        {/* SAĞ: 7 CRM Alanı & Servis Emri Önerisi (#113: Onayla, Reddet, Düzenle) (5 Kolon) */}
        <div className="space-y-6 lg:col-span-5">
          <CrmSuggestionCard
            suggestion={{
              callId: call.id,
              caller: call.customer_name ?? "İsimsiz",
              boatName: call.boat_name ?? undefined,
              requestCategory: crm?.request_category ?? null,
              location: crm?.location ?? null,
              problem: crm?.problem ?? null,
              serviceMode: crm?.service_mode ?? null,
              urgency: crm?.urgency ?? null,
              potentialJob: crm?.potential_job ?? null,
              nextAction: crm?.next_action ?? null,
              evidence: crm?.evidence ?? {},
              reviewStatus: "bekliyor",
              editedFields: {},
              serviceOrderId: null,
            }}
            variant="detail"
          />
        </div>
      </div>
    </div>
  );
}
