import { Suspense } from "react";
import Link from "next/link";
import { fetchCalls } from "@/lib/api";
import {
  ANALYSIS_STATUS_LABELS,
  CALL_TYPE_LABELS,
  EMPTY_LABEL,
  labelOf,
  LOSS_REASON_LABELS,
  URGENCY_LABELS,
  type AnalysisStatus,
  type Call,
  type CallType,
  type Urgency,
} from "@/lib/types";
import { CallsTableSkeleton } from "@/components/skeletons";

export const metadata = { title: "Çağrılar | Miço Usta" };

const URGENCY_BADGE: Record<Urgency, string> = {
  acil: "bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-300 dark:border-red-900 font-bold",
  yuksek: "bg-orange-100 dark:bg-orange-950/60 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-900",
  normal: "bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-900",
  dusuk: "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700",
};

const CALL_TYPE_BADGE: Record<CallType, string> = {
  acil: "bg-red-50 dark:bg-red-950/60 text-red-600 dark:text-red-300",
  servis: "bg-sky-50 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300",
  teklif: "bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300",
  yeni_musteri: "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300",
  bilgi: "bg-gray-50 dark:bg-slate-800 text-gray-600 dark:text-slate-300",
};

const ANALYSIS_STATUS_BADGE: Record<AnalysisStatus, string> = {
  tamam: "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800",
  kismi: "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800",
  basarisiz: "bg-red-50 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800",
};

const ANALYSIS_STATUS_ICON: Record<AnalysisStatus, string> = {
  tamam: "✓",
  kismi: "⚠",
  basarisiz: "✕",
};

function formatDuration(sec: number): string {
  if (sec === 0) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function CallsPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Çağrılar &amp; Analizler</h1>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            Tüm marinalardan gelen sesli görüşmeler ve yapay zekâ analiz sonuçları
          </p>
        </div>
        <div>
          <Link
            href="/admin/calls/upload"
            className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-sky-700 active:scale-[0.98] transition-all"
          >
            <span>🎙️</span>
            <span>+ Yeni Çağrı Yükle</span>
          </Link>
        </div>
      </div>

      <Suspense fallback={<CallsTableSkeleton />}>
        <CallsListContent />
      </Suspense>
    </div>
  );
}

async function CallsListContent() {
  let calls: Call[] = [];
  let errorMsg: string | null = null;

  try {
    calls = await fetchCalls();
  } catch (err) {
    errorMsg = err instanceof Error ? err.message : "Çağrılar yüklenemedi";
  }

  if (errorMsg) {
    return (
      <div className="rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50 dark:bg-amber-950/40 p-6 text-center shadow-sm">
        <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
          ⚠️ Veriler alınırken bir sorun oluştu: {errorMsg}
        </p>
        <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
          Servise ulaşılamıyor. Lütfen biraz sonra tekrar deneyin; sorun sürerse sistem yöneticinize başvurun.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-slate-800">
        <thead className="bg-gray-50 dark:bg-slate-800/70">
          <tr>
            {["Arayan & Tekne", "Marina", "Çağrı Tipi", "Süre", "Aciliyet", "Analiz Durumu", "Satış Durumu", ""].map((h) => (
              <th
                key={h}
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-slate-800">
          {calls.map((call) => (
            <tr key={call.id} className="hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors">
              <td className="px-4 py-3">
                <div className="text-sm font-semibold text-gray-900 dark:text-slate-100">{call.caller}</div>
                <div className="text-xs text-gray-500 dark:text-slate-400">
                  {call.boatName || "Tekne belirtilmedi"}
                </div>
              </td>
              <td className="px-4 py-3 text-sm text-gray-600 dark:text-slate-300">
                {call.location ?? EMPTY_LABEL}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${call.callType ? CALL_TYPE_BADGE[call.callType] : "bg-gray-50 dark:bg-slate-800 text-gray-600 dark:text-slate-300"}`}
                >
                  {labelOf(CALL_TYPE_LABELS, call.callType)}
                </span>
              </td>
              <td className="px-4 py-3 text-sm text-gray-500 dark:text-slate-400">
                {formatDuration(call.durationSec)}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${call.urgency ? URGENCY_BADGE[call.urgency] : "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700"}`}
                >
                  {call.urgency === "acil" && <span className="mr-1">🚨</span>}
                  {labelOf(URGENCY_LABELS, call.urgency)}
                </span>
              </td>
              {/* Analiz Durumu Sütunu */}
              <td className="px-4 py-3">
                {call.pendingState ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-950/60 px-2.5 py-0.5 text-xs font-semibold text-sky-700 dark:text-sky-300">
                    ⏳ {call.pendingState === "beklemede" ? "Sırada" : "İşleniyor"}
                  </span>
                ) : (
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${ANALYSIS_STATUS_BADGE[call.analysisStatus]}`}
                  >
                    {ANALYSIS_STATUS_ICON[call.analysisStatus]}{" "}
                    {labelOf(ANALYSIS_STATUS_LABELS, call.analysisStatus)}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-sm">
                {call.sales.outcome === "satisa_donustu" && (
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 px-2 py-0.5 rounded-full">
                    ✓ Satışa Dönüştü
                  </span>
                )}
                {call.sales.outcome === "kaybedildi" && (
                  <span className="text-xs font-semibold text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/60 px-2 py-0.5 rounded-full">
                    ✕ Kaybedildi ({call.sales.lossReason ? labelOf(LOSS_REASON_LABELS, call.sales.lossReason) : EMPTY_LABEL})
                  </span>
                )}
                {call.sales.outcome === "beklemede" && (
                  <span className="text-xs font-medium text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 rounded-full">
                    ⏳ Beklemede
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-right text-sm">
                <Link
                  href={`/admin/calls/${call.id}`}
                  className="font-medium text-sky-600 dark:text-sky-400 hover:text-sky-800 dark:hover:text-sky-300 hover:underline"
                >
                  Detay &amp; CRM →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
