"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Feed from "@/components/Feed";
import Stat from "@/components/Stat";
import SwarmGraph from "@/components/SwarmGraph";
import { apiAlive, fetchIndex, fetchRun, fmt, killAgent, snapshotEdges, subscribe } from "@/lib/data";
import { apply, initial, stateAt, type State } from "@/lib/reduce";
import type { Edge, RunEvent, RunExport } from "@/lib/types";

const SPEEDS = [1, 2, 5, 10];

type SnapEdge = Edge & { holder?: string | null };

/** Live view: graph columns come from the FalkorDB snapshot, everything else from the event stream. */
function withSnapshot(s: State, edges: Edge[] | null): State {
  if (!edges) return s;
  const failures: State["failures"] = {};
  const hyps: State["hyps"] = {};
  for (const e of edges as SnapEdge[]) {
    if (e.origin === "baseline" && s.mode !== "baseline") continue;
    failures[e.failure] ??= {
      id: e.failure, signature: e.signature, visible: true, status: e.failure_status === "open" ? "open" : "fixed",
    };
    const status = (["open", "claimed", "fixed", "dead"].includes(e.status) ? e.status : "open") as State["hyps"][string]["status"];
    hyps[e.hypothesis] = {
      id: e.hypothesis, failure: e.failure, kind: e.kind, origin: e.origin, status,
      holder: e.holder ?? undefined, tau: Number(e.tau), fails: 0, visible: true,
    };
  }
  return { ...s, failures, hyps };
}

function SwarmView() {
  const params = useSearchParams();
  const [runId, setRunId] = useState<string | null>(params.get("run"));
  const live = params.get("live") === "1";
  const [data, setData] = useState<RunExport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // replay
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(!live);
  const [speed, setSpeed] = useState(2);
  const [hideFixed, setHideFixed] = useState(false);

  // live
  const [liveState, setLiveState] = useState<State | null>(null);
  const [writes, setWrites] = useState<number | null>(null);
  const [apiUp, setApiUp] = useState(false);

  useEffect(() => {
    if (runId) return;
    fetchIndex().then((ix) => {
      const latest = [...ix.runs].reverse().find((r) => r.mode !== "baseline") ?? ix.runs.at(-1);
      if (latest) setRunId(latest.run);
      else setError("No recorded runs published yet.");
    });
  }, [runId]);

  useEffect(() => {
    if (!runId || live) return;
    fetchRun(runId).then(setData).catch((e) => setError(String(e)));
  }, [runId, live]);

  // Live: start from an empty state and fold in streamed events.
  useEffect(() => {
    if (!live || !runId) return;
    apiAlive().then(setApiUp);
    let s: State | null = null;
    const pending: RunEvent[] = [];
    const stop = subscribe(
      runId,
      (e) => {
        if (e.type === "seeded") s = initial([], [e], String(params.get("mode") ?? "swarm"));
        if (!s) return void pending.push(e);
        s = apply(structuredClone(s), e);
        setLiveState(s);
      },
      (st) => setWrites(st.writes_per_sec),
    );
    return stop;
  }, [live, runId, params]);

  // Live graph: read straight from FalkorDB via the snapshot endpoint (real pheromone, holders, status).
  const [snap, setSnap] = useState<Edge[] | null>(null);
  useEffect(() => {
    if (!live || !runId) return;
    let alive = true;
    const poll = async () => {
      try {
        const d = await snapshotEdges(runId);
        if (alive) setSnap(d.edges);
      } catch {}
    };
    poll();
    const id = setInterval(poll, 1500);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [live, runId]);

  const duration = useMemo(() => (data ? Math.max(0, ...data.events.map((e) => e.t)) : 0), [data]);
  const mode = String(data?.run.mode ?? "swarm");
  const replayState = useMemo(
    () => (data ? stateAt(data.edges, data.events, mode, playhead) : null),
    [data, mode, playhead],
  );

  const last = useRef<number | null>(null);
  const tick = useCallback(
    (now: number) => {
      if (last.current !== null) setPlayhead((p) => Math.min(duration, p + ((now - last.current!) / 1000) * speed));
      last.current = now;
    },
    [duration, speed],
  );
  useEffect(() => {
    if (!playing || live) return;
    let raf = 0;
    const loop = (now: number) => {
      tick(now);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      last.current = null;
    };
  }, [playing, live, tick]);
  useEffect(() => {
    if (playhead >= duration && duration > 0) setPlaying(false);
  }, [playhead, duration]);

  const s = live && liveState ? withSnapshot(liveState, snap) : replayState;
  if (error) return <p className="mt-10 text-muted">{error}</p>;
  if (!s) return <p className="mt-10 font-mono text-muted">loading run…</p>;

  const agents = Object.values(s.agents).sort((a, b) => a.id.localeCompare(b.id));
  const total = s.green + s.red;

  return (
    <div className="mt-6 grid gap-5 xl:grid-cols-[1fr_380px]">
      <section className="rounded-2xl border border-line bg-panel p-5">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="text-xl font-semibold">Shared graph</h1>
          <div className="flex flex-wrap items-center gap-4 font-mono text-xs text-muted">
            <span>○ failure</span>
            <span>● hypothesis</span>
            <span className="text-amber">━ pheromone (width)</span>
            <span>┄ evaporated / dead</span>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={hideFixed} onChange={(e) => setHideFixed(e.target.checked)} className="accent-amber" />
              hide fixed
            </label>
          </div>
        </div>
        <div className="mb-2 flex justify-between px-1 font-mono text-[11px] tracking-widest text-faint">
          <span className="w-1/4 text-right">FAILURES</span>
          <span className="w-1/3">HYPOTHESES</span>
        </div>
        <div className="max-h-[70vh] overflow-y-auto pr-1">
          <SwarmGraph s={s} hideFixed={hideFixed} />
        </div>
        {!live && (
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <button
              onClick={() => {
                if (playhead >= duration) setPlayhead(0);
                setPlaying((p) => !p);
              }}
              className="rounded-lg bg-panel-2 px-4 py-2 font-mono text-sm hover:text-amber"
              aria-label={playing ? "Pause" : "Play"}
            >
              {playing ? "❚❚" : "▶"}
            </button>
            <span className="text-sm text-muted">Replay of a recorded run</span>
            <input
              type="range" min={0} max={duration} step={0.1} value={playhead}
              onChange={(e) => setPlayhead(Number(e.target.value))}
              className="min-w-40 flex-1 accent-amber" aria-label="Replay position"
            />
            <span className="font-mono text-xs text-muted">{fmt(playhead, 0)}s / {fmt(duration, 0)}s</span>
            <div className="flex gap-1">
              {SPEEDS.map((x) => (
                <button key={x} onClick={() => setSpeed(x)}
                        className={`rounded px-2 py-1 font-mono text-xs ${speed === x ? "bg-amber-dim text-amber" : "text-muted"}`}>
                  {x}×
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      <aside className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <span className="rounded-full border border-line px-3 py-1 text-muted">{String(data?.run.repo ?? runId ?? "")}</span>
          <span className="rounded-full bg-amber-dim px-3 py-1 text-amber">{s.mode} mode</span>
          <span className={live ? "text-amber" : "text-muted"}>● {live ? (apiUp ? "Live" : "connecting") : "Replay"}</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Tests green" value={`${s.green}/${total}`} accent={s.red === 0 && s.stopped} />
          {live ? (
            <Stat label="Graph writes / s" value={fmt(writes, 1)} />
          ) : (
            <Stat label="Attempts" value={fmt(s.attempts)} sub={`${s.merged} merged`} />
          )}
          <Stat label="Wasted attempts" value={fmt(s.wasted)} sub="superseded · duplicate · stale" />
          <Stat label="Tokens used" value={fmt(s.tokens)} />
        </div>

        <div className="rounded-2xl border border-line bg-panel p-4">
          <h2 className="mb-3 font-semibold">Agents</h2>
          <ul className="space-y-2">
            {agents.map((a) => (
              <li key={a.id} className="flex items-center gap-3 text-sm">
                <span className={`w-7 font-mono ${a.status === "killed" ? "text-red" : "text-amber"}`}>{a.id}</span>
                <span className="flex-1 truncate text-muted">
                  {a.status}
                  {a.doing ? ` · ${a.doing}` : ""}
                </span>
                {live && a.status !== "killed" && a.status !== "done" && (
                  <button onClick={() => runId && killAgent(runId, a.id)}
                          className="rounded-md border border-line px-2 py-1 text-xs text-muted hover:border-red hover:text-red">
                    Kill
                  </button>
                )}
              </li>
            ))}
            {!agents.length && <li className="text-sm text-faint">waiting for agents…</li>}
          </ul>
        </div>

        <div className="rounded-2xl border border-line bg-panel p-4">
          <h2 className="mb-3 font-semibold">Graph events</h2>
          <div className="max-h-[38vh] overflow-y-auto">
            <Feed events={s.feed} />
          </div>
        </div>
      </aside>
    </div>
  );
}

export default function SwarmPage() {
  return (
    <Suspense fallback={<p className="mt-10 font-mono text-muted">loading…</p>}>
      <SwarmView />
    </Suspense>
  );
}
