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
  SourceRef,
  StreamStage,
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

// ---------------------------------------------------------------------------
// Asistan SSE Akış İstemcisi (#29 / #28 / docs/api.md §4)
// ---------------------------------------------------------------------------

/**
 * Geliştirme/Seed tekne sahibi kimliği (Ahmet Yılmaz - Tekne: Poyraz).
 * Backend testleri ve seed bu UUID'ye kayıtlıdır.
 */
export const DEFAULT_OWNER_ID = "606bd734-644f-5c21-af2f-dc734c4ecd67";

export interface StreamChatCallbacks {
  onStatus?: (stage: StreamStage) => void;
  onDelta?: (text: string) => void;
  onDone?: (reply: ChatReply) => void;
  onError?: (error: ApiError) => void;
}

const MOCK_KNOWLEDGE: Record<
  string,
  { reply: string; sources: SourceRef[]; found: boolean }
> = {
  "Son motor bakımım ne zaman yapıldı?": {
    reply:
      "Tekneniz Poyraz (Motoryat 42) için son periyodik motor bakımı 15 Ağustos 2026 tarihinde Kalamış Marina'da usta Mehmet Şimşek tarafından yapılmıştır. Motor yağı, yakıt filtreleri ve impeller değişimi tamamlanmıştır.",
    sources: [
      {
        kind: "service_record",
        record_id: "rec-srv-01",
        title: "15 Ağustos 2026 Usta Servis Raporu",
        date: "2026-08-15",
        excerpt:
          "Ana makine 250 saatlik periyodik bakımı ve filtre değişimleri tamamlandı.",
      },
    ],
    found: true,
  },
  "Son bakım ne zaman yapıldı?": {
    reply:
      "Tekneniz Poyraz (Motoryat 42) için son periyodik motor bakımı 15 Ağustos 2026 tarihinde Kalamış Marina'da usta Mehmet Şimşek tarafından yapılmıştır. Motor yağı, yakıt filtreleri ve impeller değişimi tamamlanmıştır.",
    sources: [
      {
        kind: "service_record",
        record_id: "rec-srv-01",
        title: "15 Ağustos 2026 Usta Servis Raporu",
        date: "2026-08-15",
        excerpt:
          "Ana makine 250 saatlik periyodik bakımı ve filtre değişimleri tamamlandı.",
      },
    ],
    found: true,
  },
  "Bu ay ne kadar harcadım?": {
    reply:
      "Kalamış Marina bağlama sözleşmesi ve elektrik/su tüketimi kapsamında bu ay toplam 14.250 TL harcama kaydedilmiştir. Son ödeme tarihi 25 Ekim 2026'dır.",
    sources: [
      {
        kind: "expense",
        record_id: "rec-exp-02",
        title: "Kalamış Marina İskele C-12 Hizmet Faturası",
        date: "2026-10-01",
        excerpt: "12m motoryat standart bağlama ve sayaç tüketim bedeli.",
      },
    ],
    found: true,
  },
  "Bu ayki marina masrafım ne kadar?": {
    reply:
      "Kalamış Marina sözleşmenize göre Ekim 2026 dönemi bağlama ve elektrik/su tüketim toplamınız 14.250 TL olarak muhasebeleştirilmiştir. Son ödeme tarihi 25 Ekim'dir.",
    sources: [
      {
        kind: "expense",
        record_id: "rec-exp-02",
        title: "Kalamış Marina İskele C-12 Hizmet Faturası",
        date: "2026-10-01",
        excerpt: "12m motoryat standart bağlama ve sayaç tüketim bedeli.",
      },
    ],
    found: true,
  },
  "Yakında yapılması gereken bir şey var mı?": {
    reply:
      "Yaklaşan işlemler: 1) Tutya (çinko anot) kontrolü 3 hafta içinde yapılmalı, 2) Yangın tüplerinin yıllık muayene süresi Kasım ayında doluyor. İsterseniz Miço Usta üzerinden servis randevusu planlayabiliriz.",
    sources: [
      {
        kind: "boat_note",
        record_id: "rec-not-03",
        title: "Tekne Periyodik Kontrol Çizelgesi",
        date: "2026-09-20",
        excerpt: "Gövde ve şaft tutyaları 6 ayda bir kontrol edilmeli.",
      },
    ],
    found: true,
  },
  "Sintine alarmı çaldığında ilk ne yapmalıyım?": {
    reply:
      "Sintine alarmı devreye girdiğinde derhal: 1) Sintine otomatik pompasının (float switch) çalıştığını kontrol edin, 2) Şaft kovanı ve deniz suyu vanalarını (seacock) su sızıntısına karşı gözleyin, 3) Akü ana şalterinin açık olduğundan emin olun.",
    sources: [
      {
        kind: "boat_note",
        record_id: "rec-not-04",
        title: "Miço Usta Acil Güvenlik Kılavuzu",
        date: "2026-10-09",
        excerpt: "Sintine su seviyesi alarmı acil müdahale adımları.",
      },
    ],
    found: true,
  },
};

function sleepWithSignal(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      return reject(new DOMException("Aborted", "AbortError"));
    }
    const timer = setTimeout(() => resolve(), ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

/**
 * Miço AI Asistan SSE Akışını dinler (POST /chat/messages/stream).
 * NEXT_PUBLIC_USE_MOCKS=true iken mock yanıtları adım adım (araniyor -> dogrulaniyor -> delta -> done) akıtır.
 */
export async function streamAssistantChat(
  question: ChatQuestion,
  userId: string = DEFAULT_OWNER_ID,
  callbacks: StreamChatCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const useMocks = isMockEnabled();

  // -------------------------------------------------------------------------
  // 1. MOCK AKIŞ MODU
  // -------------------------------------------------------------------------
  if (useMocks) {
    try {
      const qText = question.question.trim();

      // Test amaçlı hata tetikleme: 'hata' veya 'test-api-key-error'
      if (qText.toLowerCase().includes("test-api-key-error") || qText.toLowerCase().includes("llm-error")) {
        callbacks.onStatus?.("araniyor");
        await sleepWithSignal(300, signal);
        const err = new ApiError({
          code: "LLM_NOT_CONFIGURED",
          message:
            "LLM_API_KEY tanımlı değil (.env). Lütfen AI servisi ayarlarını kontrol edin veya yöneticinize başvurun.",
          requestId: "mock-err-llm-key",
          status: 503,
        });
        callbacks.onError?.(err);
        return;
      }

      // Adım 1: aranıyor
      callbacks.onStatus?.("araniyor");
      await sleepWithSignal(250, signal);

      // Adım 2: doğrulanıyor
      callbacks.onStatus?.("dogrulaniyor");
      await sleepWithSignal(250, signal);

      // Yanıt verisi belirleme
      let matched = MOCK_KNOWLEDGE[qText];
      if (!matched && qText.toLowerCase().includes("bakım")) {
        matched = MOCK_KNOWLEDGE["Son bakım ne zaman yapıldı?"];
      } else if (!matched && (qText.toLowerCase().includes("masraf") || qText.toLowerCase().includes("harca"))) {
        matched = MOCK_KNOWLEDGE["Bu ay ne kadar harcadım?"];
      } else if (!matched && (qText.toLowerCase().includes("yakında") || qText.toLowerCase().includes("yapılacak"))) {
        matched = MOCK_KNOWLEDGE["Yakında yapılması gereken bir şey var mı?"];
      }

      const isFound = matched ? matched.found : false;
      const content = matched
        ? matched.reply
        : "Bu konuda kayıtlarda bilgi bulamadım. Daha fazla bilgi için Miço Usta servis ekibinizle iletişime geçebilirsiniz.";
      const sources: SourceRef[] = matched?.sources ?? [];

      // Adım 3: delta parçaları daktilo efekti
      const words = content.split(" ");
      let currentChunk = "";
      for (let i = 0; i < words.length; i++) {
        currentChunk += (i > 0 ? " " : "") + words[i];
        if (currentChunk.length >= 16 || i === words.length - 1) {
          callbacks.onDelta?.(currentChunk);
          currentChunk = "";
          await sleepWithSignal(40, signal);
        }
      }

      // Adım 4: done
      const sessionId = question.session_id || "5e8c2a40-3f1b-4d6e-9a7c-0b1d2e3f4a5b";
      const finalReply: ChatReply = {
        session_id: sessionId,
        question: {
          id: "6a7b8c9d-0e1f-4a2b-8c3d-4e5f6a7b8c9d",
          role: "user",
          content: qText,
          created_at: new Date().toISOString(),
          question_type: isFound ? "gecmis_oneri" : "kapsam_disi",
          sources: [],
          found: true,
        },
        answer: {
          id: "7b8c9d0e-1f2a-4b3c-9d4e-5f6a7b8c9d0e",
          role: "assistant",
          content,
          created_at: new Date().toISOString(),
          question_type: isFound ? "gecmis_oneri" : "kapsam_disi",
          sources,
          found: isFound,
        },
      };

      callbacks.onDone?.(finalReply);
      return;
    } catch (err: unknown) {
      if ((err as Error)?.name === "AbortError") {
        return; // İstek kullanıcı tarafından iptal edildi
      }
      const apiErr =
        err instanceof ApiError
          ? err
          : new ApiError({
              code: "STREAM_ERROR",
              message: (err as Error)?.message || "Akış sırasında bilinmeyen hata oluştu.",
              requestId: "mock-stream-err",
            });
      callbacks.onError?.(apiErr);
      return;
    }
  }

  // -------------------------------------------------------------------------
  // 2. GERÇEK SSE AKIŞI (POST /chat/messages/stream)
  // -------------------------------------------------------------------------
  const baseUrl = getApiBaseUrl().replace(/\/+$/, "");
  const url = `${baseUrl}/chat/messages/stream`;

  const headers = new Headers();
  headers.set("Content-Type", "application/json");
  headers.set("Accept", "text/event-stream");

  if (userId) {
    headers.set("X-User-Id", userId);
  }
  if (typeof window === "undefined" && process.env.SERVICE_KEY) {
    headers.set("X-Service-Key", process.env.SERVICE_KEY);
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(question),
      signal,
    });
  } catch (netErr: unknown) {
    if ((netErr as Error)?.name === "AbortError") return;
    const apiErr = new ApiError({
      code: "NETWORK_ERROR",
      message:
        netErr instanceof Error
          ? netErr.message
          : "Sunucuya bağlanılamadı. Ağ bağlantınızı kontrol edin.",
      requestId: null,
      status: 0,
    });
    callbacks.onError?.(apiErr);
    return;
  }

  if (!res.ok) {
    let errorData: Record<string, unknown> | null = null;
    try {
      errorData = (await res.json()) as Record<string, unknown>;
    } catch {
      // JSON formatında değilse
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
      "Sohbet servisi yanıt vermedi.";
    const requestId =
      (typeof errorBody?.request_id === "string"
        ? errorBody.request_id
        : typeof errorBody?.requestId === "string"
        ? errorBody.requestId
        : null) ||
      res.headers.get("x-request-id") ||
      null;

    const apiErr = new ApiError({
      code,
      message,
      requestId,
      status: res.status,
      details:
        typeof errorBody?.details === "object" && errorBody.details !== null
          ? (errorBody.details as Record<string, unknown>)
          : {},
    });
    callbacks.onError?.(apiErr);
    return;
  }

  if (!res.body) {
    callbacks.onError?.(
      new ApiError({
        code: "EMPTY_RESPONSE",
        message: "Akış gövdesi boş döndü.",
        requestId: res.headers.get("x-request-id"),
        status: res.status,
      }),
    );
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        if (!part.trim()) continue;
        const lines = part.split("\n");
        let eventType = "message";
        let dataStr = "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataStr = line.slice(5).trim();
          }
        }
        if (!dataStr) continue;

        try {
          const parsed = JSON.parse(dataStr);
          if (eventType === "status") {
            if (parsed.stage) callbacks.onStatus?.(parsed.stage as StreamStage);
          } else if (eventType === "delta") {
            if (typeof parsed.text === "string") callbacks.onDelta?.(parsed.text);
          } else if (eventType === "done") {
            const reply = parsed.reply ?? parsed;
            if (reply) callbacks.onDone?.(reply as ChatReply);
          } else if (eventType === "error") {
            const err = new ApiError({
              code: parsed.code || "STREAM_ERROR",
              message: parsed.message || "Akış sırasında hata oluştu.",
              requestId: parsed.request_id ?? null,
              details: parsed.details,
            });
            callbacks.onError?.(err);
          }
        } catch {
          // JSON ayrıştırma hatasını yoksay
        }
      }
    }
  } catch (err: unknown) {
    if ((err as Error)?.name === "AbortError") return;
    const apiErr =
      err instanceof ApiError
        ? err
        : new ApiError({
            code: "STREAM_READ_ERROR",
            message: (err as Error)?.message || "Akış okunurken hata oluştu.",
            requestId: null,
          });
    callbacks.onError?.(apiErr);
  }
}

