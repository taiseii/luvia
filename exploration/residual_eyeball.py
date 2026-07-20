"""Eyeball test for the residual model pass (enrichment contract v2, stage 4).

Builds the true residual set — top-3000 lemmas present in the kaikki lexicon but
lacking a short (<=12 words) EN-linked Tatoeba example — samples ~40 across rank
bands, and runs them through an OpenRouter model using the contract's output schema.

Usage:
  python residual_eyeball.py <sentences.tsv.bz2> <links.tsv.bz2> <draft.csv> <kaikki.jsonl> <out.json>

Reads OPEN_ROUTER_API from the project .env. Stdlib only.
"""
import bz2, csv, json, re, sys, time, urllib.request
from collections import defaultdict
from pathlib import Path

MODEL = "google/gemini-3.5-flash"
N_SAMPLE = 40

# --- key from .env ---
env = Path(__file__).resolve().parent.parent / ".env"
key = None
for line in env.read_text().splitlines():
    if line.startswith("OPEN_ROUTER_API"):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
if not key:
    sys.exit("OPEN_ROUTER_API not found in .env")

# --- Tatoeba short-example index (same logic as tatoeba_bench.py) ---
linked = set()
with bz2.open(sys.argv[2], "rt") as f:
    for line in f:
        parts = line.split("\t")
        if len(parts) >= 2:
            linked.add(parts[0])

tok_re = re.compile(r"[a-zàáäèéëïijöüû']+")
word_minlen = {}
with bz2.open(sys.argv[1], "rt") as f:
    for line in f:
        sid, lang, text = line.rstrip("\n").split("\t")[:3]
        if sid not in linked:
            continue
        nw = len(text.split())
        for t in set(tok_re.findall(text.lower())):
            if nw < word_minlen.get(t, 999):
                word_minlen[t] = nw

# --- candidates ---
cands = [r["lemma"] for r in csv.DictReader(open(sys.argv[3]))][:3000]
rank = {c: i + 1 for i, c in enumerate(cands)}
candset = set(cands)

# --- kaikki: glosses, POS, gender, forms for candidates ---
info = defaultdict(lambda: {"pos": set(), "gender": set(), "glosses": [], "forms": set()})
with open(sys.argv[4]) as f:
    for line in f:
        e = json.loads(line)
        w = e.get("word", "").lower()
        if w not in candset:
            continue
        rec = info[w]
        rec["pos"].add(e.get("pos", ""))
        rec["forms"].add(w)
        for s in e.get("senses", []):
            for g in s.get("glosses", [])[:1]:
                if g not in rec["glosses"] and len(rec["glosses"]) < 8:
                    rec["glosses"].append(g)
        for ht in e.get("head_templates", []):
            for part in str(ht.get("args", {}).get("1", "")).split("-"):
                if part in ("m", "f"): rec["gender"].add("de")
                if part == "n": rec["gender"].add("het")
        for fo in e.get("forms", []):
            fw = fo.get("form", "").lower()
            if fw and " " not in fw:
                rec["forms"].add(fw)

# --- residual: in lexicon, no short Tatoeba example via any form ---
residual = []
for c in cands:
    if c not in info:
        continue  # junk-drop, not the model's problem
    best = min((word_minlen.get(fm, 999) for fm in info[c]["forms"]), default=999)
    if best > 12:
        residual.append(c)
print(f"residual (in kaikki, no <=12-word example): {len(residual)}")

# spread sample across rank bands
step = max(1, len(residual) // N_SAMPLE)
sample = residual[::step][:N_SAMPLE]

# --- model calls ---
def call(lemma):
    rec = info[lemma]
    meta = {
        "lemma": lemma,
        "pos": sorted(rec["pos"]),
        "article": sorted(rec["gender"]) or None,
        "glosses": rec["glosses"],
    }
    prompt = (
        "You enrich one Dutch vocabulary item for a learner who wants casual spoken Dutch.\n"
        f"Item: {json.dumps(meta, ensure_ascii=False)}\n\n"
        "Tasks:\n"
        "1. chosen_gloss: pick the single English gloss matching the most frequent everyday "
        "sense (choose from the glosses list; shorten if wordy).\n"
        "2. example_nl: one natural informal spoken Dutch sentence (spreektaal, not textbook), "
        "max 12 words, containing the lemma or a natural inflected form.\n"
        "3. example_en: its natural English translation.\n"
        "4. notes: only if something is off (wrong POS, no good gloss), else empty string.\n\n"
        'Reply with ONLY a JSON object: {"lemma": ..., "chosen_gloss": ..., '
        '"example_nl": ..., "example_en": ..., "notes": ...}'
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
    txt = out["choices"][0]["message"]["content"].strip()
    txt = re.sub(r"^```(json)?|```$", "", txt, flags=re.M).strip()
    return json.loads(txt), out.get("usage", {})

results, total_usage = [], defaultdict(int)
for i, lemma in enumerate(sample):
    for attempt in range(3):
        try:
            obj, usage = call(lemma)
            obj["rank"] = rank[lemma]
            obj["kaikki_glosses"] = info[lemma]["glosses"]
            results.append(obj)
            for k, v in usage.items():
                if isinstance(v, (int, float)):
                    total_usage[k] += v
            break
        except Exception as exc:
            if attempt == 2:
                results.append({"lemma": lemma, "error": str(exc)})
            time.sleep(4)
    time.sleep(1)
    print(f"{i+1}/{len(sample)} {lemma}", flush=True)

Path(sys.argv[5]).write_text(json.dumps(
    {"model": MODEL, "usage": dict(total_usage), "results": results},
    ensure_ascii=False, indent=2))
print("usage:", dict(total_usage))
