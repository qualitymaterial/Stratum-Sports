import { Signal } from "@/lib/types";

export function SignalBadge({ signal }: { signal: Signal }) {
  const directionTone = signal.direction === "UP" ? "text-positive" : "text-negative";
  const kindTone =
    signal.signal_type === "MULTIBOOK_SYNC"
      ? "border-accent/50 text-accent"
      : "border-borderTone text-textMain";

  return (
    <div className={`rounded border px-2 py-1 text-[11px] ${kindTone}`}>
      <span className="mr-1 text-textMute">{signal.signal_type}</span>
      <span className={directionTone}>{signal.direction}</span>
      <span className="ml-2 text-textMute">S{signal.strength_score}</span>
    </div>
  );
}
