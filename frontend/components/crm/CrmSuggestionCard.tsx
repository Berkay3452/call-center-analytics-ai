"use client";

import { useState, useRef, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useFocusTrap } from "@/lib/use-focus-trap";
import { approveCrmRecord, matchCall, rejectCrmRecord } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  EMPTY_LABEL,
  labelOf,
  NEXT_ACTION_LABELS,
  REQUEST_CATEGORY_LABELS,
  SERVICE_MODE_LABELS,
  URGENCY_LABELS,
  CRM_REVIEW_STATUS_LABELS,
  type CrmSuggestion,
  type CrmReviewStatus,
  type Urgency,
  type RequestCategory,
  type ServiceMode,
  type NextAction,
} from "@/lib/types";
import type { CrmApproveIn } from "@/lib/api/types";
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  Select,
  Textarea,
  buttonClasses,
  type Tone,
} from "@/components/ui";

interface CrmSuggestionCardProps {
  suggestion: CrmSuggestion;
  variant?: "list" | "detail";
  onStatusChange?: (callId: string, newStatus: CrmReviewStatus, serviceOrderId?: string | null) => void;
}

const URGENCY_TONE: Record<Urgency, Tone> = {
  acil: "danger",
  yuksek: "accent",
  normal: "brand",
  dusuk: "neutral",
};

const STATUS_TONE: Record<CrmReviewStatus, Tone> = {
  bekliyor: "warning",
  onaylandi: "success",
  reddedildi: "danger",
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const CONFLICT_MESSAGE =
  "Bu çağrı henüz bir müşteri veya tekneyle eşleşmediği için servis emri açılamadı. “Elle eşleştir” ile müşteriyi bağlayıp tekrar onaylayabilirsiniz.";

/** Hata nesnesini kullanıcıya gösterilecek anlaşılır Türkçe metne çevirir. */
function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return CONFLICT_MESSAGE;
    if (err.status === 404) return "Kayıt bulunamadı. Sayfayı yenileyip tekrar deneyin.";
    if (err.status === 400) return "Girilen bilgiler geçerli değil. Alanları kontrol edip tekrar deneyin.";
    if (err.status && err.status >= 500) return "Sunucu şu an yanıt veremiyor. Biraz sonra tekrar deneyin.";
  }
  return fallback;
}

function Modal({
  title,
  titleId,
  description,
  onClose,
  triggerRef,
  children,
}: {
  title: string;
  titleId: string;
  description?: string;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
  children: ReactNode;
}) {
  const ref = useFocusTrap<HTMLDivElement>({ isOpen: true, onClose, returnFocusRef: triggerRef });
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-200 bg-white p-6"
      >
        <div className="mb-4 flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
            <h3 id={titleId} className="text-base font-semibold text-brand-800">
              {title}
            </h3>
            {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Kapat">
            ✕
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function CrmSuggestionCard({
  suggestion,
  variant = "list",
  onStatusChange,
}: CrmSuggestionCardProps) {
  const [reviewStatus, setReviewStatus] = useState<CrmReviewStatus>(
    suggestion.reviewStatus ?? "bekliyor",
  );
  const [serviceOrderId, setServiceOrderId] = useState<string | null>(
    suggestion.serviceOrderId ?? null,
  );
  const [editedFields, setEditedFields] = useState<Record<string, unknown>>(
    suggestion.editedFields ?? {},
  );

  // Güncel değerler (düzenlemeler yansıtılmış)
  const [currentValues, setCurrentValues] = useState({
    requestCategory: suggestion.requestCategory,
    location: suggestion.location,
    problem: suggestion.problem,
    serviceMode: suggestion.serviceMode,
    urgency: suggestion.urgency,
    potentialJob: suggestion.potentialJob,
    nextAction: suggestion.nextAction,
  });

  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [isMatchModalOpen, setIsMatchModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [matchForm, setMatchForm] = useState({ customerId: "", boatId: "" });
  const [matchError, setMatchError] = useState<string | null>(null);
  const [matchDone, setMatchDone] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isConflict, setIsConflict] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const router = useRouter();

  const editTriggerRef = useRef<HTMLButtonElement | null>(null);
  const rejectTriggerRef = useRef<HTMLButtonElement | null>(null);
  const matchTriggerRef = useRef<HTMLButtonElement | null>(null);

  const [editFormData, setEditFormData] = useState({
    request_category: "",
    location: "",
    problem: "",
    service_mode: "",
    urgency: "",
    potential_job: "",
    next_action: "",
    note: "",
  });

  const openEditModal = () => {
    setActionError(null);
    setIsConflict(false);
    setEditFormData({
      request_category: currentValues.requestCategory ?? "",
      location: currentValues.location ?? "",
      problem: currentValues.problem ?? "",
      service_mode: currentValues.serviceMode ?? "",
      urgency: currentValues.urgency ?? "",
      potential_job: currentValues.potentialJob ?? "",
      next_action: currentValues.nextAction ?? "",
      note: "",
    });
    setIsEditModalOpen(true);
  };

  // Onaylama işlemi (isteğe bağlı diff ile). Başarılıysa true döner.
  const handleApprove = async (diff?: Partial<CrmApproveIn>, note?: string): Promise<boolean> => {
    if (isSubmitting) return false;
    setIsSubmitting(true);
    setActionError(null);
    setIsConflict(false);

    try {
      const res = await approveCrmRecord(suggestion.callId, { ...diff, note: note || undefined });
      setReviewStatus(res.status);
      const newOrderId = res.service_order_id ? String(res.service_order_id) : null;
      setServiceOrderId(newOrderId);
      if (res.edited_fields && Object.keys(res.edited_fields).length > 0) {
        setEditedFields((prev) => ({ ...prev, ...res.edited_fields }));
      }
      setIsEditModalOpen(false);
      onStatusChange?.(suggestion.callId, res.status, newOrderId);
      router.refresh(); // sekme sayıları ve liste güncellensin
      return true;
    } catch (err: unknown) {
      setIsConflict(err instanceof ApiError && err.status === 409);
      setActionError(describeError(err, "Onaylama sırasında bir sorun oluştu. Lütfen tekrar deneyin."));
      return false;
    } finally {
      setIsSubmitting(false);
    }
  };

  // Düzenleme formunu kaydet & onayla
  const handleSaveAndApprove = async (e: React.FormEvent) => {
    e.preventDefault();

    const diff: Partial<CrmApproveIn> = {};
    if (editFormData.request_category !== (currentValues.requestCategory ?? "")) {
      diff.request_category = (editFormData.request_category as RequestCategory) || undefined;
    }
    if (editFormData.location !== (currentValues.location ?? "")) {
      diff.location = editFormData.location || undefined;
    }
    if (editFormData.problem !== (currentValues.problem ?? "")) {
      diff.problem = editFormData.problem || undefined;
    }
    if (editFormData.service_mode !== (currentValues.serviceMode ?? "")) {
      diff.service_mode = (editFormData.service_mode as ServiceMode) || undefined;
    }
    if (editFormData.urgency !== (currentValues.urgency ?? "")) {
      diff.urgency = (editFormData.urgency as Urgency) || undefined;
    }
    if (editFormData.potential_job !== (currentValues.potentialJob ?? "")) {
      diff.potential_job = editFormData.potential_job || undefined;
    }
    if (editFormData.next_action !== (currentValues.nextAction ?? "")) {
      diff.next_action = (editFormData.next_action as NextAction) || undefined;
    }

    const ok = await handleApprove(diff, editFormData.note);
    // Değerleri yalnızca kayıt başarılıysa ekranda güncelle
    if (ok) {
      setCurrentValues({
        requestCategory: (editFormData.request_category as RequestCategory) || null,
        location: editFormData.location || null,
        problem: editFormData.problem || null,
        serviceMode: (editFormData.service_mode as ServiceMode) || null,
        urgency: (editFormData.urgency as Urgency) || null,
        potentialJob: editFormData.potential_job || null,
        nextAction: (editFormData.next_action as NextAction) || null,
      });
    }
  };

  const handleReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setActionError(null);
    setIsConflict(false);

    try {
      const res = await rejectCrmRecord(suggestion.callId, {
        note: rejectReason.trim() || undefined,
      });
      setReviewStatus(res.status);
      setIsRejectModalOpen(false);
      onStatusChange?.(suggestion.callId, res.status, null);
      router.refresh();
    } catch (err: unknown) {
      setActionError(describeError(err, "Reddetme sırasında bir sorun oluştu. Lütfen tekrar deneyin."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleMatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    const customerId = matchForm.customerId.trim();
    const boatId = matchForm.boatId.trim();
    if (!UUID_RE.test(customerId)) {
      setMatchError("Müşteri numarası geçerli bir kimlik (UUID) olmalı. Örnek: 123e4567-e89b-12d3-a456-426614174000");
      return;
    }
    if (boatId && !UUID_RE.test(boatId)) {
      setMatchError("Tekne numarası geçerli bir kimlik (UUID) olmalı ya da boş bırakılmalı.");
      return;
    }
    setIsSubmitting(true);
    setMatchError(null);
    try {
      await matchCall(suggestion.callId, { customer_id: customerId, boat_id: boatId || null });
      setMatchDone(true);
      setIsMatchModalOpen(false);
      setActionError(null);
      setIsConflict(false);
      router.refresh();
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 400) {
        setMatchError("Seçilen tekne bu müşteriye ait değil. Tekne numarasını kontrol edin.");
      } else if (err instanceof ApiError && err.status === 404) {
        setMatchError("Bu numaraya sahip müşteri veya tekne bulunamadı.");
      } else {
        setMatchError(describeError(err, "Eşleştirme sırasında bir sorun oluştu. Lütfen tekrar deneyin."));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const isEdited = (key: string) => Boolean(editedFields[key]);

  const fields: { key: string; label: string; value: string }[] = [
    { key: "request_category", label: "Talep", value: labelOf(REQUEST_CATEGORY_LABELS, currentValues.requestCategory) },
    { key: "location", label: "Marina", value: currentValues.location ?? EMPTY_LABEL },
    { key: "service_mode", label: "Hizmet biçimi", value: labelOf(SERVICE_MODE_LABELS, currentValues.serviceMode) },
    { key: "potential_job", label: "Olası iş", value: currentValues.potentialJob ?? EMPTY_LABEL },
    { key: "next_action", label: "Sonraki adım", value: labelOf(NEXT_ACTION_LABELS, currentValues.nextAction) },
  ];

  const evidence = suggestion.evidence ? Object.entries(suggestion.evidence) : [];

  return (
    <Card className="space-y-4">
      {/* Başlık: müşteri · tekne, durum ve aciliyet */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-brand-800">
            {suggestion.caller}
            {suggestion.boatName && (
              <span className="font-normal text-slate-500"> · {suggestion.boatName}</span>
            )}
          </h2>
          <p className="mt-0.5 text-sm text-slate-700">
            {currentValues.problem ?? "Sorun tanımı çıkarılamadı"}
            {isEdited("problem") && <span className="ml-2 text-xs text-slate-500">(düzenlendi)</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {currentValues.urgency && (
            <Badge tone={URGENCY_TONE[currentValues.urgency]}>
              {labelOf(URGENCY_LABELS, currentValues.urgency)}
            </Badge>
          )}
          <Badge tone={STATUS_TONE[reviewStatus]}>{labelOf(CRM_REVIEW_STATUS_LABELS, reviewStatus)}</Badge>
        </div>
      </div>

      {/* Okunur etiketli alanlar */}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
        {fields.map((f) => (
          <div key={f.key}>
            <dt className="text-xs text-slate-500">
              {f.label}
              {isEdited(f.key) && " (düzenlendi)"}
            </dt>
            <dd className="font-medium text-slate-800">{f.value}</dd>
          </div>
        ))}
      </dl>

      {evidence.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs font-medium text-brand-700">
            Konuşmadan alıntılar ({evidence.length})
          </summary>
          <ul className="mt-2 space-y-1 text-slate-600">
            {evidence.map(([key, val]) => (
              <li key={key}>
                <span className="font-medium text-slate-700">{key}:</span> &ldquo;{val}&rdquo;
              </li>
            ))}
          </ul>
        </details>
      )}

      {matchDone && (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          Çağrı müşteriye bağlandı. Şimdi tekrar onaylayabilirsiniz.
        </p>
      )}

      {actionError && !isEditModalOpen && !isRejectModalOpen && (
        <div
          role="alert"
          className={`rounded-lg border p-3 text-sm ${
            isConflict ? "border-amber-200 bg-amber-50 text-amber-800" : "border-red-200 bg-red-50 text-red-700"
          }`}
        >
          <p>{actionError}</p>
          {isConflict && (
            <Button
              variant="secondary"
              size="sm"
              className="mt-2"
              onClick={() => {
                setMatchError(null);
                setIsMatchModalOpen(true);
              }}
            >
              Elle eşleştir
            </Button>
          )}
        </div>
      )}

      {/* Eylemler: duruma göre */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          {reviewStatus === "onaylandi" && (
            <>
              <span>Onaylandı, servis emri açıldı.</span>
              {serviceOrderId && (
                <Link
                  href={`/admin/service-orders/${serviceOrderId}`}
                  className={buttonClasses("secondary", "sm")}
                >
                  Servis emrini aç
                </Link>
              )}
            </>
          )}
          {reviewStatus === "reddedildi" && <span>Bu öneri reddedildi.</span>}
          {variant === "list" && (
            <Link href={`/admin/calls/${suggestion.callId}`} className="text-brand-700 underline">
              Çağrıyı gör
            </Link>
          )}
        </div>

        {reviewStatus !== "onaylandi" && (
          <div className="flex flex-wrap items-center gap-2">
            {/* Eşleşme uyarısında aynı eylem uyarı kutusunda sunulur; iki kez gösterilmez */}
            {!isConflict && (
            <button
              ref={matchTriggerRef}
              type="button"
              disabled={isSubmitting}
              onClick={() => {
                setMatchError(null);
                setIsMatchModalOpen(true);
              }}
              className={buttonClasses("ghost", "sm")}
            >
              Elle eşleştir
            </button>
            )}
            <button
              ref={editTriggerRef}
              type="button"
              onClick={openEditModal}
              disabled={isSubmitting}
              className={buttonClasses("secondary", "sm")}
            >
              Düzenle
            </button>
            {reviewStatus === "bekliyor" && (
              <button
                ref={rejectTriggerRef}
                type="button"
                onClick={() => {
                  setActionError(null);
                  setIsRejectModalOpen(true);
                }}
                disabled={isSubmitting}
                className={buttonClasses("danger", "sm")}
              >
                Reddet
              </button>
            )}
            <Button size="sm" disabled={isSubmitting} onClick={() => handleApprove()}>
              {isSubmitting ? "Onaylanıyor…" : "Onayla ve Servis Emri Oluştur"}
            </Button>
          </div>
        )}
      </div>

      {isEditModalOpen && (
        <Modal
          title="Öneri alanlarını düzenle"
          titleId="edit-modal-title"
          description="Kaydettiğinizde değişen alanlar “düzenlendi” diye işaretlenir ve öneri onaylanır."
          onClose={() => setIsEditModalOpen(false)}
          triggerRef={editTriggerRef}
        >
          {actionError && (
            <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {actionError}
            </p>
          )}
          <form onSubmit={handleSaveAndApprove} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field id="crm-edit-category" label="Müşteri talebi">
                <Select
                  id="crm-edit-category"
                  value={editFormData.request_category}
                  onChange={(e) => setEditFormData({ ...editFormData, request_category: e.target.value })}
                >
                  <option value="">Seçiniz</option>
                  {Object.entries(REQUEST_CATEGORY_LABELS).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id="crm-edit-location" label="Marina">
                <Input
                  id="crm-edit-location"
                  value={editFormData.location}
                  onChange={(e) => setEditFormData({ ...editFormData, location: e.target.value })}
                  placeholder="Örn: Tuzla Marina"
                />
              </Field>
              <Field id="crm-edit-problem" label="Sorun tanımı" className="sm:col-span-2">
                <Textarea
                  id="crm-edit-problem"
                  rows={3}
                  value={editFormData.problem}
                  onChange={(e) => setEditFormData({ ...editFormData, problem: e.target.value })}
                  placeholder="Arıza veya müşteri şikayeti"
                />
              </Field>
              <Field id="crm-edit-service-mode" label="Hizmet biçimi">
                <Select
                  id="crm-edit-service-mode"
                  value={editFormData.service_mode}
                  onChange={(e) => setEditFormData({ ...editFormData, service_mode: e.target.value })}
                >
                  <option value="">Seçiniz</option>
                  {Object.entries(SERVICE_MODE_LABELS).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id="crm-edit-urgency" label="Aciliyet">
                <Select
                  id="crm-edit-urgency"
                  value={editFormData.urgency}
                  onChange={(e) => setEditFormData({ ...editFormData, urgency: e.target.value })}
                >
                  <option value="">Seçiniz</option>
                  {Object.entries(URGENCY_LABELS).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id="crm-edit-potential-job" label="Olası iş">
                <Input
                  id="crm-edit-potential-job"
                  value={editFormData.potential_job}
                  onChange={(e) => setEditFormData({ ...editFormData, potential_job: e.target.value })}
                  placeholder="Örn: Motor arıza tespiti ve bakımı"
                />
              </Field>
              <Field id="crm-edit-next-action" label="Sonraki adım">
                <Select
                  id="crm-edit-next-action"
                  value={editFormData.next_action}
                  onChange={(e) => setEditFormData({ ...editFormData, next_action: e.target.value })}
                >
                  <option value="">Seçiniz</option>
                  {Object.entries(NEXT_ACTION_LABELS).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id="crm-edit-note" label="Onay notu (isteğe bağlı)" className="sm:col-span-2">
                <Input
                  id="crm-edit-note"
                  value={editFormData.note}
                  onChange={(e) => setEditFormData({ ...editFormData, note: e.target.value })}
                  placeholder="Örn: Müşteri acil usta istedi."
                />
              </Field>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <Button variant="secondary" onClick={() => setIsEditModalOpen(false)} disabled={isSubmitting}>
                İptal
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Kaydediliyor…" : "Kaydet ve Onayla"}
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {isRejectModalOpen && (
        <Modal
          title="Öneriyi reddet"
          titleId="reject-modal-title"
          onClose={() => setIsRejectModalOpen(false)}
          triggerRef={rejectTriggerRef}
        >
          {actionError && (
            <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {actionError}
            </p>
          )}
          <form onSubmit={handleReject} className="space-y-4">
            <Field id="crm-reject-reason" label="Red gerekçesi (isteğe bağlı)">
              <Textarea
                id="crm-reject-reason"
                rows={3}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Örn: Bilgi amaçlı arama."
              />
            </Field>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <Button variant="secondary" onClick={() => setIsRejectModalOpen(false)} disabled={isSubmitting}>
                Vazgeç
              </Button>
              <Button type="submit" variant="danger" disabled={isSubmitting}>
                {isSubmitting ? "Reddediliyor…" : "Reddet"}
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {isMatchModalOpen && (
        <Modal
          title="Çağrıyı elle eşleştir"
          titleId="match-modal-title"
          description="Çağrıyı kayıtlı bir müşteriye (ve istenirse teknesine) bağlar. Eşleşince servis emri açılabilir."
          onClose={() => setIsMatchModalOpen(false)}
          triggerRef={matchTriggerRef}
        >
          <form onSubmit={handleMatch} className="space-y-4">
            <Field
              id="crm-match-customer"
              label="Müşteri numarası"
              hint="Müşteri kaydındaki kimlik (UUID)."
              error={matchError}
            >
              <Input
                id="crm-match-customer"
                value={matchForm.customerId}
                onChange={(e) => setMatchForm({ ...matchForm, customerId: e.target.value })}
                placeholder="123e4567-e89b-12d3-a456-426614174000"
                autoComplete="off"
                required
              />
            </Field>
            <Field id="crm-match-boat" label="Tekne numarası (isteğe bağlı)" hint="Boşsa yalnızca müşteri bağlanır.">
              <Input
                id="crm-match-boat"
                value={matchForm.boatId}
                onChange={(e) => setMatchForm({ ...matchForm, boatId: e.target.value })}
                autoComplete="off"
              />
            </Field>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <Button variant="secondary" onClick={() => setIsMatchModalOpen(false)} disabled={isSubmitting}>
                Vazgeç
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Eşleştiriliyor…" : "Eşleştir"}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}
