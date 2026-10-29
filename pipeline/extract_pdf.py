"""Extract clean Thai text from a law PDF that is NOT a Krisdika consolidated
file: Royal Gazette (ราชกิจจานุเบกษา) PDFs and Word exports of a law.

Repairs the text-layer problems these files have:
  * old Thai fonts (AngsanaUPC, EucrosiaUPC …) that put tone marks and
    vowels at Private Use Area code points U+F700–U+F71A
  * Word exports whose sara am glyph has no Unicode mapping and comes out
    as a space: "ก าหนด" -> "กำหนด"
  * sara am written as nikhahit + sara aa ("ํา")
  * page headers ("หน้า ๑", "เล่ม ๑๒๔ ตอนพิเศษ ๙๑ ง", "~ ๑ ~")

Paragraphs are rebuilt from layout: a line indented past the left margin,
a centred line, or a line after a blank gap starts a new paragraph. Each
paragraph also keeps its original lines, with " | " between text that sits
in separate columns on the same baseline, so tables (บัญชี) can be shown
line by line instead of as run-on text.

Usage:
    python pipeline/extract_pdf.py SRC_PDF OUT.md
"""

import re
import sys
from collections import Counter

import pymupdf

from extract_krisdika import normalize

# Thai positional glyphs in the Private Use Area (Windows / Mac Thai fonts)
PUA = str.maketrans({
    0xF700: "ฐ", 0xF701: "ิ", 0xF702: "ี", 0xF703: "ึ",
    0xF704: "ื", 0xF705: "่", 0xF706: "้", 0xF707: "๊",
    0xF708: "๋", 0xF709: "์", 0xF70A: "่", 0xF70B: "้",
    0xF70C: "๊", 0xF70D: "๋", 0xF70E: "์", 0xF70F: "ญ",
    0xF710: "ั", 0xF711: "ํ", 0xF712: "็", 0xF713: "่",
    0xF714: "้", 0xF715: "๊", 0xF716: "๋", 0xF717: "์",
    0xF718: "ุ", 0xF719: "ู", 0xF71A: "ฺ",
})
# a consonant (with optional tone mark) followed by " า": no Thai word starts
# with sara aa, so the space is a lost sara am
LOST_SARA_AM = re.compile(r"([ก-ฮ][่-๋]?) า")

HEADER = re.compile(
    r"^(หน้า ?[๐-๙0-9]+|เล่ม .*(ตอน|ตอนที่|ตอนพิเศษ).*|ราชกิจจานุเบกษา"
    r"|~ ?[๐-๙0-9]+ ?~|- ?[๐-๙0-9]+ ?-|[๐-๙]+ \S+ [๐-๙]{4})$")
HEADER_ZONE = 100  # pt from the top of the page where headers live
INDENT = 20  # pt past the left margin that marks a paragraph's first line
RULE = re.compile(r"^[-_=.]{5,}$")
# "/ ประเทศที่มีสิทธิ . . ." at the foot of a page: the next page's first words
CONTINUED = re.compile(r"^/ .*(\. ?){3}$")


# Lines in these files end with a justification space even inside a word,
# so a line-end space means nothing. Thai words are not separated, but a
# number, a bracket or "พ.ศ." always follows a space.
SPACE_BEFORE = re.compile(r"^(พ\.ศ\.|[(“\"0-9๐-๙A-Za-z])")


def join(prev, nxt):
    prev = prev.rstrip()
    if SPACE_BEFORE.match(nxt) or not THAI_END.search(prev):
        return prev + " " + nxt
    return prev + nxt


THAI_END = re.compile(r"[ก-\u0e4e]$")  # Thai letters, not Thai digits


def clean(text):
    text = normalize(text.translate(PUA))
    return LOST_SARA_AM.sub(lambda m: m[1] + "ำ", text)


def page_lines(page):
    """Yield (x, y, size, text) for every non-empty line on a page."""
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["chars"]]
            raw = "".join(c["c"] for s in spans for c in s["chars"])
            if not raw.strip():
                continue
            text = clean(raw)
            text = text.strip() + (" " if raw.endswith(" ") else "")
            size = max(round(s["size"]) for s in spans)
            yield line["bbox"][0], line["bbox"][1], size, text


def extract(path, with_header=False):
    """Return a list of paragraphs: {"text", "page", "centered", "lines"}.

    with_header=True also returns the first page's header lines (for a Royal
    Gazette PDF: volume, issue and publication date).
    """
    doc = pymupdf.open(path)
    pages, header = [], []
    for pno, page in enumerate(doc, 1):
        rows = []
        for r in page_lines(page):
            if r[1] < HEADER_ZONE and HEADER.match(r[3].strip()):
                if pno == 1 and not r[3].startswith(("หน้า", "~", "-")):
                    header.append(re.sub(r" +", " ", r[3]).strip())
            else:
                rows.append(r)
        # PyMuPDF splits a line into several when spacing is wide; merge rows
        # that share a baseline
        rows.sort(key=lambda r: (round(r[1]), r[0]))
        merged = []
        for r in rows:
            if merged and abs(merged[-1][1] - r[1]) < 3:
                x, y, size, text = merged[-1]
                merged[-1] = (x, y, max(size, r[2]), text.rstrip() + " | " + r[3])
            else:
                merged.append(r)
        pages.append((pno, merged))

    xs = Counter(round(r[0]) for _, rows in pages for r in rows)
    margin = min(x for x, n in xs.items() if n >= 3)
    width = max(r[0] for _, rows in pages for r in rows)

    steps = Counter(round(b[1] - a[1]) for _, rows in pages
                    for a, b in zip(rows, rows[1:]) if b[1] > a[1])
    gap = steps.most_common(1)[0][0] * 1.5 if steps else 30

    body = []
    for pno, rows in pages:
        prev_y = None
        for x, y, size, text in rows:
            if RULE.match(text.strip()) or CONTINUED.match(text.strip()):
                continue
            indented = x > margin + INDENT
            centered = x > margin + (width - margin) / 3 and len(text) < 70
            after_gap = prev_y is not None and y - prev_y > gap
            prev_y = y
            line = re.sub(r" +", " ", text).strip()
            if not body or indented or centered or after_gap or body[-1]["centered"]:
                body.append({"text": text, "page": pno, "centered": centered,
                             "lines": [line]})
            else:
                body[-1]["text"] = join(body[-1]["text"], text)
                body[-1]["lines"].append(line)
    for p in body:
        p["text"] = re.sub(r" +", " ", p["text"].replace(" | ", " ")).strip()
    return (body, header) if with_header else body


def main(src, dst):
    with open(dst, "w", encoding="utf-8") as f:
        for p in extract(src):
            f.write(p["text"] + "\n\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
