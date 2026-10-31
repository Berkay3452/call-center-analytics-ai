/** Ortak ton paleti: lacivert ana, turuncu vurgu, durum renkleri. */
export type Tone = "neutral" | "brand" | "accent" | "success" | "warning" | "danger";

export const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-brand-800",
  brand: "text-brand-700",
  accent: "text-accent-600",
  success: "text-emerald-600",
  warning: "text-amber-600",
  danger: "text-red-600",
};

export const TONE_BAR: Record<Tone, string> = {
  neutral: "bg-slate-400",
  brand: "bg-brand-600",
  accent: "bg-accent-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
};

export const TONE_BADGE: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700 border-slate-200",
  brand: "bg-brand-50 text-brand-700 border-brand-100",
  accent: "bg-accent-50 text-accent-700 border-accent-100",
  success: "bg-emerald-50 text-emerald-700 border-emerald-200",
  warning: "bg-amber-50 text-amber-800 border-amber-200",
  danger: "bg-red-50 text-red-700 border-red-200",
};
