"""把 ECDICT 的 CSV 转成 SQLite，方便快速查词和查短语。

输出 data/dict.db：
  dict(word, phonetic, translation, definition, pos, tag, collins, oxford, bnc, frq, exchange)
  phrase(key, word)   短语的"查询键"：去掉 sb/sth 这类占位词后的小写形式，例如
                      "look sth up" -> "look up"，"take sth into account" -> "take into account"
用法: python3 scripts/build_dict.py
"""
import csv
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/ecdict/ecdict.csv"
OUT = ROOT / "data/dict.db"

PLACEHOLDERS = {"sb", "sth", "somebody", "something", "someone", "one's", "sb's", "sth's",
                "oneself", "somewhere", "sb/sth", "sth/sb", "doing", "do"}


def phrase_key(word: str) -> str:
    w = word.lower().replace("’", "'")
    w = re.sub(r"[()\[\]]", " ", w)
    parts = [p for p in re.split(r"\s+", w) if p and p not in PLACEHOLDERS]
    return " ".join(parts)


def main():
    if OUT.exists():
        OUT.unlink()
    db = sqlite3.connect(OUT)
    db.executescript("""
        CREATE TABLE dict(word TEXT PRIMARY KEY, phonetic TEXT, translation TEXT, definition TEXT,
                          pos TEXT, tag TEXT, collins INT, oxford INT, bnc INT, frq INT, exchange TEXT);
        CREATE TABLE phrase(key TEXT, word TEXT);
    """)
    rows, phrases = [], []
    with open(SRC, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            word = r["word"].strip()
            if not word or not r["translation"].strip():
                continue
            # 原数据里换行写成了字面的 \n，转成真正的换行
            tr = r["translation"].replace("\\n", "\n").strip()
            df = r["definition"].replace("\\n", "\n").strip()
            rows.append((word, r["phonetic"], tr, df, r["pos"], r["tag"],
                         int(r["collins"] or 0), int(r["oxford"] or 0), int(r["bnc"] or 0),
                         int(r["frq"] or 0), r["exchange"]))
            if " " in word:
                k = phrase_key(word)
                if k and " " in k or (k and k != word.lower()):
                    phrases.append((k, word))
    db.executemany("INSERT OR IGNORE INTO dict VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO phrase VALUES (?,?)", phrases)
    db.executescript("""
        CREATE INDEX dict_lower ON dict(lower(word));
        CREATE INDEX phrase_key ON phrase(key);
    """)
    db.commit()
    print(f"{len(rows)} 词条，{len(phrases)} 个短语键 -> {OUT}")


if __name__ == "__main__":
    main()
