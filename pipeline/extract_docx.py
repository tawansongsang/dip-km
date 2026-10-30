"""Extract Thai text and footnotes from a consolidated law in Word (.docx)
format, in the same shape as extract_krisdika.extract().

Word files keep real footnotes (word/footnotes.xml), so no layout guessing is
needed: each non-empty paragraph becomes one paragraph, footnote references
become [^n] at their position, manual line breaks (w:br) are joined the way
extract_krisdika joins wrapped lines, and footnotes are renumbered 1, 2, … in
the order they are referenced. Page numbers come from the page breaks Word saved
when the file was last rendered, so they are approximate.

Usage:
    python pipeline/extract_docx.py raw/x.docx out.md
"""

import re
import sys
import zipfile
import xml.etree.ElementTree as ET

from extract_krisdika import join, normalize

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def runs_text(par, refs=None):
    """Text of one w:p. Footnote references are written as [^n]; `refs` maps
    Word footnote ids to sequential numbers and is extended as ids appear."""
    out, page_breaks = [], 0
    for el in par.iter():
        if el.tag == f"{W}t":
            out.append((el.text or "").replace("\u00a0", " "))
        elif el.tag == f"{W}tab":
            out.append(" ")
        elif el.tag == f"{W}br":
            if el.get(f"{W}type") == "page":
                page_breaks += 1
            else:
                out.append("\x01")  # manual line break, joined below
        elif el.tag == f"{W}lastRenderedPageBreak":
            page_breaks += 1
        elif el.tag == f"{W}footnoteReference" and refs is not None:
            wid = el.get(f"{W}id")
            refs.setdefault(wid, str(len(refs) + 1))
            out.append(f"[^{refs[wid]}]")
    lines = "".join(out).split("\x01")
    text = lines[0]
    for line in lines[1:]:
        text = join(text, line)
    return normalize(text).strip(), page_breaks


def extract(path):
    with zipfile.ZipFile(path) as z:
        body_xml = ET.fromstring(z.read("word/document.xml"))
        try:
            notes_xml = ET.fromstring(z.read("word/footnotes.xml"))
        except KeyError:
            notes_xml = None

    refs, body, page = {}, [], 1
    for par in body_xml.iter(f"{W}p"):
        text, breaks = runs_text(par, refs)
        page += breaks
        if text:
            body.append({"text": text, "page": page, "centered": False})

    raw_notes = {}
    if notes_xml is not None:
        for fn in notes_xml.iter(f"{W}footnote"):
            parts = [runs_text(p)[0] for p in fn.iter(f"{W}p")]
            raw_notes[fn.get(f"{W}id")] = " ".join(p for p in parts if p)
    notes = {n: re.sub(r"\s+", " ", raw_notes.get(wid, "")).strip()
             for wid, n in refs.items()}
    return body, notes


def main(src, dst):
    paragraphs, notes = extract(src)
    with open(dst, "w", encoding="utf-8") as f:
        for p in paragraphs:
            f.write(p["text"] + "\n\n")
        for n, text in notes.items():
            f.write(f"[^{n}]: {text}\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
