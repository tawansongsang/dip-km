"""Split a Krisdika consolidated act into knowledge files: one file per มาตรา,
plus overview, definitions, fee schedule and amendment history.

Usage:
    python pipeline/build_act.py SRC OUT_DIR --id tm-act-2534 \
        --title-en "Trademark Act B.E. 2534 (1991)" [--audience public] \
        [--consolidated-by "กรมทรัพย์สินทางปัญญา"]

SRC is a Krisdika PDF or a consolidated act in Word (.docx, see extract_docx).

Body text is kept verbatim (Thai digits included). Frontmatter uses Arabic
digits so that "มาตรา 6" and "มาตรา ๖" both find the file.
"""

import argparse
import json
import os
import re
from collections import OrderedDict

import extract_docx
import extract_krisdika
from extract_krisdika import THAI_DIGITS

THAI_NUM = "[๐-๙]+"
SUFFIXES = {"ทวิ": "tawi", "ตรี": "tri", "จัตวา": "chattawa", "เบญจ": "benja",
            "ฉ": "cha", "สัตต": "satta", "อัฏฐ": "attha", "นว": "nawa"}
SECTION = re.compile(
    rf"^มาตรา ({THAI_NUM}(?:/{THAI_NUM})?(?: (?:{'|'.join(SUFFIXES)}))?)(?=[\s\[])")
CHAPTER = re.compile(rf"^หมวด {THAI_NUM}(?:/{THAI_NUM})?(\[\^\d+\])?$")
PART = re.compile(rf"^ส่วนที่ {THAI_NUM}(\[\^\d+\])?$")
TRANSITIONAL = "บทเฉพาะกาล"
SIGNATURE = "ผู้รับสนองพระบรมราชโองการ"
FEES = re.compile(r"^อัตราค่าธรรมเนียม")
NOTE = re.compile(r"^หมายเหตุ")
# an amending act is "พระราชบัญญัติ…(ฉบับที่ n) พ.ศ. …" or another act that
# amends several laws, e.g. "พระราชบัญญัติแก้ไขเพิ่มเติมบทบัญญัติ… พ.ศ. ๒๕๖๐"
ACT_NAME = r"พระราชบัญญัติ(?:.+?\(ฉบับที่ [๐-๙]+\)|แก้ไขเพิ่มเติม.+?) พ\.ศ\. ?[๐-๙]{4}"
AMENDING_ACT = re.compile(rf"^{ACT_NAME}")
FOOTREF = re.compile(r"\[\^(\d+)\]")
AMENDMENT = re.compile(
    r"^(?P<target>.*?)\s*(?P<action>แก้ไขเพิ่มเติม|เพิ่ม|ยกเลิก)โดย"
    rf"(?P<by>{ACT_NAME})")


def arabic(s):
    return s.translate(THAI_DIGITS)


def section_slug(num_th):
    num, _, suffix = num_th.partition(" ")
    main, _, sub = arabic(num).partition("/")
    slug = f"s{int(main):03d}" + (f"-{sub}" if sub else "")
    return slug + (f"-{SUFFIXES[suffix]}" if suffix else "")


def yaml_value(v, indent=0):
    """Tiny YAML writer: JSON scalars are valid YAML."""
    pad = " " * indent
    if isinstance(v, list):
        if not v:
            return " []"
        if all(not isinstance(i, dict) for i in v):
            return " [" + ", ".join(json.dumps(i, ensure_ascii=False) for i in v) + "]"
        out = ""
        for item in v:
            first = True
            for k, val in item.items():
                out += f"\n{pad}  {'- ' if first else '  '}{k}:{yaml_value(val, indent + 4)}"
                first = False
        return out
    return " " + json.dumps(v, ensure_ascii=False)


def frontmatter(meta):
    return "---\n" + "".join(f"{k}:{yaml_value(v)}\n" for k, v in meta.items()) + "---\n"


def footnotes_block(paragraphs, notes):
    refs = OrderedDict()
    for p in paragraphs:
        for n in FOOTREF.findall(p):
            refs[n] = notes.get(n, "")
    if not refs:
        return ""
    return "\n" + "".join(f"[^{n}]: {t}\n" for n, t in refs.items())


def amendments(paragraphs, notes):
    out = []
    for p in paragraphs:
        for n in FOOTREF.findall(p):
            m = AMENDMENT.match(notes.get(n, ""))
            if m:
                out.append({"action": m["action"], "target": arabic(m["target"]),
                            "by": arabic(m["by"]), "footnote": int(n)})
    return out


def is_heading(t):
    return bool(SECTION.match(t) or CHAPTER.match(t) or PART.match(t)
                or t in (TRANSITIONAL, SIGNATURE))


def parse(paragraphs):
    """Split the paragraph stream into the parts of a consolidated act."""
    doc = {"preamble": [], "sections": [], "signature": [], "fees": [],
           "history": [], "chapters": []}
    chapter = part = None
    zone, i = "preamble", 0
    texts = [p["text"] for p in paragraphs]
    while i < len(texts):
        t, page = texts[i], paragraphs[i]["page"]
        if zone in ("preamble", "body"):
            if CHAPTER.match(t):
                # a long chapter title can run over several paragraphs
                j = i + 2
                while j < len(texts) and not is_heading(texts[j]):
                    j += 1
                chapter = " ".join([FOOTREF.sub('', t)] + texts[i + 1:j])
                doc["chapters"].append({"title": chapter, "heading": t, "parts": [],
                                        "sections": []})
                part = None
                i = j
                continue
            if PART.match(t):
                part = f"{FOOTREF.sub('', t)} {texts[i + 1]}"
                doc["chapters"][-1]["parts"].append({"title": part, "heading": t,
                                                     "sections": []})
                i += 2
                continue
            if t == TRANSITIONAL:
                chapter, part = TRANSITIONAL, None
                doc["chapters"].append({"title": t, "heading": t, "parts": [],
                                        "sections": []})
                i += 1
                continue
            m = SECTION.match(t)
            if m:
                zone = "body"
                sec = {"num_th": m[1],
                       "chapter": chapter and FOOTREF.sub("", chapter),
                       "part": part and FOOTREF.sub("", part),
                       "paragraphs": [t], "pages": [page]}
                doc["sections"].append(sec)
                if doc["chapters"]:
                    target = doc["chapters"][-1]
                    if part and target["parts"]:
                        target["parts"][-1]["sections"].append(sec)
                    target["sections"].append(sec)
            elif t == SIGNATURE:
                zone = "signature"
                doc["signature"].append(t)
            elif zone == "body":
                doc["sections"][-1]["paragraphs"].append(t)
                if page not in doc["sections"][-1]["pages"]:
                    doc["sections"][-1]["pages"].append(page)
            else:
                doc["preamble"].append(t)
        elif zone == "signature":
            if FEES.match(t):
                zone = "fees"
                doc["fees"].append(t)
            elif NOTE.match(t):  # act without a fee schedule
                zone = "history"
                doc["history"].append(t)
            else:
                doc["signature"].append(t)
        elif zone == "fees":
            if NOTE.match(t):
                zone = "history"
                doc["history"].append(t)
            else:
                doc["fees"].append(t)
        else:
            doc["history"].append(t)
        i += 1
    return doc


FEE_UNIT = re.compile(r"^\S+ละ$")
FEE_AMOUNT = re.compile(r"^[๐-๙,]+ บาท$")
ITEM = re.compile(r"\s(?=\([๐-๙]+\)\s)")
SUBITEM = re.compile(r"\s(?=\([ก-ฮ]\)\s)")


def fee_rows(paragraphs):
    """Turn the fee schedule (description / unit / amount triples) into rows."""
    rows, desc, item = [], [], ""
    for t in paragraphs[1:]:
        if FEE_UNIT.match(t):
            unit = t
            continue
        if FEE_AMOUNT.match(t):
            text = " ".join(desc)
            # a note for the previous row can lead the next description,
            # e.g. "เศษของเซนติเมตรให้คิดเป็นหนึ่งเซนติเมตร (๓) คำคัดค้าน..."
            lead, *rest = ITEM.split(text, maxsplit=1)
            if rest and not lead.startswith("("):
                rows[-1]["note"] = lead
                text = rest[0]
            head, *sub = SUBITEM.split(text, maxsplit=1)
            if head.startswith("(") and re.match(r"^\([๐-๙]+\)", head):
                item = head
                text = sub[0] if sub else ""
            rows.append({"item": item, "sub": text if text != item else "",
                         "unit": unit, "amount": t, "note": ""})
            desc = []
            continue
        desc.append(t)
    if desc and rows:
        rows[-1]["note"] = " ".join(desc)
    return rows


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def build(src, out, law_id, title_en, audience, consolidated_by):
    reader = extract_docx if src.lower().endswith(".docx") else extract_krisdika
    paragraphs, notes = reader.extract(src)
    doc = parse(paragraphs)
    title_th = re.search(r"“(.+?)”", doc["sections"][0]["paragraphs"][0])[1]
    title_th = re.sub(r"พ\.ศ\.\s*", "พ.ศ. ", title_th)
    source = os.path.relpath(src)
    base = {"law_id": law_id, "law": arabic(title_th), "law_th": title_th,
            "law_en": title_en, "audience": audience, "language": "th",
            "source": source, "consolidated_by": consolidated_by}

    slugs = {s["num_th"]: section_slug(s["num_th"]) for s in doc["sections"]}
    ref_pattern = re.compile(rf"มาตรา ({THAI_NUM}(?:/{THAI_NUM})?(?: (?:{'|'.join(SUFFIXES)}))?)")

    for s in doc["sections"]:
        body = s["paragraphs"]
        slug = slugs[s["num_th"]]
        text = "\n".join(body)
        repealed = re.match(rf"^มาตรา [^\s]+(?: \S+)?(\[\^\d+\])* \(ยกเลิก\)$", body[0]) \
            and len(body) == 1
        refs = []
        for p in body:
            for num in ref_pattern.findall(p[len("มาตรา ") + len(s["num_th"]):]
                                            if p is body[0] else p):
                ref = slugs.get(num)
                if ref and ref != slug and f"{law_id}-{ref}" not in refs:
                    refs.append(f"{law_id}-{ref}")
        meta = {"id": f"{law_id}-{slug}", "type": "act-section", **base,
                "section": arabic(s["num_th"]), "section_th": s["num_th"],
                "chapter": arabic(s["chapter"]) if s["chapter"] else None,
                "part": arabic(s["part"]) if s["part"] else None,
                "status": "repealed" if repealed else "in-force",
                "amendment_history": amendments(body, notes),
                "references": refs, "source_pages": s["pages"]}
        meta = {k: v for k, v in meta.items() if v is not None}
        md = frontmatter(meta)
        md += f"\n# มาตรา {s['num_th']} (มาตรา {arabic(s['num_th'])})\n\n"
        md += f"> {title_th}" + (f" · {s['chapter']}" if s["chapter"] else "") + \
              (f" · {s['part']}" if s["part"] else "") + "\n\n"
        md += "\n\n".join(body) + "\n"
        md += footnotes_block(body, notes)
        write(os.path.join(out, "sections", f"{slug}.md"), md)

    write_definitions(out, doc, notes, base, law_id, slugs)
    write_fees(out, doc, notes, base, law_id)
    write_history(out, doc, notes, base, law_id)
    write_overview(out, doc, notes, base, law_id, slugs)


def write_definitions(out, doc, notes, base, law_id, slugs):
    sec = next((s for s in doc["sections"] if s["num_th"] == "๔"), None)
    if not sec:
        return
    meta = {"id": f"{law_id}-definitions", "type": "act-definitions", **base,
            "section": "4", "derived_from": [f"{law_id}-{slugs['๔']}"]}
    md = frontmatter(meta) + f"\n# บทนิยาม — {base['law_th']} (มาตรา ๔)\n\n"
    md += "ข้อความตามตัวบท แยกเป็นรายคำเพื่อค้นหาง่าย ดูต้นฉบับที่ " \
          f"[มาตรา ๔](sections/{slugs['๔']}.md)\n"
    for p in sec["paragraphs"][1:]:
        m = re.match(r"^“(.+?)”", p)
        if m:
            md += f"\n## {m[1]}\n\n"
        md += p + "\n" + footnotes_block([p], notes)
    write(os.path.join(out, "definitions.md"), md)


def write_fees(out, doc, notes, base, law_id):
    if not doc["fees"]:
        return
    rows = fee_rows(doc["fees"])
    meta = {"id": f"{law_id}-fees", "type": "act-fee-schedule", **base,
            "authorized_by": f"{law_id}-s005"}
    md = frontmatter(meta) + f"\n# อัตราค่าธรรมเนียมท้าย{base['law_th']}\n\n"
    md += ("> **สำคัญ:** ตารางนี้เป็น *อัตราสูงสุด* ที่กฎหมายกำหนด ตามมาตรา ๕ "
           "รัฐมนตรีออกกฎกระทรวงกำหนดค่าธรรมเนียม \"ไม่เกินอัตราท้ายพระราชบัญญัตินี้\" "
           "ค่าธรรมเนียมที่เรียกเก็บจริงให้ดูกฎกระทรวงกำหนดค่าธรรมเนียมฉบับที่ใช้บังคับ\n>\n"
           "> These are statutory *maximum* fees. Actual fees are set by ministerial "
           "regulation under section 5.\n\n")
    md += "| รายการ | กรณี | หน่วย | อัตราสูงสุด |\n|---|---|---|---|\n"
    for r in rows:
        md += f"| {r['item']} | {r['sub']} | {r['unit']} | {r['amount']} |\n"
        if r["note"]:
            md += f"| | *{r['note']}* | | |\n"
    md += footnotes_block(doc["fees"][:1], notes)
    write(os.path.join(out, "fees.md"), md)


def write_history(out, doc, notes, base, law_id):
    meta = {"id": f"{law_id}-history", "type": "act-history", **base}
    md = frontmatter(meta) + f"\n# ประวัติและเหตุผลการตรา — {base['law_th']}\n\n"
    md += f"## {base['law_th']} (ฉบับเดิม)\n\n"
    for t in doc["history"]:
        if AMENDING_ACT.match(t):
            md += f"\n## {t}\n\n"
        elif SECTION.match(t):
            md += t + "\n\n"
        elif NOTE.match(t):
            md += f"**{t.split(' ', 1)[0]}** {t.split(' ', 1)[1]}\n\n"
        else:
            md += t + "\n\n"
    md += footnotes_block(doc["history"], notes)
    write(os.path.join(out, "history.md"), md)


def write_overview(out, doc, notes, base, law_id, slugs):
    amending = [FOOTREF.sub("", t) for t in doc["history"] if AMENDING_ACT.match(t)]
    meta = {"id": f"{law_id}-overview", "type": "act-overview", **base,
            "amended_by": [arabic(a) for a in amending],
            "section_count": len(doc["sections"]),
            "repealed_sections": []}
    md = f"\n# {base['law_th']}\n\n*{base['law_en']}*\n\n"
    md += "## ข้อมูลทั่วไป\n\n"
    for t in doc["preamble"]:
        if t.startswith("ให้ไว้"):
            md += f"- {t}\n"
        elif t.startswith("โดยที่"):
            md += f"- คำปรารภ: {t}\n"
    md += f"- ประกาศในราชกิจจานุเบกษา: {notes.get('1', '-')}\n"
    md += f"- ฉบับนี้เป็นฉบับรวมแก้ไข (consolidated) จัดทำโดย{base['consolidated_by']} " \
          "ไม่ใช่ฉบับทางราชการ หากต้องอ้างอิงทางกฎหมายให้ตรวจกับราชกิจจานุเบกษา\n\n"
    md += "## กฎหมายที่แก้ไขเพิ่มเติม\n\n"
    md += "".join(f"- {a}\n" for a in amending) or "- ไม่มี\n"
    md += "\nรายละเอียดและเหตุผลการตรา: [history.md](history.md)\n\n"
    md += "## โครงสร้างและสารบัญมาตรา\n\n"
    md += "ไฟล์อื่น: [บทนิยาม](definitions.md) · " + \
          ("[อัตราค่าธรรมเนียม](fees.md) · " if doc["fees"] else "") + \
          "[ประวัติ](history.md)\n\n"

    def links(sections):
        return " · ".join(f"[{s['num_th']}](sections/{slugs[s['num_th']]}.md)"
                          for s in sections)

    top = [s for s in doc["sections"] if not s["chapter"]]
    if top:
        md += f"### บททั่วไป\n\nมาตรา {links(top)}\n\n"
    for c in doc["chapters"]:
        md += f"### {FOOTREF.sub('', c['title'])}\n\n"
        for n in FOOTREF.findall(c["title"]):
            md += f"> {notes.get(n, '')}\n\n"
        loose = [s for s in c["sections"] if not s["part"]]
        if loose:
            md += f"มาตรา {links(loose)}\n\n"
        for p in c["parts"]:
            md += f"- **{FOOTREF.sub('', p['title'])}** — มาตรา {links(p['sections'])}\n"
            for n in FOOTREF.findall(p["title"]):
                md += f"  > {notes.get(n, '')}\n"
        if c["parts"]:
            md += "\n"
    repealed = []
    for s in doc["sections"]:
        if re.search(r"\(ยกเลิก\)$", s["paragraphs"][0]) and len(s["paragraphs"]) == 1:
            repealed.append(arabic(s["num_th"]))
    meta["repealed_sections"] = repealed
    write(os.path.join(out, "_overview.md"), frontmatter(meta) + md)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--id", required=True)
    ap.add_argument("--title-en", required=True)
    ap.add_argument("--audience", default="public")
    ap.add_argument("--consolidated-by", default="สำนักงานคณะกรรมการกฤษฎีกา")
    a = ap.parse_args()
    build(a.src, a.out, a.id, a.title_en, a.audience, a.consolidated_by)
