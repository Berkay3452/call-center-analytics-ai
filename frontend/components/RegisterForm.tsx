"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";
import { Button, Card, Field, Input } from "@/components/ui";
import {
  passwordProblems,
  registerErrorMessage,
  validateRegister,
  type RegisterErrors,
  type RegisterForm as RegisterValues,
} from "@/lib/register";

const EMPTY: RegisterValues = {
  firstName: "",
  lastName: "",
  phone: "",
  email: "",
  password: "",
  passwordConfirm: "",
};

/**
 * Kaydol formu (#384): müşteri kendi tekne sahibi hesabını açar. Doğum tarihi sorulmaz (projeye
 * gerekmez, veri en aza indirilir). Parola kuralı canlı gösterilir; kayıt başarılıysa otomatik
 * giriş yapılır. Aynı kurallar sunucuda da zorunludur.
 */
export function RegisterForm() {
  const router = useRouter();
  const [values, setValues] = useState<RegisterValues>(EMPTY);
  const [errors, setErrors] = useState<RegisterErrors>({});
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const missing = useMemo(() => passwordProblems(values.password), [values.password]);

  function set<K extends keyof RegisterValues>(key: K, value: string) {
    setValues((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const found = validateRegister(values);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          first_name: values.firstName.trim(),
          last_name: values.lastName.trim(),
          phone: values.phone.trim(),
          email: values.email.trim(),
          password: values.password,
          password_confirm: values.passwordConfirm,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
        setFormError(registerErrorMessage(res.status, data?.error?.message));
        setValues((prev) => ({ ...prev, password: "", passwordConfirm: "" }));
        return;
      }
      router.replace("/owner/assistant");
      router.refresh();
    } catch {
      setFormError(registerErrorMessage(503));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <form onSubmit={onSubmit} className="space-y-4" noValidate aria-busy={busy}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field id="reg-first-name" label="Ad" error={errors.firstName}>
            <Input
              id="reg-first-name"
              name="given-name"
              autoComplete="given-name"
              maxLength={80}
              value={values.firstName}
              onChange={(e) => set("firstName", e.target.value)}
              aria-invalid={!!errors.firstName}
              disabled={busy}
            />
          </Field>
          <Field id="reg-last-name" label="Soyad" error={errors.lastName}>
            <Input
              id="reg-last-name"
              name="family-name"
              autoComplete="family-name"
              maxLength={80}
              value={values.lastName}
              onChange={(e) => set("lastName", e.target.value)}
              aria-invalid={!!errors.lastName}
              disabled={busy}
            />
          </Field>
        </div>

        <Field id="reg-phone" label="Telefon numarası" hint="Cep telefonu, ör. 0532 123 45 67" error={errors.phone}>
          <Input
            id="reg-phone"
            name="tel"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            maxLength={30}
            value={values.phone}
            onChange={(e) => set("phone", e.target.value)}
            aria-invalid={!!errors.phone}
            disabled={busy}
          />
        </Field>

        <Field id="reg-email" label="E-posta" hint="Giriş yaparken bu adresi kullanacaksınız." error={errors.email}>
          <Input
            id="reg-email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            maxLength={120}
            value={values.email}
            onChange={(e) => set("email", e.target.value)}
            aria-invalid={!!errors.email}
            disabled={busy}
          />
        </Field>

        <Field id="reg-password" label="Parola" error={errors.password}>
          <div className="relative">
            <Input
              id="reg-password"
              name="new-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              maxLength={200}
              value={values.password}
              onChange={(e) => set("password", e.target.value)}
              aria-invalid={!!errors.password}
              aria-describedby="reg-password-rules"
              disabled={busy}
              className="pr-20"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-pressed={showPassword}
              className="absolute inset-y-0 right-2 my-1 rounded-md px-2 text-xs font-medium text-brand-700 hover:bg-slate-100"
            >
              {showPassword ? "Gizle" : "Göster"}
            </button>
          </div>
          <ul id="reg-password-rules" className="mt-2 space-y-0.5 text-xs" aria-live="polite">
            {[
              ["en az 12 karakter", "12 karakter"],
              ["en az bir büyük harf", "büyük harf"],
              ["en az bir küçük harf", "küçük harf"],
              ["en az bir özel sembol (! ? # % + = - _ .)", "özel sembol"],
            ].map(([label, key]) => {
              const ok = values.password.length > 0 && !missing.some((m) => m.includes(key));
              return (
                <li key={key} className={ok ? "text-emerald-700" : "text-slate-500"}>
                  <span aria-hidden="true">{ok ? "✓" : "•"}</span> {label}
                  <span className="sr-only">{ok ? " (sağlandı)" : " (gerekli)"}</span>
                </li>
              );
            })}
          </ul>
        </Field>

        <Field id="reg-password-confirm" label="Parolayı tekrarla" error={errors.passwordConfirm}>
          <Input
            id="reg-password-confirm"
            name="new-password-confirm"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            maxLength={200}
            value={values.passwordConfirm}
            onChange={(e) => set("passwordConfirm", e.target.value)}
            aria-invalid={!!errors.passwordConfirm}
            disabled={busy}
          />
        </Field>

        {formError && (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {formError}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Hesap oluşturuluyor…" : "Hesap oluştur"}
        </Button>
        <p className="text-center text-sm text-slate-600">
          Zaten hesabınız var mı?{" "}
          <Link href="/login" className="font-medium text-brand-700 hover:underline">
            Giriş yapın
          </Link>
        </p>
      </form>
    </Card>
  );
}
