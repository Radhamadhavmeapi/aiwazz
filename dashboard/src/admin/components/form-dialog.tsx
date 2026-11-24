import { Loader2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errMsg } from "../lib/admin-api";

/** Dialog with a form: runs onSubmit, toasts errors, closes on success. Children are the fields. */
export function FormDialog({ open, onOpenChange, title, description, children, submitLabel = "Save", destructive, onSubmit, disabled, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: ReactNode; children?: ReactNode;
  submitLabel?: string; destructive?: boolean; onSubmit: () => Promise<unknown>; disabled?: boolean; wide?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSubmit();
      onOpenChange(false);
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={wide ? "sm:max-w-2xl" : "sm:max-w-md"}>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          {children && <div className="my-5 space-y-4">{children}</div>}
          <DialogFooter className={children ? "" : "mt-5"}>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant={destructive ? "destructive" : "brand"} disabled={busy || disabled}>
              {busy && <Loader2 className="animate-spin" />} {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Small hook for "which dialog is open" state. */
export function useDialogs<K extends string>() {
  const [open, setOpen] = useState<K | null>(null);
  return { open, show: (k: K) => setOpen(k), props: (k: K) => ({ open: open === k, onOpenChange: (o: boolean) => setOpen(o ? k : null) }) };
}
