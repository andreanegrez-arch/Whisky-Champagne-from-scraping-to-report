"""
Costruisce distillerie_vocabolario.json dai titoli del database whisky.
Una sequenza iniziale di parole P e' considerata il nome di una distilleria/marca
("radice") se compare in almeno 3 titoli e non e' quasi sempre seguita dalla
stessa parola (es. "Crown" e' quasi sempre "Crown Royal" -> la radice e' "Crown
Royal"; "Caperdonich" e' seguita da prodotti diversi -> la radice e' "Caperdonich").
Uso: python build_vocab.py DB PARSERS_PY OUTPUT_JSON
"""
import sqlite3, collections, json, sys, importlib.util
DB, PARSERS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("p", PARSERS); p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
titles = [r[0] for r in sqlite3.connect(DB).execute("select title from lots where title is not null")]
cands = []
for t in titles:
    for part in p._first_segment(t).split(" + "):
        part = part.strip()
        if not part or part.startswith("'"):
            continue
        c = p._cut_name(part)
        if c:
            cands.append(c.split(" "))
pref = collections.Counter(); nxt = collections.defaultdict(collections.Counter); spell = collections.defaultdict(collections.Counter)
for w in cands:
    for k in range(1, len(w) + 1):
        key = " ".join(w[:k]).lower()
        pref[key] += 1
        spell[key][" ".join(w[:k])] += 1
        nxt[key][w[k].lower() if k < len(w) else ""] += 1
roots = {}
for w in cands:
    for k in range(1, len(w) + 1):
        key = " ".join(w[:k]).lower()
        if pref[key] < 3 or (k == 1 and key in p._GENERIC_START) or len(key) < 3:
            continue
        # quota di titoli in cui P e' l'intero nome (subito dopo vengono annata/eta').
        # "Crown" da solo e' raro (quasi sempre "Crown Royal"), "Port" da solo non
        # esiste (Port Dundas, Port Ellen...), "Caperdonich" da solo e' frequente.
        if nxt[key][""] / pref[key] < 0.2:
            continue
        roots[key] = p.KNOWN_DISTILLERIAS.get(key, spell[key].most_common(1)[0][0])
        break
json.dump(dict(sorted(roots.items())), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(roots), "voci nel vocabolario")
