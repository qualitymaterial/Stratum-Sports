export function formatLine(value: number | null | undefined, decimals = 1): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const rounded = Number(value.toFixed(decimals));
  return rounded.toString();
}

export function formatMoneyline(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const rounded = Math.round(value);
  if (rounded > 0) {
    return `+${rounded}`;
  }
  return `${rounded}`;
}

export function formatSigned(value: number | null | undefined, decimals = 3): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const rounded = Number(value.toFixed(decimals));
  if (rounded > 0) {
    return `+${rounded}`;
  }
  return `${rounded}`;
}
