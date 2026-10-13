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

import { isApiError } from "./api/errors";
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
  AnalysisStatus,
} from "@/lib/types";
import type { CallState } from "./api/types";

/** Çağrının analizi bitti mi? (isleniyor/beklemede/yaziya_cevriliyor: bitmedi) */
function isFinal(state: CallState): state is AnalysisStatus {
  return state === "tamam" || state === "kismi" || state === "basarisiz";
}

function finalStatus(state: CallState): AnalysisStatus {
  return isFinal(state) ? state : "kismi";
}

// ---------------------------------------------------------------------------
// Çağrı listesi
// ---------------------------------------------------------------------------
export async function fetchCalls(): Promise<Call[]> {
  const page = await getApiCalls({ page_size: 100 });
  return page.items.map((item) => ({
    id: item.id,
    caller: item.customer_name ?? "İsimsiz Arayan",
    boatName: item.boat_name ?? undefined,
    startedAt: item.started_at,
    durationSec: item.duration_s ?? 0,
    status: "completed",
    callType: item.call_type ?? null,
    urgency: item.urgency ?? null,
    location: item.marina ?? null,
    analysisStatus: finalStatus(item.state),
    pendingState: isFinal(item.state) ? undefined : item.state,
    transcript: "",
    summary: item.summary ?? "",
    tags: item.call_type ? [item.call_type] : [],
    crm: {
      requestCategory: item.request_category ?? null,
      location: item.marina ?? null,
      problem: null,
      serviceMode: null,
      urgency: item.urgency ?? null,
      potentialJob: null,
      nextAction: null,
    },
    sales: {
      outcome: item.sales_outcome ?? "beklemede",
      lossReason: null,
      evidence: null,
      confidence: 0,
    },
  }));
}

// ---------------------------------------------------------------------------
// Tek çağrı detayı
// ---------------------------------------------------------------------------
export async function fetchCallById(id: string): Promise<Call | undefined> {
  let detail;
  try {
    detail = await getApiCallById(id);
  } catch (err) {
    if (isApiError(err) && err.status === 404) return undefined;
    throw err;
  }
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
    status: "completed",
    callType: classification?.call_type ?? null,
    urgency: crm?.urgency ?? null,
    location: detail.marina ?? null,
    analysisStatus: detail.analysis?.status ?? finalStatus(detail.state),
    pendingState: isFinal(detail.state) ? undefined : detail.state,
    transcript: detail.transcript?.text ?? "",
    summary: summary?.summary ?? "",
    keyPoints: summary?.key_points,
    tags: classification?.call_type ? [classification.call_type] : [],
    crm: {
      requestCategory: crm?.request_category ?? null,
      location: crm?.location ?? detail.marina ?? null,
      problem: crm?.problem ?? null,
      serviceMode: crm?.service_mode ?? null,
      urgency: crm?.urgency ?? null,
      potentialJob: crm?.potential_job ?? null,
      nextAction: crm?.next_action ?? null,
      evidence: crm?.evidence,
    },
    sales: {
      outcome: sales?.outcome ?? "beklemede",
      lossReason: sales?.loss_reason ?? null,
      evidence: sales?.evidence ?? null,
      confidence: sales?.confidence ?? 0,
    },
  };
}

// ---------------------------------------------------------------------------
// KPI kartları
// ---------------------------------------------------------------------------
export async function fetchKpis(): Promise<KpiCard[]> {
  const summary = await getApiKpiSummary();
  const rate = summary.conversion_rate;
  const delay = summary.avg_answer_delay_s;
  return [
    { label: "Gelen Çağrı", value: summary.total_calls, unit: "adet" },
    { label: "Yeni Müşteri", value: summary.new_customers, unit: "tekne" },
    { label: "Servis Talebi", value: summary.service_requests, unit: "adet" },
    { label: "Teklif Talebi", value: summary.quote_requests, unit: "adet" },
    { label: "Acil Servis", value: summary.urgent_requests, unit: "adet", variant: "urgent" },
    {
      label: "Satışa Dönüşen",
      value: rate == null ? "—" : `%${Math.round(rate * 100)}`,
      variant: "success",
    },
    {
      label: "Ort. Cevap Süresi",
      value: delay == null ? "—" : Math.round(delay),
      unit: delay == null ? undefined : "sn",
    },
  ];
}

// ---------------------------------------------------------------------------
// CRM önerileri (7 alanlı CRM çıkarımları)
// ---------------------------------------------------------------------------
export async function fetchCrmSuggestions(): Promise<CrmSuggestion[]> {
  const res = await getApiCrmRecords({ page_size: 100 });
  return res.items.map((item) => ({
    callId: item.call_id,
    caller: item.customer_name ?? "İsimsiz",
    boatName: item.boat_name ?? undefined,
    requestCategory: item.request_category ?? null,
    location: item.location ?? null,
    problem: item.problem ?? null,
    serviceMode: item.service_mode ?? null,
    urgency: item.urgency ?? null,
    potentialJob: item.potential_job ?? null,
    nextAction: item.next_action ?? null,
    evidence: item.evidence,
  }));
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
