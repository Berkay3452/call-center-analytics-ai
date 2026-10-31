/**
 * Uygulama genelinde kullanılan tip tanımları.
 * backend/app/domain/enums.py ve backend/app/schemas/analysis.py ile birebir uyumludur.
 */

// ---------------------------------------------------------------------------
// Rol sistemi
// ---------------------------------------------------------------------------
export type Role = "admin" | "owner";

// ---------------------------------------------------------------------------
// Backend Enum Eşdeğerleri (Miço Usta Domain)
// ---------------------------------------------------------------------------
export type CallType =
  | "yeni_musteri"
  | "servis"
  | "teklif"
  | "acil"
  | "bilgi";

export type RequestCategory =
  | "makine"
  | "mekanik_hidrolik"
  | "elektrik_elektronik"
  | "su_sihhi_tesisat"
  | "iklimlendirme"
  | "tekne_guvenligi"
  | "temizlik_bakim"
  | "diger";

export type ServiceMode =
  | "yerinde_servis"
  | "atolyede"
  | "uzaktan_destek";

export type Urgency =
  | "dusuk"
  | "normal"
  | "yuksek"
  | "acil";

export type NextAction =
  | "servis_randevusu_olustur"
  | "teklif_hazirla"
  | "geri_ara"
  | "bilgi_ver"
  | "usta_ata"
  | "aksiyon_yok";

export type SalesOutcomeType =
  | "satisa_donustu"
  | "kaybedildi"
  | "beklemede";

export type LossReason =
  | "fiyat"
  | "gec_donus"
  | "rakip"
  | "takvim"
  | "guven"
  | "diger";

/** Boş (null) değer için gösterilecek metin. */
export const EMPTY_LABEL = "—";

/** Etiket sözlüğünden Türkçe karşılığı döner; değer boşsa "—" gösterir. */
export function labelOf<T extends string>(
  labels: Record<T, string>,
  value: T | null | undefined,
): string {
  return value ? (labels[value] ?? value) : EMPTY_LABEL;
}

export type AnalysisStatus = "tamam" | "kismi" | "basarisiz";

// ---------------------------------------------------------------------------
// Türkçe Etiket Haritası
// ---------------------------------------------------------------------------
export const CALL_TYPE_LABELS: Record<CallType, string> = {
  yeni_musteri: "Yeni müşteri",
  servis: "Servis talebi",
  teklif: "Teklif talebi",
  acil: "Acil servis",
  bilgi: "Bilgi",
};

export const REQUEST_CATEGORY_LABELS: Record<RequestCategory, string> = {
  makine: "Makine",
  mekanik_hidrolik: "Mekanik & Hidrolik",
  elektrik_elektronik: "Elektrik & Elektronik",
  su_sihhi_tesisat: "Su & Sıhhi Tesisat",
  iklimlendirme: "İklimlendirme & Havalandırma",
  tekne_guvenligi: "Tekne Güvenlik Hizmetleri",
  temizlik_bakim: "Temizlik & Tekne Bakımı",
  diger: "Diğer",
};

export const SERVICE_MODE_LABELS: Record<ServiceMode, string> = {
  yerinde_servis: "Yerinde servis",
  atolyede: "Atölyede servis",
  uzaktan_destek: "Uzaktan destek",
};

export const URGENCY_LABELS: Record<Urgency, string> = {
  dusuk: "Düşük",
  normal: "Normal",
  yuksek: "Yüksek",
  acil: "Acil",
};

export const NEXT_ACTION_LABELS: Record<NextAction, string> = {
  servis_randevusu_olustur: "Servis randevusu oluştur",
  teklif_hazirla: "Teklif hazırla",
  geri_ara: "Müşteriyi geri ara",
  bilgi_ver: "Bilgi ver",
  usta_ata: "Usta ata",
  aksiyon_yok: "Aksiyon gerekmiyor",
};

export const LOSS_REASON_LABELS: Record<LossReason, string> = {
  fiyat: "Fiyat yüksek bulundu",
  gec_donus: "Geç dönüş yapıldı",
  rakip: "Rakip teklif tercih edildi",
  takvim: "Takvim uygunsuzluğu",
  guven: "Güven / yetersiz referans",
  diger: "Diğer",
};

export const SALES_OUTCOME_LABELS: Record<SalesOutcomeType, string> = {
  satisa_donustu: "Satışa Dönüştü (Kazanıldı)",
  kaybedildi: "Kaybedildi",
  beklemede: "Beklemede / Takipte",
};

// ---------------------------------------------------------------------------
// CRM Kaydı — 7 Temel Alan (Hocanın Şartı / CrmExtraction)
// ---------------------------------------------------------------------------
export interface CrmRecord {
  // Backend (CrmExtraction) konuşmada geçmeyen alanı UYDURMAZ ve null döndürür;
  // bu yüzden 7 alanın hepsi null olabilir ve arayüz boş durumu göstermelidir.
  /** 1. Müşteri talebi / talep kategorisi */
  requestCategory: RequestCategory | null;
  /** 2. Marina veya lokasyon */
  location: string | null;
  /** 3. Problem tanımı */
  problem: string | null;
  /** 4. Hizmetin veriliş biçimi (Yerinde servis vb.) */
  serviceMode: ServiceMode | null;
  /** 5. Aciliyet seviyesi */
  urgency: Urgency | null;
  /** 6. Doğacak potansiyel iş */
  potentialJob: string | null;
  /** 7. Önerilen sonraki aksiyon / servis emri */
  nextAction: NextAction | null;
  /** Kanıt alıntıları */
  evidence?: Partial<Record<string, string>>;
}

export type CrmReviewStatus = "bekliyor" | "onaylandi" | "reddedildi";

export const CRM_REVIEW_STATUS_LABELS: Record<CrmReviewStatus, string> = {
  bekliyor: "Bekliyor",
  onaylandi: "Onaylandı",
  reddedildi: "Reddedildi",
};

// ---------------------------------------------------------------------------
// CRM Önerisi Kartı (Sayfalar ve API için)
// ---------------------------------------------------------------------------
export interface CrmSuggestion extends CrmRecord {
  callId: string;
  caller: string;
  boatName?: string;
  reviewStatus?: CrmReviewStatus;
  editedFields?: Record<string, unknown>;
  serviceOrderId?: string | null;
}

// ---------------------------------------------------------------------------
// Satış Analizi
// ---------------------------------------------------------------------------
export interface SalesAnalysisData {
  outcome: SalesOutcomeType;
  lossReason?: LossReason | null;
  evidence?: string | null;
  confidence: number;
}

// ---------------------------------------------------------------------------
// Çağrı Nesnesi
// ---------------------------------------------------------------------------
export type CallStatus = "completed" | "missed" | "ongoing";

export interface Call {
  id: string;
  caller: string;
  callerPhone?: string;
  boatName?: string;
  boatModel?: string;
  startedAt: string;
  durationSec: number;
  status: CallStatus;
  callType: CallType | null;
  urgency: Urgency | null;
  location: string | null;
  analysisStatus: AnalysisStatus;
  /** Analiz henüz bitmediyse süreç aşaması (beklemede, yaziya_cevriliyor, isleniyor). */
  pendingState?: "beklemede" | "yaziya_cevriliyor" | "isleniyor";
  transcript: string;
  summary: string;
  keyPoints?: string[];
  crm: CrmRecord;
  sales: SalesAnalysisData;
  tags: string[];
}

// ---------------------------------------------------------------------------
// KPI Kartları ve Grafikler
// ---------------------------------------------------------------------------
export interface KpiCard {
  label: string;
  value: number | string;
  unit?: string;
  changePercent?: number;
  variant?: "default" | "urgent" | "success" | "warning";
}

export interface CountItem {
  name: string;
  count: number;
}

// ---------------------------------------------------------------------------
// Asistan Mesajı ve Kaynak Atfı
// ---------------------------------------------------------------------------
export type MessageRole = "user" | "assistant";

/** Tekil kaynak atıf kartı */
export interface CitationCard {
  sourceTitle: string;
  date: string;
  callId?: string;
  excerpt?: string;
  kind?: "service_record" | "boat_note" | "expense" | "subscription" | string;
  recordId?: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  /**
   * Birden fazla kaynak kartı listesi.
   * Boş dizi veya undefined → kaynak kartı gösterilmez ("bulamadım" durumu).
   */
  citations?: CitationCard[];
  /** Bilgi bulunup bulunmadığı bayrağı */
  found?: boolean;
  /** Mesajın akmakta (streaming) olup olmadığı */
  isStreaming?: boolean;
  /** Hata durumu */
  error?: {
    code: string;
    message: string;
    requestId?: string | null;
    isApiKeyError?: boolean;
  };
}

// ---------------------------------------------------------------------------
// Günlük Çağrı Trendi
// ---------------------------------------------------------------------------
export interface DailyCallPoint {
  date: string;
  label: string;
  count: number;
}

// ---------------------------------------------------------------------------
// Arıza Kategorisi İstatistiği
// ---------------------------------------------------------------------------
export interface FailureCategoryItem {
  category: RequestCategory;
  label: string;
  count: number;
  pct: number;
  color: string;
}

// ---------------------------------------------------------------------------
// Marina İstatistiği
// ---------------------------------------------------------------------------
export interface MarinaStatItem {
  name: string;
  count: number;
  pct: number;
  tag: string;
}

// ---------------------------------------------------------------------------
// Kayıp Nedeni İstatistiği
// ---------------------------------------------------------------------------
export interface LossReasonItem {
  reason: LossReason;
  label: string;
  pct: number;
  count: number;
  color: string;
}

// ---------------------------------------------------------------------------
// Analiz Durumu Etiketi
// ---------------------------------------------------------------------------
export const ANALYSIS_STATUS_LABELS: Record<AnalysisStatus, string> = {
  tamam: "Tamam",
  kismi: "Kısmi",
  basarisiz: "Başarısız",
};

// ---------------------------------------------------------------------------
// Standart Marina Listesi
// ---------------------------------------------------------------------------
export const MARINA_OPTIONS = [
  "Ataköy Marina",
  "Bodrum Milta Marina",
  "Çeşme Marina",
  "Göcek D-Marin",
  "İstinye Tekne Park",
  "Kalamış Marina",
  "Marmaris Netsel Marina",
  "Pendik Marinturk Marina",
  "Tuzla Marina",
  "Yalıkavak Marina",
];


// ---------------------------------------------------------------------------
// Servis Emirleri (#118 / #114)
// ---------------------------------------------------------------------------
export type ServiceOrderStatus =
  | "yeni_atandi"
  | "kesifte"
  | "onaylandi"
  | "devam_ediyor"
  | "tamamlandi";

export const SERVICE_ORDER_STATUS_ORDER: ServiceOrderStatus[] = [
  "yeni_atandi",
  "kesifte",
  "onaylandi",
  "devam_ediyor",
  "tamamlandi",
];

export const SERVICE_ORDER_STATUS_LABELS: Record<ServiceOrderStatus, string> = {
  yeni_atandi: "Yeni Atandı",
  kesifte: "Keşifte",
  onaylandi: "Onaylandı",
  devam_ediyor: "Devam Ediyor",
  tamamlandi: "Tamamlandı",
};

export const NEXT_SERVICE_ORDER_STATUS: Record<ServiceOrderStatus, ServiceOrderStatus | null> = {
  yeni_atandi: "kesifte",
  kesifte: "onaylandi",
  onaylandi: "devam_ediyor",
  devam_ediyor: "tamamlandi",
  tamamlandi: null,
};

export const NEXT_STATUS_ACTION_LABELS: Record<ServiceOrderStatus, string | null> = {
  yeni_atandi: "Keşfe Gönder",
  kesifte: "Keşfi Onayla",
  onaylandi: "İşe Başla",
  devam_ediyor: "İşi Tamamla",
  tamamlandi: null,
};

export const SERVICE_ORDER_STATUS_BADGE: Record<ServiceOrderStatus, string> = {
  yeni_atandi: "bg-brand-50 text-brand-700 border-brand-100",
  kesifte: "bg-amber-50 text-amber-800 border-amber-200",
  onaylandi: "bg-accent-50 text-accent-700 border-accent-100",
  devam_ediyor: "bg-brand-100 text-brand-800 border-brand-200",
  tamamlandi: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

export function formatOrderCode(id: string): string {
  if (id.startsWith("SO-")) return id;
  if (id === "55555555-5555-4555-8555-555555555555") return "SO-2026-0001";
  return `SO-${id.slice(0, 8).toUpperCase()}`;
}
