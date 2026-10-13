import Link from "next/link";
import { notFound } from "next/navigation";
import { getCallById, getCalls } from "@/lib/api/client";
import type {
  CallDetail,
  Urgency,
  CallType,
  RequestCategory,
  ServiceMode,
  NextAction,
} from "@/lib/api/types";
import { PlaceholderCard } from "@/components/PlaceholderCard";
import {
  CALL_TYPE_LABELS,
  EMPTY_LABEL,
  labelOf,
  NEXT_ACTION_LABELS,
  REQUEST_CATEGORY_LABELS,
  SERVICE_MODE_LABELS,
  URGENCY_LABELS,
} from "@/lib/types";

interface Props {
  params: Promise<{ id: string }>;
}

export async function generateStaticParams() {
  try {
    const res = await getCalls();
    return res.items.map((c) => ({ id: c.id }));
  } catch {
    return [{ id: "11111111-1111-4111-8111-111111111111" }];
  }
}

export async function generateMetadata({ params }: Props) {
  const { id } = await params;
  return { title: `Çağrı Analizi ${id} | Miço Usta` };
}

const URGENCY_COLOR: Record<Urgency, { bg: string; text: string; border: string }> = {
  acil: { bg: "bg-red-50", text: "text-red-700", border: "border-red-300" },
  yuksek: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-300" },
  normal: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-300" },
  dusuk: { bg: "bg-gray-50", text: "text-gray-700", border: "border-gray-300" },
};

export default async function CallDetailPage({ params }: Props) {
  const { id } = await params;
  let call: CallDetail | null = null;

  try {
    call = await getCallById(id);
  } catch {
    notFound();
  }

  if (!call) notFound();

  const crm = call.analysis?.crm;
  const sales = call.analysis?.sales;
  const summary = call.analysis?.summary;
  const classification = call.analysis?.classification;
  const durationSec = call.duration_s ?? 0;

  // Aciliyet çıkarılamadıysa (null) nötr renk kullanılır.
  const urgency = crm?.urgency;
  const urgencyStyle = urgency ? URGENCY_COLOR[urgency] : URGENCY_COLOR.dusuk;
  const callType = classification?.call_type;
  const analysisStatus = call.analysis?.status ?? (call.state === "tamam" ? "tamam" : "kismi");

  return (
    <div className="space-y-6">
      {/* Üst Bar / Geri Dönüş */}
      <div className="flex items-center justify-between">
        <Link
          href="/admin/calls"
          className="text-sm font-medium text-blue-600 hover:underline"
        >
          ← Çağrı listesine dön
        </Link>

        <div className="flex items-center gap-2">
          {analysisStatus === "kismi" && (
            <span className="inline-flex items-center rounded-md bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 border border-amber-200">
              ⚠️ Kısmi Analiz — Eksik Bilgi Mevcut
            </span>
          )}
          {analysisStatus === "basarisiz" && (
            <span className="inline-flex items-center rounded-md bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-800 border border-red-200">
              ✕ Analiz Başarısız — Transkript Eksik
            </span>
          )}
          {analysisStatus === "tamam" && (
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
            <span className="inline-flex rounded-md bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">
              {labelOf(CALL_TYPE_LABELS, callType as CallType)}
            </span>
          )}
        </div>
      </div>

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
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Analiz Güveni:</span>
            <span className="text-sm font-bold text-emerald-600">
              %{Math.round((sales?.confidence ?? 0) * 100)}
            </span>
          </div>
        </div>
      </div>

      {/* 2 Kolonlu Düzen: Sol = Ses & Transkript / Sağ = 7 Alanlı CRM & Servis Emri */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* SOL: Ses Oynatıcı & Transkript (7 Kolon) */}
        <div className="space-y-6 lg:col-span-7">
          {/* Ses Oynatıcı Dalga Formu */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-600">
                Ses Kaydı & Dalga Formu
              </h2>
              <span className="text-xs font-mono text-gray-500">
                {Math.floor(durationSec / 60)}:
                {String(durationSec % 60).padStart(2, "0")}
              </span>
            </div>

            {/* Simüle Edilmiş Waveform */}
            <div className="flex h-14 items-center justify-between gap-1 rounded-lg bg-slate-900 px-4 py-2">
              <div className="text-slate-200">▶</div>
              <div className="flex flex-1 items-center justify-center gap-1 px-3">
                {[
                  30, 60, 45, 80, 20, 95, 65, 40, 75, 90, 35, 60, 85, 45, 70, 30,
                  90, 50, 40, 80, 60, 35, 70, 95, 40, 20, 50, 65, 85, 30,
                ].map((height, i) => (
                  <span
                    key={i}
                    style={{ height: `${height}%` }}
                    className={`w-1 rounded-full transition-all ${
                      i < 12 ? "bg-sky-400" : "bg-slate-600"
                    }`}
                  />
                ))}
              </div>
              <span className="text-xs font-mono text-sky-400">01:14</span>
            </div>
          </div>

          {/* Transkript Konuşma Balonları */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-600">
              Konuşma Transkripti (Ayrıştırılmış)
            </h2>

            {call.transcript?.text ? (
              <div className="space-y-3">
                {call.transcript.text.split("\n").map((line, idx) => {
                  const isCustomer = line.startsWith("Müşteri:");
                  const text = line.replace(/^(Müşteri:|Temsilci:)\s*/, "");

                  return (
                    <div
                      key={idx}
                      className={`flex ${isCustomer ? "justify-start" : "justify-end"}`}
                    >
                      <div
                        className={`max-w-[85%] rounded-2xl p-3 text-sm shadow-sm ${
                          isCustomer
                            ? "bg-slate-100 text-slate-800 rounded-tl-sm border border-slate-200"
                            : "bg-sky-600 text-white rounded-tr-sm"
                        }`}
                      >
                        <div
                          className={`mb-1 text-[11px] font-bold ${
                            isCustomer ? "text-slate-600" : "text-sky-200"
                          }`}
                        >
                          {isCustomer ? "⚓ Müşteri (Tekne Sahibi)" : "🛠 Miço Usta Temsilcisi"}
                        </div>
                        <p>{text}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-lg bg-gray-50 p-6 text-center text-sm text-gray-400">
                Ses kaydı transkripti henüz oluşturulmadı (cevapsız çağrı).
              </div>
            )}
          </div>

          {/* AI Görüşme Özeti */}
          <PlaceholderCard title="AI Görüşme Özeti & Önemli Noktalar">
            <p className="text-sm text-gray-800 leading-relaxed">
              {summary?.summary ?? "Özet hazırlanıyor..."}
            </p>
            {summary?.key_points && summary.key_points.length > 0 && (
              <ul className="mt-3 list-inside list-disc space-y-1 text-xs text-gray-600">
                {summary.key_points.map((point, i) => (
                  <li key={i}>{point}</li>
                ))}
              </ul>
            )}
          </PlaceholderCard>
        </div>

        {/* SAĞ: 7 CRM Alanı & Servis Emri Önerisi (5 Kolon) */}
        <div className="space-y-6 lg:col-span-5">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between border-b pb-3 mb-4">
              <div>
                <h2 className="text-base font-bold text-gray-900">
                  CRM Kayıt Önerisi
                </h2>
                <p className="text-xs text-gray-500">
                  7 Temel Alan (Miço Usta AI Çıkarımı)
                </p>
              </div>
              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
                7 / 7 Alan
              </span>
            </div>

            <div className="space-y-3">
              {/* 1. Müşteri Talebi */}
              <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <span className="block text-[11px] font-semibold text-gray-500 uppercase">
                  1. Müşteri Talebi (Kategori)
                </span>
                <span className="mt-0.5 block text-sm font-semibold text-gray-900">
                  {labelOf(REQUEST_CATEGORY_LABELS, crm?.request_category as RequestCategory | null | undefined)}
                </span>
              </div>

              {/* 2. Lokasyon */}
              <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <span className="block text-[11px] font-semibold text-gray-500 uppercase">
                  2. Marina / Lokasyon
                </span>
                <span className="mt-0.5 block text-sm font-semibold text-gray-900">
                  📍 {crm?.location ?? EMPTY_LABEL}
                </span>
              </div>

              {/* 3. Problem Tanımı */}
              <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <span className="block text-[11px] font-semibold text-gray-500 uppercase">
                  3. Problem Tanımı
                </span>
                <p className="mt-0.5 text-sm text-gray-800">
                  {crm?.problem ?? EMPTY_LABEL}
                </p>
              </div>

              {/* 4. Hizmet Biçimi */}
              <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <span className="block text-[11px] font-semibold text-gray-500 uppercase">
                  4. Talep / Hizmet Biçimi
                </span>
                <span className="mt-0.5 block text-sm font-semibold text-gray-900">
                  ⚙️ {labelOf(SERVICE_MODE_LABELS, crm?.service_mode as ServiceMode | null | undefined)}
                </span>
              </div>

              {/* 5. Aciliyet */}
              <div className={`rounded-lg border p-3 ${urgencyStyle.bg} ${urgencyStyle.border}`}>
                <span className="block text-[11px] font-semibold text-gray-500 uppercase">
                  5. Aciliyet Seviyesi
                </span>
                <span className={`mt-0.5 block text-sm font-bold ${urgencyStyle.text}`}>
                  {crm?.urgency === "acil" && "🚨 "}
                  {labelOf(URGENCY_LABELS, crm?.urgency as Urgency | null | undefined)}
                </span>
              </div>

              {/* 6. Potansiyel İş */}
              <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <span className="block text-[11px] font-semibold text-gray-500 uppercase">
                  6. Doğacak Potansiyel İş
                </span>
                <span className="mt-0.5 block text-sm font-semibold text-gray-900">
                  💼 {crm?.potential_job ?? EMPTY_LABEL}
                </span>
              </div>

              {/* 7. Sonraki Aksiyon / Servis Emri */}
              <div className="rounded-lg border border-sky-200 bg-sky-50 p-3">
                <span className="block text-[11px] font-semibold text-sky-700 uppercase">
                  7. Önerilen Sonraki Aksiyon
                </span>
                <span className="mt-0.5 block text-sm font-bold text-sky-900">
                  📋 {labelOf(NEXT_ACTION_LABELS, crm?.next_action as NextAction | null | undefined)}
                </span>
              </div>
            </div>

            {/* Kanıt Alıntıları */}
            {crm?.evidence && Object.keys(crm.evidence).length > 0 && (
              <div className="mt-4 rounded-lg bg-amber-50/50 p-3 border border-amber-200/60">
                <span className="block text-[11px] font-semibold text-amber-800 uppercase mb-1">
                  🔍 Konuşmadan Kanıt Alıntıları
                </span>
                <div className="space-y-1 text-xs text-amber-900">
                  {Object.entries(crm.evidence).map(([key, val]) => (
                    <div key={key}>
                      <span className="font-semibold text-amber-700">{key}:</span> &ldquo;{val}&rdquo;
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Aksiyon Butonları */}
            <div className="mt-6 space-y-2 border-t pt-4">
              <button
                type="button"
                className="w-full rounded-xl bg-sky-600 px-4 py-3 text-sm font-bold text-white shadow-sm hover:bg-sky-700 transition-colors"
              >
                ✓ Onayla ve Servis Emri Oluştur
              </button>
              <button
                type="button"
                className="w-full rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
              >
                ✕ Öneriyi Reddet / Düzenle
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
