import { PlaceholderCard } from "@/components/PlaceholderCard";
import {
  fetchDailyCalls,
  fetchFailureCategories,
  fetchKpis,
  fetchLossReasons,
  fetchMarinaStats,
} from "@/lib/api";
import { EMPTY_LABEL } from "@/lib/types";

export const metadata = { title: "Çağrı Analitiği Dashboard | Miço Usta" };

export default async function AnalyticsPage() {
  const [kpis, dailyCalls, failureCategories, marinaStats, lossReasons] =
    await Promise.all([
      fetchKpis(),
      fetchDailyCalls(),
      fetchFailureCategories(),
      fetchMarinaStats(),
      fetchLossReasons(),
    ]);

  // Bar grafik ölçekleme: en yüksek değeri 100% kabul et
  const maxCount = Math.max(...dailyCalls.map((d) => d.count), 1);

  return (
    <div className="space-y-6">
      {/* Üst Filtre Barı */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Çağrı Analitiği Dashboard</h1>
          <p className="text-xs text-gray-500">
            Tüm marinalar, sesli görüşme analizleri ve operasyonel KPI göstergeleri
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Marina Seçimi */}
          <select
            defaultValue="all"
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="all">⚓ Tüm Marinalar</option>
            <option value="kalamis">Kalamış Marina</option>
            <option value="gocek">Göcek D-Marin</option>
            <option value="bodrum">Bodrum Milta Marina</option>
            <option value="tuzla">Tuzla Marina</option>
            <option value="yalikavak">Yalıkavak Marina</option>
          </select>

          {/* Tarih Filtresi */}
          <select
            defaultValue="30"
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="7">Son 7 Gün</option>
            <option value="30">Son 30 Gün</option>
            <option value="90">Son 3 Ay (Sezon)</option>
          </select>
        </div>
      </div>

      {/* KPI Kartları Izgarası (7 Kart) */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {kpis.map((kpi) => {
          const isUrgent = kpi.variant === "urgent";
          const isSuccess = kpi.variant === "success";

          return (
            <div
              key={kpi.label}
              className={`rounded-xl border p-4 shadow-sm transition-all ${
                isUrgent
                  ? "border-red-300 bg-red-50/70"
                  : isSuccess
                  ? "border-emerald-200 bg-emerald-50/50"
                  : "border-gray-200 bg-white"
              }`}
            >
              <p
                className={`text-[11px] font-semibold uppercase tracking-wider ${
                  isUrgent ? "text-red-800" : "text-gray-500"
                }`}
              >
                {isUrgent && "🚨 "}
                {kpi.label}
              </p>
              <p
                className={`mt-1 text-2xl font-black ${
                  isUrgent
                    ? "text-red-700"
                    : isSuccess
                    ? "text-emerald-700"
                    : "text-gray-900"
                }`}
              >
                {kpi.value ?? EMPTY_LABEL}
                {kpi.unit && (
                  <span className="ml-1 text-xs font-normal text-gray-400">
                    {kpi.unit}
                  </span>
                )}
              </p>
              {kpi.changePercent !== undefined && (
                <p
                  className={`mt-1 text-[11px] font-bold ${
                    kpi.changePercent >= 0 ? "text-emerald-600" : "text-red-600"
                  }`}
                >
                  {kpi.changePercent >= 0 ? "▲" : "▼"}{" "}
                  {Math.abs(kpi.changePercent)}%
                  <span className="ml-1 font-normal text-gray-400">vs geçen ay</span>
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Günlük Çağrı Trendi Grafiği */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold text-gray-900">Günlük Çağrı Sayısı Trendi</h2>
        <p className="text-xs text-gray-400 mb-5">Son 7 güne ait çağrı hacmi</p>

        <div className="flex items-end gap-3 h-40">
          {dailyCalls.map((day) => {
            const heightPct = Math.round((day.count / maxCount) * 100);
            return (
              <div key={day.date} className="flex flex-1 flex-col items-center gap-1">
                {/* Sayı etiketi */}
                <span className="text-[10px] font-bold text-sky-700">{day.count}</span>
                {/* Bar */}
                <div className="w-full rounded-t-md bg-sky-500 transition-all" style={{ height: `${heightPct}%` }} />
                {/* Gün etiketi */}
                <span className="text-[10px] text-gray-500 font-medium">{day.label ?? EMPTY_LABEL}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3 Temel Analiz Grafiği */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* 1. En Sık Tekne Arızaları */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold text-gray-900">
            En Sık Tekne Arızaları
          </h2>
          <p className="text-xs text-gray-400 mb-4">
            Çağrılardan çıkarılan problem kategorileri
          </p>

          <div className="space-y-3">
            {failureCategories.map((item) => (
              <div key={item.category} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-gray-700">{item.label ?? EMPTY_LABEL}</span>
                  <span className="font-bold text-gray-900">{item.count}</span>
                </div>
                <div className="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
                  <div
                    style={{ width: `${item.pct}%` }}
                    className={`h-full rounded-full ${item.color}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 2. En Yoğun Marinalar */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold text-gray-900">
            En Yoğun Marinalar
          </h2>
          <p className="text-xs text-gray-400 mb-4">
            Lokasyon bazlı çağrı ve servis dağılımı
          </p>

          <div className="space-y-3">
            {marinaStats.map((m) => (
              <div key={m.name} className="flex items-center justify-between border-b pb-2 text-xs">
                <div>
                  <p className="font-semibold text-gray-800">{m.name ?? EMPTY_LABEL}</p>
                  <span className="text-[10px] text-gray-400">{m.pct}% toplam çağrı</span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-sky-700">{m.count} çağrı</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 3. Satış Kaçırma Sebepleri */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold text-gray-900">
            Satış Kaçırma Sebepleri
          </h2>
          <p className="text-xs text-gray-400 mb-4">
            Kaybedilen teklif ve fırsat analizleri
          </p>

          <div className="space-y-3">
            {lossReasons.map((loss) => (
              <div key={loss.reason} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-gray-700">{loss.label ?? EMPTY_LABEL}</span>
                  <span className="font-bold text-gray-900">%{loss.pct} ({loss.count})</span>
                </div>
                <div className="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
                  <div
                    style={{ width: `${loss.pct}%` }}
                    className={`h-full rounded-full ${loss.color}`}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-lg bg-amber-50 p-2.5 border border-amber-200 text-[11px] text-amber-900">
            💡 <strong>Aksiyon:</strong> Fiyat itirazı olan tekliflerde standart kış bakım paketleri önerilmeli.
          </div>
        </div>
      </div>

      {/* Hızlı Erişim: Çağrılar Özeti */}
      <PlaceholderCard title="Son Görüşmeler & Hızlı Servis Emri Geçişi">
        <p className="text-xs text-gray-500 mb-3">
          Detaylı konuşma transkripti ve 7 alanlı CRM kaydı incelemek için Çağrılar sekmesini kullanın.
        </p>
        <div className="h-16 rounded-lg bg-slate-50 flex items-center justify-center text-xs text-slate-500">
          Tüm çağrı kayıtları ve CRM önerileri sistemde aktif olarak işlenmektedir.
        </div>
      </PlaceholderCard>
    </div>
  );
}
