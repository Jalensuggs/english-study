"""核对短语书每道练习：答案里的小题号，在网页上是不是都有对应的、能自动判分的空。

用法: python3 scripts/check_pv.py
判分规则和网页一致（web/pv.js 的 gradeKey）：
  一个小题一个空 → 空的编号对上就能判；
  一个小题几个空（答案写成 "clock, clock"）→ 空的个数要和答案的个数一样；
  选择题 → 这个小题下面要有 a) b) c) 选项。
对不上的会列出来，多半是 OCR 把题号或者填空的点漏掉了，可以在
content-src/pv/ocr-fixes.json 里按位置补，再运行 python3 scripts/build_pv.py。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from pv_layout import answer_parts  # noqa: E402


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[.,!?;:]+$", "", s.lower().replace("’", "'"))).strip()


def grade_key(md):
    """答案 -> {小题号: [可接受的答案]}；不是短答案格式（要自己对照）时返回 None。和 pv.js 一致。"""
    if not md:
        return None
    lines = [l.strip() for l in md.split("\n") if l.strip()]
    if not lines or any(re.match(r"^[*|>]", l) or re.search(r"suggested|possible", l, re.I) for l in lines):
        return None
    out, parts = {}, {}
    for line in lines:
        for part in re.split(r"\s+·\s+", line):
            m = re.match(r"^(\d+)\.?\s+(.+)$", part)
            if not m:
                return None
            ans = re.sub(r"\([^)]*\)", " ", m.group(2)).replace("*", "").strip()
            alts = [norm(a) for a in re.split(r"\s*/\s*|\s+or\s+", ans) if norm(a)]
            if not alts or any(len(a.split()) > 4 for a in alts):
                return None
            out[m.group(1)] = alts
            n = answer_parts(m.group(2))
            parts[m.group(1)] = n if n > 1 else 0
    return out, parts


def blank_numbers(sec):
    """这道练习里每个空算第几小题（和 pv.js 的 inline 一样）。"""
    nums, item = [], ""
    for line in sec.split("\n"):
        t = line.strip()
        m = re.match(r"^(\d+)\.\s+(.*)$", t)
        body = m.group(2) if m else t
        if m:
            item = m.group(1)
        chunks = body.split("|") if t.startswith("|") else [body]
        for c in chunks:
            bits = re.split(r"(\{__?\})", c)
            count = sum(1 for b in bits if b in ("{_}", "{__}"))
            for i, b in enumerate(bits):
                if b not in ("{_}", "{__}"):
                    continue
                nxt = re.match(r"^\s*\((\d+)\)", bits[i + 1] if i + 1 < len(bits) else "")
                nums.append(nxt.group(1) if nxt else (item if count == 1 and m else ""))
    return nums


def item_blanks(sec):
    out = {}
    for line in sec.split("\n"):
        m = re.match(r"^(\d+)\.\s+(.*)$", line.strip())
        if m:
            out[m.group(1)] = len(re.findall(r"\{__?\}", m.group(2)))
    return out


def mcq_items(sec):
    out, item = set(), None
    for line in sec.split("\n"):
        t = line.strip()
        m = re.match(r"^(\d+)\.\s", t)
        if m:
            item = m.group(1)
        elif item and re.match(r"^a\)\s", t):
            out.add(item)
    return out


def main():
    total = ok = 0
    for u in range(1, 71):
        f = ROOT / f"content/pv/{u:02d}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        body = d["doc"].split("## Exercises", 1)
        if len(body) < 2:
            continue
        secs = re.split(r"^### (\d+\.\d+)", body[1], flags=re.M)
        for i in range(1, len(secs), 2):
            ex, sec = secs[i], secs[i + 1]
            key = grade_key(d["keyEx"].get(ex, ""))
            if not key:
                continue
            key, parts = key
            total += 1
            nums, counts, mcq = blank_numbers(sec), item_blanks(sec), mcq_items(sec)
            missing = [q for q in key if not (q in mcq or nums.count(q) == 1
                                              or (parts.get(q) and (counts.get(q) == parts[q]
                                                                    or nums.count(q) == parts[q])))]
            if missing:
                print(f"{ex}: 判不了第 {','.join(missing)} 题（空的编号 {nums}）")
            else:
                ok += 1
    print(f"能自动判分的练习 {total} 道，题号都对得上的 {ok} 道")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
