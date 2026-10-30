---
name: km-add
description: Add new knowledge to the DIP knowledge base — a พ.ร.บ., พระราชกฤษฎีกา, กฎกระทรวง, ระเบียบ, ประกาศ, คู่มือ or FAQ — from files dropped in tmp/ (PDF, DOCX, TXT, MD) or from text pasted in chat. Files the source in raw/, generates or writes the knowledge files, checks the text, and updates INDEX, glossary and AGENTS. Use for "/km-add", "เพิ่มกฎหมายใหม่ใน tmp เข้าฐานความรู้", "เพิ่มประกาศนี้เข้า km: <ข้อความ>", "add this regulation to the knowledge base".
---

# Adding knowledge to the knowledge base

> Owner: ทีม KM. Changes here are in the shared layer: they go on a branch and
> are reviewed before merging. The rules in `AGENTS.md` still apply: never edit
> `raw/` files, never hand-edit generated files (`knowledge/**/<doc>/sections`,
> `schedules`, `_overview.md` …), and take every title, date and number from
> the document itself, never from memory.

## 0. Inputs and branch

- Text after the command, or pasted in the message → **text mode** (step 3b).
- Otherwise list `tmp/` (`ls -la tmp/`). Supported: `.pdf`, `.docx`, `.txt`,
  `.md`. If `tmp/` is empty and no text was given, ask for the file or text.
- If the current branch is `main`, create `km/<short-slug>` first. Never commit
  unless the user asks.

## 1. Identify each document

For each PDF, dump the text to the scratchpad and read the first page:

```sh
mise run extract:pdf "tmp/<file>.pdf" <scratchpad>/<n>.md     # Royal Gazette / Word export
mise run extract "tmp/<file>.pdf" <scratchpad>/<n>.md         # Krisdika consolidated act
```

A Krisdika consolidated act has "สำนักงานคณะกรรมการกฤษฎีกา" in the page
header and numbered footnotes. Everything else uses `extract:pdf`. For DOCX,
dump it with `mise exec -- python pipeline/extract_docx.py "tmp/<file>.docx" <scratchpad>/<n>.md`
(keeps Word footnotes as `[^n]`),
or ask for a PDF export if the layout matters (tables, schedules).

Work out, from the text:

| Field | Where it comes from |
|---|---|
| Title (Thai) | the quoted name in มาตรา/ข้อ ๑ ("…เรียกว่า “…”") |
| Type | พระราชบัญญัติ / พระราชกฤษฎีกา / กฎกระทรวง / ระเบียบ / ประกาศ / คู่มือ / FAQ |
| Unit | มาตรา or ข้อ |
| Gazette & effective date | page header (เล่ม … ตอน … วันที่) and มาตรา/ข้อ ๒ |
| Amends | "ให้ยกเลิกความใน… แห่ง…" / "ให้เพิ่มความต่อไปนี้…" → which document; is that document already in `knowledge/`? |
| Consolidated? | "(แก้ไขเพิ่มเติมถึงฉบับที่ …)" and who made it |
| Area | an existing `knowledge/public/<area>/`, or a new one (IP areas: trademark, patent, copyright, gi; others by subject, e.g. travel-expenses) |
| Layer | published law → `public`; staff-only circulars/manuals → `internal`; a team's own material → use the team flow in `CUSTOMIZE.md` instead |

Then show the user **one** summary table (file → title, type, area, folder,
law id, effective date, amends) and wait for a yes before writing anything.
Ask only for what the document cannot tell you (e.g. which area for a
non-IP subject, layer for an unpublished document).

Naming: folder `<kind>-<year>` (`act-2534`, `decree-2526`, `reg-2550`,
`reg-2550-no2-2554`, `mr-2563` for กฎกระทรวง, `notice-2565` for ประกาศ);
law id `<area-prefix>-<folder>` (`tm-act-2534`, `travel-reg-2550`).
Raw file: ASCII, e.g. `raw/<area>/mof_reg_travel_2550.pdf`.

## 2. File the source

Copy (do not move) each source into `raw/<area>/<ascii-name>`. Never overwrite
an existing file in `raw/`; if the name is taken, stop and ask.

## 3a. Generate from a PDF

Add a `build:<area>` task to `mise.toml` (or extend the area's task) and run
it. Copy the pattern of `build:tm-act` / `build:travel`:

- Krisdika consolidated act → `pipeline/build_act.py SRC OUT --id … --title-en …`
  - the same for a consolidated พ.ร.บ. in Word (`.docx`, footnotes "มาตรา … แก้ไขเพิ่มเติมโดย…"),
    with `--consolidated-by "…"` when it was not made by Krisdika (see `build:copyright`)
- Any other law → `pipeline/build_doc.py SRC OUT --id … --doc-type decree|ministerial-regulation|regulation|notification --title-en … --effective-date YYYY-MM-DD`
  - consolidated by someone other than Krisdika → `--consolidated-by "…"`
  - an amending document → `--amends <base OUT>`; build it **after** the base
    in the same task. It marks changed ข้อ/บัญชี in the base as
    `status: "amended"` with `current_text_in`.
  - `--audience internal` and an `internal/` OUT folder for staff-only content.

The task must start with `rm -rf` of its own output folders so a rebuild is
clean. Run `mise run build` at the end: the other areas must not change
(`git status --short knowledge/` shows only your folders and hand-edited files).

## 3b. Write from text (pasted text, DOCX, or anything the pipeline cannot split)

1. Save the input verbatim to `raw/<area>/<slug>.md` (pasted text) — this is
   the source of record. Add nothing to it except a first line
   `<!-- source: pasted by user in chat, YYYY-MM-DD -->`.
2. Write `knowledge/<layer>/<area>/<slug>.md` by hand, starting from
   `templates/team/document.md`. Frontmatter: `id`, `type` (law-text,
   team-guide, faq …), `audience`, `source: raw/…`, `effective_date`,
   `based_on`, `last_reviewed` (today). Keep legal wording verbatim; split by
   มาตรา/ข้อ with `## ข้อ ๕ (ข้อ 5)` headings so citations are easy.

## 4. Check the result

Fix problems in `pipeline/`, never in the generated files, then rebuild.

```sh
grep -rlP '[\x{F700}-\x{F71F}\x{0E4D}]' <out>               # broken Thai glyphs: must be empty
grep -rhoP '[ก-ฮ] า' <out> | sort | uniq -c | head          # lost sara am ("ก าหนด")
grep -rhoP '[ก-ฮ][A-Za-z0-9]{1,2}[ก-ฮ]' <out> | sort | uniq -c   # ASCII inside Thai words
ls <out>/sections | wc -l                                    # vs. the last มาตรา/ข้อ number
grep -l '"repealed"\|"amended"' -r <out>                    # do these match the notes in the text?
```

Then read `_overview.md` (headings, schedules, amendment list) and 3–5
section files side by side with the PDF, including one table (`schedules/`)
and one amended or repealed section. Tell the user about anything you could
not fix (e.g. a typo in the source, a table that needs checking).

## 5. Wire it into the knowledge base

- Area `INDEX.md`: create or update — documents table (type, status, link),
  warnings ("ข้อควรรู้": consolidated by whom, amended parts, newest amendment
  included), and a topic map (question type → มาตรา/ข้อ/บัญชี). Build the topic
  map from the section files you read; every row must point to text that is
  really there.
- `knowledge/INDEX.md`: add or update the area's row.
- `knowledge/glossary.md`: add new terms (TH ↔ EN) used in the document.
- `AGENTS.md` / `dip-answer`: only if something new is needed (a new document
  type in the order of authority, a new kind of status). Then run
  `mise run skills:sync`.
- `evals/questions.yaml`: add 1–3 questions whose answers are in the new
  files, with `expect_sections` and `source`.

## 6. Report

Reply in the user's language with: what was added (table: document → folder,
number of sections/schedules), what was amended or marked repealed, quality
notes and what a person should check, files changed, branch name. Leave
`tmp/` as it is and say the files can be deleted from there. Offer to commit.

## Example

Request: `/km-add` with `tmp/ค่าเดินทางไปราชการ 2550.pdf` and its (ฉบับที่ 2) พ.ศ. 2554.

Result: `raw/travel-expenses/mof_reg_travel_2550.pdf`, `…_no2_2554.pdf`;
`build:travel` task; `knowledge/public/travel-expenses/reg-2550/` (26 ข้อ,
10 บัญชี) and `reg-2550-no2-2554/` (9 ข้อ, 6 บัญชี) where ข้อ 8, 9, 17, 18 and
บัญชี 2, 3, 6, 7, 8, 10 of the 2550 regulation are marked amended;
`travel-expenses/INDEX.md` with topic map; INDEX and glossary rows.
