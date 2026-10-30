# pipeline

Turns source documents in `raw/` into knowledge files in `knowledge/`.

## Setup

The project uses [mise](https://mise.jdx.dev): it installs Python, creates and
activates `.venv`, and defines the tasks.

```sh
mise trust && mise install
mise run setup        # install pipeline dependencies
mise tasks            # list all tasks
```

## Acts consolidated by Krisdika (พ.ร.บ. ฉบับรวมแก้ไข)

```sh
mise run build              # rebuild every act
mise run build:tm-act       # rebuild only the Trademark Act
```

To add an act, add a `build:<name>` task to `mise.toml` that calls
`pipeline/build_act.py SRC OUT_DIR --id <id> --title-en "<English title>"`.

SRC may also be a consolidated act in Word (`.docx`) with the amendment notes
as real Word footnotes; `extract_docx.py` reads it into the same paragraphs and
footnotes as a Krisdika PDF. Pass `--consolidated-by "<who>"` when the
consolidation is not Krisdika's (example: `build:copyright`, made by DIP).

Output:

| File | Content |
|---|---|
| `_overview.md` | metadata, amending acts, table of contents by หมวด/ส่วน |
| `sections/sNNN.md` | one file per มาตรา, verbatim text + footnotes (`s028-tawi.md` = มาตรา ๒๘ ทวิ, `s079-1.md` = มาตรา ๗๙/๑) |
| `definitions.md` | มาตรา ๔ split into one heading per term |
| `fees.md` | fee schedule as a table (statutory maximum rates) |
| `history.md` | reasons for enactment and transitional provisions of each amending act |

`extract_krisdika.py` can also be run alone to dump the cleaned full text:

```sh
mise run extract raw/x.pdf /tmp/x.md
```

Krisdika PDFs have a broken text layer (watermark glyphs and shifted Thai
tone marks mapped to ASCII). The extractor repairs it from the font data, so
no OCR is needed. Re-running a build overwrites the generated files; do not
hand-edit them, fix the extractor instead.

## Other laws: Royal Gazette PDFs and Word exports

พระราชกฤษฎีกา, กฎกระทรวง, ระเบียบ and ประกาศ that are not Krisdika
consolidated files go through `build_doc.py`:

```sh
mise run build:travel       # example: travel-expense decree and regulations
mise run extract:pdf raw/x.pdf /tmp/x.md     # dump the cleaned text only
```

```sh
python pipeline/build_doc.py SRC_PDF OUT_DIR --id <id> --title-en "<English title>" \
  --doc-type decree|ministerial-regulation|regulation|notification \
  [--effective-date YYYY-MM-DD] [--consolidated-by "<who>"] [--amends BASE_OUT_DIR]
```

Output:

| File | Content |
|---|---|
| `_overview.md` | metadata, Gazette reference, preamble, table of contents, what this document amends |
| `sections/sNNN.md` | one file per มาตรา or ข้อ (`unit:` says which), verbatim text |
| `definitions.md` | the definitions unit ("ในระเบียบนี้" …) split by term |
| `schedules/bNN.md` | one file per บัญชี; table lines kept as in the PDF, ` \| ` between columns |

`extract_pdf.py` repairs old Thai fonts that put tone marks in the Private Use
Area (U+F700–F71A), Word exports that drop sara am ("ก าหนด"), and removes
Gazette page headers.

Amendments:

- Notes in a consolidated text such as "(มาตรา 6 แก้ไขเพิ่มเติมโดย…)" become
  `amendment_history`; "(มาตรา 19 ยกเลิกโดย…)" marks the section repealed.
- An amending document built with `--amends` records its changes in `amends:`
  and patches the base files: `status: "amended"`, `current_text_in:` and a
  notice linking to the new text. Build the base first, in the same task.

To add a document by chat, use the `km-add` skill (`/km-add`).
