import type { ReactNode } from "react";

interface PlaceholderCardProps {
  title: string;
  children?: ReactNode;
  className?: string;
}

export function PlaceholderCard({
  title,
  children,
  className = "",
}: PlaceholderCardProps) {
  return (
    <div
      className={`rounded-xl border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm transition-colors ${className}`}
    >
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
        {title}
      </h2>
      {children ?? (
        <div className="h-24 rounded-lg bg-gray-50 dark:bg-slate-800/60 flex items-center justify-center">
          <span className="text-xs text-gray-400 dark:text-slate-500">Veri yükleniyor…</span>
        </div>
      )}
    </div>
  );
}
