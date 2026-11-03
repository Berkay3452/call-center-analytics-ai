import { useId } from "react";
import { ProgressBar, cn } from "@/components/ui";

interface ConfidenceMeterProps {
  /** Ekranda görünen ad (ör. "Çağrı türü güveni"). */
  title: string;
  /** ⓘ ipucu metni: skorun neyi ölçtüğü. */
  hint: string;
  /** 0–1 ya da 0–100 aralığında değer; null/undefined = hesaplanamadı. */
  value?: number | null;
  /** Analiz sürüyorsa "Hesaplanıyor…" gösterilir. */
  pending?: boolean;
  className?: string;
}

/** Yapay zekâ ajanlarının güven skorları için tek görünüm: ad + ⓘ ipucu + yüzde + ilerleme çubuğu. */
export function ConfidenceMeter({ title, hint, value, pending = false, className }: ConfidenceMeterProps) {
  const tipId = useId();
  const percent = value != null && !pending ? Math.round(value <= 1 ? value * 100 : value) : null;

  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-500">
        <span className="group relative inline-flex items-center gap-1">
          <span className="font-medium text-slate-700">{title}</span>
          <span
            tabIndex={0}
            role="note"
            aria-label={`${title}: ${hint}`}
            aria-describedby={tipId}
            className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-300 text-[10px] font-semibold leading-none text-slate-500 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            i
          </span>
          <span
            id={tipId}
            role="tooltip"
            className="pointer-events-none invisible absolute left-0 top-full z-10 mt-1 w-64 rounded-lg bg-slate-800 px-3 py-2 text-xs font-normal leading-snug text-white shadow-lg group-focus-within:visible group-hover:visible"
          >
            {hint}
          </span>
        </span>
        <span className={cn("font-semibold", percent !== null ? "text-brand-800" : "text-slate-400")}>
          {pending ? "Hesaplanıyor…" : percent !== null ? `%${percent}` : "Hesaplanamadı"}
        </span>
      </div>
      <ProgressBar value={percent ?? 0} tone={percent !== null ? "success" : "neutral"} label={title} />
    </div>
  );
}
