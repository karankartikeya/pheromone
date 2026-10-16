import type { Blast } from "@/lib/types";

const BLAST_CYPHER = `MATCH p = (f:File {path:$path})<-[:IMPORTS*0..3]-(dep:File)
WHERE (dep)<-[:DEFINED_IN]-(:Test)
RETURN [n IN nodes(p) | n.path] AS chain`;

/** Merge-gate evidence: which import chains the graph walked, and which tests that selected. */
export default function BlastRadius({ file, blast }: { file: string; blast?: Blast }) {
  if (!blast) return null;
  // shortest chain to each test file is the one worth reading
  const byTest = new Map<string, string[]>();
  for (const c of blast.chains) {
    const end = c[c.length - 1];
    if (!byTest.has(end) || byTest.get(end)!.length > c.length) byTest.set(end, c);
  }
  const rows = [...byTest.entries()].sort((a, b) => (blast.tests[b[0]] ?? 0) - (blast.tests[a[0]] ?? 0));
  const total = Object.values(blast.tests).reduce((a, b) => a + b, 0);
  return (
    <div className="rounded-xl border border-line bg-panel-2 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          Merge gate · blast radius <span className="font-normal text-muted">of {file}</span>
        </h3>
        <span className="font-mono text-xs text-amber">{total} tests in its blast radius</span>
      </div>
      <ul className="space-y-1.5 font-mono text-[12px]">
        {rows.map(([testFile, chain]) => (
          <li key={testFile} className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            {chain.map((p, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-faint">←</span>}
                <span className={i === 0 ? "text-amber" : i === chain.length - 1 ? "text-blue" : "text-muted"}>
                  {p.split("/").slice(-2).join("/")}
                </span>
              </span>
            ))}
            <span className="ml-1 text-faint">· {blast.tests[testFile] ?? 0} tests · {chain.length - 1} hop{chain.length === 2 ? "" : "s"}</span>
          </li>
        ))}
      </ul>
      <pre className="mt-3 overflow-auto rounded-lg bg-[#0b0c0d] p-3 font-mono text-[11px] text-faint">{BLAST_CYPHER}</pre>
    </div>
  );
}
