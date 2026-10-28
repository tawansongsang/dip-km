# dip-km

Knowledge base of the Department of Intellectual Property (DIP), Thailand,
built for AI agents (Claude Code, Codex, Claude Desktop, Codex desktop) to
answer questions from DIP staff and the public.

- `knowledge/` — the knowledge base; start at `knowledge/INDEX.md`
- `raw/` — original source documents
- `pipeline/` — scripts that turn `raw/` into `knowledge/` (see `pipeline/README.md`)
- `evals/` — test questions with known answers (see `evals/README.md`)
- `templates/` — starting points for team folders, documents and skills
- `CUSTOMIZE.md` — how staff add team or personal knowledge and skills
- `AGENTS.md` — rules for agents (`CLAUDE.md` imports it)
- `.agents/skills/` — skills, e.g. `dip-answer`; `.claude/skills/` is a copy kept
  in sync with `mise run skills:sync` (copies, not symlinks, so Windows works)

## Setup

```sh
mise trust && mise install
mise run setup
mise run build
```
