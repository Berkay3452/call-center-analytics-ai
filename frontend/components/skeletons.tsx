import React from "react";

/**
 * Çağrılar tablosu yükleniyor iskeleti
 */
export function CallsTableSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm animate-pulse">
      <div className="border-b border-gray-200 bg-gray-50 px-4 py-3">
        <div className="grid grid-cols-8 gap-4">
          <div className="h-4 w-24 rounded bg-gray-200" />
          <div className="h-4 w-16 rounded bg-gray-200" />
          <div className="h-4 w-20 rounded bg-gray-200" />
          <div className="h-4 w-12 rounded bg-gray-200" />
          <div className="h-4 w-16 rounded bg-gray-200" />
          <div className="h-4 w-24 rounded bg-gray-200" />
          <div className="h-4 w-24 rounded bg-gray-200" />
          <div className="h-4 w-16 rounded bg-gray-200 ml-auto" />
        </div>
      </div>
      <div className="divide-y divide-gray-100 p-4 space-y-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="grid grid-cols-8 gap-4 items-center pt-2">
            <div>
              <div className="h-4 w-28 rounded bg-gray-200 mb-1.5" />
              <div className="h-3 w-20 rounded bg-gray-100" />
            </div>
            <div className="h-4 w-20 rounded bg-gray-200" />
            <div className="h-5 w-20 rounded-full bg-gray-200" />
            <div className="h-4 w-10 rounded bg-gray-200" />
            <div className="h-5 w-16 rounded-full bg-gray-200" />
            <div className="h-5 w-24 rounded-full bg-gray-200" />
            <div className="h-5 w-24 rounded-full bg-gray-200" />
            <div className="h-4 w-16 rounded bg-gray-200 ml-auto" />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Çağrı detayı yükleniyor iskeleti
 */
export function CallDetailSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Üst Bar */}
      <div className="flex items-center justify-between">
        <div className="h-4 w-36 rounded bg-gray-200" />
        <div className="flex items-center gap-2">
          <div className="h-6 w-28 rounded-md bg-gray-200" />
          <div className="h-6 w-20 rounded-md bg-gray-200" />
        </div>
      </div>

      {/* Başlık Kartı */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <div className="h-6 w-64 rounded bg-gray-200" />
            <div className="h-4 w-96 max-w-full rounded bg-gray-100" />
          </div>
          <div className="h-5 w-28 rounded bg-gray-200" />
        </div>
      </div>

      {/* 2 Kolonlu Düzen */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Sol Kolon (Ses & Transkript) */}
        <div className="space-y-6 lg:col-span-7">
          {/* Dalga Formu */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
            <div className="flex justify-between">
              <div className="h-4 w-36 rounded bg-gray-200" />
              <div className="h-4 w-12 rounded bg-gray-200" />
            </div>
            <div className="h-14 rounded-lg bg-gray-200" />
          </div>

          {/* Transkript */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
            <div className="h-4 w-48 rounded bg-gray-200 mb-2" />
            <div className="space-y-3">
              <div className="h-16 w-3/4 rounded-2xl bg-gray-100" />
              <div className="h-16 w-3/4 ml-auto rounded-2xl bg-gray-200" />
              <div className="h-16 w-3/4 rounded-2xl bg-gray-100" />
            </div>
          </div>

          {/* AI Özet */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
            <div className="h-4 w-44 rounded bg-gray-200" />
            <div className="h-12 w-full rounded bg-gray-100" />
          </div>

          {/* Satış Analizi */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
            <div className="flex justify-between items-center">
              <div className="h-4 w-32 rounded bg-gray-200" />
              <div className="h-5 w-24 rounded-full bg-gray-200" />
            </div>
            <div className="h-10 w-full rounded-lg bg-gray-100" />
            <div className="h-14 w-full rounded-lg bg-gray-100" />
          </div>
        </div>

        {/* Sağ Kolon (7 Alanlı CRM) */}
        <div className="space-y-6 lg:col-span-5">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
            <div className="flex justify-between border-b border-gray-200 pb-3">
              <div className="space-y-1">
                <div className="h-5 w-36 rounded bg-gray-200" />
                <div className="h-3 w-48 rounded bg-gray-100" />
              </div>
              <div className="h-5 w-16 rounded-full bg-gray-200" />
            </div>

            <div className="space-y-3">
              {Array.from({ length: 7 }).map((_, i) => (
                <div key={i} className="h-14 rounded-lg bg-gray-100 p-3" />
              ))}
            </div>

            <div className="pt-4 border-t border-gray-200 space-y-2">
              <div className="h-10 w-full rounded-xl bg-gray-200" />
              <div className="h-9 w-full rounded-xl bg-gray-100" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * CRM önerileri listesi yükleniyor iskeleti
 */
export function CrmSuggestionsSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4"
        >
          {/* Üst Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 pb-4">
            <div className="space-y-2">
              <div className="h-5 w-48 rounded bg-gray-200" />
              <div className="h-3 w-36 rounded bg-gray-100" />
            </div>
            <div className="flex items-center gap-2">
              <div className="h-6 w-20 rounded-full bg-gray-200" />
              <div className="h-7 w-28 rounded-lg bg-gray-200" />
            </div>
          </div>

          {/* Izgara */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, j) => (
              <div key={j} className="h-16 rounded-lg bg-gray-100 p-3" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Analitik Dashboard yükleniyor iskeleti
 */
export function AnalyticsDashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse" aria-busy="true" aria-label="Analitik verileri yükleniyor">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-28 rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-3 h-3 w-20 rounded bg-slate-200" />
            <div className="h-8 w-14 rounded bg-slate-200" />
          </div>
        ))}
      </div>
      <div className="h-56 rounded-xl border border-slate-200 bg-white p-5">
        <div className="mb-6 h-4 w-44 rounded bg-slate-200" />
        <div className="flex h-28 items-end gap-3">
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className="flex-1 rounded-t bg-slate-200"
              style={{ height: `${30 + ((i * 12) % 60)}%` }}
            />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-56 space-y-4 rounded-xl border border-slate-200 bg-white p-5">
            <div className="h-4 w-36 rounded bg-slate-200" />
            <div className="space-y-4 pt-2">
              <div className="h-3 w-full rounded bg-slate-200" />
              <div className="h-3 w-full rounded bg-slate-200" />
              <div className="h-3 w-full rounded bg-slate-200" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


/**
 * Servis Emirleri tablosu yükleniyor iskeleti (#114)
 */
export function ServiceOrdersTableSkeleton() {
  return (
    <ul className="space-y-3 animate-pulse" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, i) => (
        <li key={i} className="flex justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex-1 space-y-2">
            <div className="h-5 w-64 rounded bg-slate-200" />
            <div className="h-4 w-80 max-w-full rounded bg-slate-100" />
            <div className="h-4 w-full max-w-md rounded bg-slate-100" />
          </div>
          <div className="space-y-2">
            <div className="ml-auto h-5 w-20 rounded-full bg-slate-200" />
            <div className="h-8 w-32 rounded-lg bg-slate-200" />
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * Servis Emri detayı yükleniyor iskeleti (#114)
 */
export function ServiceOrderDetailSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-5 w-36 rounded bg-gray-200" />
        <div className="h-8 w-28 rounded-lg bg-gray-200" />
      </div>
      <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
        <div className="h-6 w-48 rounded bg-gray-200" />
        <div className="h-16 w-full rounded-lg bg-gray-100" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-3">
          <div className="h-5 w-32 rounded bg-gray-200" />
          <div className="h-4 w-full rounded bg-gray-100" />
          <div className="h-4 w-3/4 rounded bg-gray-100" />
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-3">
          <div className="h-5 w-32 rounded bg-gray-200" />
          <div className="h-4 w-full rounded bg-gray-100" />
          <div className="h-4 w-3/4 rounded bg-gray-100" />
        </div>
      </div>
    </div>
  );
}
