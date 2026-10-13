/**
 * Tipli API İstemcisi (#10).
 *
 * OpenAPI şemaları üzerinden uç noktaları çağırır veya tek bir ortam değişkeni
 * (NEXT_PUBLIC_USE_MOCKS veya USE_MOCK_API) ile frontend/mocks/ altındaki
 * Tuzla Marina senaryosu verilerini döndürür.
 */

import { ApiError } from "./errors";
import type {
  CallAccepted,
  CallCreate,
  CallDetail,
  CallListItem,
  CallStatus,
  ChatQuestion,
  ChatReply,
  ChatSessionDetail,
  ChatSessionOut,
  CrmRecordItem,
  KpiSummary,
  Page,
} from "./types";

// Mock JSON importları (docs/ornekler/api/ ile eşleşen 10 dosya)
import mockCallDetail from "@/mocks/cagri_detayi.json";
import mockCallStatus from "@/mocks/cagri_durumu.json";
import mockCallAccepted from "@/mocks/cagri_kabul.json";
import mockCallsList from "@/mocks/cagri_listesi.json";
import mockCrmList from "@/mocks/crm_listesi.json";
import mockKpiSummary from "@/mocks/kpi_ozeti.json";
import mockChatReply from "@/mocks/sohbet_cevabi.json";
import mockChatSessionDetail from "@/mocks/sohbet_oturumu.json";

export interface ApiClientConfig {
  baseUrl?: string;
  serviceKey?: string;
  useMocks?: boolean;
}

/**
 * Mock modunun etkin olup olmadığını belirler.
 * NEXT_PUBLIC_USE_MOCKS veya USE_MOCK_API 'false' veya '0' olmadığı sürece
 * geliştirme ortamında varsayılan olarak mock katmanı kullanılır.
 */
export function isMockEnabled(): boolean {
  const envVal =
    process.env.NEXT_PUBLIC_USE_MOCKS ?? process.env.USE_MOCK_API;
  if (envVal === "false" || envVal === "0") {
    return false;
  }
  return true;
}

/**
 * API taban adresi.
 * - Sunucu tarafında (Server Component): AI servisi doğrudan çağrılır (API_URL).
 * - Tarayıcıda: servis anahtarı tarayıcıya verilmez; istekler Next.js'in kendi
 *   `/api/backend` uç noktasından geçer, anahtarı orası ekler (app/api/backend/[...path]).
 */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") return "/api/backend";
  return process.env.API_URL ?? "http://localhost:8000/api/v1";
}

export interface RequestOptions extends RequestInit {
  userId?: string;
  params?: Record<string, string | number | boolean | null | undefined>;
}

/**
 * İnce fetch sarmalayıcısı:
 * 1. Mock modu açıksa yerel JSON verilerini döner.
 * 2. Gerçek API modunda tek tip hata biçimini ({ code, message, requestId }) işler.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<T> {
  const useMocks = isMockEnabled();

  if (useMocks) {
    return handleMockRequest<T>(endpoint, options);
  }

  const baseUrl = getApiBaseUrl().replace(/\/+$/, "");
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;

  // Query parametrelerini ekle
  let url = `${baseUrl}${cleanEndpoint}`;
  if (options.params) {
    const searchParams = new URLSearchParams();
    for (const [key, val] of Object.entries(options.params)) {
      if (val !== null && val !== undefined) {
        searchParams.append(key, String(val));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes("?") ? "&" : "?") + queryString;
    }
  }

  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  // Servis anahtarı yalnızca sunucuda eklenir (NEXT_PUBLIC_ ile tarayıcıya sızdırılmaz).
  if (typeof window === "undefined") {
    const serviceKey = process.env.SERVICE_KEY;
    if (serviceKey && !headers.has("X-Service-Key")) {
      headers.set("X-Service-Key", serviceKey);
    }
  }

  if (options.userId && !headers.has("X-User-Id")) {
    headers.set("X-User-Id", options.userId);
  }

  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers,
    });
  } catch (netErr: unknown) {
    throw new ApiError({
      code: "NETWORK_ERROR",
      message:
        netErr instanceof Error
          ? netErr.message
          : "Sunucuya bağlanılamadı. Ağ bağlantınızı kontrol edin.",
      requestId: null,
      status: 0,
    });
  }

  if (!res.ok) {
    let errorData: Record<string, unknown> | null = null;
    try {
      errorData = (await res.json()) as Record<string, unknown>;
    } catch {
      // JSON formatında değilse status text
    }

    const rawError = errorData?.error;
    const errorBody = (typeof rawError === "object" && rawError !== null
      ? rawError
      : errorData) as Record<string, unknown> | null;

    const code =
      (typeof errorBody?.code === "string" ? errorBody.code : null) ||
      `HTTP_${res.status}`;
    const message =
      (typeof errorBody?.message === "string" ? errorBody.message : null) ||
      (typeof errorData?.detail === "string" ? errorData.detail : null) ||
      res.statusText ||
      "Beklenmeyen bir hata oluştu";
    const requestId =
      (typeof errorBody?.request_id === "string"
        ? errorBody.request_id
        : typeof errorBody?.requestId === "string"
        ? errorBody.requestId
        : null) ||
      res.headers.get("x-request-id") ||
      null;
    const details =
      typeof errorBody?.details === "object" && errorBody.details !== null
        ? (errorBody.details as Record<string, unknown>)
        : {};

    throw new ApiError({
      code,
      message,
      requestId,
      details,
      status: res.status,
    });
  }

  return (await res.json()) as T;
}

/**
 * Mock yönlendirme mekanizması.
 * docs/ornekler/api/ altındaki 10 adet örnek JSON dosyasını döndürür.
 */
async function handleMockRequest<T>(
  endpoint: string,
  options: RequestOptions,
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const path = endpoint.split("?")[0].replace(/\/+$/, "");

  // 1. GET /calls
  if (method === "GET" && path === "/calls") {
    return mockCallsList as unknown as T;
  }

  // 2. POST /calls
  if (method === "POST" && path === "/calls") {
    return mockCallAccepted as unknown as T;
  }

  // 3. POST /calls/audio
  if (method === "POST" && path === "/calls/audio") {
    return mockCallAccepted as unknown as T;
  }

  // 4. POST /calls/:id/analyze
  if (method === "POST" && /^\/calls\/[^/]+\/analyze$/.test(path)) {
    return mockCallAccepted as unknown as T;
  }

  // 5. GET /calls/:id/status
  if (method === "GET" && /^\/calls\/[^/]+\/status$/.test(path)) {
    return mockCallStatus as unknown as T;
  }

  // 6. GET /calls/:id (Tekil çağrı detayı)
  if (method === "GET" && /^\/calls\/[^/]+$/.test(path)) {
    const id = path.split("/")[2];
    if (mockCallDetail.id === id) {
      return mockCallDetail as unknown as T;
    }
    // İstenen id cagri_listesi'ndeyse id eşleyerek detay üret veya varsayılan detay ver
    const foundInList = mockCallsList.items.find((item) => item.id === id);
    if (foundInList) {
      return {
        ...mockCallDetail,
        id: foundInList.id,
        started_at: foundInList.started_at,
        customer_name: foundInList.customer_name,
        boat_name: foundInList.boat_name,
        marina: foundInList.marina,
        state: foundInList.state,
      } as unknown as T;
    }
    // Mock detayı genel fallback olarak döndür
    return {
      ...mockCallDetail,
      id,
    } as unknown as T;
  }

  // 7. GET /crm
  if (method === "GET" && path === "/crm") {
    return mockCrmList as unknown as T;
  }

  // 8. GET /analytics/summary
  if (method === "GET" && path === "/analytics/summary") {
    return mockKpiSummary as unknown as T;
  }

  // 9. POST /chat/messages
  if (method === "POST" && path === "/chat/messages") {
    return mockChatReply as unknown as T;
  }

  // 10. GET /chat/sessions
  if (method === "GET" && path === "/chat/sessions") {
    return [mockChatSessionDetail.session] as unknown as T;
  }

  // 11. GET /chat/sessions/:id
  if (method === "GET" && /^\/chat\/sessions\/[^/]+$/.test(path)) {
    return mockChatSessionDetail as unknown as T;
  }

  throw new ApiError({
    code: "NOT_FOUND",
    message: `Mock uç noktası bulunamadı: ${method} ${path}`,
    requestId: "mock-req-404",
    status: 404,
  });
}

// ---------------------------------------------------------------------------
// Tipli Uç Nokta Fonksiyonları (OpenAPI Şemalarıyla %100 Uyumlu)
// ---------------------------------------------------------------------------

export interface CallQueryFilters {
  date_from?: string;
  date_to?: string;
  call_type?: string;
  urgency?: string;
  request_category?: string;
  state?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface PeriodQueryFilter {
  date_from?: string;
  date_to?: string;
}

/**
 * GET /calls - Sayfalı çağrı listesi
 */
export async function getCalls(
  filters?: CallQueryFilters,
): Promise<Page<CallListItem>> {
  return apiFetch<Page<CallListItem>>("/calls", {
    method: "GET",
    params: filters as Record<string, string | number | boolean | null | undefined>,
  });
}

/**
 * GET /calls/{call_id} - Çağrı ve analiz detayı
 */
export async function getCallById(callId: string): Promise<CallDetail> {
  return apiFetch<CallDetail>(`/calls/${callId}`, {
    method: "GET",
  });
}

/**
 * POST /calls - Yeni çağrı oluştur
 */
export async function createCall(payload: CallCreate): Promise<CallAccepted> {
  return apiFetch<CallAccepted>("/calls", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * POST /calls/audio - Ses dosyası yükleyerek çağrı oluştur
 */
export async function createCallWithAudio(formData: FormData): Promise<CallAccepted> {
  return apiFetch<CallAccepted>("/calls/audio", {
    method: "POST",
    body: formData,
  });
}

/**
 * POST /calls/{call_id}/analyze - Çağrıyı yeniden analize gönder
 */
export async function analyzeCall(callId: string): Promise<CallAccepted> {
  return apiFetch<CallAccepted>(`/calls/${callId}/analyze`, {
    method: "POST",
  });
}

/**
 * GET /calls/{call_id}/status - Çağrı işlem durumu
 */
export async function getCallStatus(callId: string): Promise<CallStatus> {
  return apiFetch<CallStatus>(`/calls/${callId}/status`, {
    method: "GET",
  });
}

/**
 * GET /crm - CRM kayıt ve öneri listesi
 */
export async function getCrmRecords(
  filters?: CallQueryFilters,
): Promise<Page<CrmRecordItem>> {
  return apiFetch<Page<CrmRecordItem>>("/crm", {
    method: "GET",
    params: filters as Record<string, string | number | boolean | null | undefined>,
  });
}

/**
 * GET /analytics/summary - KPI ve analitik özeti
 */
export async function getKpiSummary(
  filter?: PeriodQueryFilter,
): Promise<KpiSummary> {
  return apiFetch<KpiSummary>("/analytics/summary", {
    method: "GET",
    params: filter as Record<string, string | number | boolean | null | undefined>,
  });
}

/**
 * POST /chat/messages - Miço AI Tekne Sahibi asistanına soru gönder
 */
export async function askAssistant(
  question: ChatQuestion,
  userId: string,
): Promise<ChatReply> {
  return apiFetch<ChatReply>("/chat/messages", {
    method: "POST",
    userId,
    body: JSON.stringify(question),
  });
}

/**
 * GET /chat/sessions - Kullanıcının asistan oturumları
 */
export async function getChatSessions(
  userId: string,
): Promise<ChatSessionOut[]> {
  return apiFetch<ChatSessionOut[]>("/chat/sessions", {
    method: "GET",
    userId,
  });
}

/**
 * GET /chat/sessions/{session_id} - Sohbet oturumu detayı ve geçmişi
 */
export async function getChatSessionDetail(
  sessionId: string,
  userId: string,
): Promise<ChatSessionDetail> {
  return apiFetch<ChatSessionDetail>(`/chat/sessions/${sessionId}`, {
    method: "GET",
    userId,
  });
}
