"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getKpiSummary } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { KpiSummary } from "@/lib/api/types";
import {
  EMPTY_LABEL,
  labelOf,
  LOSS_REASON_LABELS,
  LossReason,
  MARINA_OPTIONS,
  REQUEST_CATEGORY_LABELS,
  RequestCategory,
  URGENCY_LABELS,
  Urgency,
} from "@/lib/types";

// Tarih aralığı opsiyonları (Sentetik seed verileri 5-13 Ekim 2026 arasındadır)
const DATE_RANGE_OPTIONS = [
  { value: "30", label: "Son 30 Gün (Varsayılan)" },
  { value: "oct2026", label: "Ekim 2026 (Demo Seed Dönemi)" },
  { value: "7", label: "Son 7 Gün" },
  { value: "90", label: "Son 3 Ay (Sezon)" },
  { value: "365", label: "Son 1 Yıl" },
];

// Kategori bar renkleri
const CATEGORY_COLORS: Record<string, string> = {
  makine: "bg-sky-700",
  mekanik_hidrolik: "bg-sky-400",
  elektrik_elektronik: "bg-blue-600",
  su_sihhi_tesisat: "bg-cyan-500",
  iklimlendirme: "bg-teal-500",
  tekne_guvenligi: "bg-indigo-500",
  temizlik_bakim: "bg-slate-500",
  diger: "bg-gray-400",
};

// Aciliyet bar renkleri ve rozetleri
const URGENCY_STYLES: Record<Urgency, { bar: string; badge: string; text: string }> = {
  acil: { bar: "bg-red-500", badge: "bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-200 dark:border-red-900", text: "text-red-700 dark:text-red-400" },
  yuksek: { bar: "bg-amber-500", badge: "bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-900", text: "text-amber-700 dark:text-amber-400" },
  normal: { bar: "bg-sky-500", badge: "bg-sky-100 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800", text: "text-sky-700 dark:text-sky-400" },
  dusuk: { bar: "bg-slate-400 dark:bg-slate-600", badge: "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700", text: "text-slate-700 dark:text-slate-400" },
};

// Satış kaybı bar renkleri
const LOSS_COLORS: Record<string, string> = {
  fiyat: "bg-red-500",
  gec_donus: "bg-amber-500",
  rakip: "bg-emerald-500",
  takvim: "bg-indigo-500",
  guven: "bg-purple-500",
  diger: "bg-gray-400",
};

/** Belirtilen aralık anahtarına göre ISO tarih aralığı (date_from, date_to) üretir. */
function getDateRange(rangeKey: string): { date_from?: string; date_to?: string } {
  if (rangeKey === "oct2026") {
    return {
      date_from: "2026-10-01",
      date_to: "2026-10-31",
    };
  }

  const days = parseInt(rangeKey, 10);
  if (isNaN(days) || days <= 0) return {};

  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (days - 1));

  const format = (d: Date) => d.toISOString().split("T")[0];
  return {
    date_from: format(start),
    date_to: format(end),
  };
}

/** Tarih dizesini Türkçe gün ve ay formatına dönüştürür (örn: "06 Eki, Pzt"). */
function formatDayLabel(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const day = d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short" });
    const weekday = d.toLocaleDateString("tr-TR", { weekday: "short" });
    return `${day} ${weekday}`;
  } catch {
    return dateStr;
  }
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState<KpiSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<{ message: string; code?: string; requestId?: string | null } | null>(null);
  const [dateRange, setDateRange] = useState<string>("30");
  const [selectedMarina, setSelectedMarina] = useState<string>("all");
  const [reloadKey, setReloadKey] = useState<number>(0);

  const handleRefresh = () => {
    setIsLoading(true);
    setError(null);
    setReloadKey((k) => k + 1);
  };

  const handleDateRangeChange = (newRange: string) => {
    setIsLoading(true);
    setError(null);
    setDateRange(newRange);
  };

  const handleMarinaChange = (newMarina: string) => {
    setIsLoading(true);
    setError(null);
    setSelectedMarina(newMarina);
  };

  useEffect(() => {
    let ignore = false;
    const filter = {
      ...getDateRange(dateRange),
      ...(selectedMarina !== "all" ? { marina: selectedMarina } : {}),
    };

    getKpiSummary(filter)
      .then((res) => {
        if (!ignore) {
          setData(res);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          if (isApiError(err)) {
            setError({
              message: err.message,
              code: err.code,
              requestId: err.requestId,
            });
          } else if (err instanceof Error) {
            setError({ message: err.message, code: "CLIENT_ERROR" });
          } else {
            setError({
              message: "Analitik verileri yüklenirken beklenmeyen bir hata oluştu.",
              code: "UNKNOWN",
            });
          }
        }
      })
      .finally(() => {
        if (!ignore) {
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [dateRange, selectedMarina, reloadKey]);

  // Günlük çağrı grafiği için maksimum değer (0 ise 1 kabul et)
  const dailyCalls = data?.daily_calls ?? [];
  const maxDailyCount = Math.max(...dailyCalls.map((d) => d.count), 1);

  // Kategori dağılımı toplamı
  const categoryEntries = Object.entries(data?.by_category ?? {}) as [RequestCategory, number][];
  const totalCategoryCalls = categoryEntries.reduce((acc, [, val]) => acc + val, 0);

  // Aciliyet dağılımı
  const urgencyEntries = Object.entries(data?.by_urgency ?? {}) as [Urgency, number][];
  const totalUrgencyCalls = urgencyEntries.reduce((acc, [, val]) => acc + val, 0);

  // Satış kaybı dağılımı
  const lossEntries = Object.entries(data?.lost_by_reason ?? {}) as [LossReason, number][];
  const totalLossCount = lossEntries.reduce((acc, [, val]) => acc + val, 0);

  // Marinalar (En yoğun marinalar)
  const marinas = data?.busiest_marinas ?? [];
  const totalMarinaCalls = marinas.reduce((acc, m) => acc + m.count, 0);

  // En sık rastlanan kayıp nedeni ve aksiyon önerisi (yalnızca sayısı 0'dan büyük olanlar)
  const nonZeroLossEntries = lossEntries.filter(([, count]) => count > 0);
  const topLossEntry = nonZeroLossEntries.length > 0
    ? [...nonZeroLossEntries].sort((a, b) => b[1] - a[1])[0]
    : null;
  const topLossReason = topLossEntry ? topLossEntry[0] : null;

  return (
    <div className="space-y-6">
      {/* Üst Filtre Barı */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-gray-200 dark:border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Çağrı Analitiği Dashboard</h1>
          <p className="text-xs text-gray-500 dark:text-slate-400">
            Tüm marinalar, sesli görüşme analizleri ve operasyonel KPI göstergeleri
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Marina Seçimi */}
          <div className="relative">
            <select
              value={selectedMarina}
              onChange={(e) => handleMarinaChange(e.target.value)}
              disabled={isLoading}
              title="Marina bazlı filtreleme"
              className="rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-gray-700 dark:text-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
            >
              <option value="all">⚓ Tüm Marinalar</option>
              {MARINA_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          {/* Tarih Filtresi (date_from & date_to API sorgusu) */}
          <select
            value={dateRange}
            onChange={(e) => handleDateRangeChange(e.target.value)}
            disabled={isLoading}
            className="rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-gray-700 dark:text-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50"
          >
            {DATE_RANGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {/* Yenile Butonu */}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isLoading}
            title="Verileri Yenile"
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-gray-700 dark:text-slate-200 shadow-sm hover:bg-gray-50 dark:hover:bg-slate-700 active:scale-95 transition-all disabled:opacity-50"
          >
            <span className={isLoading ? "animate-spin" : ""}>🔄</span>
            <span className="hidden sm:inline">Yenile</span>
          </button>
        </div>
      </div>

      {/* Hata Durumu (Error State) */}
      {error && !isLoading && (
        <div className="rounded-xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 p-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/60 text-xl text-red-700 dark:text-red-400">
              ⚠️
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-bold text-red-900 dark:text-red-200">
                Veriler Alınırken Bir Hata Oluştu
              </h3>
              <p className="mt-1 text-xs text-red-700 dark:text-red-300">{error.message}</p>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-red-700 dark:text-red-400">
                {error.code && (
                  <span>
                    Hata Kodu: <code className="font-mono font-bold">{error.code}</code>
                  </span>
                )}
                {error.requestId && (
                  <span>
                    İstek ID: <code className="font-mono">{error.requestId}</code>
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={handleRefresh}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-xs font-bold text-white shadow hover:bg-red-700 active:scale-95 transition-all"
              >
                🔄 Yeniden Dene
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Yükleniyor Durumu (Loading Skeleton) */}
      {isLoading && (
        <div className="space-y-6">
          {/* Skeleton KPI Kartları */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {Array.from({ length: 7 }).map((_, i) => (
              <div
                key={i}
                className="h-24 animate-pulse rounded-xl border border-gray-200 dark:border-slate-800 bg-gray-100 dark:bg-slate-900 p-4"
              >
                <div className="h-3 w-16 rounded bg-gray-200 dark:bg-slate-800 mb-3" />
                <div className="h-7 w-12 rounded bg-gray-200 dark:bg-slate-700" />
              </div>
            ))}
          </div>

          {/* Skeleton Günlük Trend Grafiği */}
          <div className="h-48 animate-pulse rounded-xl border border-gray-200 dark:border-slate-800 bg-gray-100 dark:bg-slate-900 p-5">
            <div className="h-4 w-44 rounded bg-gray-200 dark:bg-slate-700 mb-2" />
            <div className="h-3 w-28 rounded bg-gray-200 dark:bg-slate-800 mb-6" />
            <div className="flex h-28 items-end gap-3">
              {Array.from({ length: 7 }).map((_, i) => (
                <div
                  key={i}
                  className="flex-1 rounded-t-md bg-gray-200 dark:bg-slate-800"
                  style={{ height: `${30 + (i * 12) % 60}%` }}
                />
              ))}
            </div>
          </div>

          {/* Skeleton 3 Kolon */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-64 animate-pulse rounded-xl border border-gray-200 dark:border-slate-800 bg-gray-100 dark:bg-slate-900 p-5 space-y-4"
              >
                <div className="h-4 w-36 rounded bg-gray-200 dark:bg-slate-700" />
                <div className="h-3 w-48 rounded bg-gray-200 dark:bg-slate-800" />
                <div className="space-y-3 pt-2">
                  <div className="h-4 w-full rounded bg-gray-200 dark:bg-slate-800" />
                  <div className="h-4 w-full rounded bg-gray-200 dark:bg-slate-800" />
                  <div className="h-4 w-full rounded bg-gray-200 dark:bg-slate-800" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Boş Durum (Empty State) */}
      {!isLoading && !error && data && data.total_calls === 0 && (
        <div className="rounded-2xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-12 text-center shadow-sm">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-sky-50 dark:bg-sky-950/60 text-3xl">
            📊
          </div>
          <h2 className="mt-4 text-base font-bold text-gray-900 dark:text-slate-100">
            Henüz çağrı verisi bulunmuyor
          </h2>
          <p className="mx-auto mt-2 max-w-md text-xs text-gray-500 dark:text-slate-400">
            Seçili tarih aralığında ({data.period_start} — {data.period_end}) sisteme kayıtlı veya
            analizi tamamlanmış çağrı kaydı yer almamaktadır.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => handleDateRangeChange("365")}
              className="rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-xs font-semibold text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors"
            >
              Son 1 Yıllık Verileri Gör
            </button>
            <Link
              href="/admin/calls/upload"
              className="inline-flex items-center gap-2 rounded-lg bg-sky-700 px-4 py-2 text-xs font-bold text-white shadow hover:bg-sky-800 transition-colors"
            >
              <span>🎙️</span>
              <span>+ Yeni Çağrı Yükle</span>
            </Link>
          </div>
        </div>
      )}

      {/* Veri Görselleştirme (Gerçek KPI'lar) */}
      {!isLoading && !error && data && data.total_calls > 0 && (
        <div className="space-y-6">
          {/* Üst KPI Kartları Izgarası (7 Kart) */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {/* 1. Gelen Çağrı (total_calls) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                Gelen Çağrı
              </p>
              <p className="mt-1 text-2xl font-black text-gray-900 dark:text-slate-100">
                {data.total_calls.toLocaleString("tr-TR")}
                <span className="ml-1 text-xs font-normal text-gray-500 dark:text-slate-400">adet</span>
              </p>
              <p className="mt-1 text-[11px] text-gray-500 dark:text-slate-400">
                {data.analyzed_calls} analiz edildi
              </p>
            </div>

            {/* 2. Yeni Müşteri (new_customers) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                Yeni Müşteri
              </p>
              <p className="mt-1 text-2xl font-black text-sky-700 dark:text-sky-400">
                {data.new_customers.toLocaleString("tr-TR")}
                <span className="ml-1 text-xs font-normal text-gray-500 dark:text-slate-400">tekne</span>
              </p>
              <p className="mt-1 text-[11px] font-semibold text-sky-700 dark:text-sky-400">
                İlk kez arayanlar
              </p>
            </div>

            {/* 3. Servis Talebi (service_requests) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                Servis Talebi
              </p>
              <p className="mt-1 text-2xl font-black text-indigo-700 dark:text-indigo-400">
                {data.service_requests.toLocaleString("tr-TR")}
                <span className="ml-1 text-xs font-normal text-gray-500 dark:text-slate-400">adet</span>
              </p>
              <p className="mt-1 text-[11px] text-gray-500 dark:text-slate-400">
                Bakım &amp; Onarım
              </p>
            </div>

            {/* 4. Teklif Talebi (quote_requests) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                Teklif Talebi
              </p>
              <p className="mt-1 text-2xl font-black text-purple-700 dark:text-purple-400">
                {data.quote_requests.toLocaleString("tr-TR")}
                <span className="ml-1 text-xs font-normal text-gray-500 dark:text-slate-400">adet</span>
              </p>
              <p className="mt-1 text-[11px] text-gray-500 dark:text-slate-400">
                Fiyat &amp; Proje
              </p>
            </div>

            {/* 5. Acil Servis (urgent_requests - 🚨 Kırmızı Vurgu) */}
            <div className="rounded-xl border border-red-300 dark:border-red-900/60 bg-red-50/70 dark:bg-red-950/40 p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-red-800 dark:text-red-300">
                🚨 Acil Servis
              </p>
              <p className="mt-1 text-2xl font-black text-red-700 dark:text-red-400">
                {data.urgent_requests.toLocaleString("tr-TR")}
                <span className="ml-1 text-xs font-normal text-red-400 dark:text-red-500">adet</span>
              </p>
              <p className="mt-1 text-[11px] font-bold text-red-700 dark:text-red-400">
                Acil müdahale
              </p>
            </div>

            {/* 6. Satışa Dönüş Oranı (converted_sales / conversion_rate - ✓ Yeşil Vurgu) */}
            <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/40 p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                Satışa Dönüşen
              </p>
              <p className="mt-1 text-2xl font-black text-emerald-700 dark:text-emerald-400">
                {data.conversion_rate != null
                  ? `%${Math.round(data.conversion_rate * 100)}`
                  : EMPTY_LABEL}
              </p>
              <p className="mt-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                {data.converted_sales} başarılı satış
              </p>
            </div>

            {/* 7. Ort. Cevap Süresi (avg_answer_delay_s) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                Ort. Yanıt Süresi
              </p>
              <p className="mt-1 text-2xl font-black text-amber-700 dark:text-amber-400">
                {data.avg_answer_delay_s != null
                  ? `${Math.round(data.avg_answer_delay_s)}`
                  : EMPTY_LABEL}
                {data.avg_answer_delay_s != null && (
                  <span className="ml-1 text-xs font-normal text-gray-500 dark:text-slate-400">sn</span>
                )}
              </p>
              <p className="mt-1 text-[11px] text-gray-500 dark:text-slate-400">
                Santral bekleme
              </p>
            </div>
          </div>

          {/* Günlük Çağrı Trendi Grafiği (daily_calls - boş günler için 0 gösterimi) */}
          <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between mb-4">
              <div>
                <h2 className="text-sm font-bold text-gray-900 dark:text-slate-100">Günlük Çağrı Sayısı Trendi</h2>
                <p className="text-xs text-gray-500 dark:text-slate-400">
                  Dönem: {data.period_start} — {data.period_end}
                </p>
              </div>
              <div className="flex items-center gap-4 text-[11px] text-gray-500 dark:text-slate-400">
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-3 rounded bg-sky-700 inline-block" />
                  <span>En Yüksek Gün</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-3 rounded bg-sky-400 inline-block" />
                  <span>Günlük Çağrı</span>
                </div>
              </div>
            </div>

            {dailyCalls.length === 0 ? (
              <div className="h-36 flex items-center justify-center text-xs text-gray-500 dark:text-slate-400">
                Bu tarih aralığında günlük çağrı grafiği verisi bulunamadı.
              </div>
            ) : (
              <div className="flex items-end gap-2 sm:gap-3 h-44 pt-6 pb-2 border-b border-gray-100 dark:border-slate-800 overflow-x-auto">
                {dailyCalls.map((day) => {
                  const isZero = day.count === 0;
                  // 0 olan günler için en az 4px taban çizgisi, diğerleri oransal
                  const heightPct = isZero
                    ? 4
                    : Math.max(Math.round((day.count / maxDailyCount) * 100), 8);
                  const isMax = day.count === maxDailyCount && day.count > 0;

                  return (
                    <div
                      key={day.day}
                      className="flex min-w-[2.5rem] flex-1 flex-col items-center gap-1.5 group"
                    >
                      {/* Sayı etiketi (boş günler için 0 gösterimi) */}
                      <span
                        className={`text-[10px] font-bold transition-transform group-hover:scale-110 ${
                          isZero
                            ? "text-gray-500 dark:text-slate-400 font-normal"
                            : isMax
                            ? "text-sky-700 dark:text-sky-400 font-extrabold"
                            : "text-gray-600 dark:text-slate-300"
                        }`}
                      >
                        {day.count}
                      </span>

                      {/* Bar */}
                      <div className="w-full flex items-end h-28">
                        <div
                          style={{ height: `${heightPct}%` }}
                          className={`w-full rounded-t-md transition-all group-hover:opacity-90 ${
                            isZero
                              ? "bg-gray-200 dark:bg-slate-800"
                              : isMax
                              ? "bg-sky-700 shadow-sm ring-2 ring-sky-300 dark:ring-sky-700"
                              : "bg-sky-400"
                          }`}
                          title={`${day.day}: ${day.count} çağrı`}
                        />
                      </div>

                      {/* Tarih / Gün Etiketi */}
                      <span
                        className={`text-[9px] sm:text-[10px] font-medium text-center truncate max-w-full ${
                          isZero
                            ? "text-gray-500 dark:text-slate-400"
                            : isMax
                            ? "text-sky-900 dark:text-sky-300 font-bold"
                            : "text-gray-500 dark:text-slate-400"
                        }`}
                      >
                        {formatDayLabel(day.day)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 3 Temel Dağılım Grafiği */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* 1. Arıza & Talep Kategori Dağılımı (by_category) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-sm font-bold text-gray-900 dark:text-slate-100">Arıza &amp; Talep Kategorisi</h2>
                <span className="text-[11px] font-semibold text-gray-500 dark:text-slate-400">
                  {totalCategoryCalls} çağrı
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-slate-400 mb-4">
                Talep kategorisine göre dağılım
              </p>

              {categoryEntries.length === 0 ? (
                <p className="text-xs text-gray-500 dark:text-slate-400 py-6 text-center">Kategori verisi bulunmuyor</p>
              ) : (
                <div className="space-y-3">
                  {categoryEntries
                    .sort((a, b) => b[1] - a[1])
                    .map(([category, count]) => {
                      const pct = totalCategoryCalls > 0
                        ? Math.round((count / totalCategoryCalls) * 100)
                        : 0;
                      const label = labelOf(REQUEST_CATEGORY_LABELS, category);
                      const barColor = CATEGORY_COLORS[category] ?? "bg-sky-500";

                      return (
                        <div key={category} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="font-semibold text-gray-700 dark:text-slate-300 truncate max-w-[70%]">
                              {label}
                            </span>
                            <span className="font-bold text-gray-900 dark:text-slate-100">
                              %{pct} <span className="font-normal text-gray-500 dark:text-slate-400">({count})</span>
                            </span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-gray-100 dark:bg-slate-800 overflow-hidden">
                            <div
                              style={{ width: `${pct}%` }}
                              className={`h-full rounded-full ${barColor} transition-all`}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>

            {/* 2. Aciliyet Seviyesi Dağılımı (by_urgency) & En Yoğun Marinalar (busiest_marinas) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-sm font-bold text-gray-900 dark:text-slate-100">Aciliyet Dağılımı &amp; Marinalar</h2>
                <span className="text-[11px] font-semibold text-gray-500 dark:text-slate-400">
                  {totalUrgencyCalls} analiz
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-slate-400 mb-4">
                Aciliyet seviyeleri ve en yoğun lokasyonlar
              </p>

              {/* Aciliyet Dağılımı Çubukları */}
              <div className="space-y-2.5 pb-4 border-b border-gray-100 dark:border-slate-800">
                {urgencyEntries
                  .sort((a, b) => {
                    const order: Record<Urgency, number> = { acil: 0, yuksek: 1, normal: 2, dusuk: 3 };
                    return (order[a[0]] ?? 99) - (order[b[0]] ?? 99);
                  })
                  .map(([urgency, count]) => {
                    const pct = totalUrgencyCalls > 0
                      ? Math.round((count / totalUrgencyCalls) * 100)
                      : 0;
                    const label = labelOf(URGENCY_LABELS, urgency);
                    const style = URGENCY_STYLES[urgency] ?? URGENCY_STYLES.normal;

                    return (
                      <div key={urgency} className="space-y-1">
                        <div className="flex justify-between items-center text-xs">
                          <span className={`inline-flex items-center gap-1 font-semibold ${style.text}`}>
                            {urgency === "acil" && "🚨"}
                            {label}
                          </span>
                          <span className="font-bold text-gray-900 dark:text-slate-100">
                            %{pct} <span className="font-normal text-gray-500 dark:text-slate-400">({count})</span>
                          </span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-gray-100 dark:bg-slate-800 overflow-hidden">
                          <div
                            style={{ width: `${pct}%` }}
                            className={`h-full rounded-full ${style.bar} transition-all`}
                          />
                        </div>
                      </div>
                    );
                  })}
              </div>

              {/* En Yoğun Marinalar Özeti (busiest_marinas) */}
              <div className="pt-3">
                <h3 className="text-xs font-bold text-gray-800 dark:text-slate-200 mb-2">En Yoğun Marinalar</h3>
                {marinas.length === 0 ? (
                  <p className="text-[11px] text-gray-500 dark:text-slate-400">Marina verisi bulunmuyor</p>
                ) : (
                  <div className="space-y-1.5">
                    {marinas.slice(0, 3).map((m) => {
                      const mPct = totalMarinaCalls > 0
                        ? Math.round((m.count / totalMarinaCalls) * 100)
                        : 0;
                      return (
                        <div
                          key={m.name}
                          className="flex items-center justify-between text-xs py-1 border-b border-gray-50 dark:border-slate-800/60 last:border-none"
                        >
                          <span className="font-medium text-gray-700 dark:text-slate-300">⚓ {m.name || EMPTY_LABEL}</span>
                          <span className="font-bold text-sky-700 dark:text-sky-400">
                            {m.count} çağrı <span className="font-normal text-gray-500 dark:text-slate-400">(%{mPct})</span>
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* 3. Satış Kaçırma Sebepleri (lost_by_reason) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-sm font-bold text-gray-900 dark:text-slate-100">Satış Kaçırma Sebepleri</h2>
                <span className="text-[11px] font-semibold text-gray-500 dark:text-slate-400">
                  {totalLossCount} kayıp
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-slate-400 mb-4">
                Kaybedilen satışların nedenleri
              </p>

              {lossEntries.length === 0 ? (
                <div className="py-8 text-center">
                  <span className="text-2xl">🎉</span>
                  <p className="mt-2 text-xs font-medium text-gray-600 dark:text-slate-400">
                    Kayıp satış kaydı bulunmamaktadır.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {lossEntries
                    .sort((a, b) => b[1] - a[1])
                    .map(([reason, count]) => {
                      const pct = totalLossCount > 0
                        ? Math.round((count / totalLossCount) * 100)
                        : 0;
                      const label = labelOf(LOSS_REASON_LABELS, reason);
                      const color = LOSS_COLORS[reason] ?? "bg-gray-400";

                      return (
                        <div key={reason} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="font-semibold text-gray-700 dark:text-slate-300 truncate max-w-[70%]">
                              {label}
                            </span>
                            <span className="font-bold text-gray-900 dark:text-slate-100">
                              %{pct} <span className="font-normal text-gray-500 dark:text-slate-400">({count})</span>
                            </span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-gray-100 dark:bg-slate-800 overflow-hidden">
                            <div
                              style={{ width: `${pct}%` }}
                              className={`h-full rounded-full ${color} transition-all`}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}

              {/* Aksiyon İpucu Kutusu */}
              {topLossReason && totalLossCount > 0 && (
                <div className="mt-4 rounded-lg bg-amber-50 dark:bg-amber-950/40 p-2.5 border border-amber-200 dark:border-amber-900/60 text-[11px] text-amber-900 dark:text-amber-200">
                  💡 <strong>Aksiyon Önerisi:</strong>{" "}
                  {topLossReason === "fiyat" &&
                    "Fiyat itirazı olan tekliflerde standart kış bakım paketleri ve alternatif ödeme planları önerin."}
                  {topLossReason === "takvim" &&
                    "Kapasite yetersizliği nedeniyle kaybedilen talepler için anlaşmalı servis ortaklıkları değerlendirilebilir."}
                  {topLossReason === "gec_donus" &&
                    "Cevap süresini kısaltmak için acil çağrı bildirimlerini devreye alın."}
                  {topLossReason === "rakip" &&
                    "Rakip tekliflerle kaybedilen işler için garanti ve orijinal parça avantajlarını vurgulayın."}
                  {topLossReason === "guven" &&
                    "Müşteri referansları ve yetkili servis sertifikalarını tekliflere ekleyin."}
                  {topLossReason !== "fiyat" &&
                    topLossReason !== "takvim" &&
                    topLossReason !== "gec_donus" &&
                    topLossReason !== "rakip" &&
                    topLossReason !== "guven" &&
                    "Kaybedilen taleplerin nedenlerini analiz ederek servis süreçlerini gözden geçirin."}
                </div>
              )}
            </div>
          </div>

          {/* En Sık Bildirilen Arızalar (top_problems) & Hızlı Aksiyon */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Sık Karşılaşılan Arızalar (top_problems) */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
              <h2 className="text-sm font-bold text-gray-900 dark:text-slate-100 mb-1">
                En Sık Bildirilen Tekne Arızaları
              </h2>
              <p className="text-xs text-gray-500 dark:text-slate-400 mb-4">
                Konuşma transkriptlerinden çıkarılan problem ifadeleri
              </p>

              {(data.top_problems ?? []).length === 0 ? (
                <p className="text-xs text-gray-500 dark:text-slate-400">Kayıtlı arıza tanımı bulunmuyor.</p>
              ) : (
                <div className="space-y-2">
                  {data.top_problems.map((prob, idx) => (
                    <div
                      key={prob.name}
                      className="flex items-center justify-between rounded-lg bg-gray-50 dark:bg-slate-800/80 px-3 py-2 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-sky-100 dark:bg-sky-950/80 text-[10px] font-bold text-sky-700 dark:text-sky-300">
                          {idx + 1}
                        </span>
                        <span className="font-semibold text-gray-800 dark:text-slate-200">{prob.name || EMPTY_LABEL}</span>
                      </div>
                      <span className="font-bold text-sky-700 dark:text-sky-400">{prob.count} vaka</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Hızlı Erişim & Aksiyon Kartı */}
            <div className="rounded-xl border border-gray-200 dark:border-slate-800 bg-gradient-to-br from-slate-900 to-slate-800 dark:from-slate-950 dark:to-slate-900 p-6 text-white shadow-sm flex flex-col justify-between">
              <div>
                <span className="inline-flex rounded-full bg-sky-500/20 px-3 py-1 text-xs font-semibold text-sky-300 mb-3">
                  Operasyonel Hızlı Erişim
                </span>
                <h3 className="text-base font-bold text-white mb-2">
                  Çağrı Transkriptleri ve CRM Önerileri
                </h3>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Görüşme metinlerini incelemek, 7 temel alanlı CRM çıkarımlarını kontrol etmek
                  veya yeni ses kaydı yükleyip anında analize göndermek için ilgili sekmelere geçin.
                </p>
              </div>

              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  href="/admin/calls"
                  className="rounded-xl bg-white dark:bg-slate-800 px-4 py-2 text-xs font-bold text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  📞 Çağrı Listesine Git →
                </Link>
                <Link
                  href="/admin/calls/upload"
                  className="rounded-xl bg-sky-700 px-4 py-2 text-xs font-bold text-white hover:bg-sky-500 transition-colors"
                >
                  🎙️ Yeni Çağrı Yükle
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
