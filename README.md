# dip-km

Knowledge base of the Department of Intellectual Property (DIP), Thailand,
built for AI agents (Claude Code, Codex, Claude Desktop, Codex desktop) to
answer questions from DIP staff and the public.

- `knowledge/` — the knowledge base; start at `knowledge/INDEX.md`
- `raw/` — original source documents
- `pipeline/` — scripts that turn `raw/` into `knowledge/` (see `pipeline/README.md`)
- `evals/` — test questions with known answers (see `evals/README.md`)
- `AGENTS.md` — rules for agents (`CLAUDE.md` imports it)
- `.agents/skills/dip-answer/` — answering workflow (linked from `.claude/skills/`)

## Setup

```sh
mise trust && mise install
mise run setup
mise run build
```
