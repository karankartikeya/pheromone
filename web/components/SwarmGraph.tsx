"use client";

import { shortFile } from "@/lib/data";
import { TAU0, TAU_MIN, type State } from "@/lib/reduce";

const ROW = 26;
const LEFT = 250;
const RIGHT = 640;
const W = 1000;

/** Two columns: failures left, hypotheses right; edge width is pheromone. */
export default function SwarmGraph({ s, hideFixed }: { s: State; hideFixed: boolean }) {
  const failures = Object.values(s.failures)
    .filter((f) => f.visible && (!hideFixed || f.status === "open"))
    .sort((a, b) => (a.status === b.status ? a.id.localeCompare(b.id) : a.status === "open" ? -1 : 1));

  const blocks: { f: (typeof failures)[number]; hyps: State["hyps"][string][]; y0: number }[] = [];
  let y = 12;
  for (const f of failures) {
    let hyps = Object.values(s.hyps).filter((h) => h.failure === f.id && h.visible);
    if (f.status === "fixed") hyps = hyps.filter((h) => h.status === "fixed").slice(0, 1);
    if (!hyps.length) continue;
    blocks.push({ f, hyps, y0: y });
    y += hyps.length * ROW + 10;
  }
  const height = Math.max(y, 120);

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img" aria-label="Failures and hypotheses graph">
      {blocks.map(({ f, hyps, y0 }) => {
        const fy = y0 + (hyps.length * ROW) / 2;
        const done = f.status === "fixed";
        return (
          <g key={f.id} opacity={done ? 0.35 : 1}>
            <text x={LEFT - 16} y={fy + 4} textAnchor="end" className="fill-[var(--text)] font-mono" fontSize="12">
              {f.id.split("@")[0]}
            </text>
            <text x={LEFT - 16} y={fy + 17} textAnchor="end" className="fill-[var(--faint)] font-mono" fontSize="9.5">
              {shortFile(f.id.split("@")[1] ?? "")}
            </text>
            <circle cx={LEFT} cy={fy} r={6} fill="var(--bg)" stroke={done ? "var(--faint)" : "var(--text)"} strokeWidth={1.6} />
            {hyps.map((h, i) => {
              const hy = y0 + i * ROW + ROW / 2;
              const width = s.mode === "baseline" ? 1 : Math.min(10, 1 + (h.tau - TAU_MIN) * 3);
              const strong = h.tau >= TAU0 * 0.9 || h.status === "fixed";
              const faded = h.status === "dead" || (s.mode !== "baseline" && h.tau <= TAU_MIN * 1.6);
              const stroke = faded ? "var(--faint)" : strong ? "var(--amber)" : "var(--amber-dim)";
              const path = `M ${LEFT} ${fy} C ${(LEFT + RIGHT) / 2} ${fy}, ${(LEFT + RIGHT) / 2} ${hy}, ${RIGHT} ${hy}`;
              const chipX = LEFT + (RIGHT - LEFT) * 0.8;
              return (
                <g key={h.id}>
                  <path d={path} fill="none" stroke={stroke} strokeWidth={width} strokeDasharray={faded ? "4 4" : undefined}
                        style={{ transition: "stroke-width 300ms ease" }} />
                  <circle cx={RIGHT} cy={hy} r={5.5}
                          fill={h.status === "fixed" ? "var(--amber)" : "var(--bg)"}
                          stroke={faded ? "var(--faint)" : "var(--amber)"} strokeWidth={1.6} />
                  <text x={RIGHT + 14} y={hy + 4} fontSize="11.5"
                        className={`font-mono ${faded ? "fill-[var(--faint)]" : "fill-[var(--text)]"}`}>
                    {h.kind}
                    {h.origin === "recipe" ? "  ◆ recipe" : h.origin === "llm" ? "  · proposed" : ""}
                  </text>
                  {h.holder && (
                    <g transform={`translate(${chipX - 18} ${hy - 10})`}>
                      <rect width="36" height="20" rx="10" fill="var(--bg)"
                            stroke={s.agents[h.holder]?.status === "killed" ? "var(--red)" : "var(--amber)"}
                            strokeDasharray={s.agents[h.holder]?.status === "killed" ? "3 3" : undefined} />
                      <text x="18" y="14" textAnchor="middle" fontSize="11" className="fill-[var(--amber)] font-mono">
                        {h.holder}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}
