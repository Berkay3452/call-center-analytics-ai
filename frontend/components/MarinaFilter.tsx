"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useTransition } from "react";
import { MARINA_OPTIONS } from "@/lib/types";

interface MarinaFilterProps {
  selectedMarina?: string;
  className?: string;
}

export function MarinaFilter({ selectedMarina, className = "" }: MarinaFilterProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const currentMarina = selectedMarina ?? searchParams.get("marina") ?? "";

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    const params = new URLSearchParams(searchParams.toString());
    if (val && val !== "all") {
      params.set("marina", val);
    } else {
      params.delete("marina");
    }
    const query = params.toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname);
    });
  };

  return (
    <div className={`relative inline-flex items-center gap-2 ${className}`}>
      <label htmlFor="marina-filter-select" className="sr-only">
        Marina filtresi
      </label>
      <select
        id="marina-filter-select"
        value={currentMarina || "all"}
        onChange={handleChange}
        disabled={isPending}
        title="Marina bazlı filtreleme"
        aria-label="Marina seç"
        className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 shadow-sm focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 disabled:opacity-50 transition-colors"
      >
        <option value="all">Tüm Marinalar</option>
        {MARINA_OPTIONS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      {isPending && (
        <span className="text-xs text-sky-600 animate-spin" aria-hidden="true">
          ⏳
        </span>
      )}
    </div>
  );
}
