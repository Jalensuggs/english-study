"""把短语书一个单元的 OCR（data/ocr/phrasal-verbs.json）按版面还原成 content-src/pv/NN.md 的格式。

左页是讲解：A/B/C 小节、表格、对话、段落；右页是练习：题号、小题、填空、选项、词库。
OCR 没有粗体信息，讲解里本单元的短语（来自 Mini dictionary）自动加粗。

自动还原难免有错。想手工改某个单元：
  python3 scripts/pv_layout.py 12 > content-src/pv/12.md
改好后运行 python3 scripts/build_pv.py，有 content-src/pv/NN.md 的单元优先用手工版。
"""
import json
import re
import statistics
import sys
from pathlib import Path

FIXES_FILE = Path(__file__).resolve().parent.parent / "content-src/pv/ocr-fixes.json"
OCR_FIXES = json.loads(FIXES_FILE.read_text()) if FIXES_FILE.exists() else {}

PARTICLES = {"about", "above", "across", "after", "against", "ahead", "along", "apart", "around", "aside", "at",
             "away", "back", "before", "behind", "below", "between", "beyond", "by", "down", "for", "forward",
             "from", "in", "into", "of", "off", "on", "onto", "out", "over", "past", "round", "through",
             "to", "together", "towards", "under", "up", "upon", "with", "without"}

IRREGULAR = {
    "be": "was were been being is are", "become": "became", "begin": "began begun", "bite": "bit bitten",
    "blow": "blew blown", "break": "broke broken", "bring": "brought", "build": "built", "burn": "burnt",
    "buy": "bought", "catch": "caught", "choose": "chose chosen", "come": "came", "creep": "crept",
    "cut": "cut", "deal": "dealt", "dig": "dug", "do": "did done does", "draw": "drew drawn",
    "drink": "drank drunk", "drive": "drove driven", "eat": "ate eaten", "fall": "fell fallen", "feel": "felt",
    "fight": "fought", "find": "found", "fly": "flew flown flies", "freeze": "froze frozen", "get": "got gotten",
    "give": "gave given", "go": "went gone goes", "grow": "grew grown", "hang": "hung", "have": "had has",
    "hear": "heard", "hide": "hid hidden", "hit": "hit", "hold": "held", "keep": "kept", "know": "knew known",
    "lay": "laid", "lead": "led", "leave": "left", "let": "let", "lie": "lay lain lying", "light": "lit",
    "lose": "lost", "make": "made", "mean": "meant", "meet": "met", "pay": "paid", "put": "put",
    "read": "read", "ride": "rode ridden", "ring": "rang rung", "rise": "rose risen", "run": "ran",
    "say": "said", "see": "saw seen", "sell": "sold", "send": "sent", "set": "set", "shake": "shook shaken",
    "shoot": "shot", "shut": "shut", "sink": "sank sunk", "sit": "sat", "sleep": "slept", "slide": "slid",
    "speak": "spoke spoken", "spin": "spun", "split": "split", "spring": "sprang sprung", "stand": "stood",
    "stick": "stuck", "sting": "stung", "strike": "struck", "swear": "swore sworn", "sweep": "swept",
    "swing": "swung", "take": "took taken", "tear": "tore torn", "tell": "told", "think": "thought",
    "throw": "threw thrown", "wake": "woke woken", "wear": "wore worn", "win": "won", "wind": "wound",
    "write": "wrote written",
}


def verb_forms(v):
    forms = {v}
    forms |= set(IRREGULAR.get(v, "").split())
    if v.endswith("e"):
        forms |= {v + "s", v + "d", v[:-1] + "ing"}
    elif re.search(r"[^aeiou]y$", v):
        forms |= {v[:-1] + "ies", v[:-1] + "ied", v + "ing"}
    else:
        es = "es" if re.search(r"(s|sh|ch|x|z|o)$", v) else "s"
        forms |= {v + es, v + "ed", v + "ing"}
        if re.search(r"[^aeiou][aeiou][bdgklmnprt]$", v):  # stop -> stopped, stopping
            forms |= {v + v[-1] + "ed", v + v[-1] + "ing"}
    return forms


def bolder(keys):
    """本单元的短语 -> 一个函数，把句子里出现的短语加粗（可分开的 make Jim out 也认）。"""
    pats = []
    for k in sorted(set(keys), key=lambda k: (-len(k), k)):
        words = k.split()
        if len(words) < 2 or not all(w in PARTICLES for w in words[1:]) or not re.fullmatch(r"[a-z]+", words[0]):
            continue
        verb = "|".join(sorted(verb_forms(words[0]), key=len, reverse=True))
        parts = r"\s+".join(words[1:])
        # 动词 + 最多三个词（宾语）+ 小品词
        pats.append(re.compile(rf"\b({verb})\b((?:\s+[\w'’-]+){{0,3}}?)\s+({parts})\b", re.I))
    def rep(m):
        if m.group(2):
            return f"**{m.group(1)}**{m.group(2)} **{m.group(3)}**"
        return f"**{m.group(1)} {m.group(3)}**"

    def apply(s):
        for p in pats:
            # 已经加粗的部分不再动（move in together 里面的 move in）
            s = "".join(x if x.startswith("**") else p.sub(rep, x) for x in re.split(r"(\*\*.+?\*\*)", s))
        return s
    return apply


# ---------------------------------------------------------------- 版面：行

def tidy(t):
    t = t.replace("­", "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"(?<=[a-z,] )1(?= [a-z])", "I", t)  # OCR 把 I 认成 1
    t = re.sub(r"\bjim\b", "Jim", t).replace("(поил)", "(noun)")
    return re.sub(r"\s+", " ", t).strip()


def rows(page):
    """OCR 的行 -> 版面上的一行一行；每行是按 x 排好的若干段 {x, r, t}。"""
    lines = []
    fixes = OCR_FIXES.get(str(page["page"]), [])
    for l in page["lines"]:
        t = l["t"].strip()
        if not t or l["x"] < 0.07 or l["x"] > 0.97:  # 对面页透过来的字
            continue
        if re.fullmatch(r"\d{1,3}[|l]?|English Phrasal Verbs in Use|Exercises", t) and (l["y"] < 0.07 or l["y"] > 0.92):
            continue
        for f in fixes:  # content-src/pv/ocr-fixes.json：手工补上 OCR 漏掉的题号、填空
            if abs(l["y"] - f["y"]) < 0.004 and abs(l["x"] - f["x"]) < 0.006:
                if "replace" in f:
                    t = t.replace(*f["replace"], 1)
                t = f.get("prefix", "") + t + f.get("suffix", "")
        if re.search(r"English Phrasal Verbs in Use", t) and l["y"] > 0.9:
            continue
        lines.append({"x": l["x"], "r": l["x"] + l["w"], "y": l["y"], "h": l["h"], "t": t})
    for f in fixes:  # OCR 整段漏掉的字（选项之类）：按位置补上
        if "add" in f:
            lines.append({"x": f["x"], "r": f["x"] + 0.012 * len(f["add"]), "y": f["y"], "h": 0.013, "t": f["add"]})
    lines.sort(key=lambda l: l["y"] + l["h"] / 2)
    out = []
    for l in lines:
        cy = l["y"] + l["h"] / 2
        if out:
            row = out[-1]
            overlap = any(min(l["r"], s["r"]) - max(l["x"], s["x"]) > 0.5 * min(l["r"] - l["x"], s["r"] - s["x"])
                          for s in row["segs"])  # 上下两行，不是同一行
            if abs(cy - row["cy"]) < 0.55 * min(l["h"], row["h"]) + 0.002 and not overlap:
                row["segs"].append(l)
                row["h"] = max(row["h"], l["h"])
                continue
        out.append({"cy": cy, "y": l["y"], "h": l["h"], "segs": [l]})
    # 没有字的一段：只留下点（点是填空），剩下的符号（• * → = |）是杂点
    for row in out:
        row["segs"] = [s for s in row["segs"]
                       if re.search(r"[A-Za-z\d]", s["t"]) or (s.update(t=re.sub(r"[^.…·]", "", s["t"])) or s["t"])]
    out = [r for r in out if r["segs"] and any(re.search(r"[A-Za-z\d]", s["t"]) for s in r["segs"])]
    for row in out:
        segs = sorted(row["segs"], key=lambda s: s["x"])
        merged = []
        for s in segs:
            if merged and s["x"] - merged[-1]["r"] < 0.012:
                merged[-1] = {"x": merged[-1]["x"], "r": max(merged[-1]["r"], s["r"]), "t": merged[-1]["t"] + " " + s["t"]}
            else:
                merged.append({"x": s["x"], "r": s["r"], "t": s["t"]})
        for i, s in enumerate(merged):
            s["gap"] = s["x"] - merged[i - 1]["r"] if i else 0
            s["t"] = tidy(s["t"])
        row["segs"] = merged
        row["x"], row["r"] = merged[0]["x"], merged[-1]["r"]
    return out


NOTE = re.compile(r"^(['’*°®!\"•^&]|\d{1,2})\s+[a-z(]")  # 脚注：上标编号（OCR 常认成符号）+ 小写开头的释义
NOTE_MARK = re.compile(r"^(['’*°®!\"•^&]|\d{1,2}|[Il])\s+(?=[a-z(])")
HOROSCOPE = re.compile(r"^([A-Z][A-Z ]{2,})\s*\*{3,}\s*(.*)$")  # SCORPIO ********
SPEAKER = re.compile(r"^(?:\d{1,2}\s+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?|[A-Z]{1,2}):$")
LETTER = re.compile(r"^([A-F])(?:\s+(.*))?$")
EXHEAD = re.compile(r"^[\dIlSO]{1,2}\s?[.,·:]\s?[\dIlSOJ|!]{0,2}(?:\s+|$)")


def body_x(rs):
    xs = [round(r["x"], 2) for r in rs if r["r"] - r["x"] > 0.3]
    return statistics.mode(xs) if xs else 0.2


def full_right(rs):
    rights = sorted(r["r"] for r in rs)
    return rights[int(len(rights) * 0.9)] if rights else 0.95


# ---------------------------------------------------------------- 左页：讲解

def section_boxes(image):
    """小节字母 A B C 印在左边的蓝色方块里，OCR 常常认不出来，直接在页面图片上找蓝色方块。"""
    from PIL import Image
    import numpy as np
    a = np.asarray(Image.open(image).convert("RGB")).astype(int)
    h, w, _ = a.shape
    reg = a[:, int(w * 0.11):int(w * 0.20)]
    blue = ((reg[..., 2] - reg[..., 0]) > 25) & (reg[..., 2] < 235)
    frac = blue.mean(axis=1)
    # 方块右边紧挨着的是黑色的小节标题；右边也是蓝色的，是彩色的标题条（比如星座），不是小节方块
    side = a[:, int(w * 0.21):int(w * 0.30)]
    side_blue = (((side[..., 2] - side[..., 0]) > 25) & (side[..., 2] < 235)).mean(axis=1)
    out, start = [], None
    for y, f in enumerate(list(frac) + [0]):
        if f > 0.35 and start is None:
            start = y
        elif f <= 0.35 and start is not None:
            if y - start > 12 and start / h > 0.07 and side_blue[start:y].mean() < 0.2:  # 最上面那个是单元号
                out.append((start / h - 0.006, y / h + 0.006))
            start = None
    return out


def explanation(page, bold, image=None):
    rs = rows(page)
    if rs and rs[0]["y"] < 0.075:
        rs = rs[1:]  # 单元标题
    boxes = section_boxes(image) if image else []
    rs = split_columns(rs, prose=True, breaks=lambda r: any(b[0] <= r["cy"] <= b[1] for b in boxes))
    bx, fr = body_x(rs), full_right(rs)
    out, para, table, dialog, colbox = [], None, None, None, None
    letters = iter("ABCDEFGH")
    notes_n = {}  # 每个分栏块里脚注的编号
    # 哪几栏是脚注：自己有 2 行以上像脚注的；或者同一块里已经有脚注栏、自己也有 1 行的
    note_count = {}
    for r in rs:
        if r.get("col") and NOTE.match(r["segs"][0]["t"]):
            note_count[r["col"]] = note_count.get(r["col"], 0) + 1
    note_blocks = {c[0] for c, n in note_count.items() if n >= 2}
    note_cols = {c for c, n in note_count.items() if n >= 2 or (n >= 1 and c[0] in note_blocks)}

    def local_right(i):
        """第 i 行所在的这段文字的右边线（附近几行、左边对齐的行里最靠右的）。
        方框里、图片旁边的文字比整页窄，不能拿整页的右边线比。"""
        x = rs[i]["x"]
        near = [r["r"] for r in rs[max(0, i - 3):i + 4] if len(r["segs"]) == 1 and abs(r["x"] - x) < 0.03]
        return min(max(near + [rs[i]["segs"][0]["r"]]), fr) - 0.01  # 不比整页的右边线更严

    def end_para():
        nonlocal para
        if para:
            out.append(bold(re.sub(r"^['’] (?=[a-z(])", "1 ", para["t"])))  # 脚注 1 常常认成 '

            out.append("")
            for c in para.get("captions", []):  # 图片旁边的说明文字
                out.extend([bold(c), ""])
        para = None

    def end_table():
        nonlocal table
        if table:
            out.extend(render_table(table, bold))
            out.append("")
        table = None

    def end_dialog():
        nonlocal dialog
        if dialog:
            out.extend("> " + bold(f"**{s}:** {t}") for s, t in dialog)
            out.append("")
        dialog = None

    def end_col():
        nonlocal colbox
        if colbox:
            # 一栏里上下隔开的几块（一段星座运势、一组脚注）各放一个方框
            pieces, cur = [], []
            for line in colbox["raw"]:
                kind_changes = NOTE.match(line[0]) or HOROSCOPE.match(line[0]) or any(NOTE.match(c[0]) for c in cur)
                if cur and line[3] - cur[-1][3] > 0.024 and kind_changes:
                    pieces.append(cur)
                    cur = []
                cur.append(line)
            pieces.append(cur)
            for piece in pieces:
                out.extend("> " + bold(l) for l in col_lines(colbox["col"], piece))
                out.append("")
        colbox = None

    def col_lines(col, raw):
        if col not in note_cols or not any(NOTE.match(t) for t, *_ in raw):
            # 成段的文字（信、星座运势）：Dear …, 和署名、标题另起一行，其余接着上一行
            ls = []
            for t, edge, *_ in raw:
                head = HOROSCOPE.match(t)
                if head:
                    ls.append(f"**{head.group(1).strip()}**")
                    t = head.group(2)
                    if not t:
                        continue
                    ls.append(t)
                elif not ls or ls[-1].endswith(",") or ls[-1].startswith("**") and ls[-1].endswith("**") \
                        or (edge and len(t) < 25 and re.search(r"[.!?]$", ls[-1])):  # 署名
                    ls.append(t)
                else:
                    ls[-1] = join_text(ls[-1], t)
            return ls
        # 脚注：顶着栏的左边线的、或者上一行没写满的，是新的一条；编号认不准，按顺序重新编
        ls, right, prev_r = [], max(r for _, _, r, _ in raw), None
        expect = notes_n.get(col[0], 0) + 1
        for t, edge, r, _ in raw:
            d = re.match(r"^(\d{1,2})\s", t)
            if edge or not ls or prev_r < right - 0.075 or (d and int(d.group(1)) == expect + len(ls)):
                ls.append(t)
            else:
                ls[-1] = join_text(ls[-1], t)
            prev_r = r
        out_ = []
        for t in ls:
            m = NOTE_MARK.match(t)
            k = notes_n.get(col[0], 0) + 1
            if m and m.group(1).isdigit() and int(m.group(1)) >= k:  # 认得出的编号就用书上的
                k = int(m.group(1))
            notes_n[col[0]] = k
            out_.append(f"{k} {t[m.end():] if m else t}")
        return out_

    def end_all():
        end_para(); end_table(); end_dialog(); end_col()

    for i, row in enumerate(rs):
        segs = row["segs"]
        first = segs[0]
        if row.get("col"):
            # 分栏（并排的信、旁边的注释）：每一栏一个方框，按行读
            if not colbox or colbox["col"] != row["col"]:
                end_all()
                colbox = {"col": row["col"], "raw": []}
            colbox["raw"].append((" ".join(s["t"] for s in segs), first["x"] - row["lx"] < 0.012, segs[-1]["r"], row["cy"]))
            continue
        end_col()
        # 小节字母 A B C（在左边的页边）
        lm = LETTER.match(first["t"])
        box = next((b for b in boxes if b[0] <= row["cy"] <= b[1]), None)
        if box or (lm and first["x"] < bx - 0.02 and not boxes):
            if box:
                boxes.remove(box)
            end_all()
            parts = [s["t"] for s in segs]
            if first["x"] < bx - 0.02:  # 方块里的字母（或者认错的字母）
                parts[0] = re.sub(r"^\S{1,2}(\s+|$)", "", parts[0]) if not lm else (lm.group(2) or "")
            out.append(f"## {next(letters)}  {' '.join(parts).strip()}".rstrip())
            out.append("")
            continue
        sp = SPEAKER.match(first["t"])
        if sp and len(segs) > 1:
            end_para(); end_table()
            dialog = dialog or []
            dialog.append([sp.group(1), " ".join(s["t"] for s in segs[1:])])
            continue
        if dialog and len(segs) == 1 and first["x"] > bx + 0.04:
            dialog[-1][1] += " " + first["t"]
            continue
        if len(segs) > 1 and not table and first["r"] - first["x"] > 0.25 and all(
                len(s["t"]) <= 10 and len(s["t"].split()) == 1 for s in segs[1:]):
            segs = [first]  # 旁边插图里的字（ansac、CHECK-1 这种），不要
        lonely = not table and (i + 1 >= len(rs) or len(rs[i + 1]["segs"]) == 1)
        if len(segs) > 1 and lonely and para and abs(first["x"] - para["x"]) < 0.03 and para["r"] > para["edge"] - 0.06 \
                and segs[1]["x"] > para["edge"] - 0.03:
            # 段落的最后一行，旁边是图片说明
            para["t"] = join_text(para["t"], first["t"])
            para["r"] = first["r"]
            para.setdefault("captions", []).append(" ".join(s["t"] for s in segs[1:]))
            continue
        if len(segs) > 1:
            end_para(); end_dialog()
            if table and row["cy"] - table["last"] > 0.06:
                end_table()
            table = table or {"rows": [], "last": 0}
            table["rows"].append((row["cy"], segs))
            table["last"] = row["cy"]
            continue
        if table and first["x"] > bx + 0.03 and row["cy"] - table["last"] < 0.04:
            table["rows"].append((row["cy"], segs))  # 表格里换行的那一格
            table["last"] = row["cy"]
            continue
        end_table(); end_dialog()
        t = first["t"]
        if para and abs(first["x"] - para["x"]) < 0.03 and (para["r"] > para["edge"] - 0.06 or (
                re.match(r"^[a-z]", t) and re.match(r"^[A-Z]", para["t"]) and not re.search(r"[.!?]['\"]?$", para["t"]))) \
                and not re.match(r"^\d\s|^[•-]", t) and not para.get("captions"):
            para["t"] = join_text(para["t"], t)
            para["r"] = first["r"]
            para["edge"] = local_right(i)
        else:
            end_para()
            para = {"t": t, "x": first["x"], "r": first["r"], "edge": local_right(i)}
    end_all()
    return superscripts(out)


# 粗体短语后面紧跟的上标脚注号，OCR 认成了 ' ? ! * ® ° & " 或数字。? ! 后面还接着小写字（句子没完）才算
NOTE_MARK_AFTER_BOLD = re.compile(r"(?<=\*\*)(['’*®°&\"]|\d{1,2}|[?!](?=[.,;:]|\s+[a-z]))(?=[\s,.;:)?!]|$)")


def superscripts(lines):
    """讲解里短语后面的脚注号 OCR 认成了标点（get away! from London、fitted in? at once），看着像标点用错了。
    认不准是第几号，所以直接去掉；脚注就在这段文字下面。"""
    return [l if l.startswith("#") else NOTE_MARK_AFTER_BOLD.sub("", l) for l in lines]


def join_text(a, b):
    m = re.search(r"([A-Za-z]+)-$", a)
    if m and b[:1].islower():
        return a[:-1] + b
    return a + " " + b


def render_table(table, bold):
    # 列：所有格子的左边 x 聚类
    xs = sorted(s["x"] for _, r in table["rows"] for s in r)
    cols = []
    for x in xs:
        if not cols or x - cols[-1][-1] > 0.035:
            cols.append([x])
        else:
            cols[-1].append(x)
    anchors = [min(c) for c in cols]

    def col_of(x):
        return max(i for i, a in enumerate(anchors) if x >= a - 0.02) if x >= anchors[0] - 0.02 else 0

    grid, last = [], -1
    for cy, segs in table["rows"]:
        cells = [""] * len(anchors)
        for s in segs:
            i = col_of(s["x"])
            cells[i] = (cells[i] + " " + s["t"]).strip()
        # 同一格里换行的行距小；表格的下一行隔得远一些
        new_row = bool(cells[0]) and cy - last > 0.0205
        last = cy
        if not grid or new_row:
            grid.append(cells)
        else:
            grid[-1] = [join_text(a, b).strip() if b else a for a, b in zip(grid[-1], cells)]
    # 几乎总是空的一栏（表格上面的图、错位的字带出来的）：并到左边那一栏
    if len(grid) >= 3:
        c = 1
        while c < len(grid[0]):
            if sum(1 for r in grid if r[c]) <= max(1, len(grid) // 4):
                for r in grid:
                    r[c - 1] = (r[c - 1] + " " + r[c]).strip()
                    del r[c]
            else:
                c += 1
    if len(anchors) == 1 or len(grid) == 1:  # 只有一行的不是表格，是隔得比较开的一行字
        return [bold(" ".join(c for c in r if c)) for r in grid]
    out = []
    if len(grid) >= 4 and all(len(c.split()) <= 5 for c in grid[0] + grid[1]) \
            and any(re.search(r"\b[A-Z]{2,}\b", c) for c in grid[0]) \
            and any(len(c.split()) > 5 for r in grid[2:] for c in r):
        out += [" ".join(c for c in grid[0] if c), ""]  # 表头上面还有一行短字（图上的字）：不算表头
        grid = grid[1:]
    for i, r in enumerate(grid):
        cells = [c.replace("|", "/") for c in r]
        out.append("| " + " | ".join(c if i == 0 else bold(c) for c in cells) + " |")
    return out


# ---------------------------------------------------------------- 右页：练习

DOTS = re.compile(r"(?:[.…·,](?:\s?)){2,}[.…·]")


def blanks(t):
    t = re.sub(r"\(\s*\)", "({_})", t)
    t = re.sub(r"(?<=\b[a-z])" + DOTS.pattern, "\x00", t)  # b.... 这种给了首字母的空（字母紧挨着点）
    t = DOTS.sub(" {_} ", t).replace("\x00", "{_} ")
    t = re.sub(r"\{_\}(?:\s*\{_\})+", "{_}", t)
    t = re.sub(r"\{_\}\s*\.{1,2}(?=\s+[a-z])", "{_}", t)  # 空后面剩下的一两个点
    t = re.sub(r"(?<=[A-Za-z])\s*\.\.(?=\s+[a-z]|$)", " {_}", t)  # 只剩两个点的空：I.. about、……so I ..
    t = re.sub(r"\s+([?.,!;:])", r"\1", t.replace("{_} ", "{_} "))
    t = re.sub(r"\{_\}(?=[A-Za-z])", "{_} ", t)
    return re.sub(r"\s+", " ", t).strip()


def numbered_blanks(paras):
    """短文填空：书上是 (3) ......，编号在空前面；OCR 有时丢了括号或者点、认错数字。
    统一成 {_} (3)，并且按出现的顺序重新编号（分栏已经排好了阅读顺序）。"""
    paras = [re.sub(r"\{_\}[\s.•·]*(?=\(\d{1,2}\))", "{_} ", t) for t in paras]  # {_}.. (1)、{_} • (2)
    paras = [re.sub(r"\{_\}[\s.•·]*\(?([\dIl]{1,2})\)", lambda m: "{_} (" + m.group(1).replace("l", "1").replace("I", "1") + ")", t)
             for t in paras]  # {_}.. 1)、{_} l)
    text = " ".join(paras)
    before = len(re.findall(r"\(\d{1,2}\)\s*\{_\}", text))
    after = len(re.findall(r"\{_\}\s*\(\d{1,2}\)", text))
    lone = len(re.findall(r"(?<!\{_\} )\((\d{1,2})\)", text))
    if before + after < 3:
        return paras
    if after >= before:
        # 已经是 {_} (3) 的写法：补上丢了括号的 {_} 3)、丢了空的 (4)
        if after + lone < 3:
            return paras
        paras = [re.sub(r"\{_\}\s*(\d{1,2})\)", r"{_} (\1)", t) for t in paras]
        paras = [re.sub(r"(?<!\{_\} )(?<!\{_\})\s*\((\d{1,2})\)", r" {_} (\1)", t) for t in paras]
        seen = [int(n) for n in re.findall(r"\{_\} \((\d{1,2})\)", " ".join(paras))]
        if seen != list(range(1, len(seen) + 1)):  # 有认错的编号（两个 (1)）：按出现的顺序重新编
            k = 0

            def renum(m):
                nonlocal k
                k += 1
                return f"{{_}} ({k})"
            paras = [re.sub(r"\{_\} \((\d{1,2})\)", renum, t) for t in paras]
        return paras
    out, k = [], 0
    for t in paras:
        t = re.sub(r"\((\d{1,2})\)\s*[-–]\s*(?=\{_\})", r"(\1) ", t)  # (8)-...... 的横线也是空的一部分
        t = re.sub(r"(?<![\w(])(\d{1,2})\)\s*\{_\}", r"(\1) {_}", t)
        t = re.sub(r"\((\d{1,2})\)(?!\s*\{_\})", r"(\1) {_}", t)
        t = re.sub(r"\{_\}\s*\((\d{1,2})\)", r"(\1) {_}", t)

        def renumber(m):
            nonlocal k
            k += 1
            return f"{{_}} ({k})"
        out.append(re.sub(r"\((\d{1,2})\)\s*\{_\}", renumber, t))
    return out


def tick_split(segs):
    """问卷的一行：右边（页面右半）从第几段开始是打勾的选项。没有选项返回 None。"""
    for k in range(1, len(segs)):
        rest = " ".join(s["t"] for s in segs[k:])
        if segs[k]["x"] > 0.585 and ("•" in rest or re.match(r"^(yes|no|true|false)\b", rest, re.I)):
            choices = [c for c in re.split(r"\s*(?:•|\b[LO]\b(?=\s))\s*", rest.replace("|", "")) if c.strip()]
            if len(choices) >= 2 and all(len(c.split()) <= 4 for c in choices):  # 几个很短的选项才是打勾题
                return k
    return None


JUNK_SEG = re.compile(r"[A-Za-z]{1,2}[.,;:'\"]?$")
KEEP_SHORT = {"a", "A", "I", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "it", "me", "my",
              "no", "of", "on", "or", "so", "to", "up", "us", "we", "ok", "OK", "TV", "PC", "am", "an"}


def row_text(segs):
    """一行练习文字：段之间空得很开的地方是填空。"""
    # 最后一段是远远甩在右边的一两个字母（插图里的字）：不要
    while len(segs) > 1 and segs[-1]["x"] > 0.6 and segs[-1]["gap"] > 0.05 \
            and JUNK_SEG.match(segs[-1]["t"]) and segs[-1]["t"].strip(".,;:'\"") not in KEEP_SHORT:
        segs = segs[:-1]
    t = ""
    segs = [s for s in segs if not re.fullmatch(r"[•·\s]+", s["t"])] or segs  # 只有圆点的一段是杂点
    for i, s in enumerate(segs):
        after_num = i == 1 and re.fullmatch(r"[1-9]\d?|S", segs[0]["t"])  # 小题号后面空开的不是填空
        if i and s["gap"] > 0.05 and not after_num and not DOTS.search(t[-6:] + " " + s["t"][:6]) and not t.endswith("{_}"):
            t += " ..... "
        t += (" " if t else "") + s["t"]
    return blanks(t)


ITEM = re.compile(r"^([1-9]\d?|S)\s+(?=\S)")  # OCR 有时把 5 认成 S
OPTION = re.compile(r"^([a-h])[).]\s*")


def number_grid(run):
    """小题排成几栏、题号单独占一行、文字在题号下面居中（气泡框）：
    1    4
      文字   文字
    2    5 …    -> 先读左栏 1 2 3，再读右栏 4 5 6；题号接到它下面那一行的前面。"""
    is_nums = [len(r["segs"]) >= 2 and all(re.fullmatch(r"[1-9]\d?", s["t"]) for s in r["segs"]) for r in run]
    if sum(is_nums) < 2:
        return None
    start = is_nums.index(True)
    xs = [s["x"] for s in run[start]["segs"]]
    bounds = [x - 0.03 for x in xs] + [2]
    block = []
    for r in run[start:]:
        if any(s["x"] < bounds[0] - 0.03 or (s["r"] > bounds[c + 1] + 0.02 if (c := max(
                i for i, b in enumerate(bounds[:-1]) if s["x"] >= b or i == 0)) < len(xs) - 1 else False)
               for s in r["segs"]):
            break  # 跨栏的一整行：分栏结束
        block.append(r)
    if sum(1 for r in block if r in [run[i] for i, v in enumerate(is_nums) if v]) < 2:
        return None
    out = list(run[:start])
    for c in range(len(xs)):
        num = None
        for r in block:
            segs = [dict(s) for s in r["segs"] if bounds[c] <= s["x"] < bounds[c + 1] or (c == 0 and s["x"] < bounds[0])]
            if not segs:
                continue
            if len(segs) == 1 and re.fullmatch(r"[1-9]\d?", segs[0]["t"]):
                num = segs[0]
                continue
            segs[0]["gap"] = 0
            x = segs[0]["x"]
            if num:
                segs[0]["t"] = num["t"] + " " + segs[0]["t"]
                x = segs[0]["x"] = num["x"]
                num = None
            out.append({**r, "segs": segs, "x": x, "r": segs[-1]["r"], "col": (id(block), c), "lx": xs[c]})
    return out + run[start + len(block):]


def split_columns(rs, prose=False, breaks=lambda r: False):
    """几栏并排的文字（并排的几封信、两栏日记）：先读完左栏再读右栏。
    分栏 = 连续 6 行以上，每一行的每一段都在某一栏里面（没有跨栏的整行字），
    有两条以上相隔很远、对得很齐的左边线，每条线上都有 4 行以上。
    prose=True（讲解页）：其中一栏必须是脚注（' 2 3 … 开头的几行），免得把表格拆成一栏一栏的。
    breaks(row) 为真的行（小节标题、练习题号）不算在分栏里。
    分出来的每一行带上 col（第几栏）和 lx（这一栏的左边线）。"""
    runs, cur = [], []
    for r in rs:
        if cur and r["cy"] - cur[-1]["cy"] > 0.032:
            runs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        runs.append(cur)

    def anchors_of(rows_):
        xs = sorted(s["x"] for r in rows_ for s in r["segs"])
        groups = []
        for x in xs:
            if groups and x - groups[-1][0] < 0.025:
                groups[-1].append(x)
            else:
                groups.append([x])
        a = []
        for g in groups:
            if len(g) >= 4 and (not a or g[0] - a[-1] >= 0.2):  # 同一栏里的缩进不算新的一栏
                a.append(g[0])
        return a if len(a) >= 2 else []

    def fits(r, anchors):
        bounds = [x - 0.04 for x in anchors] + [2]
        for s in r["segs"]:
            c = max((i for i, x in enumerate(bounds[:-1]) if s["x"] >= x), default=None)
            if c is None or (c + 1 < len(anchors) and s["r"] > anchors[c + 1] - 0.005):  # 伸进了下一栏
                return False
        return True

    out = []
    for run in runs:
        grid = number_grid(run)
        if grid:
            out += grid
            continue
        anchors = anchors_of(run)
        blocks, cur = [], []
        for r in run:
            head = EXHEAD.match(r["segs"][0]["t"]) and r["segs"][0]["x"] < anchors[0] - 0.02 if anchors else False
            if anchors and fits(r, anchors) and not head and not breaks(r):
                cur.append(r)
            else:
                if cur:
                    blocks.append(cur)
                cur = []
                blocks.append(r)
        if cur:
            blocks.append(cur)
        for blk in blocks:
            if isinstance(blk, dict):
                out.append(blk)
                continue
            # 这一块里每一栏都要有 4 行以上，而且每一栏都对得很齐（换行甩过来的字参差不齐，不算栏），
            # 练习页还要求每一栏是成句的话（右边只有 true/false 这种短词的是打勾的格子，不是栏）
            cols_ = [[s for r in blk for s in r["segs"] if abs(s["x"] - x) < 0.03] for x in anchors]
            support = [len(c) for c in cols_]
            tidy_ = prose or all(not c or max(s["x"] for s in c) - min(s["x"] for s in c) < 0.04 for c in cols_)
            # 最右边一栏要是成句的话（只有 true/false 这种单词的是打勾的格子，不是栏）
            wordy = prose or not cols_[-1] or statistics.mean(len(s["t"].split()) for s in cols_[-1]) >= 2
            bounds = [x - 0.04 for x in anchors] + [2]
            notes = [sum(1 for r in blk for s in r["segs"] if abs(s["x"] - x) < 0.025  # noqa: B023
                         and re.match(r"^(['’*°®!\"]|\d{1,2})\s+[a-z(]", s["t"])) for x in anchors]
            if len(blk) < (4 if prose else 6) or min(support) < 4 or not tidy_ or not wordy \
                    or (prose and max(notes) < 3):
                out += blk
                continue
            for c in range(len(anchors)):
                for r in blk:
                    segs = [dict(s) for s in r["segs"] if bounds[c] <= s["x"] < bounds[c + 1]]
                    if not segs:
                        continue
                    segs[0]["gap"] = 0
                    out.append({**r, "segs": segs, "x": segs[0]["x"], "r": segs[-1]["r"], "col": (id(blk), c),
                                "lx": anchors[c]})
    return out


def key_numbers(md):
    """答案里这道练习有哪些小题号：1 b · 2 c 或者 1. …… 开头的行。"""
    nums = set()
    for line in (md or "").split("\n"):
        if re.match(r"^\d{1,2}\.?\s", line.strip()):
            nums |= {int(m) for m in re.findall(r"(?:^|·)\s*(\d{1,2})\.?\s", line.strip())}
    return sorted(nums)


INSTRUCTION = re.compile(
    r"(Use|Write|Make|Then|Look|If|Remember|There (are|is)|Each|Some|Try|Do|Note|Explain|Decide|Choose|Complete|Match|"
    r"Fill|Rewrite|Replace|Correct|Find|Put|Read|Answer|Think|Say|Underline|Check|Compare|Give|Change|Add|Describe|"
    r"Imagine|Not|Be|Sometimes|Here|Which|What|How|Now|Finally|In (each|some|these|the)|The (first|words|sentences|verbs|phrasal|"
    r"underlined|text|pictures|answers|box|following)|These|This (is|text|exercise)|One|Two|Three|Four|Five|Six)\b")


def split_instruction(t):
    """题目说明后面接着的短文（OCR 把它们排成了一段）：从第一句不像说明的句子开始分出去。
    只在后面那部分有空、或者很长的时候才分。"""
    for m in re.finditer(r"(?<=[.?!:)])\s+(?=[A-Za-z'\"{])", t):
        rest = t[m.end():]
        if INSTRUCTION.match(rest):
            continue
        if "{_}" in rest or len(rest) > 40:
            return t[:m.start()], rest
        break
    return t, ""


def no_items_repair(ex, want, letters, short_set=()):
    """没有小题的练习，照答案里的小题号给作答的地方。"""
    if not want or ex["items"]:
        return
    body = " ".join(ex["intro"])
    # 一段话里写着 (1) (2) … 但是没有空（填句子的短文）：每个 (n) 前面放一个空
    if "{_}" not in body and all(f"({k})" in body for k in want):
        ex["intro"] = [re.sub(r"\((\d{1,2})\)", r"{_} (\1)", p) for p in ex["intro"]]
        return
    # 一段话里是 1 …… 2 …… 3 ……（编号的说明，OCR 接成了一段）：按题号拆开
    for i, p in enumerate(ex["intro"]):
        cuts = [re.search(rf"(?<=[\w.?!)}}]) {k} (?=[A-Z])", p) for k in want[1:]]
        if i and all(cuts) and all(a.start() < b.start() for a, b in zip(cuts, cuts[1:])):
            starts = [0] + [c.start() for c in cuts]
            ends = [c.start() for c in cuts] + [len(p)]
            texts = [p[a:b] for a, b in zip(starts, ends)]
            texts = [re.sub(r"^\s*(\d{1,2}|[Il])\s+", "", t).strip() for t in texts]
            ex["intro"] = ex["intro"][:i] + ex["intro"][i + 1:]
            ex["items"] = [{"t": t, "n": k, "x": 0} for k, t in zip(want, texts)]
            ex["book_nums"] = True
            return
    # 看图写短语、写出原形：没有句子，给编号的作答框
    if "{_}" not in body:
        ex["items"] = [{"t": "", "n": k, "x": 0} for k in want]
        ex["book_nums"] = True
        ex["short"] = ex["ex_letters"] or ex["n"] in short_set


def key_parts(md):
    """答案里这道练习每个小题有几个空：1. clock, clock -> {1: 2}（没有分号逗号的算一个空）。"""
    out = {}
    for line in (md or "").split("\n"):
        for part in re.split(r"\s+·\s+", line.strip()):
            m = re.match(r"^(\d{1,2})\.?\s+(.+)$", part)
            if m:
                out[int(m.group(1))] = answer_parts(m.group(2))
    return out


def answer_parts(ans):
    """一个小题的答案有几个空。
    "clock, clock" -> 2；"bring; around/round *or* talk; around/round"（两种说法，各两个空）-> 2。"""
    ans = re.sub(r"\([^)]*\)", " ", ans).replace("*", "")
    if not re.search(r"[,;]", ans) or re.fullmatch(r"\s*[a-j](\s*,\s*[a-j])+\s*", ans):
        return 1  # "e, h, i" 是几个都算对，不是几个空
    alts = [len(re.split(r"[,;]", a)) for a in re.split(r"\s+or\s+", ans)]
    if len(alts) > 1 and len(set(alts)) == 1 and alts[0] > 1:
        return alts[0]  # 整句有几种说法，每种说法的空一样多
    return len(re.split(r"[,;]", ans))


def renumber_passage(ex, parts):
    """短文填空（没有分小题）：空的个数和答案里的总数对得上，就按顺序标上小题号，
    一个小题有几个空的（talk sb into：两个空）都标同一个号。"""
    if ex["items"] or not parts:
        return
    if sum(p.count("{_}") for p in ex["intro"]) != sum(parts.values()):
        return
    it = iter([n for n in sorted(parts) for _ in range(parts[n])])
    ex["intro"] = [re.sub(r"\{_\}", lambda m: f"{{_}} ({next(it)})",
                          re.sub(r"\{_\}\s*\(\d{1,2}\)", "{_}", p)) for p in ex["intro"]]


def rebuild(raw):
    out = ""
    for i, r in enumerate(raw):
        t = row_text(r["segs"])[r["head"]:] if i == 0 else row_text(r["segs"])
        out = join_text(out, t) if out else t
    return out


def trim_items(ex, parts):
    """小题里混进了旁边的东西（插图上的字、右边一栏的说明）时，空会比答案多。
    按几种办法重新拼这个小题，哪一种拼出来的空数和答案对得上就用哪一种。"""
    if ex.get("ex_letters"):
        return  # 选择题：选项之间空开的不是填空，不用按空的个数裁
    for it in ex["items"]:
        want_n = parts.get(it["n"])
        raw = it.get("raw")
        if not want_n or not raw or it["t"].count("{_}") <= want_n:
            continue
        gaps = [i for i in range(1, len(raw)) if raw[i]["cy"] - raw[i - 1]["cy"] > 0.05]  # 中间隔着插图
        tries = []
        for x0 in (0.6, 0.5):  # 右边一栏的说明
            cut = [{**r, "segs": [s for s in r["segs"] if s["x"] < x0] or r["segs"]} for r in raw]
            if any(len(c["segs"]) < len(r["segs"]) for c, r in zip(cut, raw)):
                tries.append(cut)
        if gaps:
            tries.append([{**r, "head": 0} for r in raw[gaps[-1]:]])  # 插图下面的那几行
            tries.append(raw[:gaps[0]])
        for cand in tries:
            t = rebuild(cand)
            if t.count("{_}") == want_n:
                it["t"] = t
                break


def repair_items(ex, want, in_text=()):
    """OCR 漏掉了题号的时候，照着答案里的小题号补回来：
    (a) 题号在同一行的中间（两栏的小题：1 …… 4 ……）；
    (b) 题号整个没认出来，这一题的文字接在上一题后面（上一行句子已经完，这一行大写开头另起）；
    (c) 整道题都没认出来（比如第 1 题）：放一个占位的小题，题号对上，提醒看原书。
    只在书上认出来的题号都在答案里、而且是从小到大的时候才动。"""
    items = ex["items"]
    if not want or not items or any(0 < o["after"] < len(items) for o in ex["opts"]):
        return
    have = [it["n"] for it in items]
    if have != sorted(set(have)) or not set(have) <= set(want):
        return
    missing = [m for m in want if m not in have]
    tail_opts = [o for o in ex["opts"] if o["after"] == len(items)]  # 配对题：选项在所有小题后面
    if not missing:
        ex["book_nums"] = True
        return
    for it in list(items):  # (a2) 题号单独占一行（气泡框）
        lines, raw = it.get("lines"), it.get("raw")
        if not lines or not raw or len(raw) != len(lines):
            continue
        cuts = [(j, int(lines[j])) for j in range(len(lines))
                if re.fullmatch(r"[1-9]\d?", lines[j].strip()) and int(lines[j]) in missing]
        if not cuts:
            continue
        pieces = [(it["n"], 0, cuts[0][0])] + [(m, j + 1, nxt) for (j, m), nxt in
                                               zip(cuts, [c[0] for c in cuts[1:]] + [len(lines)])]
        it["lines"], it["raw"] = lines[pieces[0][1]:pieces[0][2]], raw[pieces[0][1]:pieces[0][2]]
        it["t"] = rebuild(it["raw"])
        for m, a, b in pieces[1:]:
            part = [{**raw[a], "head": 0}] + raw[a + 1:b]
            items.append({"t": rebuild(part), "n": m, "x": part[0]["segs"][0]["x"],
                          "lines": lines[a:b], "raw": part})
            missing.remove(m)
    items.sort(key=lambda it: it["n"])
    for m in list(missing):  # (a)
        for it in items:
            mm = re.search(rf"(?<=[\w?.!)}}]) {m} (?=[A-Za-z(])", it["t"])
            if it["n"] < m and mm:
                items.append({"t": it["t"][mm.end():], "n": m, "x": it["x"]})
                it["t"] = re.sub(r"\s*\{_\}$", "", it["t"][:mm.start()]) or it["t"][:mm.start()]
                it.pop("lines", None)
                missing.remove(m)
                break
    items.sort(key=lambda it: it["n"])
    for it in list(items):  # (b)
        gap, k = [], it["n"] + 1
        while k in missing:
            gap.append(k)
            k += 1
        lines = it.get("lines", [])
        cuts = [j for j in range(1, len(lines))
                if (re.match(r"^[A-Z{]", lines[j]) and re.search(r"([.?!]['\"]?|\{__?\}|\([A-Z]{2,}\))$", lines[j - 1]))
                or (re.match(r"^[a-z]", lines[j]) and lines[j - 1].endswith("?"))]  # 释义一条一条的：…? 下一条小写开头
        raw = it.get("raw", [])
        if gap and len(cuts) > len(gap) and len(raw) == len(lines):
            # 分得太多：取上下空得最开的那几处（新的一题之间空得开一些）
            cuts = sorted(sorted(cuts, key=lambda j: raw[j]["cy"] - raw[j - 1]["cy"])[-len(gap):])
        if gap and len(cuts) == len(gap):
            parts = [lines[a:b] for a, b in zip([0] + cuts, cuts + [len(lines)])]
            join = lambda ls: " ".join(ls)
            it["t"] = join(parts[0])
            for m, part in zip(gap, parts[1:]):
                items.append({"t": join(part), "n": m, "x": it["x"]})
                missing.remove(m)
    if 1 in missing and ex["intro"] and re.match(r"^[Il]\s+[A-Z]", ex["intro"][-1]) and len(ex["intro"]) > 1:
        # 第 1 题的 1 认成了 I，跑到说明里去了
        items.append({"t": ex["intro"].pop()[2:], "n": 1, "x": 0})
        missing.remove(1)
    for it in list(items):  # (d) 题号认成了别的字（I * s）：顶着这一栏左边线的行是新的一题
        gap, k = [], it["n"] + 1
        while k in missing:
            gap.append(k)
            k += 1
        raw = it.get("raw", [])
        starts = [j for j in range(1, len(raw))
                  if abs(raw[j]["segs"][0]["x"] - raw[0]["segs"][0]["x"]) < 0.008
                  and re.match(r"^\S\s+[A-Z]", raw[j]["segs"][0]["t"])]  # 开头是认错的题号 + 大写字母
        if gap and len(starts) == len(gap):
            parts = [raw[a:b] for a, b in zip([0] + starts, starts + [len(raw)])]
            it["t"] = rebuild(parts[0])
            for m, part in zip(gap, parts[1:]):
                part = [{**part[0], "head": 0}] + part[1:]
                t = re.sub(r"^\S\s+(?=[A-Z])", "", rebuild(part))  # 开头那个认错的题号
                items.append({"t": t, "n": m, "x": part[0]["segs"][0]["x"], "raw": part})
                missing.remove(m)
    items.sort(key=lambda it: it["n"])
    for m in [m for m in missing if m in in_text]:
        missing.remove(m)  # 这一题的空在上面的短文里（小题只是选项），不用占位
    for m in list(missing):  # (c) 实在认不出来的小题：放个占位，题号和答案才对得上
        items.append({"t": "（这一题 OCR 没有认出来，请看下面的原书页面）", "n": m, "x": 0})
        missing.remove(m)
    items.sort(key=lambda it: it["n"])
    for o in tail_opts:
        o["after"] = len(items)
    ex["book_nums"] = True


def exercises(page, unit, expect=None):
    rs = rows(page)
    if rs and rs[0]["y"] < 0.075:
        rs = rs[1:]
    rs = split_columns(rs)
    bx, fr = body_x(rs), full_right(rs)
    out = ["## Exercises", ""]
    ex = None          # {"n", "intro":[], "items":[...], "after":[]}
    exs = []
    last_col = None
    item_cols = {r["col"] for r in rs if r.get("col") and ITEM.match(r["segs"][0]["t"])}
    # 有缩进的续行的栏（聊天记录）：顶着左边线的每一行是新的一句
    turn_cols = {r["col"] for r in rs if r.get("col") and 0.02 < r["x"] - r["lx"] < 0.05}
    prev_cy = 0
    for row in rs:
        segs = row["segs"]
        t0 = segs[0]["t"]
        lx = row.get("lx", bx)
        gap, prev_cy = row["cy"] - prev_cy, row["cy"]  # 和上一行隔多远（隔得远是新的一段）
        col, last_col = row.get("col"), row.get("col") or last_col
        m = EXHEAD.match(t0)
        if m and segs[0]["x"] < bx - 0.03:
            ex = {"n": f"{unit}.{len(exs) + 1}", "intro": [], "items": [], "words": [], "opts": [], "tail": []}
            exs.append(ex)
            rest = [dict(segs[0], t=t0[m.end():])] + segs[1:]
            intro = " ".join(s["t"] for s in rest if s["t"]).strip()
            if intro:
                ex["intro"].append(intro)
            ex["x"] = None
            continue
        if not ex:
            continue
        # 词库：一行好几个短词
        if len(segs) >= 3 and all(len(s["t"].split()) <= 3 and not DOTS.search(s["t"]) for s in segs) and not ITEM.match(t0) \
                and not all(OPTION.match(s["t"]) for s in segs):
            if not ex["words"] and not ex["items"]:
                ex["thead"] = segs  # 可能是要填的表格的表头
            ex["words"] += [s["t"] for s in segs]
            continue
        if len(segs) == 1 and ex.get("thead") and abs(segs[0]["x"] - ex["thead"][0]["x"]) < 0.02 \
                and re.fullmatch(r"[a-z][a-z' -]*", t0) and len(t0.split()) <= 3 and not ex["items"]:
            ex.setdefault("trows", []).append(t0)  # 表头下面第一栏的词：填表
            continue
        if len(segs) == 1 and ex["words"] and len(t0.split()) <= 3 and not ITEM.match(t0) and not ex["items"]:
            ex["words"].append(t0)
            continue
        k = tick_split(segs)
        if k is not None or (ex.get("quiz_x") and abs(segs[0]["x"] - ex["quiz_x"]) < 0.02):
            # 问卷：左边是问题，右边是打勾的选项（• yes • no）；问题可能占两行
            qsegs = segs[:k] if k is not None else segs
            if qsegs and re.fullmatch(r"[1-9]\d?", qsegs[0]["t"]):
                qsegs = qsegs[1:]  # 页边的题号
            qt = row_text(qsegs) if qsegs else ""
            if ex.get("q_open"):
                ex["items"][-1]["t"] = join_text(ex["items"][-1]["t"], qt)
            else:
                ex["items"].append({"t": qt, "x": segs[0]["x"], "n": len(ex["items"]) + 1})
            ex["quiz_x"] = ex.get("quiz_x") or (qsegs or segs)[0]["x"]
            if k is not None:
                choices = [c.strip() for c in re.split(r"\s*(?:•|\b[LO]\b(?=\s))\s*",
                                                      " ".join(s["t"] for s in segs[k:]).replace("|", ""))]
                if "{_}" not in ex["items"][-1]["t"]:
                    ex["items"][-1]["t"] += " {_}"  # 空的点没认出来
                ex["items"][-1]["t"] += " (" + " / ".join(c for c in choices if c) + ")"
            ex["q_open"] = k is None
            continue
        text = row_text(segs)
        sp = SPEAKER.match(t0)
        if sp and len(segs) > 1 and col and not ex["items"]:
            text = f"**{sp.group(1)}:** " + row_text(segs[1:])  # 分栏里的对话：留在这一栏的方框里
        elif sp and len(segs) > 1:
            text = f"**{sp.group(1)}:** " + row_text(segs[1:])
            im = re.match(r"^(\d{1,2})\s", t0)
            if im:
                ex["items"].append({"t": text, "x": segs[0]["x"], "n": int(im.group(1))})
            elif ex["items"]:
                ex["items"][-1]["t"] += "<br>" + text
            else:
                ex["intro"].append(text)
            continue
        im = ITEM.match(text)
        if im and im.group(1) == "S" and len(ex["items"]) != 4:
            im = None
        glued = re.match(r"^([1-9]\d?)(?=[A-Z])", text)  # 题号和后面的词粘在一起：4I
        if not im and glued and segs[0]["x"] < lx + 0.03 \
                and int(glued.group(1)) == (ex["items"][-1]["n"] + 1 if ex["items"] else 1):
            text = glued.group(1) + " " + text[glued.end():]
            im = ITEM.match(text)
        lm = re.match(r"^([\dIl]{2})\s+(?=\S)", text)
        if not im and lm and ex["items"] and lm.group(1).replace("I", "1").replace("l", "1") == str(ex["items"][-1]["n"] + 1):
            im = re.match(r"^(\d+)", str(ex["items"][-1]["n"] + 1))
            text = im.group(1) + text[2:]  # 小题号认错了（I1 = 11），按顺序改回来
            im = ITEM.match(text)
        om = OPTION.match(text)
        if om and segs[0]["x"] < lx + 0.1:
            # 一行里有好几个选项：a) turned b) walked c) poured
            for k, t in re.findall(r"(?:^|\s)([a-h])[).]\s*(.*?)(?=\s+[a-h][).]\s|$)", text):
                ex["opts"].append({"k": k, "t": t, "after": len(ex["items"]), "x": segs[0]["x"]})
            continue
        its = ex["items"]
        if not im and len(its) >= 2 and text.startswith("{_}") and all(it["t"].startswith("{_}") for it in its) \
                and re.search(r"[?.!]$", its[-1]["t"]):
            # 每个小题都是 "1 ..... 句子"，这一行也是空开头、上一题已经说完：题号没认出来的下一题
            its.append({"t": text, "x": segs[0]["x"], "n": its[-1]["n"] + 1})
            ex.setdefault("item_cy", []).append(row["cy"])
            continue
        if im and segs[0]["x"] < lx + 0.03:
            n = 5 if im.group(1) == "S" else int(im.group(1))
            ex["items"].append({"t": text[im.end():], "x": segs[0]["x"], "n": n, "lines": [text[im.end():]],
                                "col": col, "raw": [{"cy": row["cy"], "segs": segs, "head": im.end()}]})
            ex.setdefault("item_cy", []).append(row["cy"])
            continue
        if re.match(r"^(EXAMPLE|Example)\b", text):
            ex["tail" if ex["items"] else "intro"].append("*" + text + "*")
            continue
        # 接着上一行
        if col and col[1] > 0 and ex["items"] and col not in item_cols:
            # 配对题的右半栏（句子的后半句）：单独列出来
            # 和左栏某个小题同一行开始的是新的一项，否则接着上一项
            halves = ex.setdefault("halves", [])
            if not halves or re.search(r"[.?!]['\"]?$", halves[-1]) \
                    or any(abs(row["cy"] - c) < 0.006 for c in ex["item_cy"]):
                halves.append(text)
            else:
                halves[-1] = join_text(halves[-1], text)
        elif ex["opts"] and ex["opts"][-1]["after"] == len(ex["items"]) and not ex["items"] \
                and segs[0]["x"] < ex["opts"][-1]["x"] + 0.01:
            # 选项后面、小题前面不缩进的一行：小题的题干（Which notice would you respond to if …）
            ex.setdefault("stem", []).append(re.sub(r"\s*\{_\}$", " …", text))  # 题干末尾的点是"接下面的小题"
        elif ex["opts"] and ex["opts"][-1]["after"] == len(ex["items"]) and ex["items"] \
                and segs[0]["x"] < ex["opts"][-1]["x"] - 0.005 and re.match(r"^[A-Z]", text):
            # 选择题的选项后面、比选项靠左、大写开头的一行：题号没认出来的下一题
            ex["items"].append({"t": text, "x": segs[0]["x"], "n": ex["items"][-1]["n"] + 1, "lines": [text]})
            ex.setdefault("item_cy", []).append(row["cy"])
        elif ex["opts"] and ex["opts"][-1]["after"] == len(ex["items"]):
            ex["opts"][-1]["t"] = join_text(ex["opts"][-1]["t"], text)
        elif ex["items"] and ex["items"][-1].get("col") and not col:
            # 小题在分栏里，这一行在分栏外面（栏下面的短文）：另起一段
            if ex.get("after") and gap < 0.03:
                ex["after"][-1] = join_text(ex["after"][-1], text)
            else:
                ex.setdefault("after", []).append(text)
        elif ex["items"]:
            if re.match(r"^(Follow up|FOLLOW UP|Tip|TIP)\b", text):
                ex["tail"].append(text)
            elif ex["tail"]:
                ex["tail"][-1] = join_text(ex["tail"][-1], text)
            else:
                it_ = ex["items"][-1]
                it_["t"] = join_text(it_["t"], text) if it_["t"] else text
                if "lines" in it_:
                    it_["lines"].append(text)
                    it_.setdefault("raw", []).append({"cy": row["cy"], "segs": segs, "head": 0})
        elif col:
            # 分栏的一段话（信）：每一栏一个方框，Dear …, 另起一行
            if ex.get("col") != col:
                ex["intro"].append("> " + text)
            elif re.match(r"^(Dear\b|\*\*)", text) or ex["intro"][-1].endswith(",") or (
                    col in turn_cols and segs[0]["x"] - row["lx"] < 0.012):
                ex["intro"][-1] += "\n> " + text
            else:
                ex["intro"][-1] = join_text(ex["intro"][-1], text)
            ex["col"] = col
        else:
            if ex["intro"] and segs[0]["x"] >= bx - 0.02 and not ex["words"] and gap < 0.03:
                ex["intro"][-1] = join_text(ex["intro"][-1], text)
            else:
                ex["intro"].append(text)

    letters = (expect or {}).get("_letters", set())
    for ex in exs:
        want = (expect or {}).get(ex["n"])
        if ex["intro"]:
            head, passage = split_instruction(ex["intro"][0])
            if passage:
                ex["intro"][:1] = [head, passage]
        ex["ex_letters"] = ex["n"] in letters
        no_items_repair(ex, (expect or {}).get(ex["n"]), letters, (expect or {}).get("_short", set()))
        in_text = {int(n) for n in re.findall(r"\((\d{1,2})\)", " ".join(ex["intro"] + ex.get("after", [])))}
        repair_items(ex, (expect or {}).get(ex["n"]), in_text)
        trim_items(ex, (expect or {}).get("_parts", {}).get(ex["n"], {}))
        ex["intro"] = numbered_blanks(ex["intro"])
        renumber_passage(ex, (expect or {}).get("_parts", {}).get(ex["n"], {}))
        ex["intro"] = [p for p in ex["intro"] if not re.fullmatch(r"\d{1,2}", p.strip())]  # 插图的编号
        intro = re.sub(r"(?<=[.?!:])(\s+\d{1,2})+$", "", ex["intro"][0]) if ex["intro"] else ""

        out.append(f"### {ex['n']} {intro}".rstrip())
        for p in ex["intro"][1:]:
            out += ["", p, ""] if p.startswith("> ") else [p]  # 每封信一个方框
        if len(ex.get("trows", [])) >= 2:
            # 填表：表头 + 每行第一栏给出的词，其余格子留空
            head = [s["t"] for s in ex["thead"]]
            out += ["", "| " + " | ".join(head) + " |"]
            cell = ["{__}" if re.search(r"example|sentence", h, re.I) else "{_}" for h in head[1:]]  # 写句子的格子大一点
            out += ["| " + " | ".join([r] + cell) + " |" for r in ex["trows"]]
            out.append("")
            ex["words"] = ex["words"][len(head):]
        if ex["words"]:
            out.append("[[" + " | ".join(ex["words"]) + "]]")
        # 选项全在小题后面：配对题（每个小题填一个字母）；跟在某个小题后面：选择题
        afters = {o["after"] for o in ex["opts"]}
        matching = bool(ex["opts"]) and len(ex["items"]) > 1 and afters <= {0, len(ex["items"])}
        if matching and 0 in afters:
            out += [f"- {o['k']}) {o['t']}" for o in ex["opts"] if o["after"] == 0] + [""]
        out += ex.get("stem", [])
        nums = [it["n"] for it in ex["items"]]
        if ex.get("book_nums"):
            pass  # 题号和答案对上了，用书上的
        elif len(nums) < 2 or nums[0] < 3 or nums != list(range(nums[0], nums[0] + len(nums))):
            nums = list(range(1, len(ex["items"]) + 1))
        # 小题下面的短文里有编号的空（小题只是给看的）：小题不再给作答框
        boxed = want and all(f"({k})" in " ".join(numbered_blanks(ex.get("after", []))) for k in want)
        pairs = ex["opts"] and not ex["ex_letters"] and (expect or {}).get(ex["n"]) and not matching
        if pairs:
            # 答案不是字母：a) b) 是要比较/解释的两句话，不是选项。每个 a) 开始新的一组（OCR 有时漏了题号）
            groups = []
            for i, it in enumerate(ex["items"], 1):
                lines = ([it["t"]] if it["t"].strip() else []) + [f"{o['k']}) {o['t']}" for o in ex["opts"] if o["after"] == i]
                for line in lines:
                    if re.match(r"^a\)", line) or not groups:
                        groups.append([])
                    groups[-1].append(line)
            for num, g in enumerate(groups, 1):
                out.append(f"{num}. {g[0]}")
                out += [f"- {line}" for line in g[1:]] + ["{__}"]
            ex["items"], ex["opts"] = [], []
        for i, (it, num) in enumerate(zip(ex["items"], nums), 1):
            t = it["t"]
            mine = [o for o in ex["opts"] if o["after"] == i and not matching]
            if t.count("{_}") > 1:
                t = re.sub(r"([?.!])\s*\{_\}\s*$", r"\1", t)  # 句子说完了后面又一个空：杂点
            inline = re.findall(r"(?:^|\s)([a-h])\s?\)\s*(.*?)(?=\s+(?:\{_\}\s*)?[a-h]\s?\)|$)", t) if re.match(r"^a\)", t) else []
            if len(inline) >= 2 and ex["ex_letters"]:
                # 这一题只有选项（短文里第 n 个空选哪个）：a) back b) up c) off d) out
                out.append(f"{num}. ({num})")
                out += [f"{k}) {re.sub(r'\s*\{_?_\}\s*', ' ', v).strip(' .')}" for k, v in inline]
                continue
            if "{_}" not in t and "{__}" not in t and not mine and not boxed:
                t += " {_}" if matching or (not t and ex.get("short")) else " {__}"
            out.append(f"{num}. {t}")
            out += [f"{o['k']}) {o['t']}" for o in mine]
        if matching and len(ex["items"]) in afters:
            out.append("")
            out += [f"- {o['k']}) {o['t']}" for o in ex["opts"] if o["after"] == len(ex["items"])]
        elif not ex["items"]:
            out += [f"- {o['k']}) {o['t']}" for o in ex["opts"]]
            if "{_}" not in "".join(ex["intro"]) and not ex.get("trows") and not pairs:
                out.append("{__}")  # 没有小题、也没有空的练习（改写一段话之类）：给一个作答框
        after = numbered_blanks(ex.get("after", []))
        if after:
            out += [""] + after
        if ex.get("halves"):
            out.append("")
            out += [f"- {h}" for h in ex["halves"]]
        for p in ex["tail"]:
            out += ["", p]
        out.append("")
    return out


def unit_markdown(pages, unit, title, phrase_keys, page_dir=None, key_ex=None):
    """key_ex：答案里每道练习的答案 {"6.1": "1 apart · 2 out …"}，用来核对、补回 OCR 漏掉的题号。"""
    left, right = 9 + 2 * (unit - 1), 10 + 2 * (unit - 1)
    bold = bolder(phrase_keys)
    image = f"{page_dir}/{left}.jpg" if page_dir else None
    expect = {ex: key_numbers(md) for ex, md in (key_ex or {}).items()}
    # 答案是字母的练习（1 b · 2 c）才是选择题/配对题
    letters = {ex for ex, md in (key_ex or {}).items()
               if re.fullmatch(r"(\s*\d{1,2}\.?\s+[a-h](\s*(\*?or\*?|/)\s*[a-h])*\s*(·|$))+",
                               md.replace("\n", " · ").strip(" ·"))}
    expect["_letters"] = letters
    # 答案都很短（几个词）的练习：作答框用一行的
    def short(md):
        parts = [re.sub(r"^\d{1,2}\.?\s+", "", p.strip()) for line in md.split("\n") for p in line.split("·")]
        parts = [p for p in parts if p and not p.startswith("*")]
        return bool(parts) and all(len(re.sub(r"\*?or\*?.*", "", p).split()) <= 4 for p in parts)
    expect["_short"] = {ex for ex, md in (key_ex or {}).items() if short(md)}
    expect["_parts"] = {ex: key_parts(md) for ex, md in (key_ex or {}).items()}
    md = [f"# {unit} {title}", ""] + explanation(pages[left], bold, image) + exercises(pages[right], unit, expect)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(md)).strip() + "\n"


if __name__ == "__main__":
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    pages = {p["page"]: p for p in json.loads((root / "data/ocr/phrasal-verbs.json").read_text())}
    pv = json.loads((root / "content/phrasal-verbs.json").read_text())
    u = pv["units"][int(sys.argv[1]) - 1]
    sys.path.insert(0, str(root / "scripts"))
    from build_pv import key_by_unit
    sys.stdout.write(unit_markdown(pages, u["n"], u["title"], [p["key"] for p in u["phrases"]],
                                   root / "content/pages/phrasal-verbs", key_by_unit().get(u["n"], {}).get("ex")))
