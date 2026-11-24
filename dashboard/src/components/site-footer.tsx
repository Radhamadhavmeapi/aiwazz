import legal from "../../../legal/legal.json";
import { cn } from "@/lib/utils";

/** App footer: copyright only (business details live on aiwazz.in/contact/, /about/ and the policy pages). */
export function SiteFooter({ className }: { className?: string }) {
  return (
    <footer className={cn("px-5 py-5 text-xs text-subtle-foreground sm:px-8", className)}>
      <p>© 2026 AiWazz · {legal.legalName}</p>
    </footer>
  );
}
