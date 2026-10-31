"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTransition } from "react";
import { Button, buttonClasses } from "@/components/ui";

export interface EmptyStateProps {
  title?: string;
  description?: string;
  isFiltered?: boolean;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  title = "Filtrelere uyan çağrı bulunamadı",
  description = "Arama kriterlerinizi değiştirerek veya filtreleri temizleyerek tekrar deneyebilirsiniz.",
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
      className={`rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center ${className}`}
    >
      <h3 className="text-base font-semibold text-brand-800">{title}</h3>
      <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-slate-500">
        {description}
      </p>

      {actionHref && actionLabel && (
        <div className="mt-5">
          <Link href={actionHref} className={buttonClasses("primary")}>
            {actionLabel}
          </Link>
        </div>
      )}

      {onAction && actionLabel && !actionHref && (
        <div className="mt-5">
          <Button onClick={onAction}>{actionLabel}</Button>
        </div>
      )}

      {!actionHref && !onAction && isFiltered && (
        <div className="mt-5">
          <Button onClick={handleReset} disabled={isPending}>
            Filtreleri Sıfırla
          </Button>
        </div>
      )}
    </div>
  );
}
