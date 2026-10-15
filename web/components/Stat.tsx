export default function Stat({ label, value, sub, accent }: { label: string; value: React.ReactNode; sub?: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-line bg-panel px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 font-mono text-2xl ${accent ? "text-amber" : "text-text"}`}>{value}</div>
      {sub && <div className="mt-0.5 font-mono text-[11px] text-faint">{sub}</div>}
    </div>
  );
}
