"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTransition } from "react";

export interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: string;
  isFiltered?: boolean;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  title = "Filtrelere uyan çağrı bulunamadı",
  description = "Arama kriterlerinizi değiştirerek veya filtreleri temizleyerek tekrar deneyebilirsiniz.",
  icon = "🔍",
  isFiltered = true,
  actionLabel,
  actionHref,
  onAction,
  className = "",
}: EmptyStateProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [isPending, startTransition] = useTransition();

  const handleReset = () => {
    startTransition(() => {
      router.push(pathname);
    });
  };

  return (
    <div
      className={`rounded-2xl border border-dashed border-slate-300 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-12 text-center shadow-xs transition-colors ${className}`}
    >
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 dark:bg-slate-800 text-3xl select-none">
        {icon}
      </div>
      <h3 className="mt-4 text-base font-bold text-slate-900 dark:text-slate-100">
        {title}
      </h3>
      <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto leading-relaxed">
        {description}
      </p>

      {/* Özel Eylem Butonu (Örn: CRM Önerilerine Git) */}
      {actionHref && actionLabel && (
        <div className="mt-5">
          <Link
            href={actionHref}
            className="inline-flex items-center gap-1.5 rounded-xl bg-sky-700 dark:bg-sky-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-sky-800 dark:hover:bg-sky-700 active:scale-[0.98] transition-all focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <span>{actionLabel}</span>
            <span>➔</span>
          </Link>
        </div>
      )}

      {onAction && actionLabel && !actionHref && (
        <div className="mt-5">
          <button
            type="button"
            onClick={onAction}
            className="inline-flex items-center gap-1.5 rounded-xl bg-sky-700 dark:bg-sky-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-sky-800 dark:hover:bg-sky-700 active:scale-[0.98] transition-all focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <span>{actionLabel}</span>
          </button>
        </div>
      )}

      {/* Standart Filtreleri Sıfırla */}
      {!actionHref && !onAction && isFiltered && (
        <div className="mt-5">
          <button
            type="button"
            onClick={handleReset}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 rounded-xl bg-sky-700 dark:bg-sky-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-sky-800 dark:hover:bg-sky-700 active:scale-[0.98] transition-all focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <span>✕</span>
            <span>Filtreleri Sıfırla</span>
          </button>
        </div>
      )}
    </div>
  );
}
