"""检查转写的题目：每道题的空/题号/选项都要出现，且只出现一次。"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
ans = json.loads((ROOT / "content-src/answers.json").read_text())
bad = 0
for f in sorted((ROOT / "content-src/questions").glob("*.md")):
    uid = f.stem
    src = f.read_text()
    need = sorted(int(x) for k in ans[uid] for x in k.split("&"))
    found = [int(x) for x in re.findall(r"\{(\d+)\}", src)]
    found += [int(x) for x in re.findall(r"^(\d+)\.\s+(?!.*\{\d+\})", src, re.M)]
    for m in re.findall(r"^@pick ([\d, ]+)", src, re.M):
        found += [int(x) for x in m.split(",")]
    missing = sorted(set(need) - set(found))
    extra = sorted(set(found) - set(need))
    dup = sorted({x for x in found if found.count(x) > 1})
    # 字母/罗马数字题：要么有 @options，要么后面跟着 A. B. 选项
    if missing or extra or dup:
        bad += 1
        print(f"✗ {uid}: 缺 {missing} 多 {extra} 重复 {dup}")
    else:
        print(f"✓ {uid}")
print("有问题:", bad)
