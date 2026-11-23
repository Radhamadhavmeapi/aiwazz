# AiWazz design tokens

Single source of truth for `landing/` (Astro) and `dashboard/` (Vite + React):

- `tokens.css`: CSS custom properties: colors (dark default, `.light`), fonts, radius, shadows, motion.
- `theme.css`: Tailwind v4 mapping (`bg-surface`, `text-muted-foreground`, `bg-brand-gradient`, …), shadcn/ui names.

Rules: zinc neutrals, **one accent** (violet → cyan) used sparingly: primary button, active states, waveform.
`--brand-gradient` is decorative only; behind white text use `--brand-gradient-strong` (≥ 4.5:1 everywhere a label sits).
All text colors are ≥ 4.5:1 (WCAG AA) on their backgrounds in both themes: see the live table on
https://login.aiwazz.in/preview/tokens/ (computed in the browser).

Fonts (self-hosted via @fontsource, no Google requests): Geist (UI), Geist Mono (numbers, keys, code),
Noto Sans Devanagari (Hindi; unicode-range split, only downloads when Devanagari is on the page).
