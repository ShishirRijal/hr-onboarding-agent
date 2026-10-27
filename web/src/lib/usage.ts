// "$0.0042" for small amounts, so a single question's cost doesn't round to nothing.
export function formatUsd(amount: number): string {
  if (amount === 0) return "$0.00";
  return amount < 0.01 ? `$${amount.toFixed(4)}` : `$${amount.toFixed(2)}`;
}

const compact = new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-GB");

// "12.9K tokens" in tiles, "12,940" in table columns.
export function formatCompact(value: number): string {
  return compact.format(value);
}

export function formatNumber(value: number): string {
  return whole.format(value);
}
