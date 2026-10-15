"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchIndex, fmt } from "@/lib/data";
import type { Metrics, RunIndex } from "@/lib/types";

const MODES = [
  { key: "baseline", title: "Baseline", note: "no shared graph" },
  { key: "swarm", title: "Swarm", note: "graph on" },
  { key: "swarm+recipes", title: "Swarm + Recipes", note: "recipes from earlier runs" },
] as const;

const COLORS: Record<string, { stroke: string; dash?: string }> = {
  baseline: { stroke: "var(--muted)" },
  swarm: { stroke: "var(--amber)" },
  "swarm+recipes": { stroke: "var(--text)", dash: "6 5" },
};

function median(xs: number[]): number | null {
  const v = xs.filter((x) => x !== null && x !== undefined && !Number.isNaN(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

function range(xs: number[]): string {
  const v = xs.filter((x) => x !== null && x !== undefined);
  if (v.length < 2) return "";
  return `${fmt(Math.min(...v), 1)}–${fmt(Math.max(...v), 1)}`;
}

type Agg = { runs: Metrics[]; med: Record<string, number | null>; rng: Record<string, string> };

function aggregate(runs: Metrics[]): Agg {
  const pick = (f: (m: Metrics) => number | null) => runs.map(f).filter((x): x is number => x !== null);
  const fields: Record<string, (m: Metrics) => number | null> = {
    green: (m) => m.green_at_end,
    total: (m) => (m.green_at_end ?? 0) + (m.red_at_end ?? 0),
    red_end: (m) => m.red_at_end,
    wasted: (m) => m.superseded + m.repeated_diffs + m.repeated_dead_ends,
    tokens: (m) => m.tokens,
    minutes: (m) => (m.seconds_to_green ?? m.seconds) / 60,
    collisions: (m) => m.collisions,
    attempts: (m) => m.attempts,
    recipe: (m) => m.recipe_hit_rate * 100,
  };
  const med: Agg["med"] = {};
  const rng: Agg["rng"] = {};
  for (const [k, f] of Object.entries(fields)) {
    med[k] = median(pick(f));
    rng[k] = range(pick(f));
  }
  return { runs, med, rng };
}

function Cell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 font-mono text-3xl">{value}</div>
      <div className="h-4 font-mono text-[11px] text-faint">{sub}</div>
    </div>
  );
}

function BurnDown({ groups }: { groups: Record<string, Agg> }) {
  const all = Object.values(groups).flatMap((g) => g.runs);
  const tMax = Math.max(1, ...all.flatMap((r) => r.burn_down.map(([t]) => t)), ...all.map((r) => r.seconds ?? 0));
  const yMax = Math.max(1, ...all.map((r) => r.red_at_start));
  const W = 1000, H = 320, L = 50, B = 30;
  const x = (t: number) => L + (t / tMax) * (W - L - 20);
  const y = (red: number) => 10 + (1 - red / yMax) * (H - B - 10);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Failing tests over time per mode">
      <line x1={L} y1={y(0)} x2={W - 20} y2={y(0)} stroke="var(--line)" />
      <line x1={L} y1={y(yMax)} x2={W - 20} y2={y(yMax)} stroke="var(--line)" strokeDasharray="2 6" />
      <text x={L - 8} y={y(yMax) + 4} textAnchor="end" fontSize="12" className="fill-[var(--muted)] font-mono">{yMax}</text>
      <text x={L - 8} y={y(0) + 4} textAnchor="end" fontSize="12" className="fill-[var(--muted)] font-mono">0</text>
      <text x={W - 20} y={H - 6} textAnchor="end" fontSize="12" className="fill-[var(--muted)] font-mono">
        {fmt(tMax / 60, 1)} min
      </text>
      {Object.entries(groups).flatMap(([mode, g]) =>
        g.runs.map((r) => {
          const pts = [...r.burn_down, [r.seconds ?? r.burn_down.at(-1)![0], r.red_at_end ?? r.burn_down.at(-1)![1]] as [number, number]];
          const d = pts.map(([t, red], i) => `${i ? "L" : "M"} ${x(t).toFixed(1)} ${y(red).toFixed(1)}`).join(" ");
          // step line: hold each value until the next merge
          const step = pts.map(([t, red], i) => (i ? `H ${x(t).toFixed(1)} V ${y(red).toFixed(1)}` : `M ${x(t).toFixed(1)} ${y(red).toFixed(1)}`)).join(" ");
          return (
            <path key={r.run} d={step || d} fill="none" stroke={COLORS[mode]?.stroke} strokeDasharray={COLORS[mode]?.dash}
                  strokeWidth={2.2} opacity={g.runs.length > 1 ? 0.75 : 1} />
          );
        }),
      )}
    </svg>
  );
}

export default function Scoreboard() {
  const [ix, setIx] = useState<RunIndex | null>(null);
  const [repo, setRepo] = useState<string>("gym");
  useEffect(() => void fetchIndex().then(setIx), []);

  const repos = useMemo(() => [...new Set((ix?.runs ?? []).map((r) => r.repo ?? "gym"))], [ix]);
  const groups = useMemo(() => {
    const out: Record<string, Agg> = {};
    for (const m of MODES) {
      const runs = (ix?.runs ?? []).filter((r) => (r.repo ?? "gym") === repo && r.mode === m.key);
      if (runs.length) out[m.key] = aggregate(runs);
    }
    return out;
  }, [ix, repo]);

  if (!ix) return <p className="mt-10 font-mono text-muted">loading…</p>;
  const sample = Object.values(groups)[0]?.runs[0];
  const b = groups.baseline?.med, s = groups.swarm?.med;
  const headline =
    b && s && b.tokens && s.tokens && b.minutes && s.minutes
      ? `Without the graph the same agents used ${fmt(b.tokens / s.tokens, 1)}× the tokens and ${fmt(b.minutes / s.minutes, 1)}× the time.`
      : "Run each mode to compare them here.";

  return (
    <div className="mt-8 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs tracking-widest text-muted">
            SAME REPO · SAME MODEL · {sample?.workers ?? "–"} WORKERS · MEDIAN OF RECORDED RUNS
          </p>
          <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">{headline}</h1>
        </div>
        <div className="flex gap-1 rounded-lg border border-line p-1">
          {repos.map((r) => (
            <button key={r} onClick={() => setRepo(r)}
                    className={`rounded-md px-3 py-1.5 font-mono text-sm ${r === repo ? "bg-panel-2 text-amber" : "text-muted"}`}>
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {MODES.map((m) => {
          const g = groups[m.key];
          const hot = m.key === "swarm";
          return (
            <section key={m.key} className={`rounded-2xl border p-6 ${hot ? "border-amber bg-[#1c1813]" : "border-line bg-panel"}`}>
              <div className="mb-5 flex items-baseline justify-between">
                <h2 className={`text-xl font-semibold ${hot ? "text-amber" : ""}`}>{m.title}</h2>
                <span className="text-sm text-muted">{m.note}</span>
              </div>
              {g ? (
                <div className="grid grid-cols-2 gap-y-5">
                  <Cell label="Tests green" value={`${fmt(g.med.green)}/${fmt(g.med.total)}`} sub={g.rng.green} />
                  <Cell label="Wasted attempts" value={fmt(g.med.wasted, 1)} sub={g.rng.wasted} />
                  <Cell label="Tokens" value={fmt(g.med.tokens)} sub={g.rng.tokens} />
                  <Cell label={g.runs.every((r) => r.red_at_end === 0) ? "Minutes to green" : "Minutes"} value={fmt(g.med.minutes, 1)} sub={g.rng.minutes} />
                  <Cell label="Collisions" value={fmt(g.med.collisions, 1)} sub={g.rng.collisions} />
                  {m.key === "swarm+recipes" ? (
                    <Cell label="Recipe hits" value={`${fmt(g.med.recipe)}%`} sub={g.rng.recipe} />
                  ) : (
                    <Cell label="Still red" value={fmt(g.med.red_end)} sub={g.rng.red_end} />
                  )}
                  <p className="col-span-2 font-mono text-[11px] text-faint">{g.runs.length} run{g.runs.length > 1 ? "s" : ""}</p>
                </div>
              ) : (
                <p className="text-sm text-faint">No recorded run for this mode yet.</p>
              )}
            </section>
          );
        })}
      </div>

      <section className="rounded-2xl border border-line bg-panel p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-lg font-semibold">Failing tests over time</h2>
          <div className="flex gap-5 font-mono text-xs">
            {MODES.map((m) => (
              <span key={m.key} style={{ color: COLORS[m.key].stroke }}>
                {COLORS[m.key].dash ? "┄" : "━"} {m.title}
              </span>
            ))}
          </div>
        </div>
        <BurnDown groups={groups} />
        <p className="mt-2 text-center text-xs text-faint">One line per recorded run; steps are merges onto the run branch.</p>
      </section>

      <p className="font-mono text-xs text-faint">
        model {sample?.model ?? "–"} · raw runs: {Object.values(groups).flatMap((g) => g.runs.map((r) => `run:${r.run}`)).join(", ")}
      </p>
    </div>
  );
}
