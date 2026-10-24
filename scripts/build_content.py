"""从 OCR 结果生成题库内容。

读取: data/ocr/<书>.json（scripts/ocr.swift 生成），content-src/answers.json（手工核对过的答案）
输出: content/library.json            书 → Test → 阅读篇章 / 写作任务
      content/units/<篇章id>.json      文章段落、题目页码、答案

用法: python3 scripts/build_content.py
"""
import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content"

BOOKS = {
    "c18a": {"title": "剑桥雅思 18", "short": "剑18", "type": "A"},
    "c19a": {"title": "剑桥雅思 19", "short": "剑19", "type": "A"},
    "c11g": {"title": "剑桥雅思 11 · G类", "short": "剑11G", "type": "G"},
    "c13g": {"title": "剑桥雅思 13 · G类", "short": "剑13G", "type": "G"},
}

_dict = sqlite3.connect(ROOT / "data/dict.db")


def is_word(w):
    return _dict.execute("SELECT 1 FROM dict WHERE word = ? COLLATE NOCASE", (w,)).fetchone() is not None


# ---------------------------------------------------------------- 清理

JUNK_RE = re.compile(r"ieltstep|tstep\.com|ieltst|irlanguage|polcet|polce|books-here|more books visit|ti[^ ]{0,3}ng anh|r[^ ]{0,3}ng anh|https?://|www\.", re.I)
NONLATIN_RE = re.compile(r"[؀-ۿ]")  # 波斯语水印
RUNNING_HEAD_RE = re.compile(r"^(Test ?\d|Reading|Listening|Writing|Speaking|\d{1,3}|[\W_]{1,3})$", re.I)


def clean_text(t):
    t = t.replace("­", "")
    lines = [l.strip() for l in t.split("\n")]
    out = ""
    for l in lines:
        if not l:
            continue
        if not out:
            out = l
            continue
        if out.endswith("-") and not out.endswith(" -") and l[:1].islower():
            # 行尾断词：exam- / ple -> example；但 so-called 这种本来就有连字符的保留
            head = re.search(r"([A-Za-z]+)-$", out)
            tail = re.match(r"([A-Za-z]+)", l)
            if head and tail and is_word(head.group(1) + tail.group(1)) and not is_word(head.group(1) + "-" + tail.group(1)):
                out = out[:-1] + l
            else:
                out = out + l
        else:
            out += " " + l
    out = re.sub(r"\s+", " ", out).strip()
    out = out.replace(" ,", ",").replace("‘ ", "‘").replace(" ’", "’")
    return out


def is_junk(p):
    t = p["t"].strip()
    if not t or JUNK_RE.search(t) or NONLATIN_RE.search(t):
        return True
    if RUNNING_HEAD_RE.match(t) and (p["y"] < 0.08 or p["y"] > 0.9 or len(t) < 9):
        return True
    return False


def page_paras(page):
    ps = [dict(p, t=clean_text(p["t"])) for p in page["paras"]]
    return [p for p in ps if not is_junk(p)]


# ---------------------------------------------------------------- 识别结构

Q_RE = re.compile(r"^Questions?\s+(\d+)\s*(?:[-–—]|and|to)\s*(\d+)|^Questions?\s+(\d+)\b", re.I)
READ_INTRO_RE = re.compile(r"^Read the .{0,80}(below|on pages?|following).{0,40}Questions", re.I)
SPEND_RE = re.compile(r"^You should spend about", re.I)


def find_structure(pages, btype):
    """返回 [(test号, 篇章号, 起始页, 题号起, 题号止)] 和写作页、答案页、范文页。"""
    units, writing = [], {}
    test = 0
    in_reading = False
    for page in pages:
        n = page["page"]
        texts = [p["t"] for p in page_paras(page)]
        joined = " | ".join(texts)
        if btype == "A":
            for t in texts:
                m = re.match(r"^READING PASSAGE (\d)", t)
                if m:
                    k = int(m.group(1))
                    if k == 1:
                        test += 1
                    units.append({"test": test, "n": k, "start": n})
        else:
            # "READING" 大标题会被当成页眉过滤掉，所以这里看原始段落
            if any(re.sub(r"[^A-Z]", "", p["t"]) == "READING" for p in page["paras"]) and not in_reading:
                in_reading = True
                test += 1
            for i, t in enumerate(texts):
                m = re.match(r"^SECTION (\d)", t)
                if m and in_reading:
                    units.append({"test": test, "n": int(m.group(1)), "start": n})
        for t in texts:
            m = re.match(r"^WRITING TASK ([12])$", t.strip())
            if m and test and test not in writing.get("_done", set()):
                writing.setdefault(test, {})[int(m.group(1))] = n
                in_reading = False
        if re.search(r"Listening and Reading answer key", joined, re.I):
            writing.setdefault("_keys", []).append(n)
        m = re.search(r"TEST (\d), WRITING TASK ([12])", joined)
        if m:
            writing.setdefault("_samples", {}).setdefault(int(m.group(1)), {})[int(m.group(2))] = n
    keys = writing.pop("_keys", [])
    samples = writing.pop("_samples", {})
    return units, writing, keys, samples


# ---------------------------------------------------------------- 提取一篇

LABEL_LINE_RE = re.compile(r"^([A-J])[l1|I.:]?$")


def raw_lines(p):
    return [l.strip() for l in p["t"].split("\n") if l.strip()]


def line_h(p):
    return p["h"] / max(1, len(raw_lines(p)))


def similar(a, b):
    a, b = a.lower()[:40], b.lower()[:40]
    return difflib.SequenceMatcher(None, a, b).ratio()


def page_pitch(page):
    """这一页正文的行距（相邻两行的 y 差），用来判断段间距和字母位置。"""
    ls = sorted((l for l in page.get("lines", []) if len(l["t"]) > 30), key=lambda l: l["y"])
    diffs = sorted(b["y"] - a["y"] for a, b in zip(ls, ls[1:]) if 0.008 < b["y"] - a["y"] < 0.035)
    return diffs[len(diffs) // 2] if diffs else 0.019


def split_at(text, frac):
    """在大约 frac 比例的位置、最近的句子边界处切开。"""
    pos = int(len(text) * frac)
    best = None
    for m in re.finditer(r"[.!?’”\"')]\s+(?=[A-Z‘“\"'])", text):
        d = abs(m.end() - pos)
        if best is None or d < best[0]:
            best = (d, m.end())
    if best and best[0] < 220:
        return text[:best[1]].strip(), text[best[1]:].strip()
    return text, ""


def is_two_column(page):
    ls = [l for l in page.get("lines", []) if len(l["t"]) > 25]
    right = [l for l in ls if 0.45 < l["x"] < 0.6 and l["w"] < 0.5]
    left = [l for l in ls if l["x"] < 0.2 and l["x"] + l["w"] < 0.55]
    return len(right) >= 8 and len(left) >= 8


def two_column_blocks(page):
    """左右两栏的页面：用逐行识别结果，先左栏后右栏，行距变大就是新段落。"""
    pitch = page_pitch(page)
    lines = [l for l in page.get("lines", []) if not is_junk(dict(l, t=l["t"].strip()))]
    hs = sorted(l["h"] for l in lines if len(l["t"]) > 25)
    med = hs[len(hs) // 2] if hs else 0.015
    col_top = min((l["y"] for l in lines if 0.45 < l["x"] < 0.6 and len(l["t"]) > 25), default=0)
    head = sorted((l for l in lines if l["y"] < col_top - 0.005), key=lambda l: l["y"])
    left = sorted((l for l in lines if l["y"] >= col_top - 0.005 and l["x"] < 0.45), key=lambda l: l["y"])
    right = sorted((l for l in lines if l["y"] >= col_top - 0.005 and l["x"] >= 0.45), key=lambda l: l["y"])
    out = []
    for l in head:
        big = l["h"] > med * 1.3
        if out and big == out[-1]["title"] and l["y"] - out[-1]["_y"] < pitch * (2.2 if big else 1.45):
            out[-1]["t"] += "\n" + l["t"].strip()
        else:
            out.append({"t": l["t"].strip(), "label": None, "page": page["page"], "title": big})
        out[-1]["_y"] = l["y"]
    for col in (left, right):
        cur, prev_y = [], None
        for l in col:
            if prev_y is not None and l["y"] - prev_y > pitch * 1.45 and cur:
                out.append({"t": "\n".join(cur), "label": None, "page": page["page"], "title": False})
                cur = []
            cur.append(l["t"].strip())
            prev_y = l["y"]
        if cur:
            out.append({"t": "\n".join(cur), "label": None, "page": page["page"], "title": False})
    return out


def page_blocks(page):
    """一页里的正文块。
    1. 上下紧挨、左对齐的两块是同一段（Vision 有时把一段切成两段）
    2. 左边距单独的字母 A/B/C… 标记段落开头（来自行识别 + 段落识别）；字母在段中间就切开
    3. 字号明显大的行是标题"""
    if is_two_column(page) and not page.get("columns"):
        body = [q for q in page["paras"] if len(q["t"]) > 60]
        columnar = all(q["x"] + q["w"] < 0.55 or q["x"] > 0.44 for q in body)
        if not columnar:
            return two_column_blocks(page)
        # 段落识别没串栏：按"先左栏、再右栏"重新排序
        col_top = min((q["y"] for q in body if q["x"] > 0.44), default=0)
        def order(q):
            if q["y"] < col_top - 0.005 and q["x"] + q["w"] > 0.5:
                return (0, q["y"])  # 栏上方横跨整页的部分（标题等）
            return (1 if q["x"] < 0.44 else 2, q["y"])
        page = dict(page, paras=sorted(page["paras"], key=order))
    pitch = page_pitch(page)
    paras, marks = [], []
    for p in page["paras"]:
        t = re.sub(r"^[•·▪●]\s*", "", p["t"].strip())
        m = LABEL_LINE_RE.match(t)
        if m:
            marks.append((p["y"], m.group(1), p["x"]))
            continue
        q = dict(p, t=t)
        if is_junk(dict(q, t=clean_text(t))):
            continue
        paras.append(q)
    for l in page.get("lines", []):
        m = LABEL_LINE_RE.match(l["t"].strip())
        if m:
            marks.append((l["y"], m.group(1), l["x"]))
    # 文字层的字母要求明显在正文左边（避免把行首的冠词 a 当成字母）
    body_x = sorted(q["x"] for q in paras if len(q["t"]) > 150 and not re.match(r"^[A-J]\s", q["t"]))
    body_x = body_x[len(body_x) // 2] if body_x else 0.1
    for l in page.get("tl_marks", []):
        if l["x"] < body_x - 0.02:
            marks.append((l["y"], l["t"], l["x"]))
    hs = sorted(l["h"] for l in page.get("lines", []) if len(l["t"]) > 40)
    med = hs[len(hs) // 2] if hs else 0.015

    def big_line(text, y):
        """返回和这段开头匹配的、字号偏大的那一行文字（标题），没有就 None。"""
        best = None
        for l in page.get("lines", []):
            if abs(l["y"] - y) < 0.03 and len(l["t"].strip()) > 3:
                r = similar(l["t"], text[:len(l["t"])])
                if r > 0.75 and (best is None or r > best[0]):
                    best = (r, l)
        if best and best[1]["h"] > med * 1.3:
            return best[1]["t"].strip()
        return None

    merged = []
    for p in paras:
        if merged:
            a = merged[-1]
            gap = p["y"] - (a["y"] + a["h"])
            # 段首带字母的块（"B Ongoing research…"）左边界在字母处，比正文靠左
            same_col = abs(p["x"] - a["x"]) < 0.02 or (re.match(r"^[A-J]\s", a["t"]) and 0.02 <= p["x"] - a["x"] < 0.08)
            starts_label = any(abs(my - p["y"]) < 0.7 * pitch and mx < p["x"] for my, _, mx in marks)
            if same_col and not starts_label and -0.3 * pitch < gap < 0.45 * pitch \
                    and not a["t"].rstrip().endswith(":") and len(a["t"]) > 30 \
                    and not Q_RE.match(p["t"]) and not READ_INTRO_RE.match(p["t"]) \
                    and not big_line(a["t"], a["y"]):
                a["t"] = a["t"] + "\n" + p["t"]
                a["h"] = p["y"] + p["h"] - a["y"]
                continue
        merged.append(dict(p))
    # 每段的字母（可能有多个：Vision 把两个字母段合成了一段）
    cuts = {i: [] for i in range(len(merged))}
    seen = set()
    for y, letter, x in sorted(marks):
        if (letter, round(y, 2)) in seen:
            continue
        seen.add((letter, round(y, 2)))
        for i, p in enumerate(merged):
            if x < p["x"] + 0.01 and p["y"] - 0.7 * pitch <= y <= p["y"] + p["h"] - 0.3 * pitch:
                frac = max(0.0, (y - p["y"]) / p["h"]) if p["h"] else 0
                cuts[i].append((0.0 if y - p["y"] < 0.7 * pitch else frac, letter))
                break
    out = []
    for i, p in enumerate(merged):
        text = p["t"]
        title = big_line(text, p["y"])
        if title and len(title.split()) <= 16:
            k = len(title)
            out.append({"t": text[:k], "label": None, "page": page["page"], "title": True})
            text = text[k:].lstrip("\n ")
            if not text:
                continue
        pieces = []
        rest, done = text, 0.0
        for frac, letter in sorted(cuts[i]):
            if frac <= 0.0 or not pieces and frac < 0.05:
                pieces.append([letter, None])
                continue
            # 在剩余文字里按比例切
            local = (frac - done) / (1 - done) if done < 1 else 0
            head, tail = split_at(rest, local)
            if pieces:
                pieces[-1][1] = head
            else:
                pieces.append([None, head])
            pieces.append([letter, None])
            rest, done = tail, frac
        if pieces:
            pieces[-1][1] = rest
        else:
            pieces = [[None, rest]]
        for letter, t in pieces:
            if t and t.strip():
                out.append({"t": t, "label": letter, "page": page["page"], "title": False})
    return out


def extract_unit(pages_by_no, start, end, qrange, btype):
    """start..end 页（含）。返回 (blocks, qpages)。"""
    raw, qpages = [], []
    q_from, q_to = qrange
    for n in range(start, end + 1):
        page = pages_by_no[n]
        skip = False
        has_q = False
        for b in page_blocks(page):
            t = clean_text(b["t"])
            if re.match(r"^(READING PASSAGE \d|READING|SECTION \d.*)$", t) or SPEND_RE.match(t):
                continue
            m = Q_RE.match(t)
            if m:
                a = int(m.group(1) or m.group(3))
                bq = int(m.group(2) or a)
                if (a, bq) == (q_from, q_to) and not has_q:
                    continue  # 篇章标题里的 Questions 28-40，不是题目
                skip = True
                has_q = True
                continue
            if READ_INTRO_RE.match(t):
                skip = False
                continue
            if skip:
                continue
            raw.append(dict(b, t=t))
        if has_q:
            qpages.append(n)
    fix_labels(raw)
    return shape_blocks(raw, btype), qpages


def fix_labels(raw):
    """段落字母应该是 A、B、C… 连续的：
    - 补上合并在段首的字母（"A When one mentions…"），去掉重复的（"B B Although…"）
    - 去掉不合顺序的
    - 中间漏认的字母：两个字母之间没字母的段落数正好等于缺的字母数，就按顺序补上"""
    expected = "A"
    for b in raw:
        if b["label"]:
            if b["t"].startswith(b["label"] + " ") and b["t"][2:3].isupper():
                b["t"] = b["t"][2:]
            if b["label"] < expected:
                b["label"] = None
            else:
                expected = chr(ord(b["label"]) + 1)
            continue
        m = re.match(r"^([A-J])\s+(?=[A-Z‘“\"'])", b["t"])
        if m and expected <= m.group(1) <= chr(ord(expected) + 2) and len(b["t"]) > 80:
            b["label"] = m.group(1)
            b["t"] = b["t"][2:]
            expected = chr(ord(m.group(1)) + 1)
    idx = [i for i, b in enumerate(raw) if b["label"]]
    if len(idx) < 3:
        for b in raw:
            b["label"] = None
        return

    def body(i):
        b = raw[i]
        return not b["t"].startswith("*") and not b.get("title") and len(b["t"].split()) > 12

    # 中间缺的
    for a, c in zip(idx, idx[1:]):
        missing = ord(raw[c]["label"]) - ord(raw[a]["label"]) - 1
        between = [i for i in range(a + 1, c) if body(i)]
        if missing > 0 and len(between) == missing:
            for k, i in enumerate(between):
                raw[i]["label"] = chr(ord(raw[a]["label"]) + 1 + k)
    # 开头缺的（第一个认出的字母不是 A）
    first = idx[0]
    missing = ord(raw[first]["label"]) - ord("A")
    before = [i for i in range(0, first) if body(i)]
    if missing > 0 and len(before) >= missing:
        for k, i in enumerate(before[-missing:]):
            raw[i]["label"] = chr(ord("A") + k)


def shape_blocks(raw, btype):
    """把原始段落整理成 title / sub / h / p(带字母) / note。"""
    out = []
    for i, b in enumerate(raw):
        t = b["t"]
        label = b.get("label")
        if not t:
            continue
        words = len(t.split())
        prev = raw[i - 1] if i else None
        # 上一段没有结束（没句号），这一段是它的后半截（常见于跨页） -> 合并
        if out and out[-1]["type"] == "p" and not label and not b.get("title") \
                and not re.search(r"[.!?:’”\"')]$", out[-1]["text"]):
            out[-1]["text"] += " " + t
            continue
        if t.startswith("*") or re.match(r"^Glossary", t):
            out.append({"type": "note", "text": t})
        elif not out and (b.get("title") or words <= 16):
            out.append({"type": "title", "text": t})
        elif len(out) == 1 and out[0]["type"] == "title" and words <= 45 and not label:
            out.append({"type": "sub", "text": t})
        elif (b.get("title") or (words <= 9 and not re.search(r"[.,;!?]$", t))) and not label:
            out.append({"type": "h", "text": t})
        else:
            blk = {"type": "p", "text": t}
            if label:
                blk["label"] = label
            out.append(blk)
    return out


def writing_prompt(pages_by_no, n, task):
    texts = [p["t"] for p in page_paras(pages_by_no[n])]
    out, on = [], False
    for t in texts:
        if re.match(rf"^WRITING TASK {task}$", t):
            on = True
            continue
        if re.match(r"^WRITING TASK \d$|^SPEAKING|^PART 1", t) and on:
            break
        if on and not SPEND_RE.match(t) and not re.match(r"^Write at least", t):
            out.append(t)
    return out


# ---------------------------------------------------------------- 主流程

def load_pages(bid):
    """读 OCR 结果；左右两栏的页面用 data/ocr/cols/ 里左右分开识别的结果替换。"""
    pages = json.loads((ROOT / f"data/ocr/{bid}.json").read_text())
    by_no = {p["page"]: p for p in pages}
    for left_file in sorted((ROOT / "data/ocr/cols").glob(f"{bid}-*-L.json")):
        L = {p["page"]: p for p in json.loads(left_file.read_text())}
        R = {p["page"]: p for p in json.loads(Path(str(left_file)[:-6] + "R.json").read_text())}
        for n in L:
            orig = by_no[n]
            # 栏顶 = 左右两半在同一高度都有文字的第一行
            ll = [l for l in L[n]["lines"] if len(l["t"]) > 15]
            rl = [l for l in R[n]["lines"] if len(l["t"]) > 15]
            tops = [a["y"] for a in ll if any(abs(a["y"] - b["y"]) < 0.008 for b in rl)]
            # 横跨两栏的标题行也会被切成"两边都有"，要求下面紧跟着也是两边都有
            tops.sort()
            def run_ok(i):
                seq = tops[i:i + 6]
                return len(seq) == 6 and all(b - a < 0.03 for a, b in zip(seq, seq[1:]))
            col_top = next((t for i, t in enumerate(tops) if run_ok(i)), 0) - 0.008
            head = [q for q in orig["paras"] if q["y"] < col_top]
            lcol = sorted((q for q in L[n]["paras"] if q["y"] >= col_top), key=lambda q: q["y"])
            rcol = sorted((q for q in R[n]["paras"] if q["y"] >= col_top), key=lambda q: q["y"])
            lines = [l for l in orig["lines"] if l["y"] < col_top] + L[n]["lines"] + R[n]["lines"]
            by_no[n] = {"page": n, "paras": head + lcol + rcol, "lines": lines, "columns": True}
    # PDF 自带文字层（有的书有）：左边距的单个字母，作为段落字母的第三个来源
    try:
        import fitz
        doc = fitz.open(ROOT / f"books/{bid}.pdf")
        for n, page in by_no.items():
            pg = doc[n - 1]
            W, H = pg.rect.width, pg.rect.height
            marks = []
            for x0, y0, x1, y1, w, *_ in pg.get_text("words"):
                if re.fullmatch(r"[A-Ja-j]", w) and x0 / W < 0.2:
                    marks.append({"t": w.upper(), "x": x0 / W, "y": y0 / H, "w": (x1 - x0) / W, "h": (y1 - y0) / H})
            page["tl_marks"] = marks
    except Exception as e:  # noqa
        print("文字层读取失败", bid, e)
    return [by_no[k] for k in sorted(by_no)]


def main():
    answers = json.loads((ROOT / "content-src/answers.json").read_text(encoding="utf-8")) \
        if (ROOT / "content-src/answers.json").exists() else {}
    (OUT / "units").mkdir(parents=True, exist_ok=True)
    library = {"books": []}
    for bid, meta in BOOKS.items():
        pages = load_pages(bid)
        by_no = {p["page"]: p for p in pages}
        units, writing, keys, samples = find_structure(pages, meta["type"])
        book = {"id": bid, **meta, "tests": []}
        ranges_a = {1: (1, 13), 2: (14, 26), 3: (27, 40)}
        for idx, u in enumerate(units):
            nxt = units[idx + 1]["start"] if idx + 1 < len(units) and units[idx + 1]["test"] == u["test"] \
                else writing.get(u["test"], {}).get(1)
            end = (nxt - 1) if nxt else u["start"] + 4
            uid = f"{bid}-t{u['test']}-r{u['n']}"
            ans = answers.get(uid, {})
            if meta["type"] == "A":
                qr = ranges_a[u["n"]]
            else:
                head = [p["t"] for p in page_paras(by_no[u["start"]])]
                m = next((Q_RE.search(t) for t in head if Q_RE.search(t)), None)
                qr = (int(m.group(1)), int(m.group(2))) if m and m.group(2) else (0, 0)
                if ans:
                    nums = sorted(int(k.split("-")[0]) for k in ans)
                    qr = (nums[0], max(int(x) for k in ans for x in k.split("-")))
            blocks, qpages = extract_unit(by_no, u["start"], end, qr, meta["type"])
            title = next((b["text"] for b in blocks if b["type"] == "title"), f"Section {u['n']}")
            unit = {"id": uid, "book": bid, "test": u["test"], "n": u["n"], "kind": "reading",
                    "label": f"{'Passage' if meta['type'] == 'A' else 'Section'} {u['n']}",
                    "title": title, "q": list(qr), "pages": list(range(u["start"], end + 1)),
                    "qpages": qpages, "blocks": blocks, "answers": ans}
            qfile = ROOT / "content-src/questions" / f"{uid}.md"
            if qfile.exists():
                unit["questions"] = qfile.read_text(encoding="utf-8")
            (OUT / "units" / f"{uid}.json").write_text(json.dumps(unit, ensure_ascii=False, indent=1))
            while len(book["tests"]) < u["test"]:
                book["tests"].append({"n": len(book["tests"]) + 1, "reading": [], "writing": []})
            book["tests"][u["test"] - 1]["reading"].append(
                {"id": uid, "n": u["n"], "label": unit["label"], "title": title, "q": list(qr),
                 "words": sum(len(b["text"].split()) for b in blocks), "hasAnswers": bool(ans)})
            print(f"{uid}: 页 {u['start']}-{end} 题目页 {qpages} 题 {qr} 段落 {len(blocks)} 「{title[:40]}」")
        for t, tasks in writing.items():
            if not isinstance(t, int) or t > len(book["tests"]):
                continue
            for task, n in sorted(tasks.items()):
                wid = f"{bid}-t{t}-w{task}"
                sp = samples.get(t, {}).get(task)
                spages = [sp] if sp else []
                # 范文可能跨两页
                if sp and sp + 1 in by_no and not any(
                        re.search(r"TEST \d, WRITING TASK", p["t"]) for p in page_paras(by_no[sp + 1])) \
                        and any("Sample Writing" in p["t"] or "SAMPLE ANSWER" in p["t"].upper() for p in page_paras(by_no[sp])):
                    nxt_texts = " ".join(p["t"] for p in page_paras(by_no[sp + 1]))
                    if "answer sheet" not in nxt_texts.lower() and "Acknowledgements" not in nxt_texts:
                        spages.append(sp + 1)
                unit = {"id": wid, "book": bid, "test": t, "task": task, "kind": "writing",
                        "prompt": writing_prompt(by_no, n, task), "pages": [n], "samplePages": spages}
                (OUT / "units" / f"{wid}.json").write_text(json.dumps(unit, ensure_ascii=False, indent=1))
                book["tests"][t - 1]["writing"].append({"id": wid, "task": task})
        book["answerKeyPages"] = keys
        library["books"].append(book)
        print(bid, "答案页", keys, "范文", samples)
    (OUT / "library.json").write_text(json.dumps(library, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
