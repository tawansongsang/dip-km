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
`pipeline/build_act.py SRC_PDF OUT_DIR --id <id> --title-en "<English title>"`.

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
