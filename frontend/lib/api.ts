/**
 * Mock API istemcisi — backend hazır olana kadar JSON dosyalarından veri döndürür.
 *
 * Miço Usta entegrasyonunda her fonksiyon gerçek fetch() çağrısıyla değiştirilecektir.
 */

import type { Call, CrmSuggestion, KpiCard } from "@/lib/types";

// ---------------------------------------------------------------------------
// Çağrı listesi
// ---------------------------------------------------------------------------
export async function fetchCalls(): Promise<Call[]> {
  const data = await import("@/mocks/calls.json");
  return data.default as Call[];
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
  return data.default as KpiCard[];
}

// ---------------------------------------------------------------------------
// CRM önerileri
// ---------------------------------------------------------------------------
export async function fetchCrmSuggestions(): Promise<CrmSuggestion[]> {
  const data = await import("@/mocks/crm-suggestions.json");
  return data.default as CrmSuggestion[];
}
