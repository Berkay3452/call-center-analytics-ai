/**
 * OpenAPI'den türetilen TypeScript tipleri.
 * Kaynak: lib/api/schema.ts ve lib/api-types.ts
 */

import type { components, paths } from "./schema";

export type { components, paths };

export type Schema = components["schemas"];

// Ortak Tipler
export type CallType = Schema["CallType"];
export type RequestCategory = Schema["RequestCategory"];
export type ServiceMode = Schema["ServiceMode"];
export type Urgency = Schema["Urgency"];
export type NextAction = Schema["NextAction"];
export type SalesOutcomeType = Schema["SalesOutcomeType"];
export type SwitchboardOutcome = Schema["SwitchboardOutcome"];
export type LossReason = Schema["LossReason"];
export type CallState = Schema["CallState"];
export type AnalysisStatus = Schema["AnalysisStatus"];
export type Speaker = Schema["Speaker"];
export type QuestionType = Schema["QuestionType"];
export type SourceKind = Schema["SourceKind"];

// Hata Şemaları
export type ErrorBody = Schema["ErrorBody"];
export type ErrorResponse = Schema["ErrorResponse"];

// Sayfalı Yanıtlar
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export type PageCallListItem = Schema["PageCallListItem"];
export type PageCrmRecordItem = Schema["PageCrmRecordItem"];

// Analiz Çıktıları
export type CallClassification = Schema["CallClassification"];
export type CrmExtraction = Schema["CrmExtraction"];
export type SalesAnalysis = Schema["SalesAnalysis"];
export type CallSummary = Schema["CallSummary"];
export type AgentRun = Schema["AgentRun"];
export type AnalysisOut = Schema["AnalysisOut"];

// Çağrı Modelleri
export type CallListItem = Schema["CallListItem"];
export type TranscriptSegmentOut = Schema["TranscriptSegmentOut"];
export type TranscriptOut = Schema["TranscriptOut"];
export type CallDetail = Schema["CallDetail"];
export type CallMatchIn = Schema["CallMatchIn"];
export type SegmentIn = Schema["SegmentIn"];
export type CallCreate = Schema["CallCreate"];
export type CallAccepted = Schema["CallAccepted"];
export type CallStatus = Schema["CallStatus"];

// CRM ve KPI Modelleri
export type CrmReviewStatus = Schema["CrmReviewStatus"];
export type CrmRecordItem = Omit<Schema["CrmRecordItem"], "edited_fields"> & {
  edited_fields?: Record<string, unknown>;
};
export type CrmApproveIn = Schema["CrmApproveIn"];
export type CrmRejectIn = Schema["CrmRejectIn"];
export type CrmReviewOut = Omit<Schema["CrmReviewOut"], "edited_fields"> & {
  edited_fields?: Record<string, unknown>;
};
export type CountItem = Schema["CountItem"];
export type DailyCount = Schema["DailyCount"];
export type KpiSummary = Schema["KpiSummary"];

// Servis Emirleri Modelleri (#118 / #114)
export type ServiceOrderStatus =
  | "yeni_atandi"
  | "kesifte"
  | "onaylandi"
  | "devam_ediyor"
  | "tamamlandi";

export interface ServiceOrderCustomerOut {
  id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  marina: string | null;
}

export interface ServiceOrderBoatOut {
  id: string;
  name: string;
  model: string | null;
  year: number | null;
  marina: string | null;
}

export interface ServiceOrderCraftsmanOut {
  id: string;
  full_name: string;
  specialty: string | null;
  phone: string | null;
}

export interface ServiceOrderSourceCallOut {
  call_id: string;
  started_at: string;
  customer_name: string | null;
  boat_name: string | null;
  switchboard_outcome: SwitchboardOutcome | string | null;
  request_category: RequestCategory | string | null;
  location: string | null;
  problem: string | null;
  service_mode: ServiceMode | string | null;
  urgency: Urgency | string | null;
  potential_job: string | null;
  next_action: NextAction | string | null;
  summary: string | null;
  crm_review_status: CrmReviewStatus | string | null;
  crm_review_note: string | null;
  crm_reviewed_at: string | null;
}

export interface ServiceOrderListItem {
  id: string;
  status: ServiceOrderStatus;
  category: RequestCategory | string | null;
  description: string | null;
  scheduled_at: string | null;
  completed_at: string | null;
  created_at: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string | null;
  boat_id: string;
  boat_name: string;
  boat_model: string | null;
  marina: string | null;
  craftsman_id: string | null;
  craftsman_name: string | null;
  source_call_id: string | null;
}

export interface ServiceOrderDetail {
  id: string;
  status: ServiceOrderStatus;
  category: RequestCategory | string | null;
  description: string | null;
  scheduled_at: string | null;
  completed_at: string | null;
  created_at: string;
  customer: ServiceOrderCustomerOut;
  boat: ServiceOrderBoatOut;
  craftsman: ServiceOrderCraftsmanOut | null;
  source_call: ServiceOrderSourceCallOut | null;
}

export interface ServiceOrderStatusUpdate {
  status: ServiceOrderStatus;
}

export type PageServiceOrderListItem = Page<ServiceOrderListItem>;

export interface ServiceOrderFilters {
  status?: ServiceOrderStatus | string;
  date_from?: string;
  date_to?: string;
  marina?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

// Asistan & Chat Modelleri
export type SourceRef = Schema["SourceRef"];
export type ChatQuestion = Schema["ChatQuestion"];
export type ChatMessageOut = Schema["ChatMessageOut"];
export type ChatReply = Schema["ChatReply"];
export type ChatSessionOut = Schema["ChatSessionOut"];
export type ChatSessionDetail = Schema["ChatSessionDetail"];

// SSE Olayları
export type StatusEvent = Schema["StatusEvent"];
export type StreamStage = StatusEvent["stage"];
export type DeltaEvent = Schema["DeltaEvent"];
export type DoneEvent = Schema["DoneEvent"];
export type ErrorEvent = Schema["ErrorEvent"];
export type ChatStreamEvent = StatusEvent | DeltaEvent | DoneEvent | ErrorEvent;
