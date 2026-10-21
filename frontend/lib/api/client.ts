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
  CallState,
  CallStatus,
  ChatQuestion,
  ChatReply,
  ChatSessionDetail,
  ChatSessionOut,
  CrmApproveIn,
  CrmRecordItem,
  CrmRejectIn,
  CrmReviewOut,
  CrmReviewStatus,
  KpiSummary,
  Page,
  SourceRef,
  StreamStage,
  ServiceOrderStatus,
  ServiceOrderListItem,
  ServiceOrderDetail,
  ServiceOrderStatusUpdate,
  ServiceOrderFilters,
  RequestCategory,
  ServiceMode,
  Urgency,
  NextAction,
} from "./types";

export type { ServiceOrderStatusUpdate };

// Mock JSON importları (docs/ornekler/api/ ile eşleşen 10 dosya)
import mockCallDetail from "@/mocks/cagri_detayi.json";
import mockCallStatus from "@/mocks/cagri_durumu.json";
import mockCallAccepted from "@/mocks/cagri_kabul.json";
import mockCallsList from "@/mocks/cagri_listesi.json";
import mockCrmList from "@/mocks/crm_listesi.json";
import mockKpiSummary from "@/mocks/kpi_ozeti.json";
import mockChatReply from "@/mocks/sohbet_cevabi.json";
import mockChatSessionDetail from "@/mocks/sohbet_oturumu.json";
import mockServiceOrderDetail from "@/mocks/servis_emri_detayi.json";
import { mockSeedCalls, mockSeedCrm } from "./mock-seed";

interface MockAnalysisProgress {
  step: number;
  startedAt: number;
  analysisVersion: number;
}
const mockReanalyzeMap = new Map<string, MockAnalysisProgress>();

interface MockCrmReviewProgress {
  status: CrmReviewStatus;
  edited_fields: Record<string, unknown>;
  note?: string | null;
  service_order_id?: string | null;
  reviewed_at: string;
}
const mockCrmReviewMap = new Map<string, MockCrmReviewProgress>();

const ALLOWED_SERVICE_ORDER_TRANSITIONS: Record<ServiceOrderStatus, Set<ServiceOrderStatus>> = {
  yeni_atandi: new Set(["kesifte"]),
  kesifte: new Set(["onaylandi"]),
  onaylandi: new Set(["devam_ediyor"]),
  devam_ediyor: new Set(["tamamlandi"]),
  tamamlandi: new Set(),
};

function toServiceOrderListItem(order: ServiceOrderDetail): ServiceOrderListItem {
  return {
    id: order.id,
    status: order.status,
    category: order.category,
    description: order.description,
    scheduled_at: order.scheduled_at,
    completed_at: order.completed_at,
    created_at: order.created_at,
    customer_id: order.customer.id,
    customer_name: order.customer.full_name,
    customer_phone: order.customer.phone,
    boat_id: order.boat.id,
    boat_name: order.boat.name,
    boat_model: order.boat.model,
    marina: order.boat.marina ?? order.customer.marina,
    craftsman_id: order.craftsman?.id ?? null,
    craftsman_name: order.craftsman?.full_name ?? null,
    source_call_id: order.source_call?.call_id ?? null,
  };
}

const mockServiceOrdersStore: ServiceOrderDetail[] = [
  mockServiceOrderDetail as unknown as ServiceOrderDetail,
  {
    id: "22222222-2222-4222-8222-222222222222",
    status: "kesifte",
    category: "su_sihhi_tesisat",
    description: "Sintine pompası ve su alma arıza keşfi",
    scheduled_at: "2026-10-16T11:00:00Z",
    completed_at: null,
    created_at: "2026-10-14T11:20:00Z",
    customer: {
      id: "11111111-2222-4111-8111-111111111111",
      full_name: "Fatma Kaya",
      phone: "+90 533 333 44 55",
      email: "fatma.kaya@example.com",
      marina: "Göcek D-Marin",
    },
    boat: {
      id: "22222222-3333-4222-8222-222222222222",
      name: "Albatros",
      model: "Beneteau 45",
      year: 2021,
      marina: "Göcek D-Marin",
    },
    craftsman: {
      id: "33333333-2222-4333-8333-333333333333",
      full_name: "Mehmet Usta",
      specialty: "Sıhhi Tesisat & Sintine",
      phone: "+90 535 444 55 66",
    },
    source_call: {
      call_id: "22222222-2222-4222-8222-222222222222",
      started_at: "2026-10-14T11:00:00Z",
      customer_name: "Fatma Kaya",
      boat_name: "Albatros",
      switchboard_outcome: "usta_yonlendirildi",
      request_category: "su_sihhi_tesisat",
      location: "Göcek D-Marin",
      problem: "Tekne su alıyor, sintine pompası yetersiz",
      service_mode: "yerinde_servis",
      urgency: "acil",
      potential_job: "Acil sintine ve vana kontrolü",
      next_action: "usta_ata",
      summary: "Acil su alma vakası, acil usta yönlendirildi.",
      crm_review_status: "onaylandi",
      crm_review_note: "Göcek ekibi görevlendirildi",
      crm_reviewed_at: "2026-10-14T11:15:00Z",
    },
  },
  {
    id: "15ad79a7-d92c-57f1-9cf3-dcda09fc8130",
    status: "onaylandi",
    category: "elektrik_elektronik",
    description: "Akü grubu değişimi ve şarj regülatörü testi",
    scheduled_at: "2026-10-17T14:00:00Z",
    completed_at: null,
    created_at: "2026-10-13T10:05:00Z",
    customer: {
      id: "11111111-3333-4111-8111-111111111111",
      full_name: "Mehmet Deniz",
      phone: "+90 532 555 66 77",
      email: "mehmet.deniz@example.com",
      marina: "Bodrum Milta Marina",
    },
    boat: {
      id: "22222222-4444-4222-8222-222222222222",
      name: "Poseidon",
      model: "Jeanneau 42",
      year: 2019,
      marina: "Bodrum Milta Marina",
    },
    craftsman: {
      id: "33333333-4444-4333-8333-333333333333",
      full_name: "Ali Usta",
      specialty: "Elektrik & Elektronik",
      phone: "+90 536 777 88 99",
    },
    source_call: {
      call_id: "15ad79a7-d92c-57f1-9cf3-dcda09fc8130",
      started_at: "2026-10-13T09:45:00Z",
      customer_name: "Mehmet Deniz",
      boat_name: "Poseidon",
      switchboard_outcome: "randevu_olusturuldu",
      request_category: "elektrik_elektronik",
      location: "Bodrum Milta Marina",
      problem: "Akü voltajı düşüyor ve invertör devre dışı kalıyor",
      service_mode: "yerinde_servis",
      urgency: "yuksek",
      potential_job: "Akü değişimi",
      next_action: "servis_randevusu_olustur",
      summary: "Müşteri akü ve şarj arızası bildirdi.",
      crm_review_status: "onaylandi",
      crm_review_note: "Bodrum servisi yönlendirildi",
      crm_reviewed_at: "2026-10-13T10:00:00Z",
    },
  },
  {
    id: "1327fac1-7257-5594-af14-cf02e8fb979b",
    status: "devam_ediyor",
    category: "makine",
    description: "Yakıt filtresi değişimi ve enjektör temizliği",
    scheduled_at: "2026-10-18T09:00:00Z",
    completed_at: null,
    created_at: "2026-10-12T14:40:00Z",
    customer: {
      id: "11111111-4444-4111-8111-111111111111",
      full_name: "Kemal Aydoğan",
      phone: "+90 533 888 99 00",
      email: "kemal.aydogan@example.com",
      marina: "Kalamış Marina",
    },
    boat: {
      id: "22222222-5555-4222-8222-222222222222",
      name: "Lodos",
      model: "Hanse 415",
      year: 2017,
      marina: "Kalamış Marina",
    },
    craftsman: {
      id: "33333333-3333-4333-8333-333333333333",
      full_name: "Ahmet Usta",
      specialty: "Motor & Mekanik",
      phone: "+90 533 222 33 44",
    },
    source_call: {
      call_id: "1327fac1-7257-5594-af14-cf02e8fb979b",
      started_at: "2026-10-12T14:30:00Z",
      customer_name: "Kemal Aydoğan",
      boat_name: "Lodos",
      switchboard_outcome: "randevu_olusturuldu",
      request_category: "makine",
      location: "Kalamış Marina",
      problem: "Motor seyir halindeyken tekliyor ve siyah duman atıyor",
      service_mode: "yerinde_servis",
      urgency: "normal",
      potential_job: "Yakıt sistemi revizyonu",
      next_action: "servis_randevusu_olustur",
      summary: "Yakıt sistemi arızası, yerinde bakım sürüyor.",
      crm_review_status: "onaylandi",
      crm_review_note: "Kalamış ustası atandı",
      crm_reviewed_at: "2026-10-12T14:35:00Z",
    },
  },
  {
    id: "ac5bc381-e98b-5e92-af9a-31d7954a66d6",
    status: "tamamlandi",
    category: "temizlik_bakim",
    description: "Kışlama motor bakımı ve sintine temizliği",
    scheduled_at: "2026-10-11T10:00:00Z",
    completed_at: "2026-10-12T16:00:00Z",
    created_at: "2026-10-11T09:30:00Z",
    customer: {
      id: "11111111-5555-4111-8111-111111111111",
      full_name: "Deniz Saygın",
      phone: "+90 535 123 45 67",
      email: "deniz.saygin@example.com",
      marina: "Yalıkavak Marina",
    },
    boat: {
      id: "22222222-6666-4222-8222-222222222222",
      name: "Martı",
      model: "Lagoon 40",
      year: 2022,
      marina: "Yalıkavak Marina",
    },
    craftsman: {
      id: "33333333-5555-4333-8333-333333333333",
      full_name: "Hasan Usta",
      specialty: "Genel Bakım & Temizlik",
      phone: "+90 534 666 77 88",
    },
    source_call: {
      call_id: "ac5bc381-e98b-5e92-af9a-31d7954a66d6",
      started_at: "2026-10-11T09:00:00Z",
      customer_name: "Deniz Saygın",
      boat_name: "Martı",
      switchboard_outcome: "randevu_olusturuldu",
      request_category: "temizlik_bakim",
      location: "Yalıkavak Marina",
      problem: "Kışlama öncesi genel gövde ve sintine temizliği",
      service_mode: "yerinde_servis",
      urgency: "dusuk",
      potential_job: "Kışlık bakım paketi",
      next_action: "servis_randevusu_olustur",
      summary: "Kışlama bakımı başarıyla tamamlandı.",
      crm_review_status: "onaylandi",
      crm_review_note: "İşlem teslim edildi",
      crm_reviewed_at: "2026-10-11T09:15:00Z",
    },
  },
];



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
  next?: {
    revalidate?: number | false;
    tags?: string[];
  };
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
      cache: options.cache ?? "no-store",
      ...options,
      headers,
    });
  } catch {
    throw new ApiError({
      code: "NETWORK_ERROR",
      // Ham ağ hatası ("fetch failed" vb.) kullanıcıya gösterilmez.
      message: "Servise bağlanılamadı. Bağlantınızı kontrol edip tekrar deneyin.",
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
    const params = options.params;
    let list = [...mockSeedCalls];

    if (params?.marina) {
      const marina = String(params.marina).trim().toLowerCase();
      if (marina && marina !== "all") {
        list = list.filter((i) => i.marina?.toLowerCase() === marina);
      }
    }

    if (params?.q) {
      const q = String(params.q).trim().toLowerCase();
      if (q) {
        list = list.filter(
          (i) =>
            (i.customer_name && i.customer_name.toLowerCase().includes(q)) ||
            (i.boat_name && i.boat_name.toLowerCase().includes(q)) ||
            (i.marina && i.marina.toLowerCase().includes(q)),
        );
      }
    }

    if (params?.urgency) {
      const urgency = String(params.urgency).trim();
      if (urgency && urgency !== "all") {
        list = list.filter((i) => i.urgency === urgency);
      }
    }

    if (params?.call_type) {
      const callType = String(params.call_type).trim();
      if (callType && callType !== "all") {
        list = list.filter((i) => i.call_type === callType);
      }
    }

    if (params?.request_category) {
      const reqCat = String(params.request_category).trim();
      if (reqCat && reqCat !== "all") {
        list = list.filter((i) => i.request_category === reqCat);
      }
    }

    if (params?.state) {
      const state = String(params.state).trim();
      if (state && state !== "all") {
        list = list.filter((i) => i.state === state);
      }
    }

    if (params?.date_from) {
      const fromStr = String(params.date_from).trim();
      const fromDate = new Date(fromStr.length === 10 ? `${fromStr}T00:00:00` : fromStr);
      list = list.filter((i) => new Date(i.started_at) >= fromDate);
    }

    if (params?.date_to) {
      const toStr = String(params.date_to).trim();
      const toDate = new Date(toStr.length === 10 ? `${toStr}T23:59:59` : toStr);
      list = list.filter((i) => new Date(i.started_at) <= toDate);
    }

    const page = Math.max(1, Number(params?.page) || 1);
    const pageSize = Math.max(1, Number(params?.page_size) || 20);
    const start = (page - 1) * pageSize;
    const pagedItems = list.slice(start, start + pageSize);

    return {
      items: pagedItems,
      total: list.length,
      page,
      page_size: pageSize,
    } as unknown as T;
  }

  // 2. POST /calls
  if (method === "POST" && path === "/calls") {
    const newCallId = `mock-text-${Date.now()}`;
    mockReanalyzeMap.set(newCallId, {
      step: 0,
      startedAt: Date.now(),
      analysisVersion: 1,
    });
    return {
      ...mockCallAccepted,
      call_id: newCallId,
      state: "beklemede",
    } as unknown as T;
  }

  // 3. POST /calls/audio
  if (method === "POST" && path === "/calls/audio") {
    const newCallId = `mock-audio-${Date.now()}`;
    mockReanalyzeMap.set(newCallId, {
      step: 0,
      startedAt: Date.now(),
      analysisVersion: 1,
    });
    return {
      ...mockCallAccepted,
      call_id: newCallId,
      state: "beklemede",
    } as unknown as T;
  }

  // In-memory mock progress tracking for simulated live analysis (#110)
  // 4. POST /calls/:id/analyze
  if (method === "POST" && /^\/calls\/[^/]+\/analyze$/.test(path)) {
    const id = path.split("/")[2];
    const prev = mockReanalyzeMap.get(id);
    const nextVersion = (prev?.analysisVersion ?? 1) + 1;
    mockReanalyzeMap.set(id, {
      step: 0,
      startedAt: Date.now(),
      analysisVersion: nextVersion,
    });
    return {
      call_id: id,
      state: "beklemede",
      analysis_version: nextVersion,
      created_at: new Date().toISOString(),
    } as unknown as T;
  }

  // 5. GET /calls/:id/status
  if (method === "GET" && /^\/calls\/[^/]+\/status$/.test(path)) {
    const id = path.split("/")[2];
    const progress = mockReanalyzeMap.get(id);
    if (progress) {
      const steps: CallState[] = ["beklemede", "yaziya_cevriliyor", "isleniyor", "tamam"];
      const currentStepState = steps[Math.min(progress.step, steps.length - 1)];
      const result: CallStatus = {
        call_id: id,
        state: currentStepState,
        analysis_version: progress.analysisVersion,
        error: null,
        updated_at: new Date().toISOString(),
      };
      if (progress.step < steps.length - 1) {
        progress.step += 1;
      }
      return result as unknown as T;
    }
    return mockCallStatus as unknown as T;
  }

  // 6. GET /calls/:id (Tekil çağrı detayı)
  if (method === "GET" && /^\/calls\/[^/]+$/.test(path)) {
    const id = path.split("/")[2];
    if (mockCallDetail.id === id) {
      return mockCallDetail as unknown as T;
    }
    // İstenen id mockSeedCalls veya cagri_listesi'ndeyse id eşleyerek detay üret
    const foundInList =
      mockSeedCalls.find((item) => item.id === id) ??
      (mockCallsList.items as unknown as CallListItem[]).find((item) => item.id === id);
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


  // POST /crm/:id/approve veya /crm/suggestions/:id/approve
  if (
    method === "POST" &&
    (/^\/crm\/[^/]+\/approve$/.test(path) || /^\/crm\/suggestions\/[^/]+\/approve$/.test(path))
  ) {
    const parts = path.split("/");
    const id = parts[1] === "suggestions" ? parts[2] : parts[1];

    // 409 Conflict test senaryosu
    if (id === "mock-conflict-409") {
      throw new ApiError({
        code: "CONFLICT",
        message: "Müşteri veya tekne kaydı sistemde eşleşmediği için servis emri oluşturulamadı.",
        requestId: "mock-err-409",
        status: 409,
        details: { reason: "unmatched_customer_or_boat" },
      });
    }

    let payload: Record<string, unknown> = {};
    try {
      if (typeof options.body === "string") {
        payload = JSON.parse(options.body);
      }
    } catch {
      // ignore
    }

    const serviceOrderId = `SO-2026-${Math.floor(1000 + Math.random() * 9000)}`;
    const editedFields: Record<string, unknown> = {};
    const editableKeys = [
      "request_category",
      "location",
      "problem",
      "service_mode",
      "urgency",
      "potential_job",
      "next_action",
    ];
    for (const k of editableKeys) {
      if (payload[k] !== undefined && payload[k] !== null) {
        editedFields[k] = payload[k];
      }
    }

    const found = mockSeedCrm.find((c) => c.call_id === id);
    const reviewedAt = new Date().toISOString();
    const newServiceOrder: ServiceOrderDetail = {
      id: serviceOrderId,
      status: "yeni_atandi",
      category: ((payload.request_category as RequestCategory) || (found?.request_category as RequestCategory) || "makine"),
      description: (payload.problem as string) || (payload.potential_job as string) || found?.problem || "CRM onaylı servis talebi",
      scheduled_at: null,
      completed_at: null,
      created_at: reviewedAt,
      customer: {
        id: `cust-${id.slice(0, 8)}`,
        full_name: found?.customer_name || "Müşteri",
        phone: "+90 532 000 00 00",
        email: null,
        marina: (payload.location as string) || found?.location || "Tuzla Marina",
      },
      boat: {
        id: `boat-${id.slice(0, 8)}`,
        name: found?.boat_name || "Tekne",
        model: "Bavaria 38",
        year: 2020,
        marina: (payload.location as string) || found?.location || "Tuzla Marina",
      },
      craftsman: null,
      source_call: {
        call_id: id,
        started_at: found?.started_at || reviewedAt,
        customer_name: found?.customer_name || null,
        boat_name: found?.boat_name || null,
        switchboard_outcome: "randevu_olusturuldu",
        request_category: ((payload.request_category as RequestCategory) || (found?.request_category as RequestCategory) || null),
        location: (payload.location as string) || found?.location || null,
        problem: (payload.problem as string) || found?.problem || null,
        service_mode: ((payload.service_mode as ServiceMode) || (found?.service_mode as ServiceMode) || null),
        urgency: ((payload.urgency as Urgency) || (found?.urgency as Urgency) || null),
        potential_job: (payload.potential_job as string) || found?.potential_job || null,
        next_action: ((payload.next_action as NextAction) || (found?.next_action as NextAction) || null),
        summary: "CRM onayından otomatik oluşturulan servis emri.",
        crm_review_status: "onaylandi",
        crm_review_note: (payload.note as string) || null,
        crm_reviewed_at: reviewedAt,
      },
    };
    mockServiceOrdersStore.unshift(newServiceOrder);
    mockCrmReviewMap.set(id, {
      status: "onaylandi",
      edited_fields: editedFields as unknown as Record<string, never>,
      note: (payload.note as string) ?? null,
      service_order_id: serviceOrderId,
      reviewed_at: reviewedAt,
    });

    // mockSeedCrm listesini de güncelle
    if (found) {
      found.review_status = "onaylandi";
      found.service_order_id = serviceOrderId;
      found.edited_fields = editedFields;
      Object.assign(found, editedFields);
    }

    return {
      id: `rev-${id.slice(0, 8)}`,
      call_id: id,
      analysis_id: `an-${id.slice(0, 8)}`,
      status: "onaylandi",
      edited_fields: editedFields as unknown as Record<string, never>,
      note: (payload.note as string) ?? null,
      reviewed_at: reviewedAt,
      service_order_id: serviceOrderId,
    } as unknown as T;
  }

  // POST /crm/:id/reject veya /crm/suggestions/:id/reject
  if (
    method === "POST" &&
    (/^\/crm\/[^/]+\/reject$/.test(path) || /^\/crm\/suggestions\/[^/]+\/reject$/.test(path))
  ) {
    const parts = path.split("/");
    const id = parts[1] === "suggestions" ? parts[2] : parts[1];

    let payload: Record<string, unknown> = {};
    try {
      if (typeof options.body === "string") {
        payload = JSON.parse(options.body);
      }
    } catch {
      // ignore
    }

    const reviewedAt = new Date().toISOString();
    const note = (payload.note as string) ?? null;
    mockCrmReviewMap.set(id, {
      status: "reddedildi",
      edited_fields: {},
      note,
      service_order_id: null,
      reviewed_at: reviewedAt,
    });

    const found = mockSeedCrm.find((c) => c.call_id === id);
    if (found) {
      found.review_status = "reddedildi";
      found.service_order_id = null;
    }

    return {
      id: `rev-${id.slice(0, 8)}`,
      call_id: id,
      analysis_id: `an-${id.slice(0, 8)}`,
      status: "reddedildi",
      edited_fields: {},
      note,
      reviewed_at: reviewedAt,
      service_order_id: null,
    } as unknown as T;
  }

  // PATCH /crm/suggestions/:id veya /crm/:id (düzenleme ucu)
  if (
    (method === "PATCH" || method === "PUT") &&
    (/^\/crm\/[^/]+$/.test(path) || /^\/crm\/suggestions\/[^/]+$/.test(path))
  ) {
    const parts = path.split("/");
    const id = parts[1] === "suggestions" ? parts[2] : parts[1];

    let payload: Record<string, unknown> = {};
    try {
      if (typeof options.body === "string") {
        payload = JSON.parse(options.body);
      }
    } catch {
      // ignore
    }

    const prev = mockCrmReviewMap.get(id);
    const editedFields = { ...(prev?.edited_fields ?? {}), ...payload };
    const reviewedAt = new Date().toISOString();
    mockCrmReviewMap.set(id, {
      status: prev?.status ?? "bekliyor",
      edited_fields: editedFields,
      note: prev?.note,
      service_order_id: prev?.service_order_id,
      reviewed_at: reviewedAt,
    });

    const found = mockSeedCrm.find((c) => c.call_id === id);
    if (found) {
      found.edited_fields = editedFields;
      Object.assign(found, editedFields);
    }

    return {
      id: `rev-${id.slice(0, 8)}`,
      call_id: id,
      analysis_id: `an-${id.slice(0, 8)}`,
      status: prev?.status ?? "bekliyor",
      edited_fields: editedFields,
      note: prev?.note ?? null,
      reviewed_at: reviewedAt,
      service_order_id: prev?.service_order_id ?? null,
    } as unknown as T;
  }

  // 7. GET /crm
  if (method === "GET" && path === "/crm") {
    const params = options.params;
    let list: CrmRecordItem[] =
      mockSeedCrm.length > 0
        ? [...mockSeedCrm]
        : ([...mockCrmList.items] as unknown as CrmRecordItem[]);

    if (params?.marina) {
      const marina = String(params.marina).trim().toLowerCase();
      if (marina && marina !== "all") {
        list = list.filter((i) => i.location?.toLowerCase() === marina);
      }
    }

    if (params?.q) {
      const q = String(params.q).trim().toLowerCase();
      if (q) {
        list = list.filter(
          (i) =>
            (i.customer_name && i.customer_name.toLowerCase().includes(q)) ||
            (i.boat_name && i.boat_name.toLowerCase().includes(q)) ||
            (i.location && i.location.toLowerCase().includes(q)) ||
            (i.problem && i.problem.toLowerCase().includes(q)),
        );
      }
    }

    if (params?.urgency) {
      const urgency = String(params.urgency).trim();
      if (urgency && urgency !== "all") {
        list = list.filter((i) => i.urgency === urgency);
      }
    }

    if (params?.request_category) {
      const reqCat = String(params.request_category).trim();
      if (reqCat && reqCat !== "all") {
        list = list.filter((i) => i.request_category === reqCat);
      }
    }

    if (params?.date_from) {
      const fromStr = String(params.date_from).trim();
      const fromDate = new Date(fromStr.length === 10 ? `${fromStr}T00:00:00` : fromStr);
      list = list.filter((i) => new Date(i.started_at) >= fromDate);
    }

    if (params?.date_to) {
      const toStr = String(params.date_to).trim();
      const toDate = new Date(toStr.length === 10 ? `${toStr}T23:59:59` : toStr);
      list = list.filter((i) => new Date(i.started_at) <= toDate);
    }

    const page = Math.max(1, Number(params?.page) || 1);
    const pageSize = Math.max(1, Number(params?.page_size) || 20);
    const start = (page - 1) * pageSize;
    const pagedItems = list.slice(start, start + pageSize);

    return {
      items: pagedItems,
      total: list.length,
      page,
      page_size: pageSize,
    } as unknown as T;
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
    const mockSessions: ChatSessionOut[] = [
      {
        id: "5e8c2a40-3f1b-4d6e-9a7c-0b1d2e3f4a5b",
        title: "Teknemin son bakımı ne zamandı?",
        created_at: "2026-10-12T09:05:00Z",
        updated_at: "2026-10-12T09:05:03Z",
      },
      {
        id: "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
        title: "Bu ay ne kadar harcadım?",
        created_at: "2026-10-10T14:30:00Z",
        updated_at: "2026-10-10T14:30:45Z",
      },
      {
        id: "f1e2d3c4-b5a6-4f7e-8d9c-0b1a2f3e4d5c",
        title: "Sintine alarmı çaldığında ne yapmalıyım?",
        created_at: "2026-10-08T11:15:00Z",
        updated_at: "2026-10-08T11:16:10Z",
      },
    ];
    return mockSessions as unknown as T;
  }

  // 11. GET /chat/sessions/:id
  if (method === "GET" && /^\/chat\/sessions\/[^/]+$/.test(path)) {
    const sessionId = path.split("/")[3];
    if (sessionId === "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d") {
      return {
        session: {
          id: "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
          title: "Bu ay ne kadar harcadım?",
          created_at: "2026-10-10T14:30:00Z",
          updated_at: "2026-10-10T14:30:45Z",
        },
        messages: [
          {
            id: "msg-q2",
            role: "user",
            content: "Bu ay ne kadar harcadım?",
            created_at: "2026-10-10T14:30:00Z",
            question_type: "kapsam_disi" as const,
            sources: [],
            found: true,
          },
          {
            id: "msg-a2",
            role: "assistant",
            content:
              "Kalamış Marina bağlama sözleşmesi ve elektrik/su tüketimi kapsamında bu ay toplam 14.250 TL harcama kaydedilmiştir. Son ödeme tarihi 25 Ekim 2026'dır.",
            created_at: "2026-10-10T14:30:45Z",
            question_type: "sayisal" as const,
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
        ],
      } as unknown as T;
    }
    if (sessionId === "f1e2d3c4-b5a6-4f7e-8d9c-0b1a2f3e4d5c") {
      return {
        session: {
          id: "f1e2d3c4-b5a6-4f7e-8d9c-0b1a2f3e4d5c",
          title: "Sintine alarmı çaldığında ne yapmalıyım?",
          created_at: "2026-10-08T11:15:00Z",
          updated_at: "2026-10-08T11:16:10Z",
        },
        messages: [
          {
            id: "msg-q3",
            role: "user",
            content: "Sintine alarmı çaldığında ilk ne yapmalıyım?",
            created_at: "2026-10-08T11:15:00Z",
            question_type: "kapsam_disi" as const,
            sources: [],
            found: true,
          },
          {
            id: "msg-a3",
            role: "assistant",
            content:
              "Sintine alarmı devreye girdiğinde derhal: 1) Sintine otomatik pompasının (float switch) çalıştığını kontrol edin, 2) Şaft kovanı ve deniz suyu vanalarını (seacock) su sızıntısına karşı gözleyin, 3) Akü ana şalterinin açık olduğundan emin olun.",
            created_at: "2026-10-08T11:16:10Z",
            question_type: "gecmis_oneri" as const,
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
        ],
      } as unknown as T;
    }
    // Default: first session
    return mockChatSessionDetail as unknown as T;
  }


  // 12. GET /service-orders
  if (method === "GET" && path === "/service-orders") {
    const params = options.params;
    let list = [...mockServiceOrdersStore];

    if (params?.status) {
      const status = String(params.status).trim();
      if (status && status !== "all") {
        list = list.filter((i) => i.status === status);
      }
    }

    if (params?.marina) {
      const marina = String(params.marina).trim().toLowerCase();
      if (marina && marina !== "all") {
        list = list.filter(
          (i) =>
            i.boat.marina?.toLowerCase() === marina ||
            i.customer.marina?.toLowerCase() === marina,
        );
      }
    }

    if (params?.q) {
      const q = String(params.q).trim().toLowerCase();
      if (q) {
        list = list.filter(
          (i) =>
            i.id.toLowerCase().includes(q) ||
            i.customer.full_name.toLowerCase().includes(q) ||
            i.boat.name.toLowerCase().includes(q) ||
            (i.boat.marina && i.boat.marina.toLowerCase().includes(q)) ||
            (i.description && i.description.toLowerCase().includes(q)),
        );
      }
    }

    if (params?.date_from) {
      const fromStr = String(params.date_from).trim();
      const fromDate = new Date(fromStr.length === 10 ? `${fromStr}T00:00:00` : fromStr);
      list = list.filter((i) => new Date(i.created_at) >= fromDate);
    }

    if (params?.date_to) {
      const toStr = String(params.date_to).trim();
      const toDate = new Date(toStr.length === 10 ? `${toStr}T23:59:59` : toStr);
      list = list.filter((i) => new Date(i.created_at) <= toDate);
    }

    const page = Math.max(1, Number(params?.page) || 1);
    const pageSize = Math.max(1, Number(params?.page_size) || 20);
    const start = (page - 1) * pageSize;
    const paged = list.slice(start, start + pageSize).map(toServiceOrderListItem);

    return {
      items: paged,
      total: list.length,
      page,
      page_size: pageSize,
    } as unknown as T;
  }

  // 13. GET /service-orders/:id
  if (method === "GET" && /^\/service-orders\/[^/]+$/.test(path)) {
    const id = path.split("/")[2];
    const found = mockServiceOrdersStore.find((o) => o.id === id);
    if (found) {
      return found as unknown as T;
    }
    if (id === mockServiceOrderDetail.id) {
      return mockServiceOrderDetail as unknown as T;
    }
    return {
      ...mockServiceOrderDetail,
      id,
    } as unknown as T;
  }

  // 14. PATCH /service-orders/:id/status
  if (
    (method === "PATCH" || method === "PUT") &&
    /^\/service-orders\/[^/]+\/status$/.test(path)
  ) {
    const id = path.split("/")[2];
    let payload: { status?: ServiceOrderStatus } = {};
    try {
      if (typeof options.body === "string") {
        payload = JSON.parse(options.body);
      }
    } catch {
      // ignore
    }

    const newStatus = payload.status;
    if (!newStatus) {
      throw new ApiError({
        code: "VALIDATION_ERROR",
        message: "Durum alanı zorunludur.",
        requestId: "mock-err-val",
        status: 400,
      });
    }

    let order = mockServiceOrdersStore.find((o) => o.id === id);
    if (!order) {
      if (id === mockServiceOrderDetail.id) {
        order = mockServiceOrderDetail as unknown as ServiceOrderDetail;
        mockServiceOrdersStore.push(order);
      } else {
        throw new ApiError({
          code: "NOT_FOUND",
          message: "Servis emri bulunamadı.",
          requestId: "mock-err-404",
          status: 404,
        });
      }
    }

    const currentStatus = order.status;
    const allowed = ALLOWED_SERVICE_ORDER_TRANSITIONS[currentStatus];
    if (!allowed || !allowed.has(newStatus)) {
      throw new ApiError({
        code: "INVALID_STATUS_TRANSITION",
        message: `Geçersiz durum geçişi: '${currentStatus}' durumundan '${newStatus}' durumuna geçilemez.`,
        requestId: "mock-err-transition",
        status: 400,
        details: { current_status: currentStatus, target_status: newStatus },
      });
    }

    order.status = newStatus;
    if (newStatus === "tamamlandi") {
      order.completed_at = new Date().toISOString();
    }

    return order as unknown as T;
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
  status?: string;
  marina?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface PeriodQueryFilter {
  date_from?: string;
  date_to?: string;
  marina?: string;
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
 * POST /calls/{call_id}/analyze - Çağrıyı yeniden analize gönder (#110)
 */
export async function reanalyzeCall(callId: string): Promise<CallAccepted> {
  return analyzeCall(callId);
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
 * GET /calls/{call_id}/audio - Çağrı ses kaydı URL'si (#80)
 */
export function getCallAudioUrl(callId: string): string {
  return `/api/backend/calls/${callId}/audio`;
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

      // sse-starlette olayları CRLF ile ayırır; ayrıştırmadan önce LF'ye çevrilir.
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");
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


/**
 * POST /crm/{call_id}/approve - CRM önerisini onayla (isteğe bağlı 7 alan düzenlemesi ile) (#106 / #113)
 */
export async function approveCrmRecord(
  callId: string,
  payload?: CrmApproveIn,
): Promise<CrmReviewOut> {
  return apiFetch<CrmReviewOut>(`/crm/${callId}/approve`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : "{}",
  });
}

/**
 * POST /crm/{call_id}/reject - CRM önerisini gerekçe ile reddet (#106 / #113)
 */
export async function rejectCrmRecord(
  callId: string,
  payload?: CrmRejectIn,
): Promise<CrmReviewOut> {
  return apiFetch<CrmReviewOut>(`/crm/${callId}/reject`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : "{}",
  });
}

/**
 * Öneriyi onayla yardımcısı (#113).
 */
export async function approveSuggestion(
  callId: string,
  diff?: Partial<CrmApproveIn>,
  note?: string,
): Promise<CrmReviewOut> {
  return approveCrmRecord(callId, {
    ...diff,
    note: note ?? undefined,
  });
}

/**
 * Öneriyi reddet yardımcısı (#113).
 */
export async function rejectSuggestion(
  callId: string,
  reason?: string,
): Promise<CrmReviewOut> {
  return rejectCrmRecord(callId, {
    note: reason ?? undefined,
  });
}

/**
 * Öneri alanlarını güncelleme / diff gönderme yardımcısı (#113).
 */
export async function updateSuggestion(
  callId: string,
  diff: Partial<CrmApproveIn>,
): Promise<CrmReviewOut> {
  return apiFetch<CrmReviewOut>(`/crm/${callId}`, {
    method: "PATCH",
    body: JSON.stringify(diff),
  });
}


/**
 * GET /service-orders - Sayfalı servis emirleri listesi (#118 / #114)
 */
export async function getServiceOrders(
  filters?: ServiceOrderFilters,
): Promise<Page<ServiceOrderListItem>> {
  return apiFetch<Page<ServiceOrderListItem>>("/service-orders", {
    method: "GET",
    params: filters as Record<string, string | number | boolean | null | undefined>,
  });
}

/**
 * GET /service-orders/{order_id} - Servis emri detayı (#118 / #114)
 */
export async function getServiceOrderById(
  orderId: string,
): Promise<ServiceOrderDetail> {
  return apiFetch<ServiceOrderDetail>(`/service-orders/${orderId}`, {
    method: "GET",
  });
}

/**
 * PATCH /service-orders/{order_id}/status - Servis emri durumunu güncelle (#118 / #114)
 */
export async function updateServiceOrderStatus(
  orderId: string,
  status: ServiceOrderStatus,
): Promise<ServiceOrderDetail> {
  return apiFetch<ServiceOrderDetail>(`/service-orders/${orderId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
