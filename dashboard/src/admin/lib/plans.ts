export const PLAN_OPTIONS = [
  { value: "free", label: "Free" }, { value: "starter", label: "Starter" },
  { value: "creator", label: "Creator" }, { value: "pro", label: "Pro" },
];
export const planName = (p: string | null | undefined) => PLAN_OPTIONS.find((o) => o.value === p)?.label ?? p ?? "–";
export const planTone = (p: string) => (p === "pro" ? "blue" : p === "creator" ? "blue" : p === "starter" ? "green" : "gray");
