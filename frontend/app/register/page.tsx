import type { Metadata } from "next";
import { RegisterForm } from "@/components/RegisterForm";

export const metadata: Metadata = {
  title: "Kaydol — Miço Usta",
  description: "Tekne sahibi hesabı oluşturun",
};

/** Kaydol sayfası (#384). Yalnızca tekne sahibi (müşteri) hesabı açılır; kabuk bu yolda gösterilmez. */
export default function RegisterPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-lg">
        <div className="mb-6 text-center">
          <p className="text-3xl font-bold tracking-tight text-[#0a2540]">
            Miço <span className="text-orange-500">Usta</span>
          </p>
          <p className="mt-1 text-sm text-slate-600">Tekne sahibi hesabı oluşturun</p>
        </div>
        <RegisterForm />
      </div>
    </div>
  );
}
