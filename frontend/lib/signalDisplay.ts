export const STRUCTURAL_THRESHOLD_EVENT_LABEL = "STRUCTURAL THRESHOLD EVENT";

export function displaySignalType(signalType: string | null | undefined, displayType?: string | null): string {
  const trimmedDisplay = (displayType ?? "").trim();
  if (trimmedDisplay) {
    return trimmedDisplay;
  }

  const normalizedSignalType = (signalType ?? "").trim();
  if (normalizedSignalType === "KEY_CROSS") {
    return STRUCTURAL_THRESHOLD_EVENT_LABEL;
  }

  return normalizedSignalType;
}
