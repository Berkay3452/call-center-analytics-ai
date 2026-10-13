export {
  getCalls,
  getCallById,
  createCall,
  createCallWithAudio,
  analyzeCall,
  getCallStatus,
  getCrmRecords,
  getKpiSummary,
  askAssistant,
  getChatSessions,
  getChatSessionDetail,
  apiFetch,
} from "./api/client";
export * from "./api/types";
export * from "./api/errors";

import {
  getCalls as getApiCalls,
  getCallById as getApiCallById,
  getCrmRecords as getApiCrmRecords,
  getKpiSummary as getApiKpiSummary,
} from "./api/client";
import type {
  Call,
  CrmSuggestion,
  DailyCallPoint,
  FailureCategoryItem,
  KpiCard,
  LossReasonItem,
  MarinaStatItem,
  Urgency,
  CallType,
  RequestCategory,
  ServiceMode,
  NextAction,
  LossReason,
  SalesOutcomeType,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Çağrı listesi
// ---------------------------------------------------------------------------
export async function fetchCalls(): Promise<Call[]> {
  try {
    const page = await getApiCalls();
    // Gelen OpenAPI CallListItem'ları UI Call formatına güvenli şekilde dönüştür
    return page.items.map((item) => ({
      id: item.id,
      caller: item.customer_name ?? "İsimsiz Arayan",
      callerPhone: "+90 5** *** ** **",
      boatName: item.boat_name ?? undefined,
      startedAt: item.started_at,
      durationSec: item.duration_s ?? 0,
      status: item.state === "tamam" ? "completed" : "ongoing",
      callType: (item.call_type as CallType) ?? null,
      urgency: (item.urgency as Urgency) ?? null,
      location: item.marina ?? null,
      analysisStatus:
        item.state === "tamam"
          ? "tamam"
          : item.state === "kismi"
          ? "kismi"
          : "basarisiz",
      transcript: "",
      summary: item.summary ?? "Özet bulunmuyor",
      tags: item.call_type ? [item.call_type] : [],
      crm: {
        requestCategory: (item.request_category as RequestCategory) ?? null,
        location: item.marina ?? null,
        problem: null,
        serviceMode: null,
        urgency: (item.urgency as Urgency) ?? null,
        potentialJob: null,
        nextAction: null,
      },
      sales: {
        outcome: (item.sales_outcome as SalesOutcomeType) ?? "beklemede",
        lossReason: null,
        evidence: null,
        confidence: 0.9,
      },
    }));
  } catch {
    const data = await import("@/mocks/calls.json");
    return data.default as unknown as Call[];
  }
}

// ---------------------------------------------------------------------------
// Tek çağrı detayı
// ---------------------------------------------------------------------------
export async function fetchCallById(id: string): Promise<Call | undefined> {
  try {
    const detail = await getApiCallById(id);
    const crm = detail.analysis?.crm;
    const sales = detail.analysis?.sales;
    const summary = detail.analysis?.summary;
    const classification = detail.analysis?.classification;

    return {
      id: detail.id,
      caller: detail.customer_name ?? "İsimsiz Arayan",
      callerPhone: detail.customer_phone ?? undefined,
      boatName: detail.boat_name ?? undefined,
      boatModel: detail.boat_model ?? undefined,
      startedAt: detail.started_at,
      durationSec: detail.duration_s ?? 0,
      status: detail.state === "tamam" ? "completed" : "ongoing",
      callType: (classification?.call_type as CallType) ?? null,
      urgency: (crm?.urgency as Urgency) ?? null,
      location: detail.marina ?? null,
      analysisStatus: detail.analysis?.status ?? (detail.state === "tamam" ? "tamam" : "kismi"),
      transcript: detail.transcript?.text ?? "",
      summary: summary?.summary ?? "Özet hazırlanıyor...",
      keyPoints: summary?.key_points,
      tags: classification?.call_type ? [classification.call_type] : [],
      crm: {
        requestCategory: (crm?.request_category as RequestCategory) ?? null,
        location: crm?.location ?? detail.marina ?? null,
        problem: crm?.problem ?? null,
        serviceMode: (crm?.service_mode as ServiceMode) ?? null,
        urgency: (crm?.urgency as Urgency) ?? null,
        potentialJob: crm?.potential_job ?? null,
        nextAction: (crm?.next_action as NextAction) ?? null,
        evidence: crm?.evidence,
      },
      sales: {
        outcome: (sales?.outcome as SalesOutcomeType) ?? "beklemede",
        lossReason: (sales?.loss_reason as LossReason) ?? null,
        evidence: sales?.evidence ?? null,
        confidence: sales?.confidence ?? 0,
      },
    };
  } catch {
    const calls = await fetchCalls();
    return calls.find((c) => c.id === id);
  }
}

// ---------------------------------------------------------------------------
// KPI kartları
// ---------------------------------------------------------------------------
export async function fetchKpis(): Promise<KpiCard[]> {
  try {
    const summary = await getApiKpiSummary();
    return [
      {
        label: "Toplam Çağrı",
        value: summary.total_calls,
        changePercent: 12,
        variant: "default",
      },
      {
        label: "Dönüşüm Oranı",
        value: summary.conversion_rate ? `%${Math.round(summary.conversion_rate * 100)}` : "—",
        changePercent: 5.4,
        variant: "success",
      },
      {
        label: "Acil Talepler",
        value: summary.urgent_requests,
        variant: "urgent",
      },
      {
        label: "Ort. Yanıtlama Süresi",
        value: summary.avg_answer_delay_s ? `${summary.avg_answer_delay_s} sn` : "12 sn",
        unit: "",
        variant: "default",
      },
    ];
  } catch {
    const data = await import("@/mocks/kpis.json");
    return data.default as unknown as KpiCard[];
  }
}

// ---------------------------------------------------------------------------
// CRM önerileri (7 alanlı CRM çıkarımları)
// ---------------------------------------------------------------------------
export async function fetchCrmSuggestions(): Promise<CrmSuggestion[]> {
  try {
    const res = await getApiCrmRecords();
    return res.items.map((item) => ({
      callId: item.call_id,
      caller: item.customer_name ?? "İsimsiz",
      boatName: item.boat_name ?? undefined,
      requestCategory: (item.request_category as RequestCategory) ?? null,
      location: item.location ?? null,
      problem: item.problem ?? null,
      serviceMode: (item.service_mode as ServiceMode) ?? null,
      urgency: (item.urgency as Urgency) ?? null,
      potentialJob: item.potential_job ?? null,
      nextAction: (item.next_action as NextAction) ?? null,
      evidence: item.evidence,
    }));
  } catch {
    const data = await import("@/mocks/crm-suggestions.json");
    return data.default as unknown as CrmSuggestion[];
  }
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
