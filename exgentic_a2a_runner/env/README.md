# Vendored env templates

These `.env` files are the authoritative source of environment-variable
templates used by `deploy-benchmark.sh` and `deploy-agent.sh` when they deploy
MCP tools and A2A agents to the Rossoctl API.

- `mcp/exgentic_benchmarks/.env.<benchmark>` — per-benchmark MCP tool env
  (referenced as `--benchmark <name>`).
- `a2a/exgentic_agent/.env.example` — base agent env used by every agent
  deploy.
- `a2a/exgentic_agent/.env.advanced` — vendored for parity with upstream; not
  currently referenced by any script.

These were copied verbatim from
`github.com/yoavkatz/agent-examples` branch `feature/exgentic-mcp-server`.
Edit them in place and commit — the deploy scripts read from disk, not from
GitHub.
