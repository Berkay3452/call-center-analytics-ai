/**
 * Kaydol ve Tekne ekle formları için saf doğrulama (#384). Kurallar backend ile aynıdır
 * (`backend/app/domain/accounts.py`, `schemas/api.py`); asıl denetim her zaman sunucudadır,
 * buradaki kontrol kullanıcıya anında geri bildirim içindir. Birim testi `lib/register.test.mjs`.
 */

export const MIN_PASSWORD_LENGTH = 12;

/** Eksik her parola kuralı için bir ileti; boş liste = parola geçerli. */
export function passwordProblems(password: string): string[] {
  const problems: string[] = [];
  if ([...password].length < MIN_PASSWORD_LENGTH) problems.push(`en az ${MIN_PASSWORD_LENGTH} karakter`);
  if (!/\p{Lu}/u.test(password)) problems.push("en az bir büyük harf");
  if (!/\p{Ll}/u.test(password)) problems.push("en az bir küçük harf");
  if (!/[^\p{L}\p{N}\s]/u.test(password)) problems.push("en az bir özel sembol (ör. ! ? # % + = - _ .)");
  return problems;
}

/** TR cep numarasını `+905xxxxxxxxx` biçimine çevirir; geçersizse `null`. */
export function normalizePhone(raw: string): string | null {
  const compact = raw.replace(/[\s().-]/g, "");
  const match = /^(?:\+90|0)?(5\d{9})$/.exec(compact);
  return match ? `+90${match[1]}` : null;
}

export function isEmail(value: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(value.trim());
}

export interface RegisterForm {
  firstName: string;
  lastName: string;
  phone: string;
  email: string;
  password: string;
  passwordConfirm: string;
}

export type RegisterErrors = Partial<Record<keyof RegisterForm, string>>;

export function validateRegister(form: RegisterForm): RegisterErrors {
  const errors: RegisterErrors = {};
  if (!form.firstName.trim()) errors.firstName = "Adınızı girin.";
  if (!form.lastName.trim()) errors.lastName = "Soyadınızı girin.";
  if (!normalizePhone(form.phone)) errors.phone = "Geçerli bir cep telefonu girin (ör. 0532 123 45 67).";
  if (!isEmail(form.email)) errors.email = "Geçerli bir e-posta adresi girin.";
  const problems = passwordProblems(form.password);
  if (problems.length > 0) errors.password = `Parola şunları içermeli: ${problems.join(", ")}.`;
  if (!form.passwordConfirm) errors.passwordConfirm = "Parolayı tekrar girin.";
  else if (form.passwordConfirm !== form.password) errors.passwordConfirm = "Parola ve tekrarı aynı olmalı.";
  return errors;
}

/** Sunucu yanıt koduna göre kullanıcıya gösterilecek ileti (409/422'de sunucu iletisi korunur). */
export function registerErrorMessage(status: number, serverMessage?: string | null): string {
  if (status === 409) return serverMessage || "Bu bilgilerle kayıt yapılamadı. Giriş yapmayı deneyin.";
  if (status === 429) return "Çok fazla kayıt denemesi yapıldı; lütfen daha sonra tekrar deneyin.";
  if (status === 400 || status === 422) return serverMessage || "Bilgilerinizi kontrol edip tekrar deneyin.";
  return "Kayıt şu anda yapılamıyor. Lütfen daha sonra tekrar deneyin.";
}

export interface BoatForm {
  name: string;
  model: string;
  year: string;
  marina: string;
}

export type BoatErrors = Partial<Record<keyof BoatForm, string>>;

export function validateBoat(form: BoatForm, nowYear = new Date().getFullYear()): BoatErrors {
  const errors: BoatErrors = {};
  const name = form.name.trim();
  if (!name) errors.name = "Tekne adını girin.";
  else if (name.length > 80) errors.name = "Tekne adı en fazla 80 karakter olabilir.";
  if (form.model.trim().length > 80) errors.model = "Model en fazla 80 karakter olabilir.";
  if (form.marina.trim().length > 80) errors.marina = "Marina adı en fazla 80 karakter olabilir.";
  if (form.year.trim()) {
    const year = Number(form.year);
    if (!Number.isInteger(year) || year < 1950 || year > nowYear + 1) {
      errors.year = `Üretim yılı 1950 ile ${nowYear + 1} arasında olmalı.`;
    }
  }
  return errors;
}

/** Sık kullanılan marina adları (öneri; serbest metin de girilebilir). */
export const MARINA_SUGGESTIONS = [
  "Ataköy Marina",
  "Bodrum Milta Marina",
  "Göcek D-Marin",
  "Kalamış Marina",
  "Marmaris Netsel Marina",
  "Pendik Marinturk Marina",
  "Tuzla Marina",
  "Yalıkavak Marina",
  "Çeşme Marina",
  "İstinye Tekne Park",
] as const;
