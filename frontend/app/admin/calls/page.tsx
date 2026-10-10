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
  type CallType,
  type Urgency,
} from "@/lib/types";

export const metadata = { title: "Çağrılar | Miço Usta" };

const URGENCY_BADGE: Record<Urgency, string> = {
  acil: "bg-red-100 text-red-700 border-red-300 font-bold",
  yuksek: "bg-orange-100 text-orange-700 border-orange-200",
  normal: "bg-blue-50 text-blue-700 border-blue-200",
  dusuk: "bg-gray-100 text-gray-600 border-gray-200",
};

const CALL_TYPE_BADGE: Record<CallType, string> = {
  acil: "bg-red-50 text-red-600",
  servis: "bg-sky-50 text-sky-700",
  teklif: "bg-purple-50 text-purple-700",
  yeni_musteri: "bg-emerald-50 text-emerald-700",
  bilgi: "bg-gray-50 text-gray-600",
};

const ANALYSIS_STATUS_BADGE: Record<AnalysisStatus, string> = {
  tamam: "bg-emerald-50 text-emerald-700 border-emerald-200",
  kismi: "bg-amber-50 text-amber-700 border-amber-200",
  basarisiz: "bg-red-50 text-red-700 border-red-200",
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

export default async function CallsPage() {
  const calls = await fetchCalls();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Çağrılar & Analizler</h1>
          <p className="text-sm text-gray-500">
            Tüm marinalardan gelen sesli görüşmeler ve yapay zekâ analiz sonuçları
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {["Arayan & Tekne", "Marina", "Çağrı Tipi", "Süre", "Aciliyet", "Analiz Durumu", "Satış Durumu", ""].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {calls.map((call) => (
              <tr key={call.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3">
                  <div className="text-sm font-semibold text-gray-900">{call.caller}</div>
                  <div className="text-xs text-gray-500">
                    {call.boatName || "Tekne belirtilmedi"}
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {call.location ?? EMPTY_LABEL}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${call.callType ? CALL_TYPE_BADGE[call.callType] : "bg-gray-50 text-gray-600"}`}
                  >
                    {labelOf(CALL_TYPE_LABELS, call.callType)}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {formatDuration(call.durationSec)}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${call.urgency ? URGENCY_BADGE[call.urgency] : "bg-gray-100 text-gray-600 border-gray-200"}`}
                  >
                    {call.urgency === "acil" && <span className="mr-1">🚨</span>}
                    {labelOf(URGENCY_LABELS, call.urgency)}
                  </span>
                </td>
                {/* Analiz Durumu Sütunu */}
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${ANALYSIS_STATUS_BADGE[call.analysisStatus]}`}
                  >
                    {ANALYSIS_STATUS_ICON[call.analysisStatus]}{" "}
                    {labelOf(ANALYSIS_STATUS_LABELS, call.analysisStatus)}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm">
                  {call.sales.outcome === "satisa_donustu" && (
                    <span className="text-xs font-semibold text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
                      ✓ Satışa Dönüştü
                    </span>
                  )}
                  {call.sales.outcome === "kaybedildi" && (
                    <span className="text-xs font-semibold text-red-700 bg-red-50 px-2 py-0.5 rounded-full">
                      ✕ Kaybedildi ({call.sales.lossReason ? labelOf(LOSS_REASON_LABELS, call.sales.lossReason) : EMPTY_LABEL})
                    </span>
                  )}
                  {call.sales.outcome === "beklemede" && (
                    <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">
                      ⏳ Beklemede
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-sm">
                  <Link
                    href={`/admin/calls/${call.id}`}
                    className="font-medium text-blue-600 hover:text-blue-800 hover:underline"
                  >
                    Detay & CRM →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
