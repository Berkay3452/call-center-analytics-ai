"use client";

import React, { useRef } from "react";
import { useFocusTrap } from "@/lib/use-focus-trap";
import type { ChatSessionOut } from "@/lib/api/types";

// ──────────────────────────────────────────────────────────────────────────────
// Helper: göreceli tarih formatı (örn. "2 gün önce")
// ──────────────────────────────────────────────────────────────────────────────
function formatRelativeDate(isoDate: string): string {
  try {
    const date = new Date(isoDate);
    const now = Date.now();
    const diffMs = now - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return "Az önce";
    if (diffMin < 60) return `${diffMin} dk önce`;
    if (diffHour < 24) return `${diffHour} sa önce`;
    if (diffDay === 1) return "Dün";
    if (diffDay < 7) return `${diffDay} gün önce`;
    return date.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
  } catch {
    return "";
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Loading skeleton (3 ghost cards)
// ──────────────────────────────────────────────────────────────────────────────
function SessionSkeleton() {
  return (
    <div className="space-y-2 px-2 pt-1" aria-hidden="true">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-3 animate-pulse"
        >
          <div className="h-3.5 w-3/4 rounded bg-slate-300 dark:bg-slate-600 mb-2" />
          <div className="h-3 w-1/3 rounded bg-slate-200 dark:bg-slate-700" />
        </div>
      ))}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Props
// ──────────────────────────────────────────────────────────────────────────────
export interface ChatSidebarProps {
  /** Sunucudan gelen oturum listesi */
  sessions: ChatSessionOut[];
  /** Liste yüklenirken true */
  isLoading: boolean;
  /** Yükleme hatası varsa mesaj */
  error: string | null;
  /** Seçili oturumun kimliği (vurgu için) */
  activeSessionId: string | null;
  /** Oturum seçildiğinde çağrılır */
  onSelectSession: (sessionId: string) => void;
  /** "Yeni Sohbet" butonu tıklandığında çağrılır */
  onNewChat: () => void;
  /** Mobil: kenar çubuğu açık mı? */
  isOpen: boolean;
  /** Mobil: kenar çubuğunu kapat */
  onClose: () => void;
}

// ──────────────────────────────────────────────────────────────────────────────
// ChatSidebar
// ──────────────────────────────────────────────────────────────────────────────
export function ChatSidebar({
  sessions,
  isLoading,
  error,
  activeSessionId,
  onSelectSession,
  onNewChat,
  isOpen,
  onClose,
}: ChatSidebarProps) {
  const sidebarRef = useRef<HTMLElement>(null);
  const drawerRef = useFocusTrap<HTMLElement>({
    isOpen,
    onClose,
  });

  // Mobil: backdrop tıklamasıyla kapat
  function handleBackdropClick(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  // ── İçerik ──────────────────────────────────────────────────────────────────
  const sidebarContent = (
    <nav
      ref={sidebarRef}
      aria-label="Sohbet geçmişi"
      className="flex h-full flex-col"
    >
      {/* Başlık + Kapat butonu (yalnızca mobilde görünür) */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2 lg:pt-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Geçmiş Sohbetler
        </span>
        <button
          type="button"
          onClick={onClose}
          className="lg:hidden rounded-lg p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
          aria-label="Kenar çubuğunu kapat"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
          </svg>
        </button>
      </div>

      {/* + Yeni Sohbet */}
      <div className="px-2 pb-2">
        <button
          type="button"
          onClick={() => {
            onNewChat();
            onClose();
          }}
          className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-sky-300 dark:border-sky-700 bg-sky-50 dark:bg-sky-950/30 px-3 py-2.5 text-sm font-semibold text-sky-700 dark:text-sky-300 transition-colors hover:bg-sky-100 dark:hover:bg-sky-950/60 hover:border-sky-400 dark:hover:border-sky-500 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
          aria-label="Yeni sohbet başlat"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4 flex-shrink-0"
            aria-hidden="true"
          >
            <path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z" />
          </svg>
          Yeni Sohbet
        </button>
      </div>

      <hr className="border-slate-200 dark:border-slate-700 mx-2" />

      {/* Liste alanı */}
      <div className="flex-1 overflow-y-auto py-2 scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-600">
        {isLoading && <SessionSkeleton />}

        {!isLoading && error && (
          <div className="px-3 py-4 text-center text-xs text-red-500 dark:text-red-400">
            <p className="font-medium">Sohbet geçmişi yüklenemedi.</p>
            <p className="mt-0.5 text-slate-500 dark:text-slate-400">{error}</p>
          </div>
        )}

        {!isLoading && !error && sessions.length === 0 && (
          <div className="px-3 py-6 text-center">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-5 w-5 text-slate-400"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M2 10c0-4.418 3.582-8 8-8s8 3.582 8 8-3.582 8-8 8-8-3.582-8-8Zm8.75-3.25a.75.75 0 0 0-1.5 0V10c0 .414.336.75.75.75h2.5a.75.75 0 0 0 0-1.5h-1.75V6.75Z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
              Henüz kaydedilmiş sohbet yok
            </p>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              Yeni bir sohbet başlatın.
            </p>
          </div>
        )}

        {!isLoading && !error && sessions.length > 0 && (
          <ul role="list" className="space-y-1 px-2">
            {sessions.map((session, idx) => {
              const isActive = session.id === activeSessionId;
              const title =
                session.title?.trim() ||
                `Sohbet #${sessions.length - idx}`;
              const relDate = formatRelativeDate(session.updated_at);

              return (
                <li key={session.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelectSession(session.id);
                      onClose();
                    }}
                    aria-current={isActive ? "page" : undefined}
                    className={[
                      "w-full rounded-xl border px-3 py-2.5 text-left transition-colors focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900",
                      isActive
                        ? "border-sky-300 dark:border-sky-600 bg-sky-50 dark:bg-sky-950/50 text-sky-900 dark:text-sky-100"
                        : "border-transparent hover:border-slate-200 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300",
                    ].join(" ")}
                  >
                    <p className="truncate text-sm font-medium leading-tight">
                      {title}
                    </p>
                    {relDate && (
                      <p
                        className={[
                          "mt-0.5 text-xs",
                          isActive
                            ? "text-sky-600 dark:text-sky-400"
                            : "text-slate-400 dark:text-slate-500",
                        ].join(" ")}
                      >
                        {relDate}
                      </p>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </nav>
  );

  return (
    <>
      {/* ── Masaüstü: sabit sol panel ──────────────────────────────────────── */}
      <aside className="hidden lg:flex lg:flex-col lg:w-64 xl:w-72 flex-shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-l-2xl overflow-hidden">
        {sidebarContent}
      </aside>

      {/* ── Mobil: overlay çekmece ─────────────────────────────────────────── */}
      {isOpen && (
        /* Backdrop */
        <div
          className="lg:hidden fixed inset-0 z-40 flex"
          aria-modal="true"
          role="dialog"
          aria-label="Sohbet geçmişi"
          onClick={handleBackdropClick}
        >
          {/* Karartma */}
          <div
            className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm"
            aria-hidden="true"
          />
          {/* Panel */}
          <aside ref={drawerRef} className="relative z-50 flex w-72 max-w-[85vw] flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl">
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  );
}
