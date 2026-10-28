"""Copy skills from .agents/skills/ (used by Codex) to .claude/skills/ (used by
Claude Code).

.agents/skills/ is the source of truth. Copies are used instead of symlinks
because Git on Windows often checks symlinks out as plain text files.

Usage:
    python scripts/sync_skills.py          # make .claude/skills match
    python scripts/sync_skills.py --check  # exit 1 if they differ (for CI)
"""

import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, ".agents", "skills")
DST = os.path.join(ROOT, ".claude", "skills")


def differs(a, b):
    if os.path.islink(b) or not os.path.isdir(b):
        return True
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return True
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return True
    return any(differs(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)


def remove(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def main():
    check = "--check" in sys.argv
    skills = sorted(d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d)))
    stale = sorted(d for d in os.listdir(DST) if d not in skills) if os.path.isdir(DST) else []
    changed = [s for s in skills if differs(os.path.join(SRC, s), os.path.join(DST, s))]

    if check:
        for s in changed:
            print(f"out of date: .claude/skills/{s}")
        for s in stale:
            print(f"not in .agents/skills: .claude/skills/{s}")
        if changed or stale:
            print("run: mise run skills:sync")
            sys.exit(1)
        print(f"{len(skills)} skills in sync")
        return

    os.makedirs(DST, exist_ok=True)
    for s in changed:
        remove(os.path.join(DST, s))
        shutil.copytree(os.path.join(SRC, s), os.path.join(DST, s))
        print(f"synced {s}")
    for s in stale:
        remove(os.path.join(DST, s))
        print(f"removed {s}")
    if not changed and not stale:
        print(f"{len(skills)} skills already in sync")


if __name__ == "__main__":
    main()
