import type { RunEvent } from "@/lib/types";

const sig = (id: unknown) => String(id ?? "").split("@")[0];
const kind = (id: unknown) => String(id ?? "").split("#")[1] ?? "";

export function describe(e: RunEvent): { text: string; tone: "pass" | "fail" | "amber" | "muted" | "plain" } | null {
  switch (e.type) {
    case "attempt": {
      const o = String(e.outcome);
      if (o === "pass") return { text: `${e.agent} pass · +${Number(e.add).toFixed(1)} on ${sig(e.failure)} → ${kind(e.hypothesis)}`, tone: "pass" };
      if (o === "duplicate") return { text: `${e.agent} duplicate diff · already failed elsewhere · ${sig(e.failure)}`, tone: "muted" };
      if (o === "stale") return { text: `${e.agent} stale report · lease was lost`, tone: "muted" };
      return { text: `${e.agent} ${o} · ×${Number(e.mult).toFixed(1)}τ on ${sig(e.failure)}`, tone: "fail" };
    }
    case "claim":
      return { text: `${e.agent} claims ${sig(e.hypothesis)} → ${kind(e.hypothesis)}`, tone: "plain" };
    case "claim_lost":
      return { text: `${e.agent} claim lost · next candidate`, tone: "muted" };
    case "merged":
      return { text: `merged ${sig(e.hypothesis)} · ${e.green} green / ${e.red} red`, tone: "amber" };
    case "superseded":
      return { text: `${e.agent} superseded · failure already fixed`, tone: "muted" };
    case "merge_rejected":
      return { text: `merge gate rejected ${sig(e.hypothesis)}`, tone: "fail" };
    case "proposed":
      return { text: `${e.agent} proposed ${(e.hypotheses as string[]).length} hypotheses for ${sig(e.failure)}`, tone: "plain" };
    case "lease_expired":
      return { text: `lease expired · ${sig(e.hypothesis)} reopens for handoff`, tone: "amber" };
    case "killed":
      return { text: `${e.agent} killed · its lease is not released`, tone: "fail" };
    case "recipe":
      return { text: `recipe crystallized · ${e.signature} → ${e.kind} (support ${e.support})`, tone: "amber" };
    case "seeded":
      return { text: `seeded ${e.failures} failures, ${e.hypotheses} hypotheses from ${e.red_tests} red tests`, tone: "plain" };
    case "stopped":
      return { text: `stopped · ${e.green} green / ${e.red} red`, tone: "amber" };
    default:
      return null;
  }
}

const TONE = { pass: "text-blue", fail: "text-red", amber: "text-amber", muted: "text-faint", plain: "text-muted" };

export default function Feed({ events }: { events: RunEvent[] }) {
  return (
    <ol className="space-y-1.5 font-mono text-[12.5px] leading-snug">
      {events.map((e, i) => {
        const d = describe(e);
        if (!d) return null;
        return (
          <li key={`${e.t}-${i}`} className={TONE[d.tone]}>
            <span className="mr-2 text-faint">{e.t.toFixed(0).padStart(3, " ")}s</span>
            {d.text}
          </li>
        );
      })}
    </ol>
  );
}
