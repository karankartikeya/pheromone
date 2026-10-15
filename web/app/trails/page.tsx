"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { fetchIndex, fetchRun, fmt } from "@/lib/data";
import type { Attempt, RunExport, RunIndex } from "@/lib/types";

const TRAIL_CYPHER = `MATCH p = (t:Test {nodeid:$tid})
  -[:FAILS_WITH]->(:Failure)
  -[:SUSPECTS]->(h:Hypothesis)
  <-[:TESTED]-(a:Attempt)<-[:MADE]-(:Agent)
RETURN p ORDER BY a.at`;

const isMerged = (a: Attempt) => String(a.merged) === "true" || String(a.merged) === "True";
const label = (nodeid: string) =>
  nodeid.endsWith("::__collect__") ? `${nodeid.replace("::__collect__", "")} (import)` : nodeid;

function Diff({ text }: { text: string }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-xl bg-[#0b0c0d] p-4 font-mono text-[12px] leading-relaxed">
      {text.split("\n").filter((l) => !l.startsWith("index ")).map((l, i) => (
        <div key={i} className={l.startsWith("+") && !l.startsWith("+++") ? "text-blue" : l.startsWith("-") && !l.startsWith("---") ? "text-red" : l.startsWith("@@") ? "text-faint" : "text-muted"}>
          {l || " "}
        </div>
      ))}
    </pre>
  );
}

function TrailsView() {
  const params = useSearchParams();
  const [ix, setIx] = useState<RunIndex | null>(null);
  const [runId, setRunId] = useState<string | null>(params.get("run"));
  const [data, setData] = useState<RunExport | null>(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchIndex().then((i) => {
      setIx(i);
      if (!runId) setRunId([...i.runs].reverse().find((r) => r.mode !== "baseline")?.run ?? null);
    });
  }, [runId]);
  useEffect(() => {
    if (runId) fetchRun(runId).then(setData);
  }, [runId]);

  const tests = useMemo(
    () => (data?.tests ?? []).filter((t) => t.failures.length && t.nodeid.toLowerCase().includes(filter.toLowerCase()))
      .sort((a, b) => a.nodeid.localeCompare(b.nodeid)),
    [data, filter],
  );
  useEffect(() => {
    if (!selected && tests.length) setSelected(tests[0].nodeid);
  }, [tests, selected]);

  const trail = useMemo(() => {
    if (!data || !selected) return null;
    const t = data.tests.find((x) => x.nodeid === selected);
    if (!t) return null;
    return t.failures.map((fid) => {
      const hyps = data.edges.filter((e) => e.failure === fid);
      const attempts = data.attempts
        .filter((a) => hyps.some((h) => h.hypothesis === a.hypothesis))
        .sort((a, b) => Number(a.at) - Number(b.at));
      const winner = attempts.find(isMerged);
      return { fid, hyps, attempts, winner, edge: hyps.find((h) => h.hypothesis === winner?.hypothesis) };
    });
  }, [data, selected]);

  const status = (nodeid: string) => data?.tests.find((t) => t.nodeid === nodeid)?.status;

  return (
    <div className="mt-6 space-y-5">
      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <aside className="rounded-2xl border border-line bg-panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Tests</h2>
            <select value={runId ?? ""} onChange={(e) => { setRunId(e.target.value); setSelected(null); }}
                    className="max-w-48 rounded-md border border-line bg-panel-2 px-2 py-1 font-mono text-xs text-muted">
              {ix?.runs.map((r) => <option key={r.run} value={r.run}>{r.run}</option>)}
            </select>
          </div>
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter tests"
                 className="mb-3 w-full rounded-lg border border-line bg-bg px-3 py-2 font-mono text-sm placeholder:text-faint" />
          <ul className="max-h-[60vh] space-y-1 overflow-y-auto">
            {tests.map((t) => {
              const resolved = t.status !== "red";
              return (
                <li key={t.nodeid}>
                  <button onClick={() => setSelected(t.nodeid)}
                          className={`w-full truncate rounded-lg px-3 py-2 text-left font-mono text-[12.5px] ${selected === t.nodeid ? "bg-panel-2 text-text" : "text-muted hover:text-text"}`}>
                    <span className={resolved ? "text-blue" : "text-red"}>{resolved ? "✓" : "✗"}</span> {label(t.nodeid)}
                  </button>
                </li>
              );
            })}
            {!tests.length && <li className="text-sm text-faint">No failing tests recorded.</li>}
          </ul>
        </aside>

        <section className="rounded-2xl border border-line bg-panel p-6">
          <p className="font-mono text-xs tracking-widest text-muted">
            {selected && status(selected) !== "red" ? "WHY IS THIS TEST GREEN" : "WHAT THE SWARM TRIED"}
          </p>
          <h1 className="mt-2 break-all font-mono text-xl">{selected ? label(selected) : "–"}</h1>
          {trail?.map(({ fid, attempts, winner, edge }) => (
            <div key={fid} className="mt-5 space-y-4">
              <div className="flex flex-wrap items-center gap-2 font-mono text-sm">
                <span className="rounded-full border border-line px-3 py-1">Test</span>
                <span className="text-muted">FAILS_WITH →</span>
                <span className="rounded-full border border-line px-3 py-1">{fid.split("@")[0]}</span>
                <span className="text-amber">SUSPECTS →</span>
                <span className={`rounded-full border px-3 py-1 ${edge ? "border-amber text-amber" : "border-line text-muted"}`}>
                  {edge?.kind ?? "no fix merged"}
                </span>
                <span className="text-muted">← TESTED</span>
                <span className="rounded-full border border-line px-3 py-1">{attempts.length} attempts</span>
              </div>
              <ol className="space-y-1.5 border-l border-line pl-4 text-sm">
                {attempts.map((a) => (
                  <li key={a.id} className="flex flex-wrap gap-x-2">
                    <span className={a.outcome === "pass" ? "text-blue" : a.outcome === "superseded" ? "text-faint" : "text-red"}>
                      {a.outcome === "pass" ? "✓" : a.outcome === "superseded" ? "–" : "✗"}
                    </span>
                    <span className="font-mono text-amber">{a.agent}</span>
                    <span className="text-muted">
                      {a.hypothesis.split("#")[1]} · {a.outcome}
                      {Number(a.broken) > 0 ? ` · broke ${a.broken}` : ""} · {fmt(Number(a.tokens))} tokens
                      {isMerged(a) ? " · merged after blast-radius check" : ""}
                    </span>
                  </li>
                ))}
              </ol>
              <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
                {winner?.diff ? <Diff text={winner.diff} /> : <p className="text-sm text-faint">No merged diff for this failure.</p>}
                <div className="space-y-3">
                  <pre className="overflow-auto rounded-xl bg-[#0b0c0d] p-4 font-mono text-[12px] leading-relaxed text-muted">{TRAIL_CYPHER}</pre>
                  <button onClick={() => { navigator.clipboard?.writeText(TRAIL_CYPHER); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
                          className="rounded-lg border border-line px-4 py-2 text-sm hover:text-amber">
                    {copied ? "Copied" : "Copy Cypher"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </section>
      </div>

      <section className="rounded-2xl border border-line bg-panel p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl font-semibold">Recipes</h2>
          <p className="text-sm text-muted">Procedural memory in the shared recipes graph. It outlives every run.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr className="border-b border-line">
                <th className="py-2 pr-4 font-medium">Signature</th>
                <th className="py-2 pr-4 font-medium">Fix kind</th>
                <th className="py-2 pr-4 font-medium">Transform</th>
                <th className="py-2 pr-4 font-medium">Support</th>
                <th className="py-2 font-medium">Learned in</th>
              </tr>
            </thead>
            <tbody>
              {ix?.recipes.map((r) => (
                <tr key={`${r.signature}/${r.kind}`} className="border-b border-line/60 align-top">
                  <td className="py-2.5 pr-4 font-mono text-amber">{r.signature}</td>
                  <td className="py-2.5 pr-4 font-mono">{r.kind}</td>
                  <td className="py-2.5 pr-4 text-muted">{r.transform}</td>
                  <td className={`py-2.5 pr-4 font-mono ${r.support >= 2 ? "" : "text-faint"}`}>{r.support}</td>
                  <td className="py-2.5 font-mono text-xs text-faint">{r.runs.length} run{r.runs.length === 1 ? "" : "s"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default function TrailsPage() {
  return (
    <Suspense fallback={<p className="mt-10 font-mono text-muted">loading…</p>}>
      <TrailsView />
    </Suspense>
  );
}
