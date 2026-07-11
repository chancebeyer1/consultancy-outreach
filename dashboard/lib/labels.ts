// Turn a raw enum / snake_case / lowercase value into a human "Title Case" label for display.
// e.g. "call_booked" -> "Call Booked", "interested" -> "Interested", "warm_signal" -> "Warm Signal".
const KEEP_UPPER = new Set(["ai", "crm", "ceo", "cto", "vp", "saas", "b2b", "url", "id"]);

export function titleCase(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/[_-]+/g, " ")
    .trim()
    .split(/\s+/)
    .map((w) => (KEEP_UPPER.has(w.toLowerCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}
