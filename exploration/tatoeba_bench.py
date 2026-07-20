import bz2, csv, json, re, sys
from collections import defaultdict

# 1. Dutch sentence IDs that have an English translation link
linked = set()
with bz2.open(sys.argv[2], 'rt') as f:
    for line in f:
        parts = line.split('\t')
        if len(parts) >= 2:
            linked.add(parts[0])

# 2. Index tokens of linked Dutch sentences
tok_re = re.compile(r"[a-zàáäèéëïijöüû']+")
word_sents = defaultdict(list)   # token -> [(len, sentence)]
n_sent = 0
with bz2.open(sys.argv[1], 'rt') as f:
    for line in f:
        sid, lang, text = line.rstrip('\n').split('\t')[:3]
        if sid not in linked:
            continue
        n_sent += 1
        toks = set(tok_re.findall(text.lower()))
        nw = len(text.split())
        for t in toks:
            b = word_sents[t]
            if len(b) < 3:
                b.append((nw, text))

# 3. lemma -> inflected forms from kaikki (candidates only)
cands = [r['lemma'] for r in csv.DictReader(open(sys.argv[3]))][:3000]
candset = set(cands)
lemma_forms = defaultdict(set)
with open(sys.argv[4]) as f:
    for line in f:
        e = json.loads(line)
        w = e.get('word', '').lower()
        if w in candset:
            lemma_forms[w].add(w)
            for fo in e.get('forms', []):
                fw = fo.get('form', '').lower()
                if fw and ' ' not in fw:
                    lemma_forms[w].add(fw)

hits, miss = 0, []
short_hit = 0
for c in cands:
    forms = lemma_forms.get(c, {c})
    found = [s for fm in forms for s in word_sents.get(fm, [])]
    if found:
        hits += 1
        if min(nw for nw, _ in found) <= 12:
            short_hit += 1
    else:
        miss.append(c)

print(f"linked Dutch sentences (have EN translation): {n_sent}")
print(f"lemma coverage: {hits}/{len(cands)} ({hits/len(cands):.1%})")
print(f"  with a short (<=12 words) example: {short_hit} ({short_hit/len(cands):.1%})")
print(f"misses: {len(miss)}; sample:", miss[:30])
