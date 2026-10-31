"use client";

import React, { useState } from "react";
import { useFocusTrap } from "@/lib/use-focus-trap";
import type { ChatSessionOut } from "@/lib/api/types";
import { Button, cn } from "@/components/ui";

function formatRelativeDate(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return "";
  const diffMin = Math.floor((Date.now() - date.getTime()) / 60000);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffMin < 1) return "Az önce";
  if (diffMin < 60) return `${diffMin} dk önce`;
  if (diffHour < 24) return `${diffHour} sa önce`;
  if (diffDay === 1) return "Dün";
  if (diffDay < 7) return `${diffDay} gün önce`;
  return date.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}

export interface ChatSidebarProps {
  sessions: ChatSessionOut[];
  isLoading: boolean;
  error: string | null;
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  /** Tek oturumu siler (onay kenar çubuğunda alınır). */
  onDeleteSession: (sessionId: string) => Promise<void>;
  /** Tüm oturumları siler (onay kenar çubuğunda alınır). */
  onDeleteAll: () => Promise<void>;
  /** Mobil: kenar çubuğu açık mı? */
  isOpen: boolean;
  onClose: () => void;
}

export function ChatSidebar({
  sessions,
  isLoading,
  error,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onDeleteAll,
  isOpen,
  onClose,
}: ChatSidebarProps) {
  const drawerRef = useFocusTrap<HTMLElement>({ isOpen, onClose });
  /** Silme onayı bekleyen oturum kimliği ya da tümü için "all". */
  const [confirming, setConfirming] = useState<string | "all" | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function runDelete(action: () => Promise<void>) {
    setBusy(true);
    setDeleteError(null);
    try {
      await action();
      setConfirming(null);
    } catch (err) {
      setDeleteError(
        err instanceof Error && err.message ? err.message : "Silinemedi. Lütfen tekrar deneyin.",
      );
    } finally {
      setBusy(false);
    }
  }

  const content = (
    <nav aria-label="Sohbet geçmişi" className="flex h-full flex-col">
      <div className="flex items-center justify-between px-3 pb-2 pt-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Geçmiş Sohbetler
        </span>
        <Button variant="ghost" size="sm" className="lg:hidden" onClick={onClose} aria-label="Kenar çubuğunu kapat">
          ✕
        </Button>
      </div>

      <div className="px-3 pb-3">
        <Button
          className="w-full"
          aria-label="Yeni sohbet başlat"
          onClick={() => {
            onNewChat();
            onClose();
          }}
        >
          Yeni sohbet
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto border-t border-slate-100 px-2 py-2">
        {isLoading && <p className="px-2 py-3 text-xs text-slate-500">Yükleniyor…</p>}

        {!isLoading && error && (
          <p role="alert" className="px-2 py-3 text-xs text-red-600">
            Sohbet geçmişi yüklenemedi. {error}
          </p>
        )}

        {!isLoading && !error && sessions.length === 0 && (
          <p className="px-2 py-6 text-center text-xs text-slate-500">Henüz kayıtlı sohbet yok.</p>
        )}

        {!isLoading && !error && sessions.length > 0 && (
          <ul className="space-y-1">
            {sessions.map((session, idx) => {
              const isActive = session.id === activeSessionId;
              const title = session.title?.trim() || `Sohbet #${sessions.length - idx}`;

              if (confirming === session.id) {
                return (
                  <li key={session.id} className="rounded-lg border border-red-200 bg-red-50 p-2.5">
                    <p className="text-sm font-medium text-red-800">Bu sohbeti sil?</p>
                    <p className="mt-0.5 truncate text-xs text-red-700">{title}</p>
                    <div className="mt-2 flex gap-2">
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={busy}
                        onClick={() => void runDelete(() => onDeleteSession(session.id))}
                      >
                        {busy ? "Siliniyor…" : "Sil"}
                      </Button>
                      <Button variant="secondary" size="sm" disabled={busy} onClick={() => setConfirming(null)}>
                        Vazgeç
                      </Button>
                    </div>
                  </li>
                );
              }

              return (
                <li key={session.id} className="group flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      onSelectSession(session.id);
                      onClose();
                    }}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "min-w-0 flex-1 rounded-lg px-3 py-2 text-left transition-colors",
                      isActive ? "bg-brand-50 text-brand-800" : "text-slate-700 hover:bg-slate-50",
                    )}
                  >
                    <span className="block truncate text-sm font-medium">{title}</span>
                    <span className="block text-xs text-slate-500">{formatRelativeDate(session.updated_at)}</span>
                  </button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Sohbeti sil: ${title}`}
                    onClick={() => {
                      setDeleteError(null);
                      setConfirming(session.id);
                    }}
                  >
                    Sil
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {sessions.length > 0 && (
        <div className="border-t border-slate-100 p-3">
          {confirming === "all" ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-2.5">
              <p className="text-sm font-medium text-red-800">Tüm sohbetler silinsin mi?</p>
              <p className="mt-0.5 text-xs text-red-700">Bu işlem geri alınamaz.</p>
              <div className="mt-2 flex gap-2">
                <Button variant="danger" size="sm" disabled={busy} onClick={() => void runDelete(onDeleteAll)}>
                  {busy ? "Siliniyor…" : "Hepsini sil"}
                </Button>
                <Button variant="secondary" size="sm" disabled={busy} onClick={() => setConfirming(null)}>
                  Vazgeç
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              onClick={() => {
                setDeleteError(null);
                setConfirming("all");
              }}
            >
              Tümünü temizle
            </Button>
          )}
          {deleteError && (
            <p role="alert" className="mt-2 text-xs text-red-600">
              {deleteError}
            </p>
          )}
        </div>
      )}
    </nav>
  );

  return (
    <>
      {/* Masaüstü: sabit sol panel */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex xl:w-72">
        {content}
      </aside>

      {/* Mobil: çekmece */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 flex lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Sohbet geçmişi"
          onClick={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <div className="fixed inset-0 bg-black/50" aria-hidden="true" />
          <aside
            ref={drawerRef}
            className="relative z-50 flex w-72 max-w-[85vw] flex-col border-r border-slate-200 bg-white"
          >
            {content}
          </aside>
        </div>
      )}
    </>
  );
}
