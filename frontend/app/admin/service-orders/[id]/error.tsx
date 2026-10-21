"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function ServiceOrderDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="max-w-2xl mx-auto py-12 text-center space-y-4">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-red-100 dark:bg-red-900/60 text-3xl">
        ⚠️
      </div>
      <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
        Servis emri detayı yüklenemedi
      </h2>
      <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto">
        {error.message || "İstenen servis emri bulunamadı veya sunucu yanıt vermiyor."}
      </p>
      <div className="flex items-center justify-center gap-3 pt-2">
        <button
          type="button"
          onClick={() => reset()}
          className="rounded-xl bg-sky-700 dark:bg-sky-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-sky-800"
        >
          Yeniden Dene
        </button>
        <Link
          href="/admin/service-orders"
          className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-50"
        >
          Listeye Dön
        </Link>
      </div>
    </div>
  );
}
