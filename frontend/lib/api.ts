/**
 * Mock API istemcisi — backend hazır olana kadar JSON dosyalarından veri döndürür.
 * backend/app/schemas/analysis.py şemalarıyla birebir uyumludur.
 */

import type {
  Call,
  CrmSuggestion,
  DailyCallPoint,
  FailureCategoryItem,
  KpiCard,
  LossReasonItem,
  MarinaStatItem,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Çağrı listesi
// ---------------------------------------------------------------------------
export async function fetchCalls(): Promise<Call[]> {
  const data = await import("@/mocks/calls.json");
  return data.default as unknown as Call[];
}

// ---------------------------------------------------------------------------
// Tek çağrı detayı
// ---------------------------------------------------------------------------
export async function fetchCallById(id: string): Promise<Call | undefined> {
  const calls = await fetchCalls();
  return calls.find((c) => c.id === id);
}

// ---------------------------------------------------------------------------
// KPI kartları
// ---------------------------------------------------------------------------
export async function fetchKpis(): Promise<KpiCard[]> {
  const data = await import("@/mocks/kpis.json");
  return data.default as unknown as KpiCard[];
}

// ---------------------------------------------------------------------------
// CRM önerileri (7 alanlı CRM çıkarımları)
// ---------------------------------------------------------------------------
export async function fetchCrmSuggestions(): Promise<CrmSuggestion[]> {
  const data = await import("@/mocks/crm-suggestions.json");
  return data.default as unknown as CrmSuggestion[];
}

// ---------------------------------------------------------------------------
// Günlük çağrı trendi (son 7 gün)
// ---------------------------------------------------------------------------
export async function fetchDailyCalls(): Promise<DailyCallPoint[]> {
  const data = await import("@/mocks/daily-calls.json");
  return data.default as unknown as DailyCallPoint[];
}

// ---------------------------------------------------------------------------
// Arıza kategorileri (RequestCategory bazlı)
// ---------------------------------------------------------------------------
export async function fetchFailureCategories(): Promise<FailureCategoryItem[]> {
  const data = await import("@/mocks/failure-categories.json");
  return data.default as unknown as FailureCategoryItem[];
}

// ---------------------------------------------------------------------------
// Marina istatistikleri
// ---------------------------------------------------------------------------
export async function fetchMarinaStats(): Promise<MarinaStatItem[]> {
  const data = await import("@/mocks/marina-stats.json");
  return data.default as unknown as MarinaStatItem[];
}

// ---------------------------------------------------------------------------
// Kayıp nedenleri (LossReason bazlı)
// ---------------------------------------------------------------------------
export async function fetchLossReasons(): Promise<LossReasonItem[]> {
  const data = await import("@/mocks/loss-reasons.json");
  return data.default as unknown as LossReasonItem[];
}
