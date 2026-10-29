"""Split a law that is not a Krisdika consolidated act into knowledge files:
พระราชกฤษฎีกา, กฎกระทรวง, ระเบียบ, ประกาศ … from the Royal Gazette or a
Word export. Units can be มาตรา or ข้อ; schedules (บัญชี) get their own files.

Usage:
    python pipeline/build_doc.py SRC_PDF OUT_DIR --id travel-reg-2550 \
        --doc-type regulation --title-en "…" [--effective-date 2007-08-03] \
        [--amends BASE_OUT_DIR] [--consolidated-by "…"] [--audience public]

--amends marks this document as amending the one built in BASE_OUT_DIR:
clauses such as "ให้ยกเลิกความใน (๒) ของข้อ ๘ แห่งระเบียบ… และให้ใช้ความต่อไปนี้แทน"
are recorded here (`amends:`) and on the base files (`amendment_history`,
`status: "amended"`, `current_text_in:`). Build the base first.

Amendment notes written into a consolidated text, e.g.
"(มาตรา 6 แก้ไขเพิ่มเติมโดยพระราชกฤษฎีกา… (ฉบับที่ ๖) พ.ศ. ๒๕๔๑)", become
`amendment_history` of that section.
"""

import argparse
import glob
import json
import os
import re

from build_act import SUFFIXES, arabic, section_slug, write
from extract_pdf import extract

NUM = r"[๐-๙0-9]+(?:/[๐-๙0-9]+)?(?: (?:" + "|".join(SUFFIXES) + "))?"
UNIT = re.compile(rf"^(มาตรา|ข้อ) ({NUM})(?=\s|$|ยกเลิก)")  # "มาตรา ๕๔ ทวิยกเลิก"
HEADING = re.compile(r"^(ลักษณะ|หมวด|หมวดที่|ส่วน|ส่วนที่) [๐-๙0-9]+$")
TRANSITIONAL = "บทเฉพาะกาล"
SIGNATURE = re.compile(r"(ประกาศ ณ วันที่|ให้ไว้ ณ วันที่|ผู้รับสนองพระบรมราชโองการ)")
SCHEDULE = re.compile(r"^บัญชี(?:หมายเลข| ?ท้าย\S*)? ?([๐-๙0-9]+)\b")
NOTE = re.compile(
    rf"^\((?P<target>(?:มาตรา|ข้อ) (?P<num>{NUM})[^)]*?)\s*"
    r"(?P<action>แก้ไขเพิ่มเติม|เพิ่มเติม|ยกเลิก) ?โดย(?P<by>.+)\)$")
TITLE = re.compile(r"“(.+?)”")
DEFINITIONS = re.compile(r"ใน(พระราชกฤษฎีกา|ระเบียบ|กฎกระทรวง|ประกาศ)นี้$")
# "ให้ยกเลิกความใน (๒) ของข้อ ๘ แห่งระเบียบ…", "ให้เพิ่มความต่อไปนี้เป็นข้อ ๕/๑ แห่ง…",
# "ให้ยกเลิกความในบัญชีหมายเลข ๒ … ท้ายระเบียบ…"
AMEND = re.compile(
    r"ให้(?P<action>ยกเลิกความใน|เพิ่มความต่อไปนี้เป็น|ยกเลิก)\s*(?P<target>.*?)\s*"
    r"(?:แห่ง|ท้าย)(?P<law>(?:พระราชกฤษฎีกา|กฎกระทรวง|ระเบียบ|ประกาศ).*)")
DOC_TYPES = {"decree": "พระราชกฤษฎีกา", "ministerial-regulation": "กฎกระทรวง",
             "regulation": "ระเบียบ", "notification": "ประกาศ", "other": "อื่น ๆ"}


def frontmatter(meta):
    """One JSON value per line: valid YAML, and easy to read back."""
    return "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n"
                             for k, v in meta.items()) + "---\n"


def read_doc(path):
    with open(path, encoding="utf-8") as f:
        _, fm, body = f.read().split("---\n", 2)
    meta = {}
    for line in fm.splitlines():
        k, _, v = line.partition(": ")
        meta[k] = json.loads(v)
    return meta, body


def schedule_slug(num):
    return f"b{int(arabic(num)):02d}"


def squash(s):
    return re.sub(r"\s+", "", s)


def parse(paragraphs):
    doc = {"preamble": [], "sections": [], "signature": [], "schedules": [],
           "headings": []}
    unit_word, path, zone = None, {}, "preamble"
    i = 0
    while i < len(paragraphs):
        p = paragraphs[i]
        t = p["text"]
        if zone in ("preamble", "body"):
            if HEADING.match(t) or t == TRANSITIONAL:
                level = "ส่วน" if t.startswith("ส่วน") else \
                    "หมวด" if t.startswith("หมวด") else "ลักษณะ" if t != TRANSITIONAL else "หมวด"
                title = t
                nxt = paragraphs[i + 1]["text"] if i + 1 < len(paragraphs) else ""
                if t != TRANSITIONAL and nxt and not UNIT.match(nxt) and not HEADING.match(nxt):
                    title, i = f"{t} {nxt}", i + 1
                keep = {"ลักษณะ": [], "หมวด": ["ลักษณะ"], "ส่วน": ["ลักษณะ", "หมวด"]}[level]
                path = {k: v for k, v in path.items() if k in keep}
                path[level] = title
                doc["headings"].append({"title": title, "level": level, "sections": []})
                i += 1
                continue
            m = UNIT.match(t)
            if m and unit_word in (None, m[1]):
                unit_word, zone = m[1], "body"
                sec = {"unit": m[1], "num_th": m[2], "path": dict(path),
                       "paragraphs": [t], "pages": [p["page"]]}
                doc["sections"].append(sec)
                if doc["headings"]:
                    doc["headings"][-1]["sections"].append(sec)
                i += 1
                continue
            if zone == "body":
                sig = SIGNATURE.search(t)
                if sig:
                    if sig.start() > 0:
                        doc["sections"][-1]["paragraphs"].append(t[:sig.start()].strip())
                    doc["signature"].append(t[sig.start():])
                    zone = "signature"
                else:
                    sec = doc["sections"][-1]
                    sec["paragraphs"].append(t)
                    if p["page"] not in sec["pages"]:
                        sec["pages"].append(p["page"])
            else:
                doc["preamble"].append(t)
        else:
            m = SCHEDULE.match(t)
            if m:
                zone = "schedules"
                doc["schedules"].append({"num_th": m[1], "lines": list(p["lines"]),
                                         "pages": [p["page"]]})
            elif zone == "schedules":
                sch = doc["schedules"][-1]
                sch["lines"] += p["lines"]
                if p["page"] not in sch["pages"]:
                    sch["pages"].append(p["page"])
            else:
                doc["signature"].append(t)
        i += 1
    return doc


def amendment_notes(paragraphs):
    out = []
    for p in paragraphs:
        m = NOTE.match(p)
        if m:
            out.append({"action": m["action"], "target": arabic(m["target"]),
                        "by": arabic(m["by"])})
    return out


def amending_clauses(sec, base_title):
    """What a section of an amending document changes in the base document."""
    first = sec["paragraphs"][0]
    m = AMEND.search(first)
    if not m or not squash(m["law"]).startswith(squash(base_title)):
        return []
    action = {"ยกเลิกความใน": "แก้ไขเพิ่มเติม", "ยกเลิก": "ยกเลิก",
              "เพิ่มความต่อไปนี้เป็น": "เพิ่ม"}[m["action"]]
    if m["action"] == "ยกเลิกความใน" and "ให้ใช้ความ" not in first:
        action = "ยกเลิก"
    target = m["target"]
    out = []
    for unit, num in re.findall(rf"(มาตรา|ข้อ) ?({NUM})", target):
        out.append({"action": action, "target": arabic(target), "unit": unit,
                    "slug": section_slug(num)})
    for num in re.findall(r"บัญชีหมายเลข ?([๐-๙0-9]+)", target):
        out.append({"action": action, "target": arabic(f"บัญชีหมายเลข {num}"),
                    "unit": "บัญชี", "slug": schedule_slug(num)})
    return out


def patch_base(base_dir, slug, kind, entry, notice):
    """Record an amendment on a generated file of the base document."""
    folder = "schedules" if kind == "บัญชี" else "sections"
    path = os.path.join(base_dir, folder, f"{slug}.md")
    if not os.path.exists(path):
        return False
    meta, body = read_doc(path)
    meta["amendment_history"].append(
        {k: v for k, v in entry.items() if k != "whole"})
    meta["status"] = "repealed" if entry["action"] == "ยกเลิก" and entry["whole"] \
        else "amended"
    current = meta.pop("current_text_in", [])
    if entry["by_id"] not in current:
        current.append(entry["by_id"])
    ordered = {}
    for k, v in meta.items():
        ordered[k] = v
        if k == "status":
            ordered["current_text_in"] = current
    heading, _, rest = body.lstrip("\n").partition("\n")
    write(path, frontmatter(ordered) + "\n" + heading + "\n\n" + notice + rest.lstrip("\n"))
    return True


def build(src, out, law_id, title_en, doc_type, audience, effective_date,
          amends, consolidated_by):
    paragraphs, header = extract(src, with_header=True)
    doc = parse(paragraphs)
    first = doc["sections"][0]["paragraphs"][0]
    title_th = re.sub(r"\s+", " ", TITLE.search(first)[1])
    title_th = re.sub(r"พ\.ศ\.\s*", "พ.ศ. ", title_th)
    source = os.path.relpath(src)
    base = {"law_id": law_id, "law": arabic(title_th), "law_th": title_th,
            "law_en": title_en, "doc_type": doc_type, "doc_type_th": DOC_TYPES[doc_type],
            "audience": audience, "language": "th", "source": source}
    if consolidated_by:
        base["consolidated_by"] = consolidated_by
    if effective_date:
        base["effective_date"] = effective_date

    base_meta = None
    if amends:
        base_meta, _ = read_doc(os.path.join(amends, "_overview.md"))
        base_title, base_id = base_meta["law_th"], base_meta["law_id"]

    slugs = {s["num_th"]: section_slug(s["num_th"]) for s in doc["sections"]}
    ref_pattern = re.compile(rf"(?:มาตรา|ข้อ) ({NUM})")
    patched = []
    for s in doc["sections"]:
        body, slug = s["paragraphs"], slugs[s["num_th"]]
        notes = amendment_notes(body)
        whole_repeal = [n for n in notes if n["action"] == "ยกเลิก"
                        and n["target"] == f"{s['unit']} {arabic(s['num_th'])}"]
        repealed = bool(whole_repeal) or bool(re.search(r"\(ยกเลิก\)$", body[0]))
        refs = []
        for p in body if not amends else []:
            for num in ref_pattern.findall(p if p is not body[0] else p[len(s["unit"]) + len(s["num_th"]) + 1:]):
                ref = slugs.get(num)
                if ref and ref != slug and f"{law_id}-{ref}" not in refs:
                    refs.append(f"{law_id}-{ref}")
        meta = {"id": f"{law_id}-{slug}", "type": "section", **base,
                "unit": s["unit"], "section": arabic(s["num_th"]), "section_th": s["num_th"],
                "chapter": arabic(" › ".join(s["path"].values())) or None,
                "status": "repealed" if repealed else "in-force",
                "amendment_history": notes, "references": refs,
                "source_pages": s["pages"]}
        clauses = amending_clauses(s, base_title) if amends else []
        if clauses:
            meta["amends"] = [{"law_id": base_id, "target": c["target"], "action": c["action"],
                               "file": f"{c['slug']}.md"} for c in clauses]
        meta = {k: v for k, v in meta.items() if v is not None}
        label = f"{s['unit']} {s['num_th']} ({s['unit']} {arabic(s['num_th'])})"
        md = frontmatter(meta) + f"\n# {label}\n\n"
        md += f"> {title_th}" + "".join(f" · {v}" for v in s["path"].values()) + "\n\n"
        md += "\n\n".join(body) + "\n"
        write(os.path.join(out, "sections", f"{slug}.md"), md)

        for c in clauses:
            whole = c["unit"] == "บัญชี" or not re.search(r"วรรค|\(", c["target"])
            # a replaced schedule's new text is this document's schedule of the
            # same number; anything else is in the amending section itself
            new_file = os.path.join("schedules", f"{c['slug']}.md") if c["unit"] == "บัญชี" \
                else os.path.join("sections", f"{slug}.md")
            new_label = c["target"] if c["unit"] == "บัญชี" else \
                f"{s['unit']} {arabic(s['num_th'])}"
            entry = {"action": c["action"], "target": c["target"],
                     "by": arabic(f"{title_th} {s['unit']} {s['num_th']}"),
                     "by_id": f"{law_id}-{os.path.basename(new_file)[:-3]}", "whole": whole}
            rel = os.path.relpath(os.path.join(out, new_file),
                                  os.path.join(amends, os.path.dirname(new_file)))
            notice = (f"> **{c['action']}โดย {arabic(title_th)} {s['unit']} {arabic(s['num_th'])}**"
                      f" ({c['target']}) — ข้อความด้านล่างเป็นฉบับเดิม ข้อความที่ใช้บังคับ"
                      f"ให้ดู [{new_label} ของฉบับแก้ไข]({rel})\n\n")
            if patch_base(amends, c["slug"], c["unit"], entry, notice):
                patched.append(c["target"])
            elif c["action"] == "เพิ่ม":
                patched.append(f"{c['target']} (เพิ่มใหม่ อยู่ในไฟล์ของฉบับแก้ไขเท่านั้น)")

    write_definitions(out, doc, base, law_id, slugs)
    write_schedules(out, doc, base, law_id, amends and base_id)
    write_overview(out, doc, header, base, law_id, slugs, base_meta, patched)


def write_definitions(out, doc, base, law_id, slugs):
    sec = next((s for s in doc["sections"] if DEFINITIONS.search(s["paragraphs"][0])), None)
    if not sec:
        return
    label = f"{sec['unit']} {sec['num_th']}"
    meta = {"id": f"{law_id}-definitions", "type": "definitions", **base,
            "section": arabic(sec["num_th"]), "derived_from": [f"{law_id}-{slugs[sec['num_th']]}"]}
    md = frontmatter(meta) + f"\n# บทนิยาม — {base['law_th']} ({label})\n\n"
    md += f"ข้อความตามตัวบท แยกเป็นรายคำเพื่อค้นหาง่าย ดูต้นฉบับที่ " \
          f"[{label}](sections/{slugs[sec['num_th']]}.md)\n"
    for p in sec["paragraphs"][1:]:
        m = re.match(r"^“(.+?)”", p)
        if m:
            md += f"\n## {m[1]}\n\n"
        md += p + "\n"
    write(os.path.join(out, "definitions.md"), md)


def write_schedules(out, doc, base, law_id, amends_id):
    for sch in doc["schedules"]:
        slug = schedule_slug(sch["num_th"])
        title = " ".join(sch["lines"][:2]) if len(sch["lines"]) > 1 else sch["lines"][0]
        repealed = any("ยกเลิกโดย" in line for line in sch["lines"][:3])
        meta = {"id": f"{law_id}-{slug}", "type": "schedule", **base,
                "schedule": arabic(sch["num_th"]), "schedule_th": sch["num_th"],
                "status": "repealed" if repealed else "in-force",
                "amendment_history": [], "source_pages": sch["pages"]}
        if amends_id:
            meta["replaces"] = f"{amends_id}-{slug}"
        md = frontmatter(meta) + f"\n# {title}\n\n> {base['law_th']} · บัญชีท้าย\n\n"
        md += ("> ตารางนี้แปลงจาก PDF อัตโนมัติ: หนึ่งบรรทัดต่อหนึ่งบรรทัดในต้นฉบับ "
               "` | ` คั่นข้อความที่อยู่คนละคอลัมน์ ตัวเลขอัตราอยู่บรรทัดเดียวกับ"
               "แถวแรกของรายการนั้น ตรวจกับต้นฉบับก่อนอ้างอัตรา\n\n")
        md += "```text\n" + "\n".join(sch["lines"]) + "\n```\n"
        write(os.path.join(out, "schedules", f"{slug}.md"), md)


def write_overview(out, doc, header, base, law_id, slugs, base_meta, patched):
    meta = {"id": f"{law_id}-overview", "type": "overview", **base,
            "gazette": arabic(" ".join(header)) or None,
            "section_count": len(doc["sections"]),
            "repealed_sections": [], "schedules": [arabic(s["num_th"]) for s in doc["schedules"]]}
    if base_meta:
        meta["amends"] = base_meta["law_id"]
    md = f"\n# {base['law_th']}\n\n*{base['law_en']}*\n\n## ข้อมูลทั่วไป\n\n"
    md += f"- ประเภท: {base['doc_type_th']}\n"
    if header:
        md += f"- ประกาศในราชกิจจานุเบกษา: {' '.join(header)}\n"
    if base.get("effective_date"):
        md += f"- ใช้บังคับ (ค.ศ.): {base['effective_date']}\n"
    for t in doc["preamble"]:
        if t.startswith(("โดยที่", "อาศัยอำนาจ", "ให้ไว้", "(แก้ไขเพิ่มเติมถึง")):
            md += f"- {t}\n"
    if base.get("consolidated_by"):
        md += f"- ฉบับนี้เป็นฉบับรวมแก้ไขจัดทำโดย {base['consolidated_by']} ไม่ใช่ฉบับทางราชการ " \
              "หากต้องอ้างอิงทางกฎหมายให้ตรวจกับราชกิจจานุเบกษา\n"
    md += "".join(f"- {t}\n" for t in doc["signature"])
    if base_meta:
        md += f"\n## แก้ไข{base_meta['law_th']}\n\n"
        md += "".join(f"- {p}\n" for p in patched) or "- (ไม่พบข้อที่แก้ไขโดยอัตโนมัติ ตรวจด้วยตนเอง)\n"
    md += "\n## สารบัญ\n\n"
    if os.path.exists(os.path.join(out, "definitions.md")):
        md += "บทนิยาม: [definitions.md](definitions.md)\n\n"

    def links(sections):
        return " · ".join(f"[{s['num_th']}](sections/{slugs[s['num_th']]}.md)" for s in sections)

    unit = doc["sections"][0]["unit"]
    top = [s for s in doc["sections"] if not s["path"]]
    if top:
        md += f"### บททั่วไป\n\n{unit} {links(top)}\n\n"
    for h in doc["headings"]:
        md += f"{'#' * {'ลักษณะ': 3, 'หมวด': 4, 'ส่วน': 5}[h['level']]} {h['title']}\n\n"
        if h["sections"]:
            md += f"{unit} {links(h['sections'])}\n\n"
    if doc["schedules"]:
        md += "### บัญชีท้าย\n\n"
        for s in doc["schedules"]:
            md += f"- [บัญชี {s['num_th']}](schedules/{schedule_slug(s['num_th'])}.md) " \
                  f"{' '.join(s['lines'][1:2])}\n"
    repealed = []
    for path in sorted(glob.glob(os.path.join(out, "sections", "*.md"))):
        if 'status: "repealed"' in open(path, encoding="utf-8").read():
            repealed.append(os.path.basename(path)[:-3])
    meta["repealed_sections"] = repealed
    meta = {k: v for k, v in meta.items() if v is not None}
    write(os.path.join(out, "_overview.md"), frontmatter(meta) + md)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--id", required=True)
    ap.add_argument("--title-en", required=True)
    ap.add_argument("--doc-type", required=True, choices=DOC_TYPES)
    ap.add_argument("--audience", default="public")
    ap.add_argument("--effective-date")
    ap.add_argument("--amends", help="output folder of the document this one amends")
    ap.add_argument("--consolidated-by")
    a = ap.parse_args()
    build(a.src, a.out, a.id, a.title_en, a.doc_type, a.audience, a.effective_date,
          a.amends, a.consolidated_by)
