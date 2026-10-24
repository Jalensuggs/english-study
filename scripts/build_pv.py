"""从 OCR 结果生成《English Phrasal Verbs in Use》的单元内容和短语索引。

输出 content/phrasal-verbs.json：
  units:  [{n, title, group, pages:[左页,右页], keyPages:[答案页], phrases:[{phrase, key, def}], blocks:[...]}]
  index:  {短语查询键: [单元号, ...]}     例如 "give up": [2, 28, 35]
  entries: {短语查询键: {phrase, def, units}}   书后 Mini dictionary 的英文释义

用法: python3 scripts/build_pv.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_content import clean_text  # noqa: E402
from pv_layout import unit_markdown  # noqa: E402

pages = {p["page"]: p for p in json.loads((ROOT / "data/ocr/phrasal-verbs.json").read_text())}
FIRST_UNIT_PAGE = 9
KEY_PAGES = range(149, 186)
DICT_PAGES = range(186, 210)
PLACEHOLDERS = {"sb", "sth", "somebody", "something", "someone", "one's", "sb's", "sth's", "oneself",
                "doing", "do", "sb/sth", "sth/sb", "sth/doing", "sth/sb's", "sb/sth's"}


def phrase_key(head):
    h = head.lower().replace("’", "'")
    h = h.split(" or ")[0]
    h = re.sub(r"\([^)]*\)", " ", h)
    h = re.sub(r"[»*•]", " ", h)
    words = []
    for w in h.split():
        w = w.split("/")[0].strip(",.;:!?")
        # OCR 把 sb/sth 认成了 sbisth、thisb、thor(=sth or)、swh(=somewhere) 等
        if not w or w in PLACEHOLDERS or re.fullmatch(r"(s?[bh]?i?s?th?|th?i?s?b|thor|swh|sbisb|sh|s[bh]s?th)", w):
            continue
        words.append(w)
    half = len(words) // 2
    if len(words) % 2 == 0 and words[:half] == words[half:]:
        words = words[:half]  # "call off sth or call sth off" 识别成了 call off call off
    return " ".join(words)


def reading_order(page):
    """两栏的页面：先左栏后右栏。"""
    paras = [p for p in page["paras"] if p["t"].strip()]
    return sorted(paras, key=lambda p: (0 if p["x"] < 0.45 else 1, p["y"]))


# ---------------------------------------------------------------- 目录

def contents():
    titles, group = {}, None
    for n in (4, 5):
        for p in sorted(pages[n]["paras"], key=lambda p: (p["x"] > 0.5, p["y"])):
            for line in p["t"].split("\n"):
                line = line.strip()
                m = re.match(r"^(\d{1,2})\s+(.+?)\s*(\d{1,3})?$", line)
                if m and 1 <= int(m.group(1)) <= 70 and "Phrasal Verbs in Use" not in m.group(2):
                    titles.setdefault(int(m.group(1)), (m.group(2).strip(), group))
                elif line and not re.search(r"\d", line) and line not in ("Contents",) and len(line) < 40:
                    group = line
    # 目录里 OCR 漏掉的两行
    titles.setdefault(14, ("Out", "Key particles"))
    titles.setdefault(15, ("Off", "Key particles"))
    return titles


# ---------------------------------------------------------------- Mini dictionary

DEF_START = re.compile(
    r"\s(?=(to|if|informal|British|American|Australian|used|when|something|someone|an?|the|said|"
    r"n|adj|ad|na|phrase|very)\b)")


def mini_dictionary():
    stream = []
    for n in DICT_PAGES:
        for p in reading_order(pages[n]):
            t = clean_text(p["t"])
            if re.search(r"English Phrasal Verbs in Use|^Mini dictionary|The numbers in the Mini", t):
                continue
            stream.append(t)
    text = " ".join(stream)
    # 每个词条以单元号结尾：…… 2, 38
    entries = {}
    for m in re.finditer(r"(.+?)\s((?:\d{1,2}\s*,\s*)*\d{1,2})(?=\s+[a-zA-Z(]|$)", text):
        body, nums = m.group(1).strip(), m.group(2)
        units = sorted({int(x) for x in re.findall(r"\d+", nums) if 1 <= int(x) <= 70})
        if not units:
            continue
        # 词头 = 定义开始之前的部分
        d = DEF_START.search(" " + body)
        if not d or d.start() < 2:
            continue
        head = body[:d.start() - 1].strip(" ,;")
        definition = body[d.start():].strip()
        if not re.match(r"^[A-Za-z]", head) or len(head.split()) > 9:
            continue
        key = phrase_key(head)
        if not key or len(key) < 3:
            continue
        # 词头里 sb/sth 的 OCR 错误，显示时改回来
        for bad, good in ((r"\bthisb\b|\bth/sb\b|\bsthisb\b", "sth/sb"), (r"\bsbisth\b|\bsbsth\b", "sb/sth"),
                          (r"\bthor\b", "sth or"), (r"\bsh\b", "sb"), (r"\bth\b", "sth"), (r"\bswh\b", "somewhere"),
                          (r"\btolonto\b", "to/onto"), (r"[»*•]", "")):
            head = re.sub(bad, good, head).strip()
        e = entries.setdefault(key, {"phrase": head, "defs": [], "units": []})
        if definition not in e["defs"]:
            e["defs"].append(definition)
        e["units"] = sorted(set(e["units"]) | set(units))
    return entries


# ---------------------------------------------------------------- 单元正文

def unit_blocks(n_pages):
    out = []
    for n in n_pages:
        for p in reading_order(pages[n]):
            t = clean_text(p["t"])
            if not t or re.fullmatch(r"\d{1,3}|English Phrasal Verbs in Use|Exercises", t):
                if t == "Exercises":
                    out.append({"type": "title", "text": "Exercises"})
                continue
            if re.fullmatch(r"[A-F]", t):
                out.append({"type": "sec", "text": t})
            elif re.fullmatch(r"\d{1,2}\.\d", t):
                out.append({"type": "ex", "text": t})
            elif len(t.split()) <= 7 and not re.search(r"[.?!]$", t):
                out.append({"type": "h", "text": t})
            else:
                out.append({"type": "p", "text": t})
    return out


def key_pages():
    where = {}
    for n in KEY_PAGES:
        txt = " ".join(p["t"] for p in pages[n]["paras"])
        for m in re.finditer(r"Unit\s+(\d{1,2})\b", txt):
            where.setdefault(int(m.group(1)), n)
        # 有的单元标题没识别出来，用 "12.1" 这种题号判断
        for m in re.finditer(r"\b(\d{1,2})\.[1lI]\b", txt):
            where.setdefault(int(m.group(1)), n)
    out = {}
    for u in range(1, 71):
        start = where.get(u)
        if not start:
            # 这个单元的标题没识别出来：取前后两个单元之间的页
            prev = max((where[v] for v in range(1, u) if v in where), default=None)
            nxt = min((where[v] for v in range(u + 1, 71) if v in where), default=None)
            if prev and nxt:
                out[u] = list(range(prev, nxt + 1))
            continue
        nxt = min((where[v] for v in range(u + 1, 71) if v in where), default=start)
        out[u] = list(range(start, max(start, nxt) + 1))
    return out


# ---------------------------------------------------------------- 文字版（content-src/pv/）

def key_by_unit():
    """content-src/pv/key.md -> {单元号: {"md": 整个单元的答案, "ex": {"6.1": 这道题的答案}}}"""
    out, unit, ex = {}, None, None
    for line in (ROOT / "content-src/pv/key.md").read_text().split("\n"):
        m = re.match(r"^## Unit (\d+)\s*$", line)
        if m:
            unit, ex = int(m.group(1)), None
            out[unit] = {"md": [], "ex": {}}
            continue
        if unit is None:
            continue
        m = re.match(r"^### (\d+\.\d+)\s*$", line)
        if m:
            ex = m.group(1)
            out[unit]["ex"][ex] = []
        elif ex:
            out[unit]["ex"][ex].append(line)
        out[unit]["md"].append(line)
    return {u: {"md": "\n".join(v["md"]).strip(), "ex": {k: "\n".join(x).strip() for k, x in v["ex"].items()}}
            for u, v in out.items()}


def write_text_units(units):
    """每个单元写成 content/pv/NN.json，网页直接显示文字。
    有手工整理的 content-src/pv/NN.md 就用它，没有就按 OCR 版面自动还原（scripts/pv_layout.py）；
    自动还原出来的练习数和答案对不上的单元，还是显示原书图片。"""
    keys = key_by_unit()
    out_dir = ROOT / "content/pv"
    out_dir.mkdir(exist_ok=True)
    for u in units:
        src = ROOT / f"content-src/pv/{u['n']:02d}.md"
        k = keys.get(u["n"], {"md": "", "ex": {}})
        if src.exists():
            doc, u["auto"] = src.read_text().strip(), False
        else:
            doc = unit_markdown(pages, u["n"], u["title"], [p["key"] for p in u["phrases"]],
                                ROOT / "content/pages/phrasal-verbs").strip()
            u["auto"] = True
            if sorted(re.findall(r"^### (\d+\.\d+)", doc, re.M)) != sorted(k["ex"]):
                doc = ""
        u["text"] = bool(doc)
        u["hasKey"] = bool(k["md"])
        (out_dir / f"{u['n']:02d}.json").write_text(json.dumps({"doc": doc, "key": k["md"], "keyEx": k["ex"]},
                                                              ensure_ascii=False, indent=1))
    for old in out_dir.glob("*.json"):
        if not re.fullmatch(r"\d\d\.json", old.name):
            old.unlink()


def main():
    titles = contents()
    entries = mini_dictionary()
    kp = key_pages()
    index = {}
    for key, e in entries.items():
        index[key] = e["units"]
    units = []
    for u in range(1, 71):
        left = FIRST_UNIT_PAGE + 2 * (u - 1)
        title, group = titles.get(u, (f"Unit {u}", None))
        phrases = [{"phrase": e["phrase"], "key": k, "def": "; ".join(e["defs"][:2])}
                   for k, e in sorted(entries.items()) if u in e["units"]]
        units.append({"n": u, "title": title, "group": group, "pages": [left, left + 1],
                      "keyPages": kp.get(u, []), "phrases": phrases, "blocks": unit_blocks([left, left + 1])})
    write_text_units(units)
    out ={"units": units, "index": index,
           "entries": {k: {"phrase": e["phrase"], "def": "; ".join(e["defs"][:3]), "units": e["units"]}
                       for k, e in entries.items()}}
    (ROOT / "content/phrasal-verbs.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(units)} 个单元，Mini dictionary {len(entries)} 个短语，"
          f"有标题 {sum(1 for u in units if not u['title'].startswith('Unit'))}，"
          f"有答案页 {sum(1 for u in units if u['keyPages'])}，文字版 {sum(1 for u in units if u['text'])}"
          f"（自动还原 {sum(1 for u in units if u['text'] and u['auto'])}）")


if __name__ == "__main__":
    main()
