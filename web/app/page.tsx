"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { API, apiAlive, fetchIndex, fmt } from "@/lib/data";
import type { RunIndex } from "@/lib/types";

const REPOS = [
  { key: "gym", title: "pydantic-migration-gym", note: "38 independent v1 modules, in this repo" },
  { key: "krr", title: "robusta-dev/krr", note: "merge base of PR #512 (human reference, unmerged)" },
];
const MODES = [
  { key: "baseline", label: "Baseline", sub: "no graph" },
  { key: "swarm", label: "Swarm", sub: "" },
  { key: "swarm+recipes", label: "Swarm + Recipes", sub: "" },
];

function Field({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <span className="text-sm text-muted">{label}</span>
      <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))}
             className="mt-2 w-full rounded-xl border border-line bg-panel px-4 py-3 font-mono text-lg" />
    </label>
  );
}

export default function Launch() {
  const router = useRouter();
  const [ix, setIx] = useState<RunIndex | null>(null);
  const [live, setLive] = useState<boolean | null>(null);
  const [repo, setRepo] = useState("gym");
  const [mode, setMode] = useState("swarm");
  const [workers, setWorkers] = useState(6);
  const [budget, setBudget] = useState(2_000_000);
  const [seed, setSeed] = useState(0);
  const [lease, setLease] = useState(120);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchIndex().then(setIx);
    apiAlive().then(setLive);
  }, []);

  const failing = useMemo(() => {
    const out: Record<string, number> = {};
    for (const r of ix?.runs ?? []) out[r.repo ?? "gym"] = r.red_at_start;
    return out;
  }, [ix]);
  const usable = (ix?.recipes ?? []).filter((r) => r.support >= 2).length;

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(`${API}/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target: repo, mode, workers, budget, seed, lease_s: lease }),
      });
      if (!r.ok) throw new Error(await r.text());
      const { run_id } = await r.json();
      router.push(`/swarm?run=${run_id}&live=1&mode=${encodeURIComponent(mode)}`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="mt-10 grid gap-10 xl:grid-cols-[1fr_400px]">
      <div>
        <h1 className="text-4xl font-semibold sm:text-5xl">Six agents. Zero messages. One graph.</h1>
        <p className="mt-4 max-w-3xl text-lg text-muted">
          Pick a repo stuck on Pydantic v1. The swarm finishes the migration bump-pydantic started, coordinating only
          through FalkorDB: claims, test results and pheromone on the edges.
        </p>

        <p className="mt-10 font-mono text-xs tracking-widest text-muted">01 · REPO</p>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          {REPOS.map((r) => (
            <button key={r.key} onClick={() => setRepo(r.key)}
                    className={`rounded-2xl border p-5 text-left ${repo === r.key ? "border-amber" : "border-line"} bg-panel`}>
              <div className="font-mono text-lg">{r.title}</div>
              <div className="mt-1 text-sm text-muted">{r.note}</div>
              <div className="mt-2 font-mono text-sm text-amber">
                {failing[r.key] === undefined
                  ? "not run yet"
                  : failing[r.key] === 1
                    ? "whole suite blocked by one import error after bump"
                    : `${failing[r.key]} red after bump`}
              </div>
            </button>
          ))}
        </div>

        <p className="mt-8 font-mono text-xs tracking-widest text-muted">02 · MODE</p>
        <div className="mt-3 grid grid-cols-1 gap-1 rounded-2xl border border-line bg-panel p-1.5 sm:grid-cols-3">
          {MODES.map((m) => (
            <button key={m.key} onClick={() => setMode(m.key)}
                    className={`rounded-xl px-4 py-3 ${mode === m.key ? "bg-[#2a2216] text-amber" : "text-text"}`}>
              {m.label}
              {m.sub && <span className="text-muted"> · {m.sub}</span>}
            </button>
          ))}
        </div>

        <p className="mt-8 font-mono text-xs tracking-widest text-muted">03 · BUDGET</p>
        <div className="mt-3 grid gap-4 sm:grid-cols-4">
          <Field label="Workers" value={workers} onChange={setWorkers} />
          <Field label="Token budget" value={budget} onChange={setBudget} />
          <Field label="Seed" value={seed} onChange={setSeed} />
          <Field label="Lease (s)" value={lease} onChange={setLease} />
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-4">
          <button onClick={start} disabled={!live || busy}
                  className="rounded-xl bg-amber px-7 py-4 text-lg font-semibold text-[#1a1206] disabled:opacity-40">
            {busy ? "Seeding the graph…" : "Release the swarm →"}
          </button>
          {live === false && (
            <span className="text-sm text-muted">
              This deployment replays recorded runs; live runs need the local backend (see README).
            </span>
          )}
          {err && <span className="text-sm text-red">{err}</span>}
        </div>
      </div>

      <aside className="space-y-5">
        <div className="rounded-2xl border border-line bg-panel p-5">
          <h2 className="font-semibold">Recipes on hand</h2>
          <div className="mt-3 font-mono text-5xl text-amber">{fmt(usable)}</div>
          <p className="mt-3 text-sm text-muted">
            Learned in earlier runs (support ≥ 2). Used only in Swarm + Recipes mode.
          </p>
        </div>
        <div className="rounded-2xl border border-line bg-panel p-5">
          <h2 className="mb-3 font-semibold">Recorded runs</h2>
          <ul className="space-y-2 font-mono text-sm">
            {[...(ix?.runs ?? [])].reverse().map((r) => (
              <li key={r.run} className="flex items-center justify-between gap-3">
                <Link href={`/swarm?run=${r.run}`} className="truncate text-muted hover:text-amber">{r.run}</Link>
                <span className="shrink-0 text-xs text-faint">{r.red_at_end === 0 ? "green" : `${r.red_at_end} red`}</span>
              </li>
            ))}
            {!ix?.runs.length && <li className="text-faint">none yet</li>}
          </ul>
        </div>
        <p className="text-sm text-muted">
          Every mode gets the same model, workers, budget and hypothesis templates, so the scoreboard compares like
          with like.
        </p>
      </aside>
    </div>
  );
}
