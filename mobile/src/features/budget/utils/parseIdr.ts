// Mirrors features/budget/quickadd.py's parse_amount / _parse_decimal_last_sep_is_point
// exactly — same suffix table, same "last separator is the decimal point
// when a magnitude suffix is present" Indonesian-numeral rule, same <100
// bare-value rejection. Kept in lockstep with the Python amount table
// (tests/test_budget_quickadd.py) so AmountField never disagrees with what
// quick-add would have parsed server-side.
const AMOUNT_RE = /^(?:rp\.?\s*)?(\d[\d.,]*)\s*(rb|ribu|k|jt|juta|m)?/i;
const THOUSAND_SUFFIXES = new Set(["rb", "ribu", "k"]);
const MILLION_SUFFIXES = new Set(["jt", "juta", "m"]);

function parseDecimalLastSepIsPoint(numberStr: string): number {
  const lastDot = numberStr.lastIndexOf(".");
  const lastComma = numberStr.lastIndexOf(",");
  const lastSep = Math.max(lastDot, lastComma);
  if (lastSep === -1) return Number(numberStr);

  const integerPart = numberStr.slice(0, lastSep).replace(/[.,]/g, "");
  const decimalPart = numberStr.slice(lastSep + 1);
  if (!/^\d+$/.test(decimalPart)) return Number(numberStr.replace(",", "."));
  return Number(`${integerPart || "0"}.${decimalPart}`);
}

/** Returns the parsed IDR amount, or null if the input has no usable amount
 * (empty, unparseable, or a bare value under 100 with no magnitude suffix —
 * ambiguous, e.g. "2" from "beli 2 nasi" must never become Rp 2). */
export function parseIdr(text: string): number | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  const match = trimmed.match(AMOUNT_RE);
  if (!match) return null;

  const [, numberStr, rawSuffix] = match;
  const suffix = rawSuffix ? rawSuffix.toLowerCase() : null;

  if (suffix && (THOUSAND_SUFFIXES.has(suffix) || MILLION_SUFFIXES.has(suffix))) {
    const multiplier = THOUSAND_SUFFIXES.has(suffix) ? 1_000 : 1_000_000;
    return Math.round(parseDecimalLastSepIsPoint(numberStr) * multiplier);
  }

  const cleaned = numberStr.replace(/[.,]/g, "");
  const amount = Number(cleaned);
  if (!Number.isFinite(amount) || cleaned === "") return null;
  if (amount < 100) return null;
  return amount;
}
