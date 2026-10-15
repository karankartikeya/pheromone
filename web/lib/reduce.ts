// One reducer for live (SSE) and replay: the dashboard's state is a pure
// function of the recorded event stream, so a replay shows exactly what ran.

import type { Edge, RunEvent } from "./types";

export const TAU0 = 0.5;
export const TAU_MIN = 0.05;
const MAX_FAILS = 3;

export type Hyp = {
  id: string;
  failure: string;
  kind: string;
  origin?: string;
  status: "open" | "claimed" | "fixed" | "dead";
  holder?: string;
  tau: number;
  fails: number;
  visible: boolean;
};

export type Fail = { id: string; signature: string; status: "open" | "fixed"; visible: boolean };
export type Agent = { id: string; status: string; doing: string };

export type State = {
  t: number;
  mode: string;
  failures: Record<string, Fail>;
  hyps: Record<string, Hyp>;
  agents: Record<string, Agent>;
  feed: RunEvent[];
  green: number;
  red: number;
  tokens: number;
  attempts: number;
  wasted: number;
  merged: number;
  stopped: boolean;
};

/** Initial state from the run's final edge list; hypotheses appear when events reveal them. */
export function initial(edges: Edge[], events: RunEvent[], mode: string): State {
  const revealed = new Set<string>();
  const proposed = new Set<string>();
  for (const e of events) {
    if (e.type === "merged") (e.revealed as string[] | undefined)?.forEach((f) => revealed.add(f));
    if (e.type === "proposed") (e.hypotheses as string[] | undefined)?.forEach((h) => proposed.add(h));
  }
  const failures: Record<string, Fail> = {};
  const hyps: Record<string, Hyp> = {};
  for (const e of edges) {
    if (e.origin === "baseline" && mode !== "baseline") continue;
    failures[e.failure] ??= { id: e.failure, signature: e.signature, status: "open", visible: !revealed.has(e.failure) };
    hyps[e.hypothesis] = {
      id: e.hypothesis, failure: e.failure, kind: e.kind, origin: e.origin, status: "open", tau: TAU0, fails: 0,
      visible: !revealed.has(e.failure) && !proposed.has(e.hypothesis),
    };
  }
  const seeded = events.find((e) => e.type === "seeded");
  const tests = Number(seeded?.tests ?? 0);
  const red = Number(seeded?.red_tests ?? 0);
  return {
    t: 0, mode, failures, hyps, agents: {}, feed: [], green: Math.max(0, tests - red), red,
    tokens: 0, attempts: 0, wasted: 0, merged: 0, stopped: false,
  };
}

export function apply(s: State, e: RunEvent): State {
  s.t = e.t;
  const hyp = (id: unknown) => s.hyps[String(id)];
  switch (e.type) {
    case "agent":
      s.agents[String(e.agent)] = { id: String(e.agent), status: String(e.status), doing: String(e.doing ?? "") };
      return s;
    case "claim": {
      const h = hyp(e.hypothesis);
      if (h) Object.assign(h, { status: "claimed", holder: String(e.agent), visible: true });
      break;
    }
    case "attempt": {
      s.attempts += 1;
      s.tokens += Number(e.tokens ?? 0);
      const h = hyp(e.hypothesis);
      if (["duplicate", "stale"].includes(String(e.outcome))) s.wasted += 1;
      if (h && e.outcome !== "stale") {
        h.holder = undefined;
        if (s.mode !== "baseline") h.tau = Math.max(TAU_MIN, h.tau * Number(e.mult ?? 1) + Number(e.add ?? 0));
        if (e.outcome === "pass") h.status = "fixed";
        else {
          h.fails += 1;
          h.status = h.fails >= MAX_FAILS ? "dead" : "open";
        }
      }
      break;
    }
    case "superseded":
      s.wasted += 1;
      break;
    case "merge_rejected": {
      const h = hyp(e.hypothesis);
      if (h) h.status = "open";
      break;
    }
    case "merged":
      s.merged += 1;
      s.green = Number(e.green);
      s.red = Number(e.red);
      (e.closed as string[] | undefined)?.forEach((f) => s.failures[f] && (s.failures[f].status = "fixed"));
      (e.revealed as string[] | undefined)?.forEach((fid) => {
        if (s.failures[fid]) s.failures[fid].visible = true;
        Object.values(s.hyps).forEach((h) => h.failure === fid && (h.visible = true));
      });
      break;
    case "proposed":
      s.tokens += Number(e.tokens ?? 0);
      (e.hypotheses as string[] | undefined)?.forEach((id) => s.hyps[id] && (s.hyps[id].visible = true));
      break;
    case "lease_expired": {
      const h = hyp(e.hypothesis);
      if (h && h.status === "claimed") Object.assign(h, { status: "open", holder: undefined });
      break;
    }
    case "evaporation":
      if (s.mode !== "baseline")
        Object.values(s.hyps).forEach((h) => (h.tau = Math.max(TAU_MIN, h.tau * Number(e.keep ?? 0.95))));
      return s;
    case "killed":
      s.agents[String(e.agent)] = { id: String(e.agent), status: "killed", doing: "" };
      break;
    case "stopped":
      s.stopped = true;
      s.green = Number(e.green ?? s.green);
      s.red = Number(e.red ?? s.red);
      break;
  }
  s.feed = [e, ...s.feed].slice(0, 60);
  return s;
}

export function stateAt(edges: Edge[], events: RunEvent[], mode: string, t: number): State {
  let s = initial(edges, events, mode);
  for (const e of events) {
    if (e.t > t) break;
    s = apply(s, e);
  }
  return s;
}
