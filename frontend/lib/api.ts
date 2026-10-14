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
  streamAssistantChat,
  DEFAULT_OWNER_ID,
  getChatSessions,
  getChatSessionDetail,
  apiFetch,
} from "./api/client";
export type { StreamChatCallbacks } from "./api/client";
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
  RequestCategory,
  LossReason,
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
// Günlük çağrı trendi (getApiKpiSummary üzerinden)
// ---------------------------------------------------------------------------
export async function fetchDailyCalls(filter?: { date_from?: string; date_to?: string }): Promise<DailyCallPoint[]> {
  const summary = await getApiKpiSummary(filter);
  return summary.daily_calls.map((d) => ({
    date: d.day,
    label: d.day,
    count: d.count,
  }));
}

// ---------------------------------------------------------------------------
// Arıza kategorileri (RequestCategory bazlı, getApiKpiSummary üzerinden)
// ---------------------------------------------------------------------------
export async function fetchFailureCategories(filter?: { date_from?: string; date_to?: string }): Promise<FailureCategoryItem[]> {
  const summary = await getApiKpiSummary(filter);
  const total = Object.values(summary.by_category).reduce((a, b) => a + b, 0) || 1;
  return Object.entries(summary.by_category).map(([category, count]) => ({
    category: category as RequestCategory,
    label: category,
    count,
    pct: Math.round((count / total) * 100),
    color: "bg-sky-500",
  }));
}

// ---------------------------------------------------------------------------
// Marina istatistikleri (busiest_marinas, getApiKpiSummary üzerinden)
// ---------------------------------------------------------------------------
export async function fetchMarinaStats(filter?: { date_from?: string; date_to?: string }): Promise<MarinaStatItem[]> {
  const summary = await getApiKpiSummary(filter);
  const total = summary.busiest_marinas.reduce((a, b) => a + b.count, 0) || 1;
  return summary.busiest_marinas.map((m) => ({
    name: m.name,
    count: m.count,
    pct: Math.round((m.count / total) * 100),
    tag: m.name,
  }));
}

// ---------------------------------------------------------------------------
// Kayıp nedenleri (LossReason bazlı, getApiKpiSummary üzerinden)
// ---------------------------------------------------------------------------
export async function fetchLossReasons(filter?: { date_from?: string; date_to?: string }): Promise<LossReasonItem[]> {
  const summary = await getApiKpiSummary(filter);
  const total = Object.values(summary.lost_by_reason).reduce((a, b) => a + b, 0) || 1;
  return Object.entries(summary.lost_by_reason).map(([reason, count]) => ({
    reason: reason as LossReason,
    label: reason,
    count,
    pct: Math.round((count / total) * 100),
    color: "bg-amber-500",
  }));
}
