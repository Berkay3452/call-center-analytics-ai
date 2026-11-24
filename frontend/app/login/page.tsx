import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "Giriş — Miço Usta",
  description: "Yönetici ve tekne sahibi girişi",
};

/** Giriş sayfası (#371). Uygulama kabuğu (üst bar, sekmeler) bu yolda gösterilmez. */
export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <p className="text-3xl font-bold tracking-tight text-[#0a2540]">
            Miço <span className="text-orange-500">Usta</span>
          </p>
          <p className="mt-1 text-sm text-slate-600">Çağrı Analitiği ve Miço AI</p>
        </div>
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
        <p className="mt-6 text-center text-xs text-slate-500">
          Hesabınız yoksa veya parolanızı unuttuysanız yöneticinizle iletişime geçin.
        </p>
      </div>
    </div>
  );
}
