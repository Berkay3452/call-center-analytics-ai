"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { deleteCall } from "@/lib/api/client";
import { useFocusTrap } from "@/lib/use-focus-trap";

export interface DeleteCallButtonProps {
  callId: string;
  /** Silindikten sonra gidilecek adres (detay sayfasında liste); yoksa sayfa yenilenir. */
  redirectTo?: string;
}

/** Çağrıyı, sesini, transkriptini, analizini ve CRM önerisini siler (KVKK). Yalnızca yönetici. */
export function DeleteCallButton({ callId, redirectTo }: DeleteCallButtonProps) {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => {
    if (!deleting) setIsOpen(false);
  }, [deleting]);
  const modalRef = useFocusTrap<HTMLDivElement>({ isOpen, onClose: close, returnFocusRef: triggerRef });

  const confirmDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteCall(callId);
      setIsOpen(false);
      if (redirectTo) router.push(redirectTo);
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Çağrı silinemedi.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label="Çağrıyı sil"
        title="Çağrıyı ve ses kaydını sil"
        onClick={() => {
          setError(null);
          setIsOpen(true);
        }}
        className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border border-red-300 bg-white font-semibold text-red-700 shadow-xs hover:bg-red-50 focus-visible:ring-2 focus-visible:ring-red-500 px-3 py-1.5 text-xs`}
      >
        Sil
      </button>
      {isOpen && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby={`delete-call-title-${callId}`}
        >
          <div ref={modalRef} className="w-full max-w-md space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-lg">
            <h2 id={`delete-call-title-${callId}`} className="font-bold text-slate-900">
              Çağrı silinsin mi?
            </h2>
            <p className="text-sm text-slate-600">
              Çağrı, ses kaydı, transkript, analiz ve CRM önerisi kalıcı olarak silinir. Servis emirleri kalır. Bu işlem geri alınamaz.
            </p>
            {error && (
              <p role="alert" className="text-sm text-red-700">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-3">
              <button type="button" onClick={close} disabled={deleting} className="rounded-lg border border-slate-300 px-4 py-2 text-sm">
                Vazgeç
              </button>
              <button
                type="button"
                onClick={() => void confirmDelete()}
                disabled={deleting}
                className="rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800 disabled:opacity-60"
              >
                {deleting ? "Siliniyor…" : "Evet, Sil"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
