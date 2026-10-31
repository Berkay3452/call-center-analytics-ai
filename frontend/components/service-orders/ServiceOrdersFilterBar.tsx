"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState, useTransition } from "react";
import { MARINA_OPTIONS } from "@/lib/types";
import { Button, Input, Select } from "@/components/ui";

interface ServiceOrdersFilterBarProps {
  className?: string;
  placeholder?: string;
}

export function ServiceOrdersFilterBar({
  className = "",
  placeholder = "Kod (SO-...), müşteri, tekne veya açıklama ara...",
}: ServiceOrdersFilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const urlQ = searchParams.get("q") ?? "";
  const urlMarina = searchParams.get("marina") ?? "";

  const [searchVal, setSearchVal] = useState(urlQ);

  const updateParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(searchParams.toString());
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      // Filtre değişince sayfa 1'e döner
      next.delete("page");

      startTransition(() => {
        const query = next.toString();
        router.push(query ? `${pathname}?${query}` : pathname);
      });
    },
    [pathname, router, searchParams],
  );

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateParam("q", searchVal.trim());
  };

  const handleReset = () => {
    setSearchVal("");
    const next = new URLSearchParams(searchParams.toString());
    next.delete("q");
    next.delete("marina");
    next.delete("date_from");
    next.delete("date_to");
    next.delete("page");

    startTransition(() => {
      const query = next.toString();
      router.push(query ? `${pathname}?${query}` : pathname);
    });
  };

  const hasFilters = Boolean(urlQ || urlMarina);

  return (
    <form
      onSubmit={handleSearchSubmit}
      className={`mb-4 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center ${className}`}
    >
      <label htmlFor="so-filter-q" className="sr-only">
        Servis emri ara
      </label>
      <Input
        id="so-filter-q"
        type="search"
        value={searchVal}
        onChange={(e) => setSearchVal(e.target.value)}
        placeholder={placeholder}
        className="flex-1"
      />
      <label htmlFor="so-filter-marina" className="sr-only">
        Marina filtresi
      </label>
      <Select
        id="so-filter-marina"
        value={urlMarina}
        onChange={(e) => updateParam("marina", e.target.value)}
        className="sm:w-48"
      >
        <option value="">Tüm marinalar</option>
        {MARINA_OPTIONS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </Select>
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={isPending}>
          {isPending ? "Aranıyor…" : "Ara"}
        </Button>
        {hasFilters && (
          <Button variant="secondary" onClick={handleReset} disabled={isPending}>
            Filtreleri temizle
          </Button>
        )}
      </div>
    </form>
  );
}
