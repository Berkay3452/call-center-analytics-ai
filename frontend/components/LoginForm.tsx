"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, Card, Field, Input } from "@/components/ui";
import { LOGIN_ROLES, loginErrorMessage, safeNext, type LoginRole } from "@/lib/login";

const ROLES: LoginRole[] = ["admin", "owner"];

/**
 * Giriş formu (#371): Yönetici / Tekne sahibi seçimi, e-posta ve parola. Seçilen rol, sunucuda
 * hangi hesap tablosuna bakılacağını belirler. Hata iletisi genel tutulur (hesabın varlığı belli olmaz).
 */
export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [role, setRole] = useState<LoginRole>("admin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!username.trim() || !password) {
      setError(loginErrorMessage(400));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role, username: username.trim(), password }),
      });
      if (!res.ok) {
        const retry = Number(res.headers.get("retry-after"));
        setError(loginErrorMessage(res.status, Number.isFinite(retry) ? retry : null));
        setPassword("");
        return;
      }
      router.replace(safeNext(params.get("next"), role));
      router.refresh();
    } catch {
      setError(loginErrorMessage(503));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <form onSubmit={onSubmit} className="space-y-5" noValidate aria-busy={busy}>
        <div>
          <p id="login-role-label" className="mb-2 text-sm font-medium text-slate-700">
            Giriş türü
          </p>
          <div
            role="radiogroup"
            aria-labelledby="login-role-label"
            className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1"
          >
            {ROLES.map((value) => {
              const active = role === value;
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => {
                    setRole(value);
                    setError(null);
                  }}
                  className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-white text-[#0a2540] shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {LOGIN_ROLES[value].label}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-slate-500">{LOGIN_ROLES[role].hint}</p>
        </div>

        <Field id="login-username" label="E-posta">
          <Input
            id="login-username"
            name="username"
            type="email"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            maxLength={100}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={busy}
          />
        </Field>

        <Field id="login-password" label="Parola">
          <div className="relative">
            <Input
              id="login-password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              maxLength={200}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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
        </Field>

        {error && (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Giriş yapılıyor…" : `${LOGIN_ROLES[role].label} olarak giriş yap`}
        </Button>
      </form>
    </Card>
  );
}
