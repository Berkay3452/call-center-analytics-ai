"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useFocusTrap } from "@/lib/use-focus-trap";
import { approveCrmRecord, matchCall, rejectCrmRecord, searchCustomers } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  EMPTY_LABEL,
  labelOf,
  NEXT_ACTION_LABELS,
  CRM_FIELD_LABELS,
  crmFieldLabel,
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
import type { CrmApproveIn, CustomerSearchItem } from "@/lib/api/types";
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

const CONFLICT_MESSAGE =
  "Bu çağrı henüz bir müşteri veya tekneyle eşleşmediği için servis emri açılamadı. “Müşteri ve tekne seç” ile müşteriyi bağlayıp tekrar onaylayabilirsiniz.";

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

  const [manualMatch, setManualMatch] = useState<boolean | null>(null);
  const isMatched = manualMatch ?? Boolean(suggestion.matchMethod && suggestion.matchMethod !== "yok");
  const [matchedCustomerName, setMatchedCustomerName] = useState<string | null>(
    suggestion.matchedCustomerName ?? null,
  );
  const [matchedBoatName, setMatchedBoatName] = useState<string | null>(
    suggestion.matchedBoatName ?? null,
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

  // Eşleştirme modalı state'i
  const [searchQuery, setSearchQuery] = useState("");
  const [customers, setCustomers] = useState<CustomerSearchItem[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [selectedBoatId, setSelectedBoatId] = useState<string>("");
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
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

  const openMatchModal = () => {
    setMatchError(null);
    setSearchQuery("");
    setSelectedCustomerId("");
    setSelectedBoatId("");
    setCustomers([]);
    setIsLoadingCustomers(true);
    setIsMatchModalOpen(true);
  };

  useEffect(() => {
    if (!isMatchModalOpen) return;
    let active = true;
    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await searchCustomers(searchQuery.trim(), 20);
        if (active) {
          setCustomers(res);
          setMatchError(null);
        }
      } catch {
        if (active) setMatchError("Müşteri listesi yüklenemedi. Lütfen tekrar deneyin.");
      } finally {
        if (active) {
          setIsSearching(false);
          setIsLoadingCustomers(false);
        }
      }
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [searchQuery, isMatchModalOpen]);

  const handleSelectCustomer = (cust: CustomerSearchItem) => {
    setSelectedCustomerId(cust.id);
    setSelectedBoatId("");
  };

  const handleMatchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customers.find((c) => c.id === selectedCustomerId)?.boats?.some((b) => b.id === selectedBoatId) || isSubmitting) return;

    setIsSubmitting(true);
    setMatchError(null);

    try {
      const res = await matchCall(suggestion.callId, {
        customer_id: selectedCustomerId,
        boat_id: selectedBoatId,
      });

      const selectedCust = customers.find((c) => c.id === selectedCustomerId);
      const selectedBoat = selectedCust?.boats?.find((b) => b.id === selectedBoatId);

      if (!res.customer_id || !res.boat_id) {
        setMatchError("Eşleştirme tamamlanamadı. Müşteri ve tekneyi tekrar seçin.");
        return;
      }
      setManualMatch(true);
      setMatchDone(true);
      setMatchedCustomerName(selectedCust?.name ?? res.customer_name ?? null);
      setMatchedBoatName(selectedBoat?.name ?? res.boat_name ?? null);
      setIsMatchModalOpen(false);
      setActionError(null);
      setIsConflict(false);
      router.refresh(); // sekme ve kartları güncelle
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 400) {
        setMatchError("Seçilen tekne bu müşteriye ait değil. Lütfen geçerli bir seçim yapın.");
      } else if (err instanceof ApiError && err.status === 404) {
        setMatchError("Seçilen müşteri veya tekne sistemde bulunamadı.");
      } else {
        setMatchError(describeError(err, "Eşleştirme sırasında bir sorun oluştu. Lütfen tekrar deneyin."));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Onaylama işlemi (isteğe bağlı diff ile). Başarılıysa true döner.
  const handleApprove = async (diff?: Partial<CrmApproveIn>, note?: string): Promise<boolean> => {
    if (isSubmitting || !isMatched) return false;
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
      router.refresh();
      return true;
    } catch (err: unknown) {
      const isConf = err instanceof ApiError && err.status === 409;
      setIsConflict(isConf);
      if (isConf) {
        setManualMatch(false);
      }
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

  const isEdited = (key: string) => Boolean(editedFields[key]);

  const fields: { key: string; label: string; value: string }[] = [
    { key: "request_category", label: CRM_FIELD_LABELS.request_category, value: labelOf(REQUEST_CATEGORY_LABELS, currentValues.requestCategory) },
    { key: "location", label: CRM_FIELD_LABELS.location, value: currentValues.location ?? EMPTY_LABEL },
    { key: "service_mode", label: CRM_FIELD_LABELS.service_mode, value: labelOf(SERVICE_MODE_LABELS, currentValues.serviceMode) },
    { key: "potential_job", label: CRM_FIELD_LABELS.potential_job, value: currentValues.potentialJob ?? EMPTY_LABEL },
    { key: "next_action", label: CRM_FIELD_LABELS.next_action, value: labelOf(NEXT_ACTION_LABELS, currentValues.nextAction) },
  ];

  const evidence = suggestion.evidence ? Object.entries(suggestion.evidence) : [];
  const selectedCustomer = customers.find((c) => c.id === selectedCustomerId);

  const displayName = matchedCustomerName || suggestion.caller;
  const displayBoat = matchedBoatName || suggestion.boatName;

  return (
    <Card className="space-y-4">
      {/* Başlık: müşteri · tekne, durum ve aciliyet */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-brand-800">
            {displayName}
            {displayBoat && (
              <span className="font-normal text-slate-500"> · {displayBoat}</span>
            )}
            {isMatched ? (
              <span className="ml-2 inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                Eşleşti
              </span>
            ) : (
              <span className="ml-2 inline-flex items-center text-xs font-medium text-amber-800 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200">
                Eşleşmedi
              </span>
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

      {/* Eşleşmeyen Çağrıda Açık Türkçe Uyarı ve Tek Eylem Butonu (#209) */}
      {!isMatched && reviewStatus !== "onaylandi" && (
        <div
          role="alert"
          className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-900"
        >
          <div className="flex items-start gap-2.5">
            <span className="text-xl shrink-0" aria-hidden="true">⚠️</span>
            <p className="text-sm font-medium leading-relaxed">
              Bu çağrı otomatik olarak bir müşteri ve tekneye bağlanamadı. Servis emri açmak için önce müşteri ve tekneyi seçin.
            </p>
          </div>
          <button
            type="button"
            className={buttonClasses("primary", "sm") + " whitespace-nowrap shrink-0 bg-amber-600 hover:bg-amber-700 text-white"}
            onClick={openMatchModal}
            ref={matchTriggerRef}
          >
            Müşteri ve tekne seç
          </button>
        </div>
      )}

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
                <span className="font-medium text-slate-700">{crmFieldLabel(key)}:</span> &ldquo;{val}&rdquo;
              </li>
            ))}
          </ul>
        </details>
      )}

      {matchDone && (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          Çağrı müşteri ve tekneye bağlandı. Şimdi onaylayıp servis emri oluşturabilirsiniz.
        </p>
      )}

      {actionError && !isEditModalOpen && !isRejectModalOpen && !isConflict && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          <p>{actionError}</p>
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
            {isMatched && (
              <button
                ref={matchTriggerRef}
                type="button"
                disabled={isSubmitting}
                onClick={openMatchModal}
                className={buttonClasses("ghost", "sm")}
              >
                Müşteri ve tekne seç
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

            {/* Onay Butonu Erken Engel (Proaktif UX, #209) */}
            <div
              className="relative inline-flex group"
              tabIndex={!isMatched ? 0 : undefined}
              aria-describedby={!isMatched ? `unmatched-hint-${suggestion.callId}` : undefined}
            >
              <Button
                size="sm"
                aria-describedby={!isMatched ? `unmatched-hint-${suggestion.callId}` : undefined}
                disabled={!isMatched || isSubmitting}
                onClick={() => handleApprove()}
                title={!isMatched ? "Servis emri oluşturabilmek için önce müşteri ve tekne eşleştirmesi yapmalısınız." : undefined}
              >
                {isSubmitting ? "Onaylanıyor…" : "Onayla ve Servis Emri Oluştur"}
              </Button>
              {!isMatched && (
                <div
                  id={`unmatched-hint-${suggestion.callId}`}
                  role="tooltip"
                  className="pointer-events-none absolute bottom-full mb-2 right-0 hidden w-64 rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg transition-opacity group-hover:block group-focus-within:block z-20 text-center"
                >
                  Servis emri oluşturabilmek için önce müşteri ve tekne eşleştirmesi yapmalısınız.
                </div>
              )}
            </div>
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
              <Field id="crm-edit-category" label={CRM_FIELD_LABELS.request_category}>
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
              <Field id="crm-edit-location" label={CRM_FIELD_LABELS.location}>
                <Input
                  id="crm-edit-location"
                  value={editFormData.location}
                  onChange={(e) => setEditFormData({ ...editFormData, location: e.target.value })}
                  placeholder="Örn: Tuzla Marina"
                />
              </Field>
              <Field id="crm-edit-problem" label={CRM_FIELD_LABELS.problem} className="sm:col-span-2">
                <Textarea
                  id="crm-edit-problem"
                  rows={2}
                  value={editFormData.problem}
                  onChange={(e) => setEditFormData({ ...editFormData, problem: e.target.value })}
                  placeholder="Müşterinin belirttiği ana sorun"
                />
              </Field>
              <Field id="crm-edit-service-mode" label={CRM_FIELD_LABELS.service_mode}>
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
              <Field id="crm-edit-urgency" label={CRM_FIELD_LABELS.urgency}>
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
              <Field id="crm-edit-potential-job" label={CRM_FIELD_LABELS.potential_job}>
                <Input
                  id="crm-edit-potential-job"
                  value={editFormData.potential_job}
                  onChange={(e) => setEditFormData({ ...editFormData, potential_job: e.target.value })}
                  placeholder="Örn: Motor arıza tespiti ve bakımı"
                />
              </Field>
              <Field id="crm-edit-next-action" label={CRM_FIELD_LABELS.next_action}>
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
              <Button type="submit" disabled={isSubmitting || !isMatched}>
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

      {/* Müşteri ve Tekne Seçim Penceresi (#209) */}
      {isMatchModalOpen && (
        <Modal
          title="Müşteri ve tekne seç"
          titleId="match-modal-title"
          description="Çağrıyı sistemdeki kayıtlı bir müşteri ve tekneye bağlar. Eşleşince servis emri açılabilir."
          onClose={() => setIsMatchModalOpen(false)}
          triggerRef={matchTriggerRef}
        >
          {/* Önerilen Eşleşme Vurgusu */}
          <div className="mb-4 rounded-lg border border-brand-200 bg-brand-50/70 p-3 text-sm">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-800">
              Önerilen:
            </span>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-800">
              <span>
                <strong className="font-medium text-slate-600">Çağrıdan çıkarılan:</strong>{" "}
                <span className="font-semibold text-brand-900">{suggestion.caller}</span>
              </span>
              {suggestion.boatName && (
                <span>
                  <strong className="font-medium text-slate-600">Tekne:</strong>{" "}
                  <span className="font-semibold text-brand-900">{suggestion.boatName}</span>
                </span>
              )}
            </div>
          </div>

          <form onSubmit={handleMatchSubmit} className="space-y-4">
            <Field
              id="crm-search-customer"
              label="Müşteri ara"
              hint="Ad, telefon numarası veya tekne adı ile arayabilirsiniz."
              error={matchError}
            >
              <div className="relative">
                <Input
                  id="crm-search-customer"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setSelectedCustomerId("");
                    setSelectedBoatId("");
                  }}
                  placeholder="Müşteri adı veya telefon ara..."
                  autoComplete="off"
                  autoFocus
                />
                {isSearching && (
                  <span className="absolute right-3 top-2.5 text-xs text-slate-400">
                    Aranıyor…
                  </span>
                )}
              </div>
            </Field>

            {/* Müşteri Listesi */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700">
                Müşteri seçin {customers.length > 0 && `(${customers.length} müşteri bulundu)`}
              </label>

              {isLoadingCustomers ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
                  Müşteriler yükleniyor…
                </div>
              ) : customers.length === 0 ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
                  Aramanıza uygun müşteri bulunamadı.
                </div>
              ) : (
                <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-lg border border-slate-200 p-2">
                  {customers.map((cust) => {
                    const isSelected = selectedCustomerId === cust.id;
                    return (
                      <div
                        key={cust.id}
                        onClick={() => handleSelectCustomer(cust)}
                        className={`cursor-pointer rounded-lg border p-2.5 transition-colors ${
                          isSelected
                            ? "border-brand-500 bg-brand-50/50"
                            : "border-slate-100 bg-white hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-900 text-sm">
                            <input
                              type="radio"
                              name="customer-selection"
                              checked={isSelected}
                              onChange={() => handleSelectCustomer(cust)}
                              className="h-4 w-4 text-brand-600 focus:ring-brand-500"
                            />
                            <span>{cust.name}</span>
                          </label>
                          <span className="text-xs text-slate-500">{cust.phone ?? "Telefon yok"}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Seçilen Müşterinin Tekneleri */}
            {selectedCustomer && (
              <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50/50 p-3">
                <label className="text-xs font-semibold text-slate-700">
                  {selectedCustomer.name} için tekne seçin:
                </label>
                {selectedCustomer.boats && selectedCustomer.boats.length > 0 ? (
                  <div className="space-y-1.5">
                    {selectedCustomer.boats.map((b) => (
                      <label key={b.id} className="flex items-center gap-2 text-sm text-slate-800 cursor-pointer">
                        <input
                          type="radio"
                          name="boat-selection"
                          value={b.id}
                          checked={selectedBoatId === b.id}
                          onChange={() => setSelectedBoatId(b.id)}
                          className="h-4 w-4 text-brand-600 focus:ring-brand-500"
                        />
                        <span className="font-medium">{b.name}</span>
                        {b.model && <span className="text-xs text-slate-500">({b.model})</span>}
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">
                    Bu müşteriye kayıtlı tekne bulunmuyor. Eşleştirmek için teknesi olan bir müşteri seçin.
                  </p>
                )}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <Button
                variant="secondary"
                type="button"
                onClick={() => setIsMatchModalOpen(false)}
                disabled={isSubmitting}
              >
                Vazgeç
              </Button>
              <Button
                type="submit"
                disabled={!selectedCustomerId || !selectedBoatId || isSubmitting}
              >
                {isSubmitting ? "Eşleştiriliyor…" : "Eşleştir"}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}
