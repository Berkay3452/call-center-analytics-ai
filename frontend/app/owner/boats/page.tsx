"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, Card, Field, Input } from "@/components/ui";
import { addMyBoat, getMyBoats } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";
import type { BoatOut } from "@/lib/api/types";
import { MARINA_SUGGESTIONS, validateBoat, type BoatErrors, type BoatForm } from "@/lib/register";

const EMPTY: BoatForm = { name: "", model: "", year: "", marina: "" };

/**
 * Teknelerim (#384): tekne sahibi kendi teknelerini görür ve "Tekne ekle" ile yenisini kaydeder.
 * Sahip bilgisi istekten değil oturumdan gelir; yalnızca kendi tekneleri listelenir.
 */
export default function OwnerBoatsPage() {
  const [boats, setBoats] = useState<BoatOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<BoatForm>(EMPTY);
  const [errors, setErrors] = useState<BoatErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      setBoats(await getMyBoats());
      setLoadError(null);
    } catch {
      setLoadError("Tekneleriniz yüklenemedi. Lütfen sayfayı yenileyin.");
    }
  }, []);

  useEffect(() => {
    let active = true;
    getMyBoats()
      .then((rows) => active && setBoats(rows))
      .catch(() => active && setLoadError("Tekneleriniz yüklenemedi. Lütfen sayfayı yenileyin."));
    return () => {
      active = false;
    };
  }, []);

  function set<K extends keyof BoatForm>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const found = validateBoat(form);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const boat = await addMyBoat({
        name: form.name.trim(),
        model: form.model.trim() || null,
        year: form.year.trim() ? Number(form.year) : null,
        marina: form.marina.trim() || null,
      });
      setSaved(`“${boat.name}” teknesi eklendi.`);
      setForm(EMPTY);
      setAdding(false);
      await reload();
    } catch (err) {
      setFormError(
        isApiError(err) && (err.status === 409 || err.status === 422)
          ? err.message
          : "Tekne eklenemedi. Lütfen daha sonra tekrar deneyin.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[#0a2540]">Teknelerim</h1>
          <p className="text-sm text-slate-600">
            Kayıtlı tekneleriniz. Miço AI, bu tekneler için bakım ve gider bilgilerinizi yanıtlar.
          </p>
        </div>
        {!adding && (
          <Button
            onClick={() => {
              setAdding(true);
              setSaved(null);
            }}
          >
            Tekne ekle
          </Button>
        )}
      </div>

      {saved && (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {saved}
        </p>
      )}

      {adding && (
        <Card className="p-5">
          <form onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={busy} aria-label="Tekne ekle">
            <h2 className="text-base font-semibold text-[#0a2540]">Yeni tekne</h2>
            <Field id="boat-name" label="Tekne adı" hint="Örn. Rüzgar" error={errors.name}>
              <Input
                id="boat-name"
                maxLength={80}
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                aria-invalid={!!errors.name}
                disabled={busy}
                autoFocus
              />
            </Field>
            <Field id="boat-model" label="Tekne modeli" hint="Örn. Jeanneau Sun Odyssey 440" error={errors.model}>
              <Input
                id="boat-model"
                maxLength={80}
                value={form.model}
                onChange={(e) => set("model", e.target.value)}
                aria-invalid={!!errors.model}
                disabled={busy}
              />
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field id="boat-year" label="Üretim yılı" hint="İsteğe bağlı" error={errors.year}>
                <Input
                  id="boat-year"
                  inputMode="numeric"
                  maxLength={4}
                  value={form.year}
                  onChange={(e) => set("year", e.target.value.replace(/\D/g, ""))}
                  aria-invalid={!!errors.year}
                  disabled={busy}
                />
              </Field>
              <Field id="boat-marina" label="Marina" hint="Listeden seçin veya yazın" error={errors.marina}>
                <Input
                  id="boat-marina"
                  list="boat-marinas"
                  maxLength={80}
                  value={form.marina}
                  onChange={(e) => set("marina", e.target.value)}
                  aria-invalid={!!errors.marina}
                  disabled={busy}
                />
                <datalist id="boat-marinas">
                  {MARINA_SUGGESTIONS.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </Field>
            </div>

            {formError && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {formError}
              </p>
            )}

            <div className="flex gap-3">
              <Button type="submit" disabled={busy}>
                {busy ? "Kaydediliyor…" : "Teknemi kaydet"}
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => {
                  setAdding(false);
                  setForm(EMPTY);
                  setErrors({});
                  setFormError(null);
                }}
              >
                Vazgeç
              </Button>
            </div>
          </form>
        </Card>
      )}

      {loadError && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {loadError}
        </p>
      )}

      {boats === null && !loadError && <p className="text-sm text-slate-500">Yükleniyor…</p>}

      {boats !== null && boats.length === 0 && !adding && (
        <Card className="p-8 text-center">
          <p className="font-medium text-slate-800">Henüz tekne eklemediniz.</p>
          <p className="mt-1 text-sm text-slate-600">“Tekne ekle” ile ilk teknenizi kaydedin.</p>
        </Card>
      )}

      {boats !== null && boats.length > 0 && (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2" aria-label="Tekneler">
          {boats.map((boat) => (
            <li key={boat.id}>
              <Card className="p-4">
                <p className="text-base font-semibold text-[#0a2540]">{boat.name}</p>
                <dl className="mt-2 space-y-1 text-sm text-slate-600">
                  <div className="flex gap-2">
                    <dt className="text-slate-500">Model:</dt>
                    <dd>{boat.model ?? "—"}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-slate-500">Yıl:</dt>
                    <dd>{boat.year ?? "—"}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-slate-500">Marina:</dt>
                    <dd>{boat.marina ?? "—"}</dd>
                  </div>
                </dl>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
