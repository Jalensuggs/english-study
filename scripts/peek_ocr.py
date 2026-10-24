import json, sys, re
pages = json.load(open(sys.argv[1]))
lo, hi = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (1, 9999)
for p in pages:
    if not lo <= p['page'] <= hi: continue
    paras = sorted(p['paras'], key=lambda x: x['y'])
    ts = [x['t'].replace('\n', ' ') for x in paras]
    keys = [t[:40] for t in ts if re.match(r'(Test \d|TEST \d|READING|LISTENING|WRITING|SPEAKING|SECTION|PART \d|Questions? \d|Audioscripts|Answer key|Reading Passage)', t, re.I)]
    words = sum(len(t.split()) for t in ts)
    print(p['page'], words, '|', ' / '.join(t[:30] for t in ts[:3])[:80], '||', ' ; '.join(keys[:5])[:130])
