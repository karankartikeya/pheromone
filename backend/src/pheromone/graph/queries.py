"""Every Cypher query Pheromone runs. The README's query section is generated from this file.

Two FalkorDB facts shape these:
- Each query is atomic and writes to one graph are serialized, but there are no
  multi-query transactions. Coordination steps are therefore single queries
  (compare-and-set), never read-then-write from Python.
- SET/CREATE run on every matched row even if a LIMIT comes later, so no write
  query relies on LIMIT.
"""

# 0. Indexes, run once per graph.
INDEXES = [
    "CREATE INDEX FOR (h:Hypothesis) ON (h.id)",
    "CREATE INDEX FOR (h:Hypothesis) ON (h.status)",
    "CREATE INDEX FOR (h:Hypothesis) ON (h.signature)",
    "CREATE INDEX FOR (f:Failure) ON (f.signature)",
    "CREATE INDEX FOR (f:Failure) ON (f.id)",
    "CREATE INDEX FOR (t:Test) ON (t.nodeid)",
    "CREATE INDEX FOR (f:File) ON (f.path)",
    "CREATE INDEX FOR (a:Agent) ON (a.id)",
    "CREATE INDEX FOR (a:Attempt) ON (a.diff_hash)",
]

RECIPE_INDEXES = [
    "CREATE INDEX FOR (r:Recipe) ON (r.signature)",
    "CREATE INDEX FOR (c:Contribution) ON (c.run)",
]

# 1. Frontier (read-only, every loop). Top 12 by pheromone; the worker scores
#    and picks by roulette in Python. 12, not 5: at start every edge is tau0,
#    and a short list would hand all agents the same candidates. Failures with
#    a passing hypothesis waiting in the merge queue are skipped (if the merge
#    is rejected, the hypothesis reopens and the failure comes back).
FRONTIER = """
MATCH (f:Failure {status:'open'})-[s:SUSPECTS]->(h:Hypothesis {status:'open'})
WHERE NOT (f)-[:SUSPECTS]->(:Hypothesis {status:'fixed'})
OPTIONAL MATCH (h)<-[:TESTED]-(a:Attempt)
OPTIONAL MATCH (h)-[:SAME_SIGNATURE]-(o:Hypothesis {status:'claimed'})
OPTIONAL MATCH (f)-[:SUSPECTS]->(sib:Hypothesis {status:'claimed'})
WITH h, max(s.pheromone) AS tau, count(DISTINCT a) AS tries,
     count(DISTINCT o) AS crowd, count(DISTINCT sib) AS siblings
RETURN h.id AS id, h.text AS text, h.kind AS kind, h.signature AS signature,
       h.file AS file, h.eta AS eta, h.cluster AS cluster, tau, tries, crowd, siblings
ORDER BY tau DESC
LIMIT $limit
"""

# 2. Claim (compare-and-set). Empty result means another agent won.
#    An expired lease counts as open: that is the handoff.
CLAIM = """
MATCH (h:Hypothesis {id:$hid}), (ag:Agent {id:$agent})
WHERE h.status = 'open' OR (h.status = 'claimed' AND h.lease_until < $now)
SET h.status = 'claimed', h.claimed_by = $agent, h.lease_until = $now + $lease_ms
CREATE (ag)-[:CLAIMED {at:$now}]->(h)
RETURN h.id AS id
"""

# 3. Report an attempt and deposit pheromone. Only the deterministic reporter
#    runs this. Guarded so a worker that lost its lease cannot overwrite the new
#    owner. One deposit formula for both outcomes, clamped at tau_min:
#    pass: mult=1, add=+1*fixed -0.5*broken; fail: mult=0.7, add=0.
REPORT = """
MATCH (h:Hypothesis {id:$hid}), (ag:Agent {id:$agent})
WHERE h.status = 'claimed' AND h.claimed_by = $agent
CREATE (ag)-[:MADE]->(a:Attempt {id:$aid, outcome:$outcome, diff_hash:$dh, diff:$diff,
        fixed:$fixed, broken:$broken, ms:$ms, tokens:$tok, at:$now, mode:$mode})-[:TESTED]->(h)
SET h.status = CASE WHEN $outcome = 'pass' THEN 'fixed' ELSE 'open' END,
    h.claimed_by = null
WITH h, a
MATCH (h)<-[s:SUSPECTS]-(:Failure)
SET s.pheromone = CASE WHEN s.pheromone * $mult + $add < $tmin THEN $tmin
                       ELSE s.pheromone * $mult + $add END
RETURN a.id AS id, count(s) AS edges
"""

# 3a. Baseline record (write-only). Baseline agents never read the graph; this
#     keeps their attempts visible to metrics, replay and the merger. No pheromone.
RECORD_BASELINE_ATTEMPT = """
MERGE (ag:Agent {id:$agent})
MERGE (h:Hypothesis {id:$hid})
ON CREATE SET h.kind = $kind, h.text = $text, h.file = $file, h.signature = $sig,
              h.status = 'baseline', h.origin = 'baseline'
WITH ag, h
OPTIONAL MATCH (f:Failure {id:$fid})
FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END | MERGE (f)-[:SUSPECTS]->(h))
CREATE (ag)-[:MADE]->(a:Attempt {id:$aid, outcome:$outcome, diff_hash:$dh, diff:$diff,
        fixed:$fixed, broken:$broken, ms:$ms, tokens:$tok, at:$now, mode:'baseline'})-[:TESTED]->(h)
RETURN a.id AS id
"""

# 3b. Stale report (lease lost): record the Attempt so metrics count it,
#     touch neither status nor pheromone.
REPORT_STALE = """
MATCH (h:Hypothesis {id:$hid}), (ag:Agent {id:$agent})
CREATE (ag)-[:MADE]->(a:Attempt {id:$aid, outcome:'stale', diff_hash:$dh,
        ms:$ms, tokens:$tok, at:$now, mode:$mode})-[:TESTED]->(h)
RETURN a.id AS id
"""

# 3c. Reporter follow-ups: which tests an attempt fixed or broke.
LINK_FIXED = """
MATCH (a:Attempt {id:$aid}), (t:Test) WHERE t.nodeid IN $nodeids
CREATE (a)-[:FIXED]->(t)
"""
LINK_BROKE = """
MATCH (a:Attempt {id:$aid}), (t:Test) WHERE t.nodeid IN $nodeids
CREATE (a)-[:BROKE]->(t)
"""
LINK_FOLLOWED = """
MATCH (p:Attempt {id:$prev}), (n:Attempt {id:$next})
CREATE (p)-[:FOLLOWED]->(n)
"""

# Worker context reads (read-only).
AGENT_HEARTBEAT = """
MERGE (a:Agent {id:$id})
SET a.status = $status, a.doing = $doing, a.last_seen = $now
"""

# Context reads are split into plain-row queries on purpose: one combined query
# (properties + collect() of tests) on a just-claimed hypothesis crashed FalkorDB
# with a panic in reply_compact during the first live run.
HYPOTHESIS_CONTEXT = """
MATCH (f:Failure)-[:SUSPECTS]->(h:Hypothesis {id:$hid})
RETURN f.id AS failure_id, f.signature AS signature, f.message_head AS message,
       h.file AS file, h.text AS text, h.example AS example, h.kind AS kind
"""

FAILURE_TESTS = """
MATCH (t:Test)-[:FAILS_WITH]->(:Failure {id:$fid})
RETURN t.nodeid AS nodeid
"""

# Prior attempts on a hypothesis: the handoff history a new owner inherits.
ATTEMPTS_ON = """
MATCH (ag:Agent)-[:MADE]->(a:Attempt)-[:TESTED]->(h:Hypothesis {id:$hid})
RETURN a.id AS id, ag.id AS agent, a.outcome AS outcome, a.diff AS diff
ORDER BY a.at
"""

GREEN_AMONG = """
MATCH (t:Test) WHERE t.nodeid IN $ids AND t.status = 'green'
RETURN collect(t.nodeid) AS green
"""

# A diff that already failed somewhere is a duplicate: the swarm already knows it is a dead end.
FAILED_DIFF = """
MATCH (a:Attempt {diff_hash:$dh}) WHERE a.outcome <> 'pass' AND a.outcome <> 'stale'
RETURN count(a) AS n
"""

OPEN_WORK = """
MATCH (f:Failure {status:'open'})-[:SUSPECTS]->(h:Hypothesis)
WHERE h.status IN ['open', 'claimed']
RETURN count(DISTINCT f) AS failures, count(DISTINCT h) AS hypotheses
"""

# Proposer: open failures with nothing left to try (no template, or every
# hypothesis already failed 3+ times), capped at $max proposals per failure.
PROPOSAL_NEEDED = """
MATCH (f:Failure {status:'open'})
WHERE coalesce(f.proposals, 0) < $max AND coalesce(f.proposal_lease, 0) < $now
OPTIONAL MATCH (f)-[:SUSPECTS]->(h:Hypothesis)
OPTIONAL MATCH (h)<-[:TESTED]-(a:Attempt)
WITH f, h, count(a) AS tries
WITH f, sum(CASE WHEN h IS NOT NULL AND tries < 3 THEN 1 ELSE 0 END) AS alive
WHERE alive = 0
RETURN f.id AS id
"""

# Compare-and-set on the Failure: one worker proposes for it at a time.
CLAIM_PROPOSAL = """
MATCH (f:Failure {id:$fid})
WHERE coalesce(f.proposal_lease, 0) < $now AND coalesce(f.proposals, 0) < $max
SET f.proposal_lease = $now + $lease_ms, f.proposals = coalesce(f.proposals, 0) + 1
RETURN f.id AS id
"""

# Files a failure could be fixed in: where it surfaced, plus what its test files import.
CANDIDATE_FILES = """
MATCH (f:Failure {id:$fid})-[:IN]->(src:File)
OPTIONAL MATCH (f)<-[:FAILS_WITH]-(:Test)-[:DEFINED_IN]->(:File)-[:IMPORTS]->(dep:File)
RETURN src.path AS src, collect(DISTINCT dep.path) AS deps
"""

ADD_PROPOSED = """
MATCH (f:Failure {id:$fid}), (file:File {path:$file})
MERGE (h:Hypothesis {id:$hid})
ON CREATE SET h.text = $text, h.kind = $kind, h.signature = f.signature, h.file = $file,
              h.status = 'open', h.lease_until = 0, h.eta = 1.0 + coalesce(file.pagerank, 0.0),
              h.origin = 'llm', h.depth = 0, h.proposed_by = $agent
MERGE (f)-[s:SUSPECTS]->(h) ON CREATE SET s.pheromone = $tau0
MERGE (h)-[:TOUCHES]->(file)
RETURN h.id AS id
"""

# Merger: a passing patch that fails the merge gate counts as a failed attempt.
MERGE_REJECTED = """
MATCH (a:Attempt {id:$aid})-[:TESTED]->(h:Hypothesis)<-[s:SUSPECTS]-(:Failure)
SET a.outcome = 'merge_failed', h.status = 'open',
    s.pheromone = CASE WHEN s.pheromone * $mult < $tmin THEN $tmin ELSE s.pheromone * $mult END
RETURN count(s) AS edges
"""

# Another agent's fix closed this failure first: not a dead end, so no decay.
MARK_SUPERSEDED = """
MATCH (a:Attempt {id:$aid})-[:TESTED]->(:Hypothesis)<-[:SUSPECTS]-(f:Failure)
SET a.outcome = 'superseded'
RETURN f.status AS status
"""

FAILURE_OF_ATTEMPT = """
MATCH (:Attempt {id:$aid})-[:TESTED]->(:Hypothesis)<-[:SUSPECTS]-(f:Failure)
RETURN f.status AS status
"""

MARK_MERGED = """
MATCH (a:Attempt {id:$aid}) SET a.merged = true, a.commit = $commit
"""

# After the full-suite rerun: failures no longer present are closed.
CLOSE_FAILURES = """
MATCH (f:Failure {status:'open'}) WHERE NOT f.id IN $open_ids
SET f.status = 'fixed', f.fixed_at = $now
RETURN collect(f.id) AS closed
"""

SUITE_STATUS = """
MATCH (t:Test) WITH t, t.nodeid ENDS WITH '::__collect__' AS pseudo
WHERE NOT pseudo OR t.status = 'red'
RETURN sum(CASE WHEN t.status = 'green' THEN 1 ELSE 0 END) AS green,
       sum(CASE WHEN t.status = 'red' THEN 1 ELSE 0 END) AS red
"""

# 4. Evaporation (every 10 s). MAX-MIN floor keeps every trail explorable.
EVAPORATE = """
MATCH (:Failure)-[s:SUSPECTS]->(:Hypothesis)
SET s.pheromone = CASE WHEN s.pheromone * $keep < $tmin THEN $tmin ELSE s.pheromone * $keep END
RETURN count(s) AS edges
"""

# 4b. Lease release (with evaporation).
RELEASE_LEASES = """
MATCH (h:Hypothesis {status:'claimed'})
WHERE h.lease_until < $now
SET h.status = 'open', h.claimed_by = null
RETURN collect(h.id) AS released
"""

# 5. Blast radius before merge (multi-hop). Tests that must pass before a patch
#    to this file merges. *0.. includes tests defined in the file itself.
BLAST_RADIUS = """
MATCH (f:File {path:$path})<-[:IMPORTS*0..3]-(dep:File)<-[:DEFINED_IN]-(t:Test)
RETURN DISTINCT t.nodeid AS nodeid
"""

# 6. Crystallize (run graph, every 60 s). A (signature, kind) that won in 2+
#    places becomes a Recipe candidate.
CRYSTALLIZE_CANDIDATES = """
MATCH (a:Attempt {outcome:'pass'})-[:TESTED]->(h:Hypothesis)<-[:SUSPECTS]-(f:Failure)
WITH f.signature AS sig, h.kind AS kind, h.text AS text,
     count(DISTINCT h) AS wins, collect(a.diff) AS diffs
WHERE wins >= 2
RETURN sig, kind, text, wins, diffs
"""

# 6b. Upsert into the shared recipes graph. Idempotent: rerunning with the
#     same values changes nothing.
UPSERT_RECIPE = """
MERGE (r:Recipe {signature:$sig, kind:$kind})
ON CREATE SET r.transform = $transform, r.example = $example
MERGE (c:Contribution {run:$run, signature:$sig, kind:$kind})
SET c.wins = $wins
MERGE (c)-[:FOR]->(r)
WITH r
MATCH (r)<-[:FOR]-(c2:Contribution)
WITH r, sum(c2.wins) AS total
SET r.support = total
RETURN r.signature AS signature, r.kind AS kind, r.support AS support
"""

RECIPES_FOR = """
MATCH (r:Recipe) WHERE r.signature IN $sigs
RETURN r.signature AS signature, r.kind AS kind, r.transform AS transform,
       r.example AS example, r.support AS support
"""

# 7. Explain a fix: the trail behind an answer.
TRAIL = """
MATCH p = (t:Test {nodeid:$tid})-[:FAILS_WITH]->(:Failure)-[:SUSPECTS]->(h:Hypothesis)<-[:TESTED]-(a:Attempt)<-[:MADE]-(:Agent)
RETURN p ORDER BY a.at
"""

# 8. Graph algorithms as agent tools.
PAGERANK = """
CALL algo.pageRank('File', 'IMPORTS') YIELD node, score
SET node.pagerank = score
RETURN node.path AS path, score ORDER BY score DESC
"""

WCC = """
CALL algo.WCC({nodeLabels:['Failure','File'], relationshipTypes:['IN']}) YIELD node, componentId
RETURN componentId, collect(node) AS members
"""
