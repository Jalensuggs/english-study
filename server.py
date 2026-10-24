"""英语学习网站的本地服务器（只用 Python 标准库，不用装任何东西）。

启动:  python3 server.py          然后浏览器打开 http://localhost:8848
手机:  和 Mac 连同一个 WiFi，打开启动时打印的局域网地址

数据:
  data/dict.db   离线词典（scripts/build_dict.py 生成）
  data/user.db   你的生词本、做题记录、学习进度（自动创建，备份这个文件就行）
  content/       题库和短语书内容（scripts/ 里的脚本生成）
"""
import json
import mimetypes
import re
import socket
import sqlite3
import sys
import threading
import time
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
CONTENT = ROOT / "content"
DICT_DB = ROOT / "data/dict.db"
USER_DB = ROOT / "data/user.db"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8848

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/webp", ".webp")

# ---------------------------------------------------------------- 数据库

_local = threading.local()


def dict_db():
    if not hasattr(_local, "dict"):
        _local.dict = sqlite3.connect(f"file:{DICT_DB}?mode=ro", uri=True, check_same_thread=False)
        _local.dict.row_factory = sqlite3.Row
    return _local.dict


def user_db():
    if not hasattr(_local, "user"):
        _local.user = sqlite3.connect(USER_DB, check_same_thread=False)
        _local.user.row_factory = sqlite3.Row
    return _local.user


def init_user_db():
    db = sqlite3.connect(USER_DB)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS vocab(
            id INTEGER PRIMARY KEY,
            word TEXT NOT NULL,            -- 单词或短语
            kind TEXT DEFAULT 'word',      -- word / phrase
            phonetic TEXT, meaning TEXT,   -- 加入时的释义（可以自己改）
            note TEXT DEFAULT '',          -- 自己的笔记
            sentence TEXT DEFAULT '',      -- 出处句子
            source TEXT DEFAULT '',        -- 出处，例如 剑18 Test 1 Passage 1
            source_link TEXT DEFAULT '',   -- 出处页面的链接（#/...）
            added_at REAL,
            ease REAL DEFAULT 2.5,         -- 记忆曲线参数
            interval REAL DEFAULT 0,       -- 下次复习间隔（天）
            reps INTEGER DEFAULT 0,        -- 连续记住的次数
            lapses INTEGER DEFAULT 0,      -- 忘记次数
            due REAL                       -- 下次复习时间
        );
        CREATE UNIQUE INDEX IF NOT EXISTS vocab_word ON vocab(lower(word));
        CREATE TABLE IF NOT EXISTS attempts(
            id INTEGER PRIMARY KEY,
            unit TEXT NOT NULL,            -- 例如 c18a-t1-r1
            answers TEXT,                  -- 你的答案 JSON
            results TEXT,                  -- 每题对错 JSON
            score INTEGER, total INTEGER,
            seconds INTEGER,               -- 用时
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
    """)
    db.commit()
    db.close()


# ---------------------------------------------------------------- 查词

PARTICLES = {"up", "down", "out", "off", "in", "on", "away", "back", "over", "through", "around",
             "round", "about", "along", "across", "forward", "apart", "aside", "by", "into", "onto",
             "after", "for", "with", "at", "to", "from", "of", "together", "ahead", "behind", "under"}
OBJECT_WORDS = {"it", "them", "him", "her", "me", "us", "you", "this", "that", "these", "those",
                "something", "someone", "somebody", "one", "himself", "herself", "themselves",
                "yourself", "myself", "itself", "ourselves"}
POSSESSIVES = {"my", "your", "his", "her", "its", "our", "their"}
WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


def clean_word(w):
    return w.replace("’", "'").strip(" '\"-.,;:!?()[]").lower()


@lru_cache(maxsize=50000)
def entry(word):
    db = dict_db()
    r = db.execute("SELECT * FROM dict WHERE word = ?", (word,)).fetchone()
    if r is None:
        r = db.execute("SELECT * FROM dict WHERE lower(word) = ? LIMIT 1", (word.lower(),)).fetchone()
    return dict(r) if r else None


@lru_cache(maxsize=50000)
def lemmas(word):
    """一个词可能的原形，例如 gave -> [gave, give]，studies -> [studies, study]。"""
    w = clean_word(word)
    out = [w]
    e = entry(w)
    if e and e["exchange"]:
        for part in e["exchange"].split("/"):
            if part.startswith("0:"):
                lemma = part[2:]
                if lemma and lemma not in out:
                    out.append(lemma)
    # 词典里没有的变形，做个简单还原
    if len(out) == 1:
        for suf, rep in (("ies", "y"), ("ied", "y"), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"),
                         ("es", ""), ("s", "")):
            if w.endswith(suf) and len(w) > len(suf) + 2:
                cand = w[: -len(suf)] + rep
                if entry(cand) and cand not in out:
                    out.append(cand)
                    break
    return tuple(out)


def word_card(word):
    """单个词的卡片：原词 + 原形（如果不同）。"""
    w = clean_word(word)
    if not w:
        return None
    ls = lemmas(w)
    e = entry(w)
    main = e
    lemma_entry = None
    if len(ls) > 1:
        lemma_entry = entry(ls[1])
        # 原词条只是"xx的过去式"这种引用时，用原形作为主词条
        if lemma_entry and (not e or len(e["translation"]) < 25):
            main, lemma_entry = lemma_entry, e
    if not main:
        return None
    return {"word": main["word"], "phonetic": main["phonetic"], "translation": main["translation"],
            "definition": main["definition"], "tag": main["tag"], "exchange": main["exchange"],
            "collins": main["collins"], "oxford": main["oxford"],
            "form": ({"word": w, "note": (lemma_entry or {}).get("translation", "")} if main["word"].lower() != w else None)}


@lru_cache(maxsize=1)
def pv_index():
    """短语动词书的索引：短语 -> 单元号。"""
    p = CONTENT / "phrasal-verbs.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("index", {}).items()}


@lru_cache(maxsize=1)
def pv_entries():
    p = CONTENT / "phrasal-verbs.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("entries", {})


def phrase_translation(key):
    """短语的中文释义：先查原样，再查去掉 sb/sth 的版本。"""
    e = entry(key)
    if e and e["translation"]:
        return e["translation"]
    rows = phrase_rows([key])
    rows.sort(key=lambda r: rank(r, r["key"], key.split()), reverse=True)
    return rows[0]["translation"] if rows else ""


def phrase_rows(keys):
    keys = list(dict.fromkeys(k for k in keys if k and " " in k))
    if not keys:
        return []
    db = dict_db()
    out = []
    for i in range(0, len(keys), 300):
        chunk = keys[i:i + 300]
        q = f"SELECT p.key, d.* FROM phrase p JOIN dict d ON d.word = p.word WHERE p.key IN ({','.join('?' * len(chunk))})"
        out += [dict(r) for r in db.execute(q, chunk)]
    return out


def variants(tokens):
    """一串词的所有"原形组合"，例如 [gave, up] -> gave up / give up。"""
    combos = [[]]
    for t in tokens:
        opts = lemmas(t)[:3]
        combos = [c + [o] for c in combos for o in opts]
        if len(combos) > 200:
            break
    return [" ".join(c) for c in combos]


def keys_for_span(tokens):
    """一个片段可能对应的词典短语键。会去掉中间的宾语代词，如 put it off -> put off。"""
    keys = set(variants(tokens))
    if len(tokens) >= 3:
        inner = [t for i, t in enumerate(tokens) if i == 0 or i == len(tokens) - 1 or
                 (clean_word(t) not in OBJECT_WORDS and clean_word(t) not in POSSESSIVES)]
        if len(inner) != len(tokens):
            keys |= set(variants(inner))
        # one's：take one's time -> take one's 被去掉 -> take time
    return keys


def is_verb(word):
    e = entry(word)
    if not e:
        return False
    return ("v:" in (e["pos"] or "")) or bool(re.search(r"(^|\n)(v|vt|vi|vt\.& vi)\.", e["translation"] or ""))


def phrase_quality(row, key):
    """过滤掉词典里过于生僻、只是普通词组合的短语。"""
    words = key.split()
    if key in pv_index():
        return 3
    if row.get("tag") or row.get("collins") or row.get("oxford"):
        return 2
    first = entry(words[0])
    if len(words) >= 2 and words[-1] in PARTICLES and is_verb(words[0]):
        return 2
    if len(words) >= 3:
        return 1
    if len(words) == 2 and (words[0] in PARTICLES or words[-1] in PARTICLES):
        return 1
    if len(words) == 2 and is_verb(words[0]):
        return 1  # 动词 + 名词的搭配，例如 bear fruit
    return 0


SEPARABLE = {"up", "down", "out", "off", "away", "back", "over", "around", "round", "about", "apart",
             "aside", "along", "forward", "together", "in", "on", "through"}


def rank(row, key, span_tokens):
    """同一个片段可能匹配到好几个词条，挑最合适的：
    常用 > 不带占位词 > 只有第一个词变回原形（carry out 而不是 carried out / in term of）> 释义更全"""
    words = row["word"].lower().split()
    raw = [clean_word(t) for t in span_tokens]
    exact = row["word"].lower() == key
    rest_raw = all(w in raw for w in words[1:] if w not in OBJECT_WORDS)
    first_base = bool(words) and words[0] == lemmas(words[0])[-1]
    return (phrase_quality(row, key), exact, rest_raw, first_base, min(len(row["translation"]), 60))


def detect_phrases(sentence, index):
    """在句子里找包含第 index 个词的常用短语（点一个词时自动提示）。"""
    tokens = WORD_RE.findall(sentence)
    if not tokens or index is None or index < 0 or index >= len(tokens):
        return []
    spans = {}  # key -> (start, end)
    for start in range(max(0, index - 5), index + 1):
        for end in range(index + 1, min(len(tokens), start + 7) + 1):
            if end - start < 2:
                continue
            for k in keys_for_span(tokens[start:end]):
                spans.setdefault(k, (start, end))
    # 可分开的短语动词：动词 + (1-3 个词) + 小品词，例如 put the meeting off
    for vi in range(max(0, index - 4), index + 1):
        for pi in range(vi + 2, min(len(tokens), vi + 5)):
            if vi != index and pi != index:
                continue
            if clean_word(tokens[pi]) in SEPARABLE:
                for k in variants([tokens[vi], tokens[pi]]):
                    spans.setdefault(k, (vi, pi + 1))
    best = {}  # 每个片段只留一个最合适的词条
    for r in phrase_rows(spans.keys()):
        key = r["key"]
        if phrase_quality(r, key) == 0:
            continue
        start, end = spans[key]
        rk = (len(key.split()),) + rank(r, key, tokens[start:end])[0:1] + rank(r, key, tokens[start:end])[1:]
        if (start, end) not in best or rk > best[(start, end)][0]:
            best[(start, end)] = (rk, r, key)
    res = []
    for (start, end), (rk, r, key) in best.items():
        res.append({"phrase": r["word"], "key": key, "translation": r["translation"],
                    "phonetic": r["phonetic"], "span": [start, end], "unit": pv_index().get(key),
                    "_rank": (rk[1], end - start, rk[2:])})
    # 长短语继承它所包含的短短语的"常用度"：take part in 排在 take part 前面
    for a in res:
        for b in res:
            if a is not b and a["key"].startswith(b["key"] + " ") and b["_rank"][0] > a["_rank"][0]:
                a["_rank"] = (b["_rank"][0],) + a["_rank"][1:]
    res.sort(key=lambda x: x["_rank"], reverse=True)
    for x in res:
        del x["_rank"]
    return res[:3]


def lookup_text(text):
    """查一段选中的文字（一般是短语）。"""
    t = " ".join(WORD_RE.findall(text))
    if not t:
        return None
    e = entry(t) or entry(t.lower())
    if e and " " in t:
        return {"phrase": e["word"], "key": t.lower(), "translation": e["translation"], "phonetic": e["phonetic"],
                "definition": e["definition"], "unit": pv_index().get(t.lower())}
    tokens = t.split()
    rows = phrase_rows(keys_for_span(tokens))
    if not rows and len(tokens) >= 3:
        # 动词 + 小品词，中间隔开
        if clean_word(tokens[-1]) in PARTICLES:
            rows = phrase_rows(variants([tokens[0], tokens[-1]]))
    if rows:
        rows.sort(key=lambda r: rank(r, r["key"], tokens), reverse=True)
        r = rows[0]
        return {"phrase": r["word"], "key": r["key"], "translation": r["translation"], "phonetic": r["phonetic"],
                "definition": r["definition"], "unit": pv_index().get(r["key"])}
    return None


def related_phrases(word, limit=12):
    """以这个词开头的短语（来自短语动词书）。"""
    ls = lemmas(word)
    keys = sorted(k for k in pv_index() if k.split()[0] in ls)
    return [{"phrase": k, "key": k, "unit": pv_index()[k], "translation": phrase_translation(k)} for k in keys[:limit]]


# ---------------------------------------------------------------- 记忆曲线（简化版 SM-2）

DAY = 86400


def schedule(card, grade):
    """grade: 0 忘了 / 1 模糊 / 2 认识 / 3 太简单"""
    ease, interval, reps, lapses = card["ease"], card["interval"], card["reps"], card["lapses"]
    if grade == 0:
        reps, lapses = 0, lapses + 1
        interval = 10 / 1440  # 10 分钟后再来
        ease = max(1.3, ease - 0.2)
    elif grade == 1:
        interval = max(1, interval * 1.2) if reps else 1
        ease = max(1.3, ease - 0.15)
        reps += 1
    else:
        if reps == 0:
            interval = 1 if grade == 2 else 4
        elif reps == 1:
            interval = 3 if grade == 2 else 6
        else:
            interval = interval * ease * (1.3 if grade == 3 else 1)
        if grade == 3:
            ease += 0.15
        reps += 1
    return {"ease": ease, "interval": interval, "reps": reps, "lapses": lapses,
            "due": time.time() + interval * DAY}


# ---------------------------------------------------------------- HTTP

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def translate_path(self, path):
        path = unquote(urlparse(path).path)
        if path.startswith("/content/"):
            base, rel = CONTENT, path[len("/content/"):]
        else:
            base, rel = WEB, path.lstrip("/") or "index.html"
        full = (base / rel).resolve()
        if base.resolve() not in full.parents and full != base.resolve():
            return str(WEB / "index.html")
        return str(full)

    def end_headers(self):
        if not self.path.startswith("/api/"):
            # 页面图片可以缓存久一点，代码文件每次检查更新
            if self.path.startswith("/content/pages/"):
                self.send_header("Cache-Control", "max-age=604800")
            else:
                self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # ---- 路由
    def do_GET(self):
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return super().do_GET()
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            self.route_get(u.path, q)
        except Exception as e:  # noqa
            self.send_json({"error": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            self.route_post(u.path, self.read_json())
        except Exception as e:  # noqa
            self.send_json({"error": str(e)}, 500)

    def do_DELETE(self):
        u = urlparse(self.path)
        m = re.fullmatch(r"/api/vocab/(\d+)", u.path)
        if m:
            db = user_db()
            db.execute("DELETE FROM vocab WHERE id = ?", (int(m.group(1)),))
            db.commit()
            return self.send_json({"ok": True})
        m = re.fullmatch(r"/api/attempts/(\d+)", u.path)
        if m:
            db = user_db()
            db.execute("DELETE FROM attempts WHERE id = ?", (int(m.group(1)),))
            db.commit()
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def route_get(self, path, q):
        db = user_db()
        if path == "/api/lookup":
            # q: 选中的文字；sentence + index: 点了句子里第几个词
            text = q.get("q", "").strip()
            words = WORD_RE.findall(text)
            res = {"query": text}
            if len(words) == 1:
                res["word"] = word_card(words[0])
                if q.get("sentence"):
                    res["phrases"] = detect_phrases(q["sentence"], int(q.get("index", -1)))
                res["related"] = related_phrases(words[0])
            elif len(words) > 1:
                res["phrase"] = lookup_text(text)
                if not res["phrase"]:
                    res["words"] = [c for c in (word_card(w) for w in words[:8]) if c]
            if res.get("word"):
                key = res["word"]["word"].lower()
                row = db.execute("SELECT id FROM vocab WHERE lower(word) = ?", (key,)).fetchone()
                res["word"]["saved"] = row["id"] if row else None
            for p in res.get("phrases", []) + ([res["phrase"]] if res.get("phrase") else []):
                pe = pv_entries().get((p.get("key") or p["phrase"]).lower())
                if pe:
                    p["def"] = pe["def"]
                    p["unit"] = pe["units"]
                row = db.execute("SELECT id FROM vocab WHERE lower(word) = ?", (p["phrase"].lower(),)).fetchone()
                p["saved"] = row["id"] if row else None
            return self.send_json(res)
        if path == "/api/vocab":
            rows = [dict(r) for r in db.execute("SELECT * FROM vocab ORDER BY added_at DESC")]
            return self.send_json({"items": rows, "now": time.time()})
        if path == "/api/vocab/due":
            rows = [dict(r) for r in db.execute(
                "SELECT * FROM vocab WHERE due <= ? ORDER BY due LIMIT ?", (time.time(), int(q.get("limit", 50))))]
            total = db.execute("SELECT count(*) FROM vocab WHERE due <= ?", (time.time(),)).fetchone()[0]
            return self.send_json({"items": rows, "total": total})
        if path == "/api/attempts":
            sql = "SELECT * FROM attempts"
            args = ()
            if q.get("unit"):
                sql += " WHERE unit = ?"
                args = (q["unit"],)
            rows = [dict(r) for r in db.execute(sql + " ORDER BY created_at DESC", args)]
            for r in rows:
                r["answers"] = json.loads(r["answers"] or "{}")
                r["results"] = json.loads(r["results"] or "{}")
            return self.send_json({"items": rows})
        if path == "/api/kv":
            row = db.execute("SELECT value FROM kv WHERE key = ?", (q.get("key"),)).fetchone()
            return self.send_json({"value": json.loads(row["value"]) if row else None})
        if path == "/api/stats":
            due = db.execute("SELECT count(*) FROM vocab WHERE due <= ?", (time.time(),)).fetchone()[0]
            total = db.execute("SELECT count(*) FROM vocab").fetchone()[0]
            attempts = db.execute("SELECT count(*) FROM attempts").fetchone()[0]
            return self.send_json({"due": due, "vocab": total, "attempts": attempts})
        self.send_json({"error": "not found"}, 404)

    def route_post(self, path, body):
        db = user_db()
        if path == "/api/vocab":
            word = (body.get("word") or "").strip()
            if not word:
                return self.send_json({"error": "空的"}, 400)
            row = db.execute("SELECT id FROM vocab WHERE lower(word) = ?", (word.lower(),)).fetchone()
            if row:
                return self.send_json({"id": row["id"], "existed": True})
            now = time.time()
            cur = db.execute(
                "INSERT INTO vocab(word, kind, phonetic, meaning, sentence, source, source_link, added_at, due)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (word, body.get("kind", "phrase" if " " in word else "word"), body.get("phonetic", ""),
                 body.get("meaning", ""), body.get("sentence", ""), body.get("source", ""),
                 body.get("source_link", ""), now, now))
            db.commit()
            return self.send_json({"id": cur.lastrowid})
        m = re.fullmatch(r"/api/vocab/(\d+)", path)
        if m:  # 修改释义 / 笔记
            fields = {k: body[k] for k in ("meaning", "note") if k in body}
            if fields:
                db.execute(f"UPDATE vocab SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ?",
                           (*fields.values(), int(m.group(1))))
                db.commit()
            return self.send_json({"ok": True})
        m = re.fullmatch(r"/api/vocab/(\d+)/review", path)
        if m:
            card = db.execute("SELECT * FROM vocab WHERE id = ?", (int(m.group(1)),)).fetchone()
            if not card:
                return self.send_json({"error": "not found"}, 404)
            s = schedule(dict(card), int(body.get("grade", 2)))
            db.execute("UPDATE vocab SET ease=?, interval=?, reps=?, lapses=?, due=? WHERE id=?",
                       (s["ease"], s["interval"], s["reps"], s["lapses"], s["due"], card["id"]))
            db.commit()
            return self.send_json(s)
        if path == "/api/attempts":
            cur = db.execute(
                "INSERT INTO attempts(unit, answers, results, score, total, seconds, created_at) VALUES (?,?,?,?,?,?,?)",
                (body["unit"], json.dumps(body.get("answers", {}), ensure_ascii=False),
                 json.dumps(body.get("results", {}), ensure_ascii=False), body.get("score"), body.get("total"),
                 body.get("seconds"), time.time()))
            db.commit()
            return self.send_json({"id": cur.lastrowid})
        if path == "/api/phrases":
            return self.send_json({k: phrase_translation(k) for k in body.get("keys", [])[:200]})
        if path == "/api/kv":
            db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)",
                       (body["key"], json.dumps(body.get("value"), ensure_ascii=False)))
            db.commit()
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


if __name__ == "__main__":
    init_user_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"英语学习网站已启动：")
    print(f"  电脑: http://localhost:{PORT}")
    ip = lan_ip()
    if ip:
        print(f"  手机（同一个 WiFi）: http://{ip}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
