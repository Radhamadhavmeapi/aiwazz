import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

/*
 * Brand artwork from the AiWazz Brand Kit (design/assets, built from brand/ by tools/brand_assets.py).
 * Rules (brand guidelines): the wordmark is artwork, never retyped; "for-dark" version on dark,
 * full colour on light; no recolouring or effects; minimum widths: with tagline 160 px,
 * without tagline 120 px, icon 16 px.
 */
const base = `${import.meta.env.BASE_URL}brand/`;
const srcset = (name: string, widths: number[]) => widths.map((w) => `${base}${name}-${w}.webp ${w}w`).join(", ");

const RATIO = { full: 1024 / 248, "no-tagline": 1024 / 238 } as const;
const MIN_WIDTH = { full: 160, "no-tagline": 120 } as const;

export function Logo({
  variant = "no-tagline",
  width = variant === "full" ? 168 : 128,
  className,
  priority = false,
}: {
  variant?: "full" | "no-tagline";
  /** CSS px; clamped to the brand minimum for the variant */
  width?: number;
  className?: string;
  priority?: boolean;
}) {
  const { theme } = useTheme();
  const w = Math.max(width, MIN_WIDTH[variant]);
  const name = `${variant === "full" ? "logo" : "logo-nt"}-${theme === "dark" ? "for-dark" : "color"}`;
  return (
    <img
      src={`${base}${name}-320.webp`}
      srcSet={srcset(name, [320, 640, 960])}
      sizes={`${w}px`}
      width={w}
      height={Math.round(w / RATIO[variant])}
      alt={variant === "full" ? "AiWazz: Type it, hear it." : "AiWazz"}
      decoding="async"
      fetchPriority={priority ? "high" : undefined}
      className={cn("block h-auto shrink-0 select-none", className)}
      draggable={false}
    />
  );
}

/** A-Play icon (sidebar, mobile bars, auth brand panel). */
export function BrandIcon({ size = 32, className, decorative = false }: { size?: number; className?: string; decorative?: boolean }) {
  return (
    <img
      src={`${base}icon-64.webp`}
      srcSet={srcset("icon", [64, 128, 256])}
      sizes={`${size}px`}
      width={size}
      height={size}
      alt={decorative ? "" : "AiWazz"}
      aria-hidden={decorative || undefined}
      decoding="async"
      className={cn("block shrink-0 select-none", className)}
      draggable={false}
    />
  );
}
