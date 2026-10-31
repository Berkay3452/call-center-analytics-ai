"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getKpiSummary } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { KpiSummary } from "@/lib/api/types";
import {
  Button,
  buttonClasses,
  Card,
  CardHeader,
  PageHeader,
  ProgressBar,
  Select,
  StatCard,
  type Tone,
} from "@/components/ui";
import { AnalyticsDashboardSkeleton } from "@/components/skeletons";
import {
  EMPTY_LABEL,
  labelOf,
  LOSS_REASON_LABELS,
  LossReason,
  MARINA_OPTIONS,
  REQUEST_CATEGORY_LABELS,
  RequestCategory,
} from "@/lib/types";

// Tarih aralığı opsiyonları (Sentetik seed verileri 5-13 Ekim 2026 arasındadır)
const DATE_RANGE_OPTIONS = [
  { value: "30", label: "Son 30 gün" },
  { value: "oct2026", label: "Ekim 2026 (demo verisi)" },
  { value: "7", label: "Son 7 gün" },
  { value: "90", label: "Son 3 ay" },
  { value: "365", label: "Son 1 yıl" },
];

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

/** Tarih dizesini Türkçe gün ve ay formatına dönüştürür (örn: "06 Eki"). */
function formatDayLabel(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short" });
}

interface DistributionRow {
  key: string;
  label: string;
  count: number;
}

/** Yatay ilerleme çubuklu dağılım listesi: etiket, yüzde ve adet. */
function DistributionList({
  rows,
  tone,
  emptyText,
}: {
  rows: DistributionRow[];
  tone: Tone;
  emptyText: string;
}) {
  const total = rows.reduce((acc, r) => acc + r.count, 0);
  if (rows.length === 0 || total === 0) {
    return <p className="py-6 text-center text-sm text-slate-500">{emptyText}</p>;
  }
  return (
    <ul className="space-y-3">
      {rows.map((row) => {
        const pct = Math.round((row.count / total) * 100);
        return (
          <li key={row.key} className="space-y-1">
            <div className="flex justify-between gap-2 text-sm">
              <span className="truncate text-slate-700">{row.label}</span>
              <span className="shrink-0 font-semibold text-brand-800">
                {row.count} <span className="font-normal text-slate-500">(%{pct})</span>
              </span>
            </div>
            <ProgressBar value={row.count} max={total} tone={tone} label={`${row.label}: %${pct}`} />
          </li>
        );
      })}
    </ul>
  );
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

  const dailyCalls = data?.daily_calls ?? [];
  const maxDailyCount = Math.max(...dailyCalls.map((d) => d.count), 1);

  const categoryRows: DistributionRow[] = (
    Object.entries(data?.by_category ?? {}) as [RequestCategory, number][]
  )
    .map(([key, count]) => ({ key, label: labelOf(REQUEST_CATEGORY_LABELS, key), count }))
    .sort((a, b) => b.count - a.count);

  const marinaRows: DistributionRow[] = (data?.busiest_marinas ?? []).map((m) => ({
    key: m.name,
    label: m.name || EMPTY_LABEL,
    count: m.count,
  }));

  const lossRows: DistributionRow[] = (
    Object.entries(data?.lost_by_reason ?? {}) as [LossReason, number][]
  )
    .filter(([, count]) => count > 0)
    .map(([key, count]) => ({ key, label: labelOf(LOSS_REASON_LABELS, key), count }))
    .sort((a, b) => b.count - a.count);
  const totalLost = lossRows.reduce((acc, r) => acc + r.count, 0);

  const fmt = (n: number) => n.toLocaleString("tr-TR");

  return (
    <div>
      <PageHeader
        title="Çağrı Analitiği"
        description="Sesli görüşme analizlerinden çıkan operasyonel göstergeler"
        actions={
          <>
            <label htmlFor="analytics-marina-select" className="sr-only">
              Marina filtresi
            </label>
            <Select
              id="analytics-marina-select"
              value={selectedMarina}
              onChange={(e) => handleMarinaChange(e.target.value)}
              disabled={isLoading}
              aria-label="Marina filtresi"
              className="w-auto"
            >
              <option value="all">Tüm marinalar</option>
              {MARINA_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
            <label htmlFor="analytics-date-range-select" className="sr-only">
              Tarih aralığı
            </label>
            <Select
              id="analytics-date-range-select"
              value={dateRange}
              onChange={(e) => handleDateRangeChange(e.target.value)}
              disabled={isLoading}
              aria-label="Tarih aralığı"
              className="w-auto"
            >
              {DATE_RANGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
            <Button
              variant="secondary"
              onClick={handleRefresh}
              disabled={isLoading}
              aria-label="Verileri yenile"
            >
              Yenile
            </Button>
          </>
        }
      />

      {isLoading && <AnalyticsDashboardSkeleton />}

      {error && !isLoading && (
        <Card className="border-red-200 bg-red-50" role="alert">
          <h2 className="text-base font-semibold text-red-900">Veriler alınırken bir hata oluştu</h2>
          <p className="mt-1 text-sm text-red-700">{error.message}</p>
          {(error.code || error.requestId) && (
            <p className="mt-2 text-xs text-red-700">
              {error.code && (
                <>
                  Hata kodu: <code className="font-mono">{error.code}</code>
                </>
              )}
              {error.requestId && (
                <>
                  {" "}
                  · İstek ID: <code className="font-mono">{error.requestId}</code>
                </>
              )}
            </p>
          )}
          <Button variant="danger" className="mt-4" onClick={handleRefresh}>
            Yeniden dene
          </Button>
        </Card>
      )}

      {!isLoading && !error && data && data.total_calls === 0 && (
        <Card className="p-12 text-center">
          <h2 className="text-base font-semibold text-brand-800">Henüz çağrı verisi bulunmuyor</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
            Seçili tarih aralığında ({data.period_start} — {data.period_end}) kayıtlı veya analizi
            tamamlanmış çağrı yok.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Button variant="secondary" onClick={() => handleDateRangeChange("365")}>
              Son 1 yılı göster
            </Button>
            <Link href="/admin/calls/upload" className={buttonClasses("primary")}>
              Yeni çağrı yükle
            </Link>
          </div>
        </Card>
      )}

      {!isLoading && !error && data && data.total_calls > 0 && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Gelen Çağrı"
              value={fmt(data.total_calls)}
              unit="adet"
              hint={`${data.analyzed_calls} analiz edildi`}
            />
            <StatCard
              label="Yeni Müşteri"
              value={fmt(data.new_customers)}
              unit="tekne"
              hint="İlk kez arayanlar"
              tone="brand"
            />
            <StatCard
              label="Servis Talebi"
              value={fmt(data.service_requests)}
              unit="adet"
              hint="Bakım ve onarım"
              tone="brand"
            />
            <StatCard
              label="Teklif Talebi"
              value={fmt(data.quote_requests)}
              unit="adet"
              hint="Fiyat ve proje"
              tone="brand"
            />
            <StatCard
              label="Acil Servis"
              value={fmt(data.urgent_requests)}
              unit="adet"
              hint="Acil müdahale"
              tone="danger"
            />
            <StatCard
              label="Satışa Dönüşen"
              value={
                data.conversion_rate != null
                  ? `%${Math.round(data.conversion_rate * 100)}`
                  : EMPTY_LABEL
              }
              hint={`${data.converted_sales} başarılı satış`}
              tone="success"
            />
            <StatCard
              label="Kaybedilen Satış"
              value={fmt(totalLost)}
              unit="adet"
              hint="Nedenleri aşağıda"
              tone="accent"
            />
            <StatCard
              label="Ort. Yanıt Süresi"
              value={
                data.avg_answer_delay_s != null ? `${Math.round(data.avg_answer_delay_s)}` : EMPTY_LABEL
              }
              unit={data.avg_answer_delay_s != null ? "sn" : undefined}
              hint="Santral bekleme"
            />
          </div>

          <Card>
            <CardHeader
              title="Günlük Çağrı Sayısı Trendi"
              description={`Dönem: ${data.period_start} — ${data.period_end}`}
            />
            {dailyCalls.length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-500">
                Bu tarih aralığında günlük çağrı verisi bulunamadı.
              </p>
            ) : (
              <div
                role="region"
                aria-label="Günlük çağrı sayısı grafiği (yatay kaydırılabilir)"
                tabIndex={0}
                className="flex h-44 items-end gap-2 overflow-x-auto border-b border-slate-100 pb-2 pt-4"
              >
                {dailyCalls.map((day) => {
                  const heightPct =
                    day.count === 0
                      ? 3
                      : Math.max(Math.round((day.count / maxDailyCount) * 100), 8);
                  return (
                    <div
                      key={day.day}
                      className="flex h-full min-w-[2.5rem] flex-1 flex-col items-center justify-end gap-1"
                    >
                      <span className="text-xs font-semibold text-brand-800">{day.count}</span>
                      <div className="flex w-full flex-1 items-end">
                        <div
                          style={{ height: `${heightPct}%` }}
                          className={`w-full rounded-t ${day.count === 0 ? "bg-slate-200" : "bg-brand-600"}`}
                          title={`${day.day}: ${day.count} çağrı`}
                        />
                      </div>
                      <span className="max-w-full truncate text-[11px] text-slate-500">
                        {formatDayLabel(day.day)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader title="Talep Kategorisi" description="Arıza ve talep türüne göre dağılım" />
              <DistributionList rows={categoryRows} tone="brand" emptyText="Kategori verisi bulunmuyor" />
            </Card>
            <Card>
              <CardHeader title="En Yoğun Marinalar" description="Çağrı sayısına göre ilk marinalar" />
              <DistributionList
                rows={marinaRows.slice(0, 5)}
                tone="brand"
                emptyText="Marina verisi bulunmuyor"
              />
            </Card>
            <Card>
              <CardHeader
                title="Satış Kaçırma Sebepleri"
                description={`Kaybedilen ${totalLost} satışın nedenleri`}
              />
              <DistributionList
                rows={lossRows}
                tone="accent"
                emptyText="Kayıp satış kaydı bulunmuyor"
              />
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
