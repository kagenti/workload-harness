# Kagenti Workload Harness

## Overview

Workload harnesses for driving test and evaluation traffic to Kagenti agents.
Currently includes the AppWorld harness as the first supported workload driver,
designed to expand to additional drivers over time.

## Repository Structure

```
workload-harness/
├── appworld_a2a_runner/          # AppWorld A2A workload driver
│   ├── appworld_a2a_runner/      # Python package
│   │   ├── runner.py             # Main runner entrypoint
│   │   ├── config.py             # Configuration
│   │   ├── a2a_client.py         # A2A protocol client
│   │   ├── appworld_adapter.py   # AppWorld integration
│   │   ├── prompt.py             # Prompt handling
│   │   └── otel.py               # OpenTelemetry instrumentation
│   └── pyproject.toml            # Package dependencies
├── pyproject.toml                # Root lint config (ruff)
└── example.env                   # Environment variable template
```

## Key Commands

| Task | Command |
|------|---------|
| Lint | `make lint` |
| Format | `make fmt` |
| Test | `cd appworld_a2a_runner && pytest` |
| Run | `appworld-a2a-runner` (after install) |
| Install | `cd appworld_a2a_runner && pip install -e .` |

## Code Style

- Python 3.11+ with ruff (lint + format)
- Pre-commit hooks: `pre-commit install`
- Line length: 120

## DCO Sign-Off

All commits must include a `Signed-off-by` trailer:

```sh
git commit -s -m "feat: add new feature"
```

## Commit Attribution

Use `Assisted-By` for AI attribution (not `Co-Authored-By`):

    Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>

## Orchestration

This repo includes orchestrate skills for enhancing related repos:

| Skill | Description |
|-------|-------------|
| `orchestrate` | Run `/orchestrate <repo-url>` to start |
| `orchestrate:scan` | Assess repo structure and gaps |
| `orchestrate:plan` | Create phased enhancement plan |
| `orchestrate:precommit` | Add pre-commit hooks and linting |
| `orchestrate:tests` | Add test infrastructure and coverage |
| `orchestrate:ci` | Add CI workflows and security scanning |
| `orchestrate:security` | Add governance files |
| `orchestrate:review` | Review orchestration PRs before merge |
| `orchestrate:replicate` | Bootstrap skills into target repo |
| `skills:scan` | Discover and audit skills |
| `skills:write` | Author new skills |
| `skills:validate` | Validate skill format |
