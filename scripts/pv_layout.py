"""把短语书一个单元的 OCR（data/ocr/phrasal-verbs.json）按版面还原成 content-src/pv/NN.md 的格式。

左页是讲解：A/B/C 小节、表格、对话、段落；右页是练习：题号、小题、填空、选项、词库。
OCR 没有粗体信息，讲解里本单元的短语（来自 Mini dictionary）自动加粗。

自动还原难免有错。想手工改某个单元：
  python3 scripts/pv_layout.py 12 > content-src/pv/12.md
改好后运行 python3 scripts/build_pv.py，有 content-src/pv/NN.md 的单元优先用手工版。
"""
import re
import statistics
import sys

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
    for k in sorted(set(keys), key=len, reverse=True):
        words = k.split()
        if len(words) < 2 or not all(w in PARTICLES for w in words[1:]) or not re.fullmatch(r"[a-z]+", words[0]):
            continue
        verb = "|".join(sorted(verb_forms(words[0]), key=len, reverse=True))
        parts = r"\s+".join(words[1:])
        # 动词 + 最多三个词（宾语）+ 小品词
        pats.append(re.compile(rf"\b({verb})\b((?:\s+[\w'’-]+){{0,3}}?)\s+({parts})\b", re.I))
    def apply(s):
        for p in pats:
            def rep(m):
                if "**" in m.group(0):
                    return m.group(0)
                if m.group(2):
                    return f"**{m.group(1)}**{m.group(2)} **{m.group(3)}**"
                return f"**{m.group(1)} {m.group(3)}**"
            s = p.sub(rep, s)
        return s
    return apply


# ---------------------------------------------------------------- 版面：行

def tidy(t):
    t = t.replace("­", "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"(?<=[a-z,] )1(?= [a-z])", "I", t)  # OCR 把 I 认成 1
    t = re.sub(r"\bjim\b", "Jim", t)
    return re.sub(r"\s+", " ", t).strip()


def rows(page):
    """OCR 的行 -> 版面上的一行一行；每行是按 x 排好的若干段 {x, r, t}。"""
    lines = []
    for l in page["lines"]:
        t = l["t"].strip()
        if not t or l["x"] < 0.07 or l["x"] > 0.97:  # 对面页透过来的字
            continue
        if re.fullmatch(r"\d{1,3}|English Phrasal Verbs in Use|Exercises", t) and (l["y"] < 0.07 or l["y"] > 0.93):
            continue
        if re.search(r"English Phrasal Verbs in Use", t) and l["y"] > 0.9:
            continue
        lines.append({"x": l["x"], "r": l["x"] + l["w"], "y": l["y"], "h": l["h"], "t": t})
    lines.sort(key=lambda l: l["y"] + l["h"] / 2)
    out = []
    for l in lines:
        cy = l["y"] + l["h"] / 2
        if out:
            row = out[-1]
            if abs(cy - row["cy"]) < 0.55 * min(l["h"], row["h"]) + 0.002:
                row["segs"].append(l)
                row["h"] = max(row["h"], l["h"])
                continue
        out.append({"cy": cy, "y": l["y"], "h": l["h"], "segs": [l]})
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
    out, start = [], None
    for y, f in enumerate(list(frac) + [0]):
        if f > 0.35 and start is None:
            start = y
        elif f <= 0.35 and start is not None:
            if y - start > 12 and start / h > 0.07:  # 最上面那个是单元号
                out.append((start / h - 0.006, y / h + 0.006))
            start = None
    return out


def explanation(page, bold, image=None):
    rs = rows(page)
    if rs and rs[0]["y"] < 0.075:
        rs = rs[1:]  # 单元标题
    bx, fr = body_x(rs), full_right(rs)
    out, para, table, dialog = [], None, None, None
    boxes = section_boxes(image) if image else []
    letters = iter("ABCDEFGH")

    def end_para():
        nonlocal para
        if para:
            out.append(bold(para["t"]))
            out.append("")
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

    def end_all():
        end_para(); end_table(); end_dialog()

    for row in rs:
        segs = row["segs"]
        first = segs[0]
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
        if para and abs(first["x"] - para["x"]) < 0.03 and para["r"] > fr - 0.07 and not re.match(r"^\d\s|^[•-]", t):
            para["t"] = join_text(para["t"], t)
            para["r"] = first["r"]
        else:
            end_para()
            para = {"t": t, "x": first["x"], "r": first["r"]}
    end_all()
    return out


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
    if len(anchors) == 1 or len(grid) == 1:  # 只有一行的不是表格，是隔得比较开的一行字
        return [bold(" ".join(c for c in r if c)) for r in grid]
    out = []
    for i, r in enumerate(grid):
        cells = [c.replace("|", "/") for c in r]
        out.append("| " + " | ".join(c if i == 0 else bold(c) for c in cells) + " |")
    return out


# ---------------------------------------------------------------- 右页：练习

DOTS = re.compile(r"(?:[.…·,](?:\s?)){2,}[.…·]")


def blanks(t):
    t = re.sub(r"\(\s*\)", "({_})", t)
    t = DOTS.sub(" {_} ", t)
    t = re.sub(r"\{_\}(?:\s*\{_\})+", "{_}", t)
    t = re.sub(r"(?<=\b[a-z])\s+\{_\}", "{_}", t)  # b.... 这种给了首字母的空
    t = re.sub(r"\s+([?.,!;:])", r"\1", t.replace("{_} ", "{_} "))
    t = re.sub(r"\{_\}(?=[A-Za-z])", "{_} ", t)
    return re.sub(r"\s+", " ", t).strip()


def row_text(segs):
    """一行练习文字：段之间空得很开的地方是填空。"""
    t = ""
    for i, s in enumerate(segs):
        if i and s["gap"] > 0.05 and not DOTS.search(t[-6:] + " " + s["t"][:6]) and not t.endswith("{_}"):
            t += " ..... "
        t += (" " if t else "") + s["t"]
    return blanks(t)


ITEM = re.compile(r"^([1-9]\d?|S)\s+(?=\S)")  # OCR 有时把 5 认成 S
OPTION = re.compile(r"^([a-h])[).]\s*")


def exercises(page, unit):
    rs = rows(page)
    if rs and rs[0]["y"] < 0.075:
        rs = rs[1:]
    bx, fr = body_x(rs), full_right(rs)
    out = ["## Exercises", ""]
    ex = None          # {"n", "intro":[], "items":[...], "after":[]}
    exs = []
    for row in rs:
        segs = row["segs"]
        t0 = segs[0]["t"]
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
        if len(segs) >= 3 and all(len(s["t"].split()) <= 3 and not DOTS.search(s["t"]) for s in segs) and not ITEM.match(t0):
            ex["words"] += [s["t"] for s in segs]
            continue
        if len(segs) == 1 and ex["words"] and len(t0.split()) <= 3 and not ITEM.match(t0) and not ex["items"]:
            ex["words"].append(t0)
            continue
        text = row_text(segs)
        sp = SPEAKER.match(t0)
        if sp and len(segs) > 1:
            text = f"**{sp.group(1)}:** " + row_text(segs[1:])
            im = re.match(r"^(\d{1,2})\s", t0)
            if im:
                ex["items"].append({"t": text, "x": segs[0]["x"]})
            elif ex["items"]:
                ex["items"][-1]["t"] += "<br>" + text
            else:
                ex["intro"].append(text)
            continue
        im = ITEM.match(text)
        if im and im.group(1) == "S" and len(ex["items"]) != 4:
            im = None
        om = OPTION.match(text)
        if om and segs[0]["x"] < bx + 0.1:
            ex["opts"].append({"k": om.group(1), "t": text[om.end():], "after": len(ex["items"])})
            continue
        if im and segs[0]["x"] < bx + 0.03:
            ex["items"].append({"t": text[im.end():], "x": segs[0]["x"]})
            continue
        if re.match(r"^(EXAMPLE|Example)\b", text):
            ex["tail" if ex["items"] else "intro"].append("*" + text + "*")
            continue
        # 接着上一行
        if ex["opts"] and ex["opts"][-1]["after"] == len(ex["items"]):
            ex["opts"][-1]["t"] = join_text(ex["opts"][-1]["t"], text)
        elif ex["items"]:
            if re.match(r"^(Follow up|FOLLOW UP|Tip|TIP)\b", text):
                ex["tail"].append(text)
            elif ex["tail"]:
                ex["tail"][-1] = join_text(ex["tail"][-1], text)
            else:
                ex["items"][-1]["t"] = join_text(ex["items"][-1]["t"], text)
        else:
            if ex["intro"] and segs[0]["x"] >= bx - 0.02 and not ex["words"]:
                ex["intro"][-1] = join_text(ex["intro"][-1], text)
            else:
                ex["intro"].append(text)

    for ex in exs:
        intro = ex["intro"][0] if ex["intro"] else ""
        out.append(f"### {ex['n']} {intro}".rstrip())
        out += [p for p in ex["intro"][1:]]
        if ex["words"]:
            out.append("[[" + " | ".join(ex["words"]) + "]]")
        # 选项全在小题后面：配对题（每个小题填一个字母）；跟在某个小题后面：选择题
        afters = {o["after"] for o in ex["opts"]}
        matching = bool(ex["opts"]) and len(ex["items"]) > 1 and afters <= {0, len(ex["items"])}
        if matching and 0 in afters:
            out += [f"- {o['k']}) {o['t']}" for o in ex["opts"] if o["after"] == 0] + [""]
        for i, it in enumerate(ex["items"], 1):
            t = it["t"]
            mine = [o for o in ex["opts"] if o["after"] == i and not matching]
            if "{_}" not in t and "{__}" not in t and not mine:
                t += " {_}" if matching else " {__}"
            out.append(f"{i}. {t}")
            out += [f"{o['k']}) {o['t']}" for o in mine]
        if matching and len(ex["items"]) in afters:
            out.append("")
            out += [f"- {o['k']}) {o['t']}" for o in ex["opts"] if o["after"] == len(ex["items"])]
        elif not ex["items"]:
            out += [f"- {o['k']}) {o['t']}" for o in ex["opts"]]
            out.append("{__}")  # 没有小题的练习（改写一段话之类）：给一个作答框
        for p in ex["tail"]:
            out += ["", p]
        out.append("")
    return out


def unit_markdown(pages, unit, title, phrase_keys, page_dir=None):
    left, right = 9 + 2 * (unit - 1), 10 + 2 * (unit - 1)
    bold = bolder(phrase_keys)
    image = f"{page_dir}/{left}.jpg" if page_dir else None
    md = [f"# {unit} {title}", ""] + explanation(pages[left], bold, image) + exercises(pages[right], unit)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(md)).strip() + "\n"


if __name__ == "__main__":
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    pages = {p["page"]: p for p in json.loads((root / "data/ocr/phrasal-verbs.json").read_text())}
    pv = json.loads((root / "content/phrasal-verbs.json").read_text())
    u = pv["units"][int(sys.argv[1]) - 1]
    sys.stdout.write(unit_markdown(pages, u["n"], u["title"], [p["key"] for p in u["phrases"]],
                                   root / "content/pages/phrasal-verbs"))
