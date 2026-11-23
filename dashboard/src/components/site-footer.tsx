import legal from "../../../legal/legal.json";
import { cn } from "@/lib/utils";

const SITE = "https://aiwazz.in";
const COLS: { title: string; links: [string, string][] }[] = [
  { title: "Product", links: [["Pricing", "/pricing/"], ["Text to speech", "/text-to-speech/"], ["Hindi text to speech", "/hindi-text-to-speech/"], ["AI voiceover for reels", "/ai-voiceover-for-reels/"]] },
  { title: "Company", links: [["About", "/about/"], ["Contact", "/contact/"], ["Grievance", "/grievance/"]] },
  { title: "Legal", links: [["Terms", "/terms/"], ["Privacy", "/privacy/"], ["Refund policy", "/refund-policy/"], ["Shipping & delivery", "/shipping-policy/"], ["Acceptable use", "/acceptable-use/"], ["Data deletion", "/data-deletion/"]] },
];

/** Company footer (same content as aiwazz.in); links go to the public site. */
export function SiteFooter({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <footer className={cn("border-t text-xs text-subtle-foreground", className)}>
      {!compact && (
        <div className="grid gap-6 px-5 pt-8 sm:grid-cols-3 sm:px-8">
          {COLS.map((c) => (
            <nav key={c.title} aria-label={c.title}>
              <p className="text-xs font-semibold text-foreground">{c.title}</p>
              <ul className="mt-2 space-y-1.5">
                {c.links.map(([label, href]) => (
                  <li key={href}>
                    <a href={SITE + href} className="text-muted-foreground hover:text-foreground">
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
      )}
      {compact && (
        <nav aria-label="Legal" className="flex flex-wrap gap-x-4 gap-y-0.5 px-5 pt-5 sm:px-8">
          {COLS.flatMap((c) => c.links).map(([label, href]) => (
            <a key={href} href={SITE + href} className="inline-flex min-h-7 items-center text-muted-foreground hover:text-foreground">
              {label}
            </a>
          ))}
        </nav>
      )}
      <p className="px-5 pt-4 pb-6 leading-5 sm:px-8">
        © 2026 {legal.legalName} · AiWazz is a brand of {legal.parentBrand} · GSTIN {legal.gstin} · {legal.address} ·{" "}
        <a href={`mailto:${legal.supportEmail}`} className="hover:text-foreground">
          {legal.supportEmail}
        </a>{" "}
        ·{" "}
        <a href={`tel:${legal.phone.replace(/\s+/g, "")}`} className="hover:text-foreground">
          {legal.phone}
        </a>
      </p>
    </footer>
  );
}
