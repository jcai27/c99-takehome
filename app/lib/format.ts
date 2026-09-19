// Turns a (rate_kind, rate_value, rate_text) triple -- db/schema.sql's
// operator/operand split -- into what a human reads. rate_text (the raw
// source string) is always the fallback, so nothing categorized imprecisely
// ever displays as blank.

export type RateKind =
  | "free"
  | "additive"
  | "ad_valorem"
  | "no_change"
  | "specific"
  | "other";

export function formatRate(
  kind: RateKind | null,
  value: number | string | null,
  text: string | null,
): string {
  const v = value === null ? null : Number(value);
  switch (kind) {
    case "free":
      return "Free";
    case "no_change":
      return "No change";
    case "ad_valorem":
      return v !== null ? `${trimNum(v)}%` : (text ?? "—");
    case "additive":
      return v !== null ? `+${trimNum(v)}% (on top of the applicable rate)` : (text ?? "—");
    case "specific":
      return text ?? "—";
    case "other":
      // A real, if uncommon, source shape: the provision's own rate column
      // was blank (e.g. a quota-administered price bracket, where duty
      // depends on which bracket the good falls in, not a flat rate stated
      // here) -- distinct from a parsing failure, which would still carry
      // the raw text. Say so rather than showing a bare "-", which reads as
      // missing data.
      return text ?? "not stated — see notes";
    default:
      return text ?? "—";
  }
}

function trimNum(n: number): string {
  return Number.isInteger(n) ? String(n) : String(n);
}

export function rateBadgeClass(kind: RateKind | null): string {
  switch (kind) {
    case "free":
      return "badge badge-free";
    case "no_change":
      return "badge badge-neutral";
    case "additive":
      return "badge badge-additive";
    case "ad_valorem":
      return "badge badge-advalorem";
    case "specific":
      return "badge badge-specific";
    default:
      return "badge badge-other";
  }
}
