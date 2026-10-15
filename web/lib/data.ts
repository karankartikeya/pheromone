import type { RunEvent, RunExport, RunIndex } from "./types";

// Live mode talks to the Control API; the deployed dashboard replays static files.
export const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function fetchIndex(): Promise<RunIndex> {
  const r = await fetch("/runs/index.json", { cache: "no-store" });
  if (!r.ok) return { runs: [], recipes: [], generated_at: "" };
  return r.json();
}

export async function fetchRun(id: string): Promise<RunExport> {
  const r = await fetch(`/runs/${id}.json`, { cache: "no-store" });
  if (!r.ok) throw new Error(`run ${id} not found`);
  return r.json();
}

export async function apiAlive(): Promise<boolean> {
  if (!API) return false;
  try {
    const r = await fetch(`${API}/runs`, { cache: "no-store" });
    return r.ok;
  } catch {
    return false;
  }
}

export function subscribe(runId: string, onEvent: (e: RunEvent) => void, onStats: (s: { writes_per_sec: number }) => void) {
  const es = new EventSource(`${API}/runs/${runId}/events`);
  es.onmessage = (m) => onEvent(JSON.parse(m.data));
  es.addEventListener("stats", (m) => onStats(JSON.parse((m as MessageEvent).data)));
  return () => es.close();
}

export async function snapshotEdges(runId: string) {
  const r = await fetch(`${API}/runs/${runId}/snapshot`, { cache: "no-store" });
  return r.json();
}

export async function killAgent(runId: string, agent: string) {
  await fetch(`${API}/runs/${runId}/agents/${agent}/kill`, { method: "POST" });
}

export const shortFile = (p: string) => p.split("/").pop() ?? p;
export const fmt = (n: number | null | undefined, d = 0) =>
  n === null || n === undefined || Number.isNaN(n) ? "–" : n.toLocaleString("en-US", { maximumFractionDigits: d });
