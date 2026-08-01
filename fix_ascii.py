"""
One-time fix-up for lexicon.json / parallel_sentences.jsonl / parallel_sentences.csv.

Recomputes every *_ascii field using the corrected diacritic-stripping rule
(the raised aspiration mark 'ʰ' is now dropped instead of expanded into a
literal 'h', which was flooding heavily-marked sentences with h's). Nothing
else in the files is touched -- originals, glosses, examples, etc. are left
exactly as they are.

Run it once, in the same folder as your files:
    python3 fix_ascii.py

It edits the files in place (after printing a summary) and does not create
backups, so make a copy first if you want a safety net.
"""

import json
import csv
import os
import unicodedata

LEXICON_PATH = "lexicon.json"
PARALLEL_JSONL_PATH = "parallel_sentences.jsonl"
PARALLEL_CSV_PATH = "parallel_sentences.csv"
PARALLEL_FIELDS = ["bravanese_original", "bravanese_ascii", "english", "register", "headword", "page"]


def strip_diacritics(s):
    if not s:
        return s
    repl = {
        'ʰ': '', 'ʼ': "'", '’': "'", 'ʻ': "'", 'ˈ': '',
        'ð': 'dh', 'Ð': 'Dh', 'ŋ': 'ng',
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def fix_lexicon():
    if not os.path.exists(LEXICON_PATH):
        print(f"  {LEXICON_PATH} not found, skipping.")
        return 0
    with open(LEXICON_PATH, encoding='utf-8') as f:
        data = json.load(f)
    changed = 0
    for e in data:
        old = e.get('headword_ascii')
        new = strip_diacritics(e.get('headword_original', ''))
        if new != old:
            e['headword_ascii'] = new
            changed += 1
        for ex in e.get('examples', []):
            old_ex = ex.get('bravanese_ascii')
            new_ex = strip_diacritics(ex.get('bravanese_original', ''))
            if new_ex != old_ex:
                ex['bravanese_ascii'] = new_ex
                changed += 1
    with open(LEXICON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return changed


def fix_parallel():
    if not os.path.exists(PARALLEL_JSONL_PATH):
        print(f"  {PARALLEL_JSONL_PATH} not found, skipping.")
        return 0
    rows = []
    changed = 0
    with open(PARALLEL_JSONL_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            old = row.get('bravanese_ascii')
            new = strip_diacritics(row.get('bravanese_original', ''))
            if new != old:
                row['bravanese_ascii'] = new
                changed += 1
            rows.append(row)

    with open(PARALLEL_JSONL_PATH, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    with open(PARALLEL_CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=PARALLEL_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, '') for k in PARALLEL_FIELDS})

    return changed


def main():
    print("Fixing ascii fields (dropping the aspiration mark 'ʰ' instead of expanding it to 'h')...")
    n1 = fix_lexicon()
    print(f"  lexicon.json: {n1} ascii field(s) updated.")
    n2 = fix_parallel()
    print(f"  parallel_sentences.jsonl/.csv: {n2} ascii field(s) updated.")
    print("Done.")


if __name__ == '__main__':
    main()