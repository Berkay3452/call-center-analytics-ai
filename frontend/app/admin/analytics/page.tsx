import { PlaceholderCard } from "@/components/PlaceholderCard";
import { fetchKpis } from "@/lib/api";

export const metadata = { title: "Çağrı Analitiği | Miço Usta" };

export default async function AnalyticsPage() {
  const kpis = await fetchKpis();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Çağrı Analitiği</h1>

      {/* KPI Kartları */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
          >
            <p className="text-xs text-gray-500">{kpi.label}</p>
            <p className="mt-1 text-xl font-bold text-gray-900">
              {kpi.value}
              {kpi.unit && (
                <span className="ml-1 text-sm font-normal text-gray-400">
                  {kpi.unit}
                </span>
              )}
            </p>
            {kpi.changePercent !== undefined && (
              <p
                className={`mt-1 text-xs font-medium ${
                  kpi.changePercent >= 0 ? "text-green-600" : "text-red-600"
                }`}
              >
                {kpi.changePercent >= 0 ? "▲" : "▼"}{" "}
                {Math.abs(kpi.changePercent)}%
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Grafik alanı (ileride chart kütüphanesi buraya gelecek) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PlaceholderCard title="Günlük Çağrı Trendi">
          <div className="h-48 rounded-lg bg-gray-50 flex items-center justify-center text-gray-400 text-sm">
            📈 Grafik — Recharts veya Chart.js ile doldurulacak
          </div>
        </PlaceholderCard>
        <PlaceholderCard title="Duygu Dağılımı">
          <div className="h-48 rounded-lg bg-gray-50 flex items-center justify-center text-gray-400 text-sm">
            🥧 Pasta grafik — duygu analizi
          </div>
        </PlaceholderCard>
      </div>

      {/* Çağrı listesi özeti */}
      <PlaceholderCard title="Son Çağrılar">
        <div className="h-32 rounded-lg bg-gray-50 flex items-center justify-center text-gray-400 text-sm">
          📋 Tablo — /admin/calls sayfasına tam liste bağlanacak
        </div>
      </PlaceholderCard>
    </div>
  );
}
