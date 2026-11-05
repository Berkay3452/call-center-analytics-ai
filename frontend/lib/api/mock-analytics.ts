import type { KpiSummary } from "./types";
import { mockSeedCalls } from "./mock-seed";

/** Aynı çağrı seed'i üzerinden tüm dağılımlara aynı marina ve tarih filtresini uygular. */
export function buildMockKpi(filters: { date_from?: unknown; date_to?: unknown; marina?: unknown }): KpiSummary {
  const from = String(filters.date_from ?? "2026-10-01");
  const to = String(filters.date_to ?? "2026-10-31");
  const calls = mockSeedCalls.filter((call) => {
    const day = call.started_at.slice(0, 10);
    return day >= from && day <= to && (!filters.marina || filters.marina === "all" || call.marina === filters.marina);
  });
  const countBy = (values: Array<string | null | undefined>): Record<string, number> => {
    const result: Record<string, number> = {};
    for (const value of values) if (value) result[value] = (result[value] ?? 0) + 1;
    return result;
  };
  const analyzed = calls.filter((call) => call.state === "tamam").length;
  const converted = calls.filter((call) => call.sales_outcome === "satisa_donustu").length;
  const delays = calls.flatMap((call) => call.answer_delay_s == null ? [] : [call.answer_delay_s]);
  const marinas = countBy(calls.map((call) => call.marina));
  const daily = countBy(calls.map((call) => call.started_at.slice(0, 10)));
  const firstCalls = new Map<string, string>();
  for (const call of mockSeedCalls) {
    if (call.customer_name && (!firstCalls.has(call.customer_name) || call.started_at < firstCalls.get(call.customer_name)!)) {
      firstCalls.set(call.customer_name, call.started_at);
    }
  }
  return {
    period_start: from, period_end: to,
    total_calls: calls.length, analyzed_calls: analyzed,
    new_customers: new Set(calls.filter((call) => call.customer_name && firstCalls.get(call.customer_name) === call.started_at).map((call) => call.customer_name)).size,
    service_requests: calls.filter((call) => call.call_type === "servis" || call.call_type === "acil").length,
    quote_requests: calls.filter((call) => call.call_type === "teklif").length,
    urgent_requests: calls.filter((call) => call.urgency === "acil").length,
    converted_sales: converted, conversion_rate: calls.length ? converted / calls.length : null,
    lost_by_reason: countBy(calls.filter((call) => call.sales_outcome === "kaybedildi").map((call) => call.loss_reason)),
    top_problems: [],
    busiest_marinas: Object.entries(marinas).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count),
    by_category: countBy(calls.map((call) => call.request_category)),
    by_urgency: countBy(calls.map((call) => call.urgency)),
    daily_calls: Object.entries(daily).sort(([a], [b]) => a.localeCompare(b)).map(([day, count]) => ({ day, count })),
    avg_answer_delay_s: delays.length ? delays.reduce((sum, value) => sum + value, 0) / delays.length : null,
  };
}
