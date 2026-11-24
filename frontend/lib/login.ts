/** Giriş formu yardımcıları (#371): saf mantık, birim testi `lib/login.test.mjs`. */

export type LoginRole = "admin" | "owner";

export const LOGIN_ROLES: Record<LoginRole, { label: string; hint: string; home: string }> = {
  admin: {
    label: "Yönetici",
    hint: "Çağrı analitiği, CRM önerileri ve servis emirleri paneli.",
    home: "/admin/analytics",
  },
  owner: {
    label: "Tekne sahibi",
    hint: "Teknenize ve kayıtlarınıza özel Miço AI asistanı.",
    home: "/owner/assistant",
  },
};

/**
 * Girişten sonra gidilecek yer. `next` yalnızca rolün kendi alanındaki göreli bir yolsa kullanılır
 * (açık yönlendirme ve rol dışı yola atlama engellenir); aksi halde rolün ana sayfası.
 */
export function safeNext(next: string | null | undefined, role: LoginRole): string {
  const home = LOGIN_ROLES[role].home;
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return home;
  const area = role === "admin" ? "/admin" : "/owner";
  return next === area || next.startsWith(`${area}/`) ? next : home;
}

/** Sunucu yanıt koduna göre kullanıcıya gösterilecek ileti. */
export function loginErrorMessage(status: number, retryAfterS?: number | null): string {
  if (status === 401) return "Kullanıcı adı veya parola hatalı.";
  if (status === 429) {
    const wait = retryAfterS && retryAfterS > 0 ? ` (yaklaşık ${Math.ceil(retryAfterS)} sn)` : "";
    return `Çok fazla deneme yapıldı; lütfen biraz bekleyip tekrar deneyin${wait}.`;
  }
  if (status === 400) return "Kullanıcı adı ve parolayı girin.";
  return "Giriş şu anda yapılamıyor. Lütfen daha sonra tekrar deneyin.";
}
