"use client";

import { useEffect } from "react";

export default function ServiceOrdersError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Hatayı logla
    console.error(error);
  }, [error]);

  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center space-y-4">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-red-100 text-2xl">
        ⚠️
      </div>
      <h3 className="text-base font-bold text-red-900">
        Servis emirleri yüklenirken bir sorun oluştu
      </h3>
      <p className="text-xs text-red-700 max-w-md mx-auto">
        {error.message || "Bilinmeyen bir hata meydana geldi."}
      </p>
      <div className="pt-2">
        <button
          type="button"
          onClick={() => reset()}
          className="rounded-xl bg-red-700 px-4 py-2 text-xs font-bold text-white hover:bg-red-800 transition-colors shadow-xs"
        >
          Yeniden Dene
        </button>
      </div>
    </div>
  );
}
