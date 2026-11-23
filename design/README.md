# AiWazz design tokens

Single source of truth for `landing/` (Astro) and `dashboard/` (Vite + React), based on the
**AiWazz Brand Kit v1.0** (`brand/AiWazz-Brand-Kit/`, start with the guidelines PDF).

- `tokens.css`: CSS custom properties: colours (dark default, `.light`), fonts, radius, shadows, motion.
- `theme.css`: Tailwind v4 mapping (`bg-surface`, `text-muted-foreground`, `bg-brand-gradient`, `.tagline`, …), shadcn/ui names.
- `assets/`: web-sized brand artwork built from the kit masters by `tools/brand_assets.py` (needs Pillow):
  logos (`logo-*`, with tagline; `logo-nt-*`, without), `icon-*`, `favicon/` (site root), `og-image.png`.
  Never edit these by hand; never recolour or add effects to the logo.

Colours: Midnight Navy #070D25, Sky Blue #51B2F6, Royal Indigo #2D36DB (primary), Electric Violet #7420DD,
Ink #0A0A0B, Cloud #F4F6FB, Slate #64748B. Gradient #51B2F6 → #2D36DB → #7420DD (decorative);
behind white text `--brand-gradient-strong` (#1F6FD1 → #2D36DB → #7420DD, ≥ 5.8:1).
All text ≥ 4.5:1 (WCAG AA) in both themes; where a brand colour fails, a tint of the same hue is used
(see comments in tokens.css and the live table at https://login.aiwazz.in/preview/tokens/).

Theme: **light by default** on every page of both sites (not OS-based); dark is optional via the toggle and remembered
(localStorage key `aiwazz-theme`), applied before first paint by an inline script.

Fonts (self-hosted via @fontsource, no Google requests): Poppins (headings), Inter (UI/body),
Montserrat (tagline only), Noto Sans Devanagari (Hindi), Geist Mono (codes, keys, timecodes).
