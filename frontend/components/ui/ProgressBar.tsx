import { cn } from "./cn";
import { TONE_BAR, type Tone } from "./tone";

interface ProgressBarProps {
  value: number;
  max?: number;
  tone?: Tone;
  /** Erişilebilir ad (ekran okuyucu) */
  label: string;
  className?: string;
}

/** Yatay ilerleme çubuğu. */
export function ProgressBar({ value, max = 100, tone = "brand", label, className }: ProgressBarProps) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-slate-100", className)}
    >
      <div className={cn("h-full rounded-full", TONE_BAR[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}
