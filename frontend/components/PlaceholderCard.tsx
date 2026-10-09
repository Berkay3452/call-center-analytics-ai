/**
 * Basit placeholder kart bileşeni — sayfa iskeletlerinde kullanılır.
 * İçeriği ileride gerçek veri ile doldurulacaktır.
 */
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
      className={`rounded-xl border border-gray-200 bg-white p-5 shadow-sm ${className}`}
    >
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        {title}
      </h2>
      {children ?? (
        <div className="h-24 rounded-lg bg-gray-50 flex items-center justify-center">
          <span className="text-xs text-gray-400">Veri yükleniyor…</span>
        </div>
      )}
    </div>
  );
}
