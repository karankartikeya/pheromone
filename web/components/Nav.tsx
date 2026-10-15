"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Launch" },
  { href: "/swarm", label: "Live swarm" },
  { href: "/scoreboard", label: "Scoreboard" },
  { href: "/trails", label: "Trails" },
];

export function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M5 19 L12 5 L19 15" stroke="var(--amber)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="5" cy="19" r="2.6" fill="var(--amber)" />
      <circle cx="12" cy="5" r="2.6" fill="var(--amber)" />
      <circle cx="19" cy="15" r="2.6" fill="none" stroke="var(--amber)" strokeWidth="2" />
    </svg>
  );
}

export default function Nav() {
  const path = usePathname();
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-4 px-4 py-3 sm:px-8">
        <Link href="/" className="flex items-center gap-2 font-mono text-lg font-medium">
          <Logo /> pheromone
        </Link>
        <nav className="flex flex-1 justify-center gap-1 overflow-x-auto">
          {TABS.map((t) => {
            const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
            return (
              <Link
                key={t.href}
                href={t.href}
                className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                  active ? "bg-panel-2 text-text" : "text-muted hover:text-text"
                }`}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
        <span className="hidden font-mono text-xs text-faint md:block">FalkorDB · Graph Hacks</span>
      </div>
    </header>
  );
}
