import type { HTMLAttributes } from "react";
import { cn } from "./cn";
import { TONE_BADGE, type Tone } from "./tone";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

/** Durum rozeti. Emoji yok; renk anlamı metinle birlikte verilir. */
export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONE_BADGE[tone],
        className,
      )}
      {...props}
    />
  );
}
