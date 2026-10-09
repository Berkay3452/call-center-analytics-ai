import { fetchCrmSuggestions } from "@/lib/api";
import {
  NEXT_ACTION_LABELS,
  REQUEST_CATEGORY_LABELS,
  SERVICE_MODE_LABELS,
  URGENCY_LABELS,
  type Urgency,
} from "@/lib/types";
import Link from "next/link";

export const metadata = { title: "CRM Kayıt Önerileri | Miço Usta" };

const URGENCY_BADGE: Record<Urgency, string> = {
  acil: "bg-red-100 text-red-700 border-red-300 font-bold",
  yuksek: "bg-orange-100 text-orange-700 border-orange-200",
  normal: "bg-blue-50 text-blue-700 border-blue-200",
  dusuk: "bg-gray-100 text-gray-600 border-gray-200",
};

export default async function CrmPage() {
  const suggestions = await fetchCrmSuggestions();

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            CRM Kayıt ve Servis Emri Önerileri
          </h1>
          <p className="text-sm text-gray-500">
            Çağrılardan yapay zekâ tarafından otomatik çıkarılan 7 alanlı servis kayıtları
          </p>
        </div>
        <span className="rounded-lg bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-800 border border-sky-200">
          {suggestions.length} Bekleyen Öneri
        </span>
      </div>

      <div className="grid grid-cols-1 gap-5">
        {suggestions.map((s) => (
          <div
            key={s.callId}
            className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all hover:border-sky-300"
          >
            {/* Üst Kısım: Arayan, Tekne, Aciliyet ve Buton */}
            <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-gray-900">{s.caller}</h2>
                  {s.boatName && (
                    <span className="text-xs font-medium text-slate-500">
                      • {s.boatName}
                    </span>
                  )}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                  <span>📍 {s.location}</span>
                  <span>•</span>
                  <span>Çağrı ID: {s.callId}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${URGENCY_BADGE[s.urgency]}`}
                >
                  {s.urgency === "acil" && <span className="mr-1">🚨</span>}
                  {URGENCY_LABELS[s.urgency]}
                </span>
                <Link
                  href={`/admin/calls/${s.callId}`}
                  className="rounded-lg bg-sky-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-sky-700 transition-colors"
                >
                  İncele &amp; Onayla →
                </Link>
              </div>
            </div>

            {/* 7 CRM Alanı Izgara Görünümü */}
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  1. Müşteri Talebi (Kategori)
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800">
                  {REQUEST_CATEGORY_LABELS[s.requestCategory]}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  2. Lokasyon / Marina
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800">
                  {s.location}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  3. Problem Tanımı
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800 line-clamp-2">
                  {s.problem}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  4. Hizmet Biçimi
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800">
                  {SERVICE_MODE_LABELS[s.serviceMode]}
                </p>
              </div>

              <div className="rounded-lg bg-slate-50 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  6. Potansiyel İş
                </span>
                <p className="mt-0.5 text-xs font-semibold text-slate-800">
                  {s.potentialJob}
                </p>
              </div>

              <div className="rounded-lg bg-sky-50 border border-sky-100 p-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-sky-600">
                  7. Sonraki Aksiyon / Servis Emri
                </span>
                <p className="mt-0.5 text-xs font-bold text-sky-900">
                  {NEXT_ACTION_LABELS[s.nextAction]}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
