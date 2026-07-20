import json, csv, sys
from collections import defaultdict

# Load draft lemma candidates
cands = []
with open(sys.argv[2]) as f:
    for row in csv.DictReader(f):
        cands.append(row['lemma'])
candset = set(cands[:3000])

# Index kaikki: word -> info. Also index all inflected forms -> lemma.
entries = defaultdict(lambda: {'pos': set(), 'gender': set(), 'gloss': False, 'labels': set()})
form_to_lemma = {}
n = 0
with open(sys.argv[1]) as f:
    for line in f:
        n += 1
        e = json.loads(line)
        w = e.get('word', '')
        if not w or not w.islower() or ' ' in w:
            continue
        pos = e.get('pos', '')
        rec = entries[w]
        rec['pos'].add(pos)
        # gender from head template args / tags
        for s in e.get('senses', []):
            for t in s.get('tags', []):
                if t in ('masculine', 'feminine', 'neuter'):
                    rec['gender'].add(t)
            if s.get('glosses'):
                rec['gloss'] = True
            for t in s.get('tags', []):
                if t in ('informal', 'colloquial', 'vulgar', 'slang', 'formal'):
                    rec['labels'].add(t)
        for ht in e.get('head_templates', []):
            a = ht.get('args', {})
            g = a.get('1', '')
            for part in str(g).split('-'):
                if part in ('m', 'f'): rec['gender'].add('de')
                if part == 'n': rec['gender'].add('het')
        for fo in e.get('forms', []):
            fw = fo.get('form', '')
            if fw and fw.islower() and ' ' not in fw:
                form_to_lemma.setdefault(fw, w)

print(f"kaikki entries scanned: {n}, indexed lemmas: {len(entries)}, inflected forms: {len(form_to_lemma)}")

hit = sum(1 for c in candset if c in entries)
hit_via_form = sum(1 for c in candset if c not in entries and c in form_to_lemma)
miss = [c for c in candset if c not in entries and c not in form_to_lemma]
print(f"top-3000 candidates: direct hit {hit} ({hit/len(candset):.1%}), hit-as-inflected-form {hit_via_form}, miss {len(miss)}")

nouns = [c for c in candset if c in entries and 'noun' in entries[c]['pos']]
nouns_with_gender = [c for c in nouns if entries[c]['gender']]
print(f"nouns among hits: {len(nouns)}, with de/het derivable: {len(nouns_with_gender)} ({len(nouns_with_gender)/max(1,len(nouns)):.1%})")
gloss = sum(1 for c in candset if c in entries and entries[c]['gloss'])
print(f"with EN gloss: {gloss} ({gloss/len(candset):.1%})")
print("\nsample misses (likely names/junk -> auto-drop):", miss[:30])
