---
name: dip-answer
description: Answer questions about Thai intellectual-property law and DIP (กรมทรัพย์สินทางปัญญา) services — trademarks, patents, copyright, GI, fees, deadlines, registration steps — using the knowledge/ folder, with มาตรา citations. Use for any question in Thai or English about IP law or DIP procedures, e.g. "จดเครื่องหมายการค้าต้องทำอย่างไร", "เครื่องหมายการค้ามีอายุกี่ปี", "how do I oppose a trademark application".
---

# Answering from the DIP knowledge base

Follow these steps in order. The rules in `AGENTS.md` (cite everything, order
of authority, fees, audience, language) apply to every step.

## 1. Understand the question

- Identify the IP area (เครื่องหมายการค้า, สิทธิบัตร, ลิขสิทธิ์, สิ่งบ่งชี้ทางภูมิศาสตร์ …)
  and the type of question: definition, eligibility, procedure, deadline,
  fee, rights/infringement, penalty.
- Decide the audience: **public** (default) or **staff** (user says they are
  staff, uses legal terms, asks for มาตรา or analysis).
- If the question is in English, look up the Thai terms in
  `knowledge/glossary.md` before searching.
- Ask a clarifying question only if the answer really differs by case
  (e.g. trademark vs. service mark rarely matters; Thai vs. Madrid filing does).

## 2. Find the sources

1. Read `knowledge/INDEX.md`, then the area's `INDEX.md`. Its topic map tells
   you which files and มาตรา cover each kind of question.
2. Open those files. For a definition, read `definitions.md` first.
3. Search when the topic map is not enough. Thai has no spaces, so plain
   substring search works; search key nouns, not whole sentences:
   ```sh
   grep -rl "ต่ออายุ" knowledge/public/trademark/
   grep -rl 'section: "53"' knowledge/          # by number
   grep -rn "มาตรา ๕๓" knowledge/public/         # citations in other files
   ```
4. Follow `references:` in frontmatter and "ตามมาตรา …" in the text: many
   sections only make sense with the ones they point to (e.g. a deadline in
   one มาตรา, the consequence in the next).
5. Look for lower-level documents that implement the section (กฎกระทรวง,
   ประกาศ, คู่มือ, FAQ) — search for the section number and topic in other
   folders. When a section says "ให้เป็นไปตามที่กำหนดในกฎกระทรวง" and the
   กฎกระทรวง is not in the knowledge base, say the details are set by
   ministerial regulation that is not yet available here.

## 3. Check before answering

- `status: repealed` → not current law.
- `amendment_history` → is the text you quote the amended version? (Section
  files already contain the current consolidated text.)
- Conflicting sources → follow the order of authority and mention the conflict.
- Every claim you are about to make → which file and มาตรา supports it? Drop
  any claim without a source.

## 4. Write the answer

**Public style** (default), in Thai unless the user wrote in English:

```
<one- or two-sentence direct answer, numbers first: อายุ 10 ปี, ภายใน 60 วัน, …>

<steps or conditions as a short numbered list, plain words, no legal jargon
 unless explained>

อ้างอิง: พ.ร.บ.เครื่องหมายการค้า พ.ศ. 2534 มาตรา 53, 54
<if relevant: ค่าธรรมเนียมที่เรียกเก็บจริงกำหนดในกฎกระทรวง / ข้อมูลนี้เป็นข้อมูลทั่วไป ไม่ใช่คำปรึกษาทางกฎหมาย>
```

**Staff style:**

```
<direct answer>

ข้อกฎหมาย
- มาตรา 53: <short quote or close paraphrase> (knowledge/public/trademark/act-2534/sections/s053.md)
- มาตรา 54 …

ข้อสังเกต
- amendments, related sections, edge cases, gaps in the knowledge base
```

Rules for both:

- Quote the law exactly when wording matters (definitions, conditions,
  deadlines). Paraphrase only to make it easier to read, and keep the
  citation.
- Write numbers the way the user did (Arabic by default); keep Thai digits
  inside quotations.
- If nothing relevant is found: say "ไม่พบข้อมูลนี้ในฐานความรู้" and suggest
  contacting DIP (สายด่วน 1368, www.ipthailand.go.th).
- English answers: translate using `glossary.md` and note that English
  renderings are unofficial.

## Example

Question: เครื่องหมายการค้าจดทะเบียนแล้วคุ้มครองกี่ปี ต่ออายุได้ไหม

Sources read: `trademark/INDEX.md` → topic "อายุและการต่ออายุ" → `s053.md`–`s056.md`.

Answer (public style): state the term and the renewal window exactly as
written in มาตรา 53–54, then the consequence of missing it (มาตรา 55–56),
then `อ้างอิง: พ.ร.บ.เครื่องหมายการค้า พ.ศ. 2534 มาตรา 53–56` and the
note that the actual renewal fee is set by กฎกระทรวง.
