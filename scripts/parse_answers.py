"""把 content-src/answers.txt 转成 content-src/answers.json。
每题保存为可接受答案的列表；顺序不限的多选题保存为 {"10&11": {"any": ["C", "D"]}}。"""
import itertools
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def expand(ans):
    """flavour / flavor -> [flavour, flavor]；(food) consumption -> [food consumption, consumption]"""
    out = []
    for alt in ans.split("/"):
        alt = alt.strip()
        parts = re.split(r"(\([^)]*\))", alt)
        opts = [[p] if not p.startswith("(") else ["", p[1:-1]] for p in parts]
        for combo in itertools.product(*opts):
            v = re.sub(r"\s+", " ", "".join(combo)).strip()
            if v and v not in out:
                out.append(v)
    return out


def main():
    data, cur = {}, None
    for line in (ROOT / "content-src/answers.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1)
            data[cur] = {}
            continue
        num, ans = line.split(" ", 1)
        if "&" in num:
            data[cur][num] = {"any": [a.strip() for a in ans.split(",")]}
        else:
            data[cur][num] = expand(ans)
    (ROOT / "content-src/answers.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    total = sum(len(k.split("&")) for u in data.values() for k in u)
    print(f"{len(data)} 个篇章，{total} 道题")
    for uid, u in data.items():
        nums = sorted(int(x) for k in u for x in k.split("&"))
        if nums != list(range(nums[0], nums[-1] + 1)):
            print("  题号不连续:", uid, nums)


if __name__ == "__main__":
    main()
