# Ask the swarm's memory over MCP

Any MCP client can query Pheromone's graphs through the official [FalkorDB MCP server](https://docs.falkordb.com/genai-tools/mcpserver). The repo ships a read-only setup for Claude Code:

- [`.mcp.json`](../.mcp.json) starts `@falkordb/mcpserver@1.3.0` against the local FalkorDB (`localhost:6380`) with `FALKORDB_DEFAULT_READONLY` and `FALKORDB_STRICT_READONLY` set.
- [`.claude/settings.json`](../.claude/settings.json) allows the read-only tools (`query_graph_readonly`, `list_graphs`, schema tools) and denies `delete_graph` and the read-write `query_graph`, so a careless prompt can't change a recorded run.

Start FalkorDB (`docker compose up -d`), open Claude Code in the repo, approve the `pheromone-graph` server once, then ask questions like these:

- "List the Pheromone run graphs, then tell me why `robusta_krr/core/runner.py` changed in `run:krr-swarm-1015-185816`: which failures, which fixes, which agents, which commits."
- "In that run, which hypotheses were tried and failed before a fix won, and did any agent take over work after another agent's lease expired?"
- "Before the fix to `robusta_krr/formatters/json.py` merged, which tests did its blast radius include, and through which import chain?"
- "Which Recipes in the `recipes` graph have the most support, and which runs contributed to them?"

The agent picks the tools itself (schema discovery, then read-only Cypher), so the answer comes straight from the graph the swarm wrote.

Verified with a direct stdio session: the read-only tool answers the runner.py question (A2 merged `dict-call → model-dump` and `json-call → model-dump-json`), and a `CREATE` through it is rejected (`graph.RO_QUERY is to be executed only on read-only queries`).

Note: in our test the MCP Inspector CLI did not pass the connection settings through to the server it spawned (neither from the shell nor with `-e`), and the server fell back to `localhost:6379`. Clients that set `env` in their config, like Claude Code with `.mcp.json`, and a direct stdio session both work.
