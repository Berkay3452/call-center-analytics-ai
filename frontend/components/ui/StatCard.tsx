import type { ReactNode } from "react";
import { Card } from "./Card";
import { cn } from "./cn";
import { TONE_TEXT, type Tone } from "./tone";

interface StatCardProps {
  label: string;
  value: ReactNode;
  /** Değerin yanında küçük birim (adet, sn vb.) */
  unit?: string;
  hint?: ReactNode;
  tone?: Tone;
  className?: string;
}

/** Büyük rakamlı özet kartı. */
export function StatCard({ label, value, unit, hint, tone = "neutral", className }: StatCardProps) {
  return (
    <Card className={cn("p-4", className)}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn("mt-2 text-3xl font-bold tabular-nums", TONE_TEXT[tone])}>
        {value}
        {unit && <span className="ml-1 text-sm font-medium text-slate-500">{unit}</span>}
      </p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
}
