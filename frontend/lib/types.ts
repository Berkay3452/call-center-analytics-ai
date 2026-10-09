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
  | "motor_arizasi"
  | "elektrik_arizasi"
  | "yakit_sistemi"
  | "govde_ve_kil"
  | "periyodik_bakim"
  | "kis_bakimi"
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
  motor_arizasi: "Motor arızası",
  elektrik_arizasi: "Elektrik arızası",
  yakit_sistemi: "Yakıt sistemi",
  govde_ve_kil: "Gövde ve kıl bakımı",
  periyodik_bakim: "Periyodik bakım",
  kis_bakimi: "Kış bakımı",
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
  acil: "Kritik (Acil)",
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

// ---------------------------------------------------------------------------
// CRM Kaydı — 7 Temel Alan (Hocanın Şartı / CrmExtraction)
// ---------------------------------------------------------------------------
export interface CrmRecord {
  /** 1. Müşteri talebi / talep kategorisi */
  requestCategory: RequestCategory;
  /** 2. Marina veya lokasyon */
  location: string;
  /** 3. Problem tanımı */
  problem: string;
  /** 4. Hizmetin veriliş biçimi (Yerinde servis vb.) */
  serviceMode: ServiceMode;
  /** 5. Aciliyet seviyesi */
  urgency: Urgency;
  /** 6. Doğacak potansiyel iş */
  potentialJob: string;
  /** 7. Önerilen sonraki aksiyon / servis emri */
  nextAction: NextAction;
  /** Kanıt alıntıları */
  evidence?: Partial<Record<string, string>>;
}

// ---------------------------------------------------------------------------
// CRM Önerisi Kartı (Sayfalar ve API için)
// ---------------------------------------------------------------------------
export interface CrmSuggestion extends CrmRecord {
  callId: string;
  caller: string;
  boatName?: string;
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
  callType: CallType;
  urgency: Urgency;
  location: string;
  analysisStatus: AnalysisStatus;
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

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  /** Kaynak atıf kartı (örn. "Kaynak: 12 Ekim tarihli usta görüşmesi") */
  citation?: {
    sourceTitle: string;
    date: string;
    callId?: string;
    excerpt?: string;
  };
}
