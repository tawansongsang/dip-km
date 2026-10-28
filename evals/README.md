# evals

Questions with known answers, used to check that agents answer correctly from
`knowledge/` — and to catch regressions when the knowledge base, `AGENTS.md` or
the `dip-answer` skill change.

```sh
mise run eval -- --agent claude                 # Claude Code (claude -p)
mise run eval -- --agent codex                  # Codex (codex exec, read-only sandbox)
mise run eval -- --agent claude --only tm-term,nf-patent-term
mise run eval:grade evals/results/<run-dir>     # regrade saved answers, no agent calls
```

Each run writes `evals/results/<timestamp>-<agent>/` (git-ignored):
`summary.md` (pass/fail table), `results.json`, and one `<id>.md` per answer.

## What is checked

Grading is deterministic, per question in `questions.yaml`:

- **Citations:** the answer cites at least one มาตรา, and every
  `expect_sections` entry (Thai or Arabic digits, lists and ranges like
  `มาตรา 53–56` are understood).
- **Facts:** each `must_include` fact appears in at least one accepted spelling.
- **Wrong answers:** no `must_not_include` phrase appears.
- **Gaps:** for `expect_not_found` questions the agent must say the knowledge
  base has no answer, and must not answer from memory.

Checks can be wrong too. Read every failed answer before deciding whether to
fix the knowledge base, the instructions, or the question.

## Adding questions

Add real questions from the call center or staff, phrased the way people ask
them. Take expected facts from the source file, not from memory, and put the
file in `source:`. When a new document type arrives (กฎกระทรวง, FAQ …), add
questions that need it — and questions where it conflicts with a higher
source.
