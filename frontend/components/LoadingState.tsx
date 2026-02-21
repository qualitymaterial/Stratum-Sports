export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="rounded-xl border border-borderTone bg-panelSoft p-6 text-sm text-textMute shadow-terminal">
      {label}
    </div>
  );
}
