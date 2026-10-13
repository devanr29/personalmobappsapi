export function formatRupiah(amount: number): string {
  const rounded = Math.round(amount);
  const withDots = Math.abs(rounded).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${rounded < 0 ? "-" : ""}Rp ${withDots}`;
}

/** formatRupiah as a worklet, for text driven on the UI thread
 * (AnimatedCurrency). Same output; digit loop instead of a regex so it
 * doesn't depend on RegExp support in the worklet runtime. */
export function formatRupiahWorklet(amount: number): string {
  "worklet";
  const rounded = Math.round(amount);
  const digits = Math.abs(rounded).toString();
  let withDots = "";
  for (let i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 === 0) withDots += ".";
    withDots += digits[i];
  }
  return `${rounded < 0 ? "-" : ""}Rp ${withDots}`;
}

/** Axis-tick form: "Rp 3,9jt". formatRupiah is ~12 characters wide
 * ("Rp 3.850.000") and does not fit a chart's value-axis gutter.
 * rb/jt/m = ribu/juta/miliar, matching the existing "Rp" + dot-thousands
 * convention rather than switching to K/M. */
export function formatRupiahCompact(amount: number): string {
  const rounded = Math.round(amount);
  const abs = Math.abs(rounded);
  const sign = rounded < 0 ? "-" : "";

  if (abs >= 1_000_000_000) return `${sign}Rp ${trimDecimal(abs / 1_000_000_000)}m`;
  if (abs >= 1_000_000) return `${sign}Rp ${trimDecimal(abs / 1_000_000)}jt`;
  if (abs >= 1_000) return `${sign}Rp ${trimDecimal(abs / 1_000)}rb`;
  return `${sign}Rp ${abs}`;
}

function trimDecimal(n: number): string {
  // One decimal place, comma-separated (Indonesian convention), and the
  // decimal dropped entirely when it's a round number ("4jt" not "4,0jt").
  const fixed = n.toFixed(1);
  return fixed.endsWith(".0") ? fixed.slice(0, -2) : fixed.replace(".", ",");
}
