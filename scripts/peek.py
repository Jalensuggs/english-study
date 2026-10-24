import fitz, sys, re
doc = fitz.open(sys.argv[1])
for i, p in enumerate(doc):
    t = p.get_text()
    lines = [l.strip() for l in t.splitlines() if l.strip() and 'polcet' not in l.lower() and 'POLCET' not in l]
    keys = [l for l in lines if re.search(r'^(Test \d|TEST \d|READING|Reading|LISTENING|WRITING|SPEAKING|READING PASSAGE|SECTION|Section \d|Answer key|Listening and Reading answer|Audioscripts?|Contents|Unit \d)', l)]
    print(i+1, len(t.split()), '|', ' / '.join(lines[:3])[:90], '||', ' ; '.join(keys[:4])[:120])
