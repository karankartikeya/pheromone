// Shapes of the files written by backend/src/pheromone/export.py and metrics.py.

export type RunEvent = { t: number; type: string; [k: string]: unknown };

export type Edge = {
  failure: string;
  signature: string;
  failure_status: string;
  failure_file?: string;
  hypothesis: string;
  kind: string;
  text?: string;
  status: string;
  origin?: string;
  file?: string;
  tau: number;
};

export type Attempt = {
  id: string;
  agent: string;
  hypothesis: string;
  outcome: string;
  diff: string | null;
  diff_hash: string;
  resolved: number;
  broken: number;
  tokens: number;
  ms: number;
  at: number;
  merged: boolean | string | null;
  commit: string | null;
};

export type TestRow = { nodeid: string; status: string; failures: string[] };

export type RunExport = {
  run: Record<string, unknown> & { id: string; mode?: string; model?: string; repo?: string };
  events: RunEvent[];
  edges: Edge[];
  attempts: Attempt[];
  tests: TestRow[];
};

export type Metrics = {
  run: string;
  mode: string;
  model: string;
  repo?: string;
  workers: number;
  red_at_start: number;
  red_at_end: number;
  green_at_end: number | null;
  seconds_to_green: number | null;
  seconds: number;
  tokens: number;
  attempts: number;
  merged: number;
  superseded: number;
  repeated_diffs: number;
  repeated_dead_ends: number;
  collisions: number;
  proposals: number;
  recipe_hit_rate: number;
  burn_down: [number, number][];
};

export type Recipe = { signature: string; kind: string; transform: string; support: number; runs: string[] };

export type RunIndex = { runs: Metrics[]; recipes: Recipe[]; generated_at: string };
