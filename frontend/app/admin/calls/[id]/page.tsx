import { connection } from "next/server";
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
import { CallDetailSkeleton } from "@/components/skeletons";
import { AudioPlayer } from "@/components/AudioPlayer";
import { AnalysisBanner } from "@/components/AnalysisTracker";
import { ReanalyzeButton } from "@/components/ReanalyzeButton";
import { CrmSuggestionCard } from "@/components/crm";
import {
  CALL_TYPE_LABELS,
  labelOf,
  LOSS_REASON_LABELS,
  SALES_OUTCOME_LABELS,
} from "@/lib/types";
import {
  ANALYSIS_SECTION_LABELS,
  ANALYSIS_STATUS_LABELS,
  ANALYSIS_STATUS_TONE,
  describeAnalysis,
} from "@/lib/types";
import { Badge, Card, CardHeader, type Tone } from "@/components/ui";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
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

const SALES_OUTCOME_TONE: Record<SalesOutcomeType, Tone> = {
  satisa_donustu: "success",
  kaybedildi: "danger",
  beklemede: "warning",
};

type TranscriptSpeaker = "firma" | "musteri" | "unknown";

function normalizeSpeaker(speaker: string): TranscriptSpeaker {
  if (/^(customer|musteri|müşteri)$/i.test(speaker)) return "musteri";
  if (/^(rep|firma|temsilci|miço usta)$/i.test(speaker)) return "firma";
  return "unknown";
}

function cleanSpeakerPrefix(text: string): string {
  return text.replace(/^(rep|customer|firma|temsilci|müşteri|musteri|miço usta)\s*:\s*/i, "").trim();
}

export default function CallDetailPage({ params }: Props) {
  return (
    <Suspense fallback={<CallDetailSkeleton />}>
      <CallDetailContent params={params} />
    </Suspense>
  );
}

async function CallDetailContent({ params }: Props) {
  await connection();
  const { id } = await params;
  let call: CallDetail | null = null;

  try {
    call = await getCallById(id);
  } catch (err) {
    if (isApiError(err) && err.status === 404) notFound();
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <h2 className="text-base font-semibold text-red-900">Çağrı Detayı Yüklenemedi</h2>
        <p className="mt-1 text-sm text-red-700">
          {err instanceof Error
            ? err.message
            : "Sunucuya bağlanılamadı. Ağ bağlantınızı veya backend durumunu kontrol edin."}
        </p>
        <Link
          href="/admin/calls"
          className="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline"
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

  // Durum etiketi/rengi tek kaynaktan (lib/types); güven yüzdesi yalnızca tam analizde gösterilir.
  const { missing: missingSections } = describeAnalysis(analysisStatus, call.analysis);
  // Bölümü üretilemeyen ajanın skoru gösterilmez ("Hesaplanamadı").
  const classificationConfidence = missingSections.includes(ANALYSIS_SECTION_LABELS.classification)
    ? null
    : classification?.confidence;
  const salesConfidence = missingSections.includes(ANALYSIS_SECTION_LABELS.sales) ? null : sales?.confidence;

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

  const isPartial = analysisStatus !== "tamam" || errorEntries.length > 0;

  // API, transcript_segments kayıtlarını transcript.segments olarak sunar.
  const sourceSegments = call.transcript?.segments?.length
    ? call.transcript.segments
    : (call.transcript?.text ?? "").split("\n").filter((line) => line.trim()).map((text) => ({
        speaker: text.match(/^([^:]+)\s*:/)?.[1]?.trim() ?? "unknown",
        text,
      }));
  const segments: Array<{ speaker: TranscriptSpeaker; text: string }> = [];
  for (const segment of sourceSegments) {
    const speaker = normalizeSpeaker(segment.speaker);
    const text = cleanSpeakerPrefix(segment.text);
    if (!text) continue;
    const previous = segments.at(-1);
    if (previous?.speaker === speaker && speaker !== "unknown") {
      previous.text += `\n${text}`;
    } else {
      segments.push({ speaker, text });
    }
  }

  const analysisBadge = inProgress
    ? { tone: "brand" as Tone, text: "Analiz sürüyor" }
    : {
        tone: ANALYSIS_STATUS_TONE[analysisStatus] as Tone,
        text: `Analiz: ${ANALYSIS_STATUS_LABELS[analysisStatus]}`,
      };

  return (
    <div className="space-y-6">
      <Link href="/admin/calls" className="inline-block text-sm font-medium text-brand-700 hover:underline">
        ← Çağrı listesine dön
      </Link>

      <AnalysisBanner initial={{ call_id: call.id, state: call.state, stage: call.stage, updated_at: call.updated_at, analysis_version: call.analysis?.version }} />

      {/* Özet: kim, ne zaman, durum */}
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold">
              {call.customer_name ?? "İsimsiz Müşteri"} — {call.boat_name || "Tekne bilgisi yok"}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {call.customer_phone ?? "Telefon yok"} · {call.boat_model || "Model belirtilmedi"} ·{" "}
              {call.marina ?? "Marina belirtilmedi"} ·{" "}
              {new Date(call.started_at).toLocaleString("tr-TR", { timeZone: "Europe/Istanbul" })}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={analysisBadge.tone}>{analysisBadge.text}</Badge>
            {urgency === "acil" && <Badge tone="danger">Acil servis</Badge>}
            {callType && <Badge>{labelOf(CALL_TYPE_LABELS, callType as CallType)}</Badge>}
            {/* Kısmi/başarısız analizde aynı eylem uyarı kutusunda sunulur; iki kez gösterilmez */}
            {!(isPartial && !inProgress) && (
              <ReanalyzeButton callId={call.id} currentState={call.state} variant="header" />
            )}
          </div>
        </div>
      </Card>

      {/* İki ayrı ajanın güven skoru tek bölümde, aynı görünümle */}
      <Card>
        <CardHeader
          title="Analiz güveni"
          description="Her skor, ilgili yapay zekâ ajanının kendi kararından ne kadar emin olduğunu gösterir; iki skor birbirinden bağımsızdır."
        />
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <ConfidenceMeter
            title="Çağrı türü güveni"
            hint="Çağrı Sınıflandırma ajanının, çağrının türünü (ör. servis talebi, fiyat sorusu) doğru belirlediğinden ne kadar emin olduğunu gösterir."
            value={classificationConfidence}
            pending={inProgress}
          />
          <ConfidenceMeter
            title="Satış sonucu güveni"
            hint="Satış Analiz ajanının, satış sonucunu (satıldı, kaybedildi, takipte…) doğru belirlediğinden ne kadar emin olduğunu gösterir."
            value={salesConfidence}
            pending={inProgress}
          />
        </div>
      </Card>

      {/* Kısmi / başarısız analiz uyarısı: eksik bölümler adlandırılır */}
      {isPartial && !inProgress && (
        <Card className="border-amber-300 bg-amber-50">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-amber-900">
              {analysisStatus === "basarisiz" ? "Analiz tamamlanamadı" : "Analiz kısmen tamamlandı"}
            </h2>
            <ReanalyzeButton callId={call.id} currentState={call.state} variant="banner" />
          </div>
          <p className="mt-1 text-sm text-amber-800">
            {missingSections.length > 0
              ? `${missingSections.join(", ")} üretilemedi; diğer bölümlerin sonuçları geçerlidir. Yeniden analiz ederek deneyebilirsiniz.`
              : "Bazı bölümler üretilemedi; diğer bölümlerin sonuçları geçerlidir. Yeniden analiz ederek deneyebilirsiniz."}
          </p>
          {errorEntries.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm text-amber-950">
              {errorEntries.map((e, idx) => (
                <li key={idx} title={e.detail}>
                  <span className="font-medium">{e.section}:</span> {e.message}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* Üstte: özet ve satış analizi solda, CRM alanları sağda */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-7">
          <Card>
            <CardHeader title="Görüşme Özeti" />
            <p className="text-sm leading-relaxed text-slate-800">
              {summary?.summary ?? (inProgress ? "Özet hazırlanıyor..." : "Bu görüşme için özet üretilemedi.")}
            </p>
            {summary?.key_points && summary.key_points.length > 0 && (
              <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-slate-600">
                {summary.key_points.map((point, i) => (
                  <li key={i}>{point}</li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Satış Analizi"
              action={
                sales?.outcome ? (
                  <Badge tone={SALES_OUTCOME_TONE[sales.outcome] ?? "neutral"}>
                    {labelOf(SALES_OUTCOME_LABELS, sales.outcome)}
                  </Badge>
                ) : undefined
              }
            />
            {sales ? (
              <dl className="space-y-3 text-sm">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Satış Durumu</dt>
                  <dd className="mt-0.5 font-semibold text-brand-800">
                    {labelOf(SALES_OUTCOME_LABELS, sales.outcome)}
                  </dd>
                </div>
                {(sales.outcome === "kaybedildi" || sales.loss_reason) && (
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Kayıp Nedeni</dt>
                    <dd className="mt-0.5 font-semibold text-red-700">
                      {labelOf(LOSS_REASON_LABELS, sales.loss_reason as LossReason | null | undefined)}
                    </dd>
                  </div>
                )}
                {sales.evidence && (
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Dayanak</dt>
                    <dd className="mt-0.5 italic text-slate-700">&ldquo;{sales.evidence}&rdquo;</dd>
                  </div>
                )}
              </dl>
            ) : (
              <p className="text-sm text-slate-500">Bu çağrı için henüz satış analizi oluşturulmadı.</p>
            )}
          </Card>
        </div>

        <div className="lg:col-span-5">
          <CrmSuggestionCard
            suggestion={{
              callId: call.id,
              caller: call.customer_name ?? "İsimsiz",
              boatName: call.boat_name ?? undefined,
              callerPhone: call.customer_phone ?? undefined,
              boatModel: call.boat_model ?? undefined,
              customerId: call.customer_id,
              boatId: call.boat_id,
              matchMethod: call.match_method,
              matchedCustomerName: call.customer_name ?? undefined,
              matchedBoatName: call.boat_name ?? undefined,
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

      {/* Altta: ses kaydı ve konuşma metni */}
      <AudioPlayer
        key={call.id}
        callId={call.id}
        hasAudio={Boolean(call.has_audio)}
        durationSec={durationSec}
      />

      <Card>
        <CardHeader title="Konuşma Metni" />
        {segments.length > 0 ? (
          <div className="space-y-3" role="region" aria-label="Konuşma metni">
            {segments.map((seg, index) => (
              <div key={index} className={`flex ${seg.speaker === "musteri" ? "justify-end" : seg.speaker === "firma" ? "justify-start" : "justify-center"}`}>
                <div
                  data-testid="transcript-bubble"
                  data-speaker={seg.speaker}
                  className={`min-w-0 max-w-[75%] rounded-xl p-3 text-sm ${
                    seg.speaker === "musteri"
                      ? "bg-brand-700 text-white"
                      : seg.speaker === "firma"
                        ? "border border-sky-200 bg-sky-50 text-sky-950"
                        : "border border-slate-200 bg-slate-100 text-slate-700"
                  }`}
                >
                  <p className="mb-1 text-xs font-semibold">
                    {seg.speaker === "musteri" ? "Müşteri" : seg.speaker === "firma" ? "Miço Usta" : "Bilinmeyen konuşmacı"}
                  </p>
                  <p className="whitespace-pre-wrap break-words leading-relaxed">{seg.text}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-lg bg-slate-50 p-6 text-center text-sm text-slate-500">
            Ses kaydı transkripti henüz oluşturulmadı (cevapsız çağrı veya işleniyor).
          </p>
        )}
      </Card>
    </div>
  );
}
