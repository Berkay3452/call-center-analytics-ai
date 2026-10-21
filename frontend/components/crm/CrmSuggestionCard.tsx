"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { approveCrmRecord, rejectCrmRecord } from "@/lib/api/client";
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

interface CrmSuggestionCardProps {
  suggestion: CrmSuggestion;
  variant?: "list" | "detail";
  onStatusChange?: (callId: string, newStatus: CrmReviewStatus, serviceOrderId?: string | null) => void;
}

const URGENCY_BADGE: Record<Urgency, string> = {
  acil: "bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-300 dark:border-red-800 font-bold",
  yuksek: "bg-orange-100 dark:bg-orange-950/60 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-800",
  normal: "bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800",
  dusuk: "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700",
};

const STATUS_BADGE: Record<CrmReviewStatus, { bg: string; text: string; border: string; icon: string }> = {
  bekliyor: {
    bg: "bg-amber-50 dark:bg-amber-950/60",
    text: "text-amber-800 dark:text-amber-300",
    border: "border-amber-300 dark:border-amber-800",
    icon: "⏳",
  },
  onaylandi: {
    bg: "bg-emerald-50 dark:bg-emerald-950/60",
    text: "text-emerald-800 dark:text-emerald-300",
    border: "border-emerald-300 dark:border-emerald-800",
    icon: "✓",
  },
  reddedildi: {
    bg: "bg-red-50 dark:bg-red-950/60",
    text: "text-red-800 dark:text-red-300",
    border: "border-red-300 dark:border-red-800",
    icon: "✕",
  },
};

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

  // Modal ve form state'leri
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const router = useRouter();
  const [is409Error, setIs409Error] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Düzenleme formunun iç state'i
  const [editFormData, setEditFormData] = useState({
    request_category: currentValues.requestCategory ?? "",
    location: currentValues.location ?? "",
    problem: currentValues.problem ?? "",
    service_mode: currentValues.serviceMode ?? "",
    urgency: currentValues.urgency ?? "",
    potential_job: currentValues.potentialJob ?? "",
    next_action: currentValues.nextAction ?? "",
    note: "",
  });

  // Düzenleme modalını açarken mevcut değerlerle doldur
  const openEditModal = () => {
    setActionError(null);
    setIs409Error(false);
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

  // Onaylama işlemi (isteğe bağlı diff ile)
  const handleApprove = async (diff?: Partial<CrmApproveIn>, note?: string) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setActionError(null);
    setIs409Error(false);

    try {
      const payload: CrmApproveIn = {
        ...diff,
        note: note || undefined,
      };

      const res = await approveCrmRecord(suggestion.callId, payload);
      setReviewStatus(res.status);
      const newOrderId = res.service_order_id ? String(res.service_order_id) : null;
      setServiceOrderId(newOrderId);
      if (res.edited_fields && Object.keys(res.edited_fields).length > 0) {
        setEditedFields((prev) => ({ ...prev, ...res.edited_fields }));
      }
      setIsEditModalOpen(false);
      onStatusChange?.(suggestion.callId, res.status, newOrderId);
      router.refresh(); // başlıktaki bekleyen sayısı ve durum sekmeleri güncellensin
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setIs409Error(true);
        setActionError(
          "Müşteri veya tekne kaydı sistemde eşleşmediği için servis emri oluşturulamadı. Lütfen önce çağrı detayından müşteri/tekne kaydını doğrulayın veya eşleştirin.",
        );
      } else {
        setActionError(
          err instanceof Error
            ? err.message
            : "Onaylama işlemi sırasında beklenmeyen bir hata oluştu.",
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Düzenleme formunu kaydet & onayla
  const handleSaveAndApprove = async (e: React.FormEvent) => {
    e.preventDefault();

    // Sadece değişen alanların diff'ini hesapla
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

    // Arayüz state'ini de güncelle
    setCurrentValues({
      requestCategory: (editFormData.request_category as RequestCategory) || null,
      location: editFormData.location || null,
      problem: editFormData.problem || null,
      serviceMode: (editFormData.service_mode as ServiceMode) || null,
      urgency: (editFormData.urgency as Urgency) || null,
      potentialJob: editFormData.potential_job || null,
      nextAction: (editFormData.next_action as NextAction) || null,
    });

    await handleApprove(diff, editFormData.note);
  };

  // Reddetme işlemi
  const handleReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setActionError(null);
    setIs409Error(false);

    try {
      const res = await rejectCrmRecord(suggestion.callId, {
        note: rejectReason.trim() || undefined,
      });
      setReviewStatus(res.status);
      setIsRejectModalOpen(false);
      onStatusChange?.(suggestion.callId, res.status, null);
      router.refresh();
    } catch (err: unknown) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Reddetme işlemi sırasında beklenmeyen bir hata oluştu.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const statusStyle = STATUS_BADGE[reviewStatus];
  const isEdited = (fieldKey: string) => Boolean(editedFields && editedFields[fieldKey]);

  return (
    <div
      className={`rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs transition-all ${
        variant === "detail" ? "p-5" : "p-5 hover:border-sky-300 dark:hover:border-sky-500"
      }`}
    >
      {/* Üst Başlık & Durum Rozeti */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
              {suggestion.caller}
            </h2>
            {suggestion.boatName && (
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                • {suggestion.boatName}
              </span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span>📍 {currentValues.location ?? EMPTY_LABEL}</span>
            <span>•</span>
            <span>Çağrı ID: {suggestion.callId}</span>
          </div>
        </div>

        {/* Durum Rozeti ve Aciliyet */}
        <div className="flex flex-wrap items-center gap-2">
          {/* İnceleme Durumu Rozeti (#113) */}
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${statusStyle.bg} ${statusStyle.text} ${statusStyle.border}`}
          >
            <span>{statusStyle.icon}</span>
            <span>{labelOf(CRM_REVIEW_STATUS_LABELS, reviewStatus)}</span>
          </span>

          {/* Aciliyet Rozeti */}
          {currentValues.urgency && (
            <span
              className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${
                URGENCY_BADGE[currentValues.urgency]
              }`}
            >
              {currentValues.urgency === "acil" && <span className="mr-1">🚨</span>}
              {labelOf(URGENCY_LABELS, currentValues.urgency)}
            </span>
          )}

          {variant === "list" && (
            <Link
              href={`/admin/calls/${suggestion.callId}`}
              className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-1 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              Çağrı Detayı →
            </Link>
          )}
        </div>
      </div>

      {/* Servis Emri Bilgisi (Onaylandıysa) */}
      {serviceOrderId && (
        <div className="mt-4 flex items-center justify-between rounded-lg bg-emerald-50 dark:bg-emerald-950/40 p-3 border border-emerald-200 dark:border-emerald-800 text-xs">
          <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-300 font-semibold">
            <span>📋</span>
            <span>Servis Emri Oluşturuldu:</span>
            <Link
              href="/admin/service-orders"
              className="font-mono font-bold text-emerald-900 dark:text-emerald-200 underline hover:text-emerald-700 dark:hover:text-emerald-100"
              title="Servis Emirleri Sayfasına Git"
            >
              {serviceOrderId} ➔
            </Link>
          </div>
          <span className="rounded bg-emerald-100 dark:bg-emerald-900/60 px-2 py-0.5 text-[10px] font-bold text-emerald-800 dark:text-emerald-200 uppercase tracking-wider">
            Aktif Servis Emri
          </span>
        </div>
      )}

      {/* Hata Uyarısı (409 veya diğerleri) */}
      {actionError && (
        <div
          className={`mt-4 rounded-lg p-3 text-xs border ${
            is409Error
              ? "bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-200"
              : "bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-900 text-red-800 dark:text-red-200"
          }`}
        >
          <div className="flex items-start gap-2">
            <span className="font-bold flex-shrink-0">{is409Error ? "⚠️" : "✕"}</span>
            <div className="flex-1">
              <p className="font-semibold">{is409Error ? "Eşleşme Uyarısı (409):" : "Hata Oluştu:"}</p>
              <p className="mt-0.5">{actionError}</p>
            </div>
          </div>
        </div>
      )}

      {/* 7 CRM Alanı Izgara Görünümü */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {/* 1. Kategori */}
        <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800/50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              1. Müşteri Talebi (Kategori)
            </span>
            {isEdited("request_category") && (
              <span className="rounded bg-amber-100 dark:bg-amber-950/80 px-1.5 py-0.2 text-[9px] font-bold text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                düzenlendi
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
            {labelOf(REQUEST_CATEGORY_LABELS, currentValues.requestCategory)}
          </p>
        </div>

        {/* 2. Lokasyon */}
        <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800/50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              2. Lokasyon / Marina
            </span>
            {isEdited("location") && (
              <span className="rounded bg-amber-100 dark:bg-amber-950/80 px-1.5 py-0.2 text-[9px] font-bold text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                düzenlendi
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
            {currentValues.location ?? EMPTY_LABEL}
          </p>
        </div>

        {/* 3. Problem Tanımı */}
        <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800/50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              3. Problem Tanımı
            </span>
            {isEdited("problem") && (
              <span className="rounded bg-amber-100 dark:bg-amber-950/80 px-1.5 py-0.2 text-[9px] font-bold text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                düzenlendi
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200 line-clamp-2">
            {currentValues.problem ?? EMPTY_LABEL}
          </p>
        </div>

        {/* 4. Hizmet Biçimi */}
        <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800/50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              4. Hizmet Biçimi
            </span>
            {isEdited("service_mode") && (
              <span className="rounded bg-amber-100 dark:bg-amber-950/80 px-1.5 py-0.2 text-[9px] font-bold text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                düzenlendi
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
            {labelOf(SERVICE_MODE_LABELS, currentValues.serviceMode)}
          </p>
        </div>

        {/* 6. Potansiyel İş */}
        <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800/50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              6. Potansiyel İş
            </span>
            {isEdited("potential_job") && (
              <span className="rounded bg-amber-100 dark:bg-amber-950/80 px-1.5 py-0.2 text-[9px] font-bold text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                düzenlendi
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
            {currentValues.potentialJob ?? EMPTY_LABEL}
          </p>
        </div>

        {/* 7. Sonraki Aksiyon */}
        <div className="rounded-lg bg-sky-50 dark:bg-sky-950/40 border border-sky-100 dark:border-sky-900/60 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-sky-700 dark:text-sky-400">
              7. Sonraki Aksiyon / Servis Emri
            </span>
            {isEdited("next_action") && (
              <span className="rounded bg-amber-100 dark:bg-amber-950/80 px-1.5 py-0.2 text-[9px] font-bold text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                düzenlendi
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs font-bold text-sky-900 dark:text-sky-200">
            {labelOf(NEXT_ACTION_LABELS, currentValues.nextAction)}
          </p>
        </div>
      </div>

      {/* Kanıt Alıntıları */}
      {suggestion.evidence && Object.keys(suggestion.evidence).length > 0 && (
        <div className="mt-4 rounded-lg bg-amber-50/50 dark:bg-amber-950/30 p-3 border border-amber-200/60 dark:border-amber-900/60 text-xs">
          <span className="block text-[11px] font-semibold text-amber-800 dark:text-amber-300 uppercase mb-1">
            🔍 Konuşmadan Kanıt Alıntıları
          </span>
          <div className="space-y-1 text-amber-900 dark:text-amber-200">
            {Object.entries(suggestion.evidence).map(([key, val]) => (
              <div key={key}>
                <span className="font-semibold text-amber-700 dark:text-amber-400">{key}:</span> &ldquo;{val}&rdquo;
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Aksiyon Butonları (Onayla, Düzenle, Reddet) */}
      <div className="mt-5 flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800 pt-4">
        {/* Düzenle Butonu */}
        <button
          type="button"
          onClick={openEditModal}
          disabled={isSubmitting}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <span>✏️</span>
          <span>Düzenle</span>
        </button>

        {/* Reddet Butonu */}
        {reviewStatus !== "reddedildi" && (
          <button
            type="button"
            onClick={() => {
              setActionError(null);
              setIsRejectModalOpen(true);
            }}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/30 px-3.5 py-2 text-xs font-semibold text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-950/60 focus:outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <span>✕</span>
            <span>Reddet</span>
          </button>
        )}

        {/* Onayla Butonu */}
        {reviewStatus !== "onaylandi" ? (
          <button
            type="button"
            onClick={() => handleApprove()}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-xs"
          >
            {isSubmitting ? (
              <>
                <div className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                <span>Onaylanıyor...</span>
              </>
            ) : (
              <>
                <span>✓</span>
                <span>Onayla ve Servis Emri Oluştur</span>
              </>
            )}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => handleApprove()}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 px-3.5 py-2 text-xs font-bold text-emerald-800 dark:text-emerald-300 hover:bg-emerald-100 transition-colors"
          >
            <span>✓</span>
            <span>Tekrar Onayla (Güncelle)</span>
          </button>
        )}
      </div>

      {/* ------------------------------------------------------------- */}
      {/* 1. DÜZENLEME MODALI                                           */}
      {/* ------------------------------------------------------------- */}
      {isEditModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-modal-title"
            className="w-full max-w-2xl rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-xl max-h-[90vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-4">
              <div>
                <h3 id="edit-modal-title" className="text-base font-bold text-slate-900 dark:text-slate-100">
                  CRM Öneri Alanlarını Düzenle
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Değiştirilen alanlar kaydedildiğinde &quot;düzenlendi&quot; olarak işaretlenecek ve onaylanacaktır.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsEditModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            {actionError && (
              <div className="mb-4 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 p-3 text-xs text-red-700 dark:text-red-300">
                {actionError}
              </div>
            )}

            <form onSubmit={handleSaveAndApprove} className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {/* 1. Kategori */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    1. Müşteri Talebi (Kategori)
                  </label>
                  <select
                    value={editFormData.request_category}
                    onChange={(e) => setEditFormData({ ...editFormData, request_category: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  >
                    <option value="">Seçiniz</option>
                    {Object.entries(REQUEST_CATEGORY_LABELS).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 2. Lokasyon / Marina */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    2. Lokasyon / Marina
                  </label>
                  <input
                    type="text"
                    value={editFormData.location}
                    onChange={(e) => setEditFormData({ ...editFormData, location: e.target.value })}
                    placeholder="Örn: Tuzla Marina"
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>

                {/* 3. Problem Tanımı */}
                <div className="sm:col-span-2">
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    3. Problem Tanımı
                  </label>
                  <textarea
                    rows={3}
                    value={editFormData.problem}
                    onChange={(e) => setEditFormData({ ...editFormData, problem: e.target.value })}
                    placeholder="Arıza veya müşteri şikayeti tanımı..."
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 p-2.5 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>

                {/* 4. Hizmet Biçimi */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    4. Hizmet Biçimi
                  </label>
                  <select
                    value={editFormData.service_mode}
                    onChange={(e) => setEditFormData({ ...editFormData, service_mode: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  >
                    <option value="">Seçiniz</option>
                    {Object.entries(SERVICE_MODE_LABELS).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 5. Aciliyet */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    5. Aciliyet Seviyesi
                  </label>
                  <select
                    value={editFormData.urgency}
                    onChange={(e) => setEditFormData({ ...editFormData, urgency: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  >
                    <option value="">Seçiniz</option>
                    {Object.entries(URGENCY_LABELS).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 6. Potansiyel İş */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    6. Potansiyel İş
                  </label>
                  <input
                    type="text"
                    value={editFormData.potential_job}
                    onChange={(e) => setEditFormData({ ...editFormData, potential_job: e.target.value })}
                    placeholder="Örn: Motor arıza tespiti ve bakımı"
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>

                {/* 7. Sonraki Aksiyon */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    7. Önerilen Sonraki Aksiyon
                  </label>
                  <select
                    value={editFormData.next_action}
                    onChange={(e) => setEditFormData({ ...editFormData, next_action: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  >
                    <option value="">Seçiniz</option>
                    {Object.entries(NEXT_ACTION_LABELS).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Onay Notu */}
                <div className="sm:col-span-2">
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    İsteğe Bağlı Onay Notu
                  </label>
                  <input
                    type="text"
                    value={editFormData.note}
                    onChange={(e) => setEditFormData({ ...editFormData, note: e.target.value })}
                    placeholder="Örn: Müşteri acil usta istediği için öncelik verildi."
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  disabled={isSubmitting}
                  className="rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  İptal
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white hover:bg-emerald-700 active:scale-[0.98] disabled:opacity-50 transition-all shadow-xs"
                >
                  {isSubmitting ? (
                    <>
                      <div className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      <span>Kaydediliyor...</span>
                    </>
                  ) : (
                    <>
                      <span>✓</span>
                      <span>Değişiklikleri Kaydet &amp; Onayla</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 2. REDDETME MODALI                                            */}
      {/* ------------------------------------------------------------- */}
      {isRejectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reject-modal-title"
            className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-4">
              <h3 id="reject-modal-title" className="text-base font-bold text-slate-900 dark:text-slate-100">
                CRM Önerisini Reddet
              </h3>
              <button
                type="button"
                onClick={() => setIsRejectModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            {actionError && (
              <div className="mb-4 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 p-3 text-xs text-red-700 dark:text-red-300">
                {actionError}
              </div>
            )}

            <form onSubmit={handleReject} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Red Gerekçesi veya Not <span className="text-slate-400 font-normal">(İsteğe Bağlı)</span>
                </label>
                <textarea
                  rows={3}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Örn: Tekne sahibi başka bir servis ile anlaştı / bilgi amaçlı arama..."
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 p-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsRejectModalOpen(false)}
                  disabled={isSubmitting}
                  className="rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  Vazgeç
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-xs font-bold text-white hover:bg-red-700 active:scale-[0.98] disabled:opacity-50 transition-all shadow-xs"
                >
                  {isSubmitting ? (
                    <>
                      <div className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      <span>Reddediliyor...</span>
                    </>
                  ) : (
                    <>
                      <span>✕</span>
                      <span>Reddetmeyi Onayla</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
