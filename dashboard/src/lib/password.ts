/** 0–4. Length matters most; character variety helps; obvious patterns cap the score. */
export function passwordScore(pw: string): number {
  if (!pw) return 0;
  let s = 0;
  if (pw.length >= 10) s++;
  if (pw.length >= 14) s++;
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  if (kinds >= 3) s++;
  if (pw.length >= 18 || (kinds === 4 && pw.length >= 12)) s++;
  if (/^(.)\1+$/.test(pw) || /(password|qwerty|123456|aiwazz)/i.test(pw)) s = Math.min(s, 1);
  return Math.min(4, s);
}
