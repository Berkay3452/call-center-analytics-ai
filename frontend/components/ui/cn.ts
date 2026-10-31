/** Sınıf adlarını birleştirir; falsy değerleri atar. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
