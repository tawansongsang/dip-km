"""Run the evaluation questions through an agent CLI and grade the answers.

Usage:
    python evals/run.py run --agent claude [--model M] [--only ID,ID] [--jobs 4]
    python evals/run.py run --agent codex
    python evals/run.py grade evals/results/<run-dir>   # regrade saved answers

Each run writes evals/results/<timestamp>-<agent>/ with one <id>.md per answer,
results.json and summary.md. Grading is deterministic (citations and required
facts), so it can be rerun after changing questions.yaml without calling the
agent again. Read the failed answers yourself: a failed check can be a wrong
check, not a wrong answer.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = os.path.join(ROOT, "evals", "questions.yaml")
RESULTS = os.path.join(ROOT, "evals", "results")
TIMEOUT = 600

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
NOT_FOUND = ["ไม่พบ", "ไม่มีข้อมูล", "ยังไม่มีข้อมูล", "not found",
             "not in the knowledge base", "not available in the knowledge base",
             "does not contain", "doesn't contain", "doesn't have", "does not have"]

CLAUDE_TOOLS = "Read,Grep,Glob,Skill,Bash(grep:*),Bash(ls:*),Bash(find:*),Bash(cat:*)"


# --- running agents ----------------------------------------------------------

def ask_claude(question, model, workdir):
    cmd = ["claude", "-p", question, "--output-format", "json",
           "--allowedTools", CLAUDE_TOOLS, "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                         timeout=TIMEOUT)
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return out.stdout + out.stderr, {}
    meta = {k: data.get(k) for k in ("total_cost_usd", "num_turns", "duration_ms")}
    return data.get("result") or "", meta


def ask_codex(question, model, workdir):
    last = os.path.join(workdir, ".codex-last.txt")
    cmd = ["codex", "exec", "--sandbox", "read-only", "--ephemeral",
           "-C", ROOT, "-o", last, question]
    if model:
        cmd[2:2] = ["--model", model]
    start = time.time()
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                         timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    meta = {"duration_ms": int((time.time() - start) * 1000)}
    try:
        with open(last, encoding="utf-8") as f:
            return f.read(), meta
    except FileNotFoundError:
        return out.stdout + out.stderr, meta
    finally:
        if os.path.exists(last):
            os.remove(last)


AGENTS = {"claude": ask_claude, "codex": ask_codex}


# --- grading -----------------------------------------------------------------

def normalize(text):
    text = text.translate(THAI_DIGITS).lower()
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)  # 400,000 -> 400000
    return re.sub(r"\s+", " ", text)


SECTION_NUM = r"\d+(?:/\d+)?(?:\s*(?:ทวิ|ตรี|จัตวา|bis|ter))?"
CITATION = re.compile(
    rf"(?:มาตรา|ม\.|ข้อ|sections?|clauses?|ss?\.|§)\s*({SECTION_NUM}"
    rf"(?:\s*(?:,|และ|and|or|หรือ|–|-|—|ถึง|to)\s*{SECTION_NUM})*)", re.I)


def cited_sections(answer):
    """All มาตรา / ข้อ numbers the answer cites, ranges like 53–56 expanded."""
    found = set()
    text = answer.translate(THAI_DIGITS)
    text = re.sub(r"s0*(\d+)(?:-(\d+))?\.md",
                  lambda m: f"มาตรา {m[1]}" + (f"/{m[2]}" if m[2] else ""), text)
    for group in CITATION.findall(text):
        parts = re.split(r"\s*(,|และ|and|or|หรือ|ถึง|to|–|-|—)\s*", group.lower())
        nums = [p.strip() for i, p in enumerate(parts) if i % 2 == 0]
        seps = [p for i, p in enumerate(parts) if i % 2 == 1]
        for i, n in enumerate(nums):
            n = re.sub(r"\s+", " ", n).replace("bis", "ทวิ").replace("ter", "ตรี")
            found.add(n)
            if i and seps[i - 1] in ("–", "-", "—", "ถึง", "to"):
                lo, hi = nums[i - 1], n
                if lo.isdigit() and hi.isdigit() and int(lo) < int(hi) <= int(lo) + 30:
                    found.update(str(x) for x in range(int(lo), int(hi) + 1))
    return found


def grade(case, answer):
    norm = normalize(answer)
    checks = []
    if case.get("expect_not_found"):
        ok = any(p in norm for p in NOT_FOUND)
        checks.append(("says not found", ok, ""))
    else:
        cited = cited_sections(answer)
        checks.append(("cites a มาตรา", bool(cited), ""))
        for s in case.get("expect_sections", []):
            checks.append((f"cites มาตรา {s}", s in cited, ""))
    for fact in case.get("must_include", []):
        ok = any(normalize(alt) in norm for alt in fact)
        checks.append((f"includes {fact[0]}", ok, " | ".join(fact)))
    for bad in case.get("must_not_include", []):
        checks.append((f"avoids {bad}", normalize(bad) not in norm, ""))
    passed = all(ok for _, ok, _ in checks)
    return {"passed": passed,
            "checks": [{"check": c, "ok": ok, "accepted": a} for c, ok, a in checks]}


# --- reports -----------------------------------------------------------------

def write_answer(run_dir, case, answer, meta):
    with open(os.path.join(run_dir, f"{case['id']}.md"), "w", encoding="utf-8") as f:
        f.write(f"# {case['id']}\n\n**Q ({case['audience']}, {case['lang']}):** "
                f"{case['question']}\n\n**Meta:** {json.dumps(meta)}\n\n---\n\n{answer}\n")


def read_answer(run_dir, case_id):
    with open(os.path.join(run_dir, f"{case_id}.md"), encoding="utf-8") as f:
        return f.read().split("\n---\n\n", 1)[1]


def summarize(run_dir, cases, results):
    passed = sum(r["passed"] for r in results.values())
    lines = [f"# Eval results: {os.path.basename(run_dir)}", "",
             f"**{passed}/{len(results)} passed**", "",
             "| id | audience | lang | result | failed checks |", "|---|---|---|---|---|"]
    for case in cases:
        r = results.get(case["id"])
        if not r:
            continue
        failed = "; ".join(c["check"] for c in r["checks"] if not c["ok"])
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| [{case['id']}]({case['id']}.md) | {case['audience']} | "
                     f"{case['lang']} | {mark} | {failed} |")
    costs = [r["meta"].get("total_cost_usd") for r in results.values()
             if r.get("meta", {}).get("total_cost_usd")]
    if costs:
        lines += ["", f"Total cost: ${sum(costs):.2f}"]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(run_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(run_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(text)
    return passed == len(results)


def load_cases(only=None):
    with open(QUESTIONS, encoding="utf-8") as f:
        cases = yaml.safe_load(f)
    ids = [c["id"] for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"duplicate ids in questions.yaml: {', '.join(sorted(dupes))}")
    if only:
        wanted = set(only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    return cases


def cmd_run(args):
    cases = load_cases(args.only)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(RESULTS, f"{stamp}-{args.agent}")
    os.makedirs(run_dir)
    ask = AGENTS[args.agent]

    def one(case):
        try:
            answer, meta = ask(case["question"], args.model, run_dir)
        except subprocess.TimeoutExpired:
            answer, meta = "(timed out)", {}
        write_answer(run_dir, case, answer, meta)
        r = grade(case, answer)
        r["meta"] = meta
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {case['id']}", flush=True)
        return case["id"], r

    with ThreadPoolExecutor(args.jobs) as pool:
        results = dict(pool.map(one, cases))
    return summarize(run_dir, cases, results)


def cmd_grade(args):
    run_dir = args.run_dir.rstrip("/")
    with open(os.path.join(run_dir, "results.json"), encoding="utf-8") as f:
        old = json.load(f)
    cases = [c for c in load_cases() if c["id"] in old]
    results = {}
    for case in cases:
        r = grade(case, read_answer(run_dir, case["id"]))
        r["meta"] = old[case["id"]].get("meta", {})
        results[case["id"]] = r
    return summarize(run_dir, cases, results)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--agent", choices=AGENTS, default="claude")
    r.add_argument("--model")
    r.add_argument("--only", help="comma-separated question ids")
    r.add_argument("--jobs", type=int, default=4)
    g = sub.add_parser("grade")
    g.add_argument("run_dir")
    args = ap.parse_args()
    ok = cmd_run(args) if args.cmd == "run" else cmd_grade(args)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
