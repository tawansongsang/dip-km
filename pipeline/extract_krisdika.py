"""Extract clean Thai text from a consolidated-law PDF published by Krisdika
(สำนักงานคณะกรรมการกฤษฎีกา).

These PDFs have a broken text layer:
  * a watermark drawn in EucrosiaUPC Italic that shows up as stray "ก"
  * TH SarabunPSK "shifted" glyphs (tone marks / vowels moved for tall
    consonants) whose ToUnicode maps to ASCII, e.g. "เป0น" -> "เป็น"
  * sara am written as nikhahit + sara aa ("ํา")

Instead of OCR we read the raw characters with PyMuPDF, drop the watermark
font, map the shifted glyphs back and rebuild paragraphs.

Usage:
    python pipeline/extract_krisdika.py raw/x.pdf out.md

The output is Markdown: body paragraphs in reading order with footnote
references as [^n], followed by footnote definitions.
"""

import re
import sys

import pymupdf

WATERMARK_FONT = "Eucrosia"
BODY_SIZE = 16.0
FOOTNOTE_SIZE = 14.0
REF_SIZES = (10.5, 9.0)  # superscript footnote numbers in body / footnotes

# Shifted TH SarabunPSK glyphs -> real Thai characters. Only applied right
# after a Thai character, so genuine ASCII stays untouched.
SHIFTED = {
    "\x1e": "\u0e49",  # ไม้โท
    "T": "\u0e49",     # ไม้โท (over ป ฝ ฟ)
    "8": "\u0e48",     # ไม้เอก
    "V": "\u0e48",     # ไม้เอก (over ป ฝ ฟ)
    "0": "\u0e47",     # ไม้ไต่คู้
    "1": "\u0e35",     # สระอี
    "3": "\u0e31",     # ไม้หันอากาศ
    "R": "\u0e34",     # สระอิ
    "W": "\u0e37",     # สระอือ
    "I": "\u0e4c",     # ทัณฑฆาต
}

THAI = re.compile(r"[\u0e01-\u0e5b]")
TONES = "\u0e48\u0e49\u0e4a\u0e4b"
UPPER_LOWER_VOWELS = "\u0e31\u0e34\u0e35\u0e36\u0e37\u0e38\u0e39\u0e47"
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def fix_chars(chars, prev=""):
    out = []
    for c in chars:
        if c in SHIFTED and THAI.match((out[-1:] or [prev])[0] or " "):
            c = SHIFTED[c]
        out.append(c)
    return "".join(out)


def normalize(text):
    # nikhahit + (tone) + sara aa -> (tone) + sara am
    text = re.sub(f"\u0e4d([{TONES}]?)\u0e32", "\\1\u0e33", text)
    text = re.sub(f"([{TONES}])\u0e4d\u0e32", "\\1\u0e33", text)
    # tone mark typed before its vowel -> canonical order
    text = re.sub(f"([{TONES}])([{UPPER_LOWER_VOWELS}])", "\\2\\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def page_lines(page):
    """Yield (kind, x, y, text) for every non-empty line on a page.

    kind is "body" or "footnote". Superscript numbers become [^n].
    A line that ended with a space keeps one trailing space, because a
    wrapped line may end exactly at a word gap.
    """
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            parts, kind = [], None
            for span in line["spans"]:
                font, size = span["font"], round(span["size"], 1)
                if WATERMARK_FONT in font or "Italic" in font:
                    continue
                prev = (parts[-1][-1:] if parts else "")
                text = fix_chars((c["c"] for c in span["chars"]), prev)
                if not text.strip(" \t"):
                    parts.append(text)
                    continue
                if size in REF_SIZES:
                    n = text.strip().translate(THAI_DIGITS)
                    if size == 9.0 and kind is None:
                        parts.append(f"\x00{n}\x00")  # footnote definition start
                    else:
                        parts.append(f"[^{n}]")
                    continue
                if kind is None:
                    kind = "footnote" if size == FOOTNOTE_SIZE else "body"
                parts.append(text)
            text = normalize("".join(parts)).lstrip()
            if kind and text.strip():
                text = text.rstrip() + (" " if text.endswith(" ") else "")
                yield kind, line["bbox"][0], line["bbox"][1], text


HEADER = re.compile(r"^(สำนักงานคณะกรรมการกฤษฎีกา|- ?[๐-๙]+ ?-)$")
PARA_START_X = 120  # indented first line of a paragraph; continuation at ~90
PARA_GAP = 26  # vertical gap (pt) that always starts a new paragraph
BREAK_BEFORE = re.compile(r"^(หมายเหตุ|พระราชบัญญัติ.+\(ฉบับที่)")
# Krisdika editors' sign-off on the last page, e.g. "จุฑามาศ/ปรับปรุง" + date
EDITOR_NOTE = re.compile(r"^(\S+/(ปรับปรุง|เพิ่มเติม)|[๐-๙]+ \S+ [๐-๙]{4})$")


def join(prev, nxt):
    # Thai has no spaces between words: lines wrap at word boundaries.
    if prev.endswith((" ", "-")) or nxt.startswith(" "):
        return prev + nxt
    if prev[-1:].isascii() and nxt[:1].isascii():
        return prev + " " + nxt
    return prev + nxt


def extract(path):
    doc = pymupdf.open(path)
    body, notes = [], {}
    current_note = None
    for pno, page in enumerate(doc, 1):
        rows = sorted(page_lines(page), key=lambda r: (r[2], r[1]))
        prev_y = None
        for kind, x, y, text in rows:
            if HEADER.match(text.strip()) or (x > 380 and EDITOR_NOTE.match(text.strip())):
                continue
            if kind == "footnote":
                m = re.match(r"\x00(\d+)\x00\s*(.*)", text)
                if m:
                    current_note = m.group(1)
                    notes[current_note] = m.group(2)
                elif current_note:
                    notes[current_note] = join(notes[current_note], text)
                continue
            centered = x > 200 and len(text) < 60
            gap = prev_y is not None and y - prev_y > PARA_GAP
            prev_y = y
            if (not body or x > PARA_START_X or centered or gap
                    or body[-1]["centered"] or BREAK_BEFORE.match(text)):
                body.append({"text": text, "page": pno, "centered": centered})
            else:
                body[-1]["text"] = join(body[-1]["text"], text)
    for p in body:
        p["text"] = p["text"].replace("\x00", "").strip()
    return body, {n: t.strip() for n, t in notes.items()}


def main(src, dst):
    paragraphs, notes = extract(src)
    with open(dst, "w", encoding="utf-8") as f:
        for p in paragraphs:
            f.write(p["text"] + "\n\n")
        for n, text in notes.items():
            f.write(f"[^{n}]: {text}\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
