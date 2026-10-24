import json, sys
for uid in sys.argv[1:]:
    u = json.load(open(f"content/units/{uid}.json"))
    print("#####", uid, u["title"], u["pages"], u["qpages"])
    for b in u["blocks"]:
        print(f"  [{b['type']}{(' '+b['label']) if b.get('label') else ''}] {b['text'][:110]}{'…' if len(b['text'])>110 else ''}")
