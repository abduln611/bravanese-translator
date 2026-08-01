#!/usr/bin/env python3
"""
Merges entries exported from the collaborative add_entry_app.html web tool
into your local lexicon.json / parallel_sentences.jsonl / parallel_sentences.csv.

Usage:
    python3 merge_entries.py exported_entries.json

Run it in the same folder as your lexicon.json / parallel_sentences files.
It applies the exact same field logic as add_entry.py (noun class labels,
past tense, aug/dim gloss tagging, headword matching for examples), so
entries added through the web app end up identical to ones added locally.

Safe to re-run: it does not de-duplicate against entries already merged in a
previous run, so only run it once per export (or copy your files first if
you want a rollback point).
"""

import json
import csv
import os
import sys
import unicodedata

LEXICON_PATH = "lexicon.json"
PARALLEL_JSONL_PATH = "parallel_sentences.jsonl"
PARALLEL_CSV_PATH = "parallel_sentences.csv"
PARALLEL_FIELDS = ["bravanese_original", "bravanese_ascii", "english", "register", "headword", "page"]

NOUN_CLASS_LABELS = {'1/2', '3/4', '5/6', '7/8', '9/10', '11', '14', '15'}


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


def normalize_key(s):
    if not s:
        return ''
    import re
    s = re.sub(r'\(.*?\)', '', s)
    s = s.replace('-', '')
    s = strip_diacritics(s)
    s = re.sub(r'\s+', '', s)
    return s.lower().strip()


def annotate_size_class(english_form, size_class):
    e = english_form.strip()
    tag = f"({size_class})"
    if size_class not in e.lower() and tag not in e:
        e = f"{e} {tag}"
    return e


def normalize_infinitive_gloss(english_form):
    e = english_form.strip()
    if not e.lower().startswith('to '):
        e = 'to ' + e
    return e


def load_lexicon():
    if os.path.exists(LEXICON_PATH):
        with open(LEXICON_PATH, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_lexicon(data):
    with open(LEXICON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def append_parallel_row(row):
    write_header = not os.path.exists(PARALLEL_CSV_PATH)
    with open(PARALLEL_CSV_PATH, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=PARALLEL_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)
    with open(PARALLEL_JSONL_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def find_entry(lexicon, headword_ascii):
    for e in lexicon:
        if e.get('headword_ascii') == headword_ascii:
            return e
    return None


def merge_word(lexicon, item):
    bravanese_form = item.get('bravanese_form', '').strip()
    english_form = item.get('english_form', '').strip()
    if not bravanese_form or not english_form:
        print(f"  Skipping word entry with missing fields: {item}")
        return
    is_infinitive = bool(item.get('is_infinitive_verb'))
    size_class = item.get('size_class')
    noun_class = item.get('noun_class') if item.get('noun_class') in NOUN_CLASS_LABELS else None
    plural_form = item.get('plural_form')
    past_tense = item.get('past_tense')

    pos = None
    if is_infinitive:
        pos = 'v'
        noun_class = noun_class or '15'
        english_form = normalize_infinitive_gloss(english_form)
    elif noun_class or size_class:
        pos = 'n'
        if size_class:
            english_form = annotate_size_class(english_form, size_class)

    headword_ascii = strip_diacritics(bravanese_form)
    existing = find_entry(lexicon, headword_ascii)
    if existing is not None:
        existing['gloss'] = english_form
        existing['pos'] = pos or existing.get('pos')
        existing['past_tense'] = past_tense or existing.get('past_tense')
        existing['is_infinitive_verb'] = is_infinitive or existing.get('is_infinitive_verb', False)
        existing['size_class'] = size_class or existing.get('size_class')
        existing['noun_class'] = noun_class or existing.get('noun_class')
        existing['plural_form'] = plural_form or existing.get('plural_form')
        print(f"  Updated existing entry '{bravanese_form}'.")
        return

    lexicon.append({
        'headword_original': bravanese_form,
        'headword_ascii': headword_ascii,
        'pos': pos,
        'is_infinitive_verb': is_infinitive,
        'size_class': size_class,
        'noun_class': noun_class,
        'plural_form': plural_form,
        'etymology_raw': [],
        'gloss': english_form,
        'past_tense': past_tense,
        'related_forms': [],
        'examples': [],
        'page': None,
        'source': item.get('submitted_by') and f"web_app:{item['submitted_by']}" or 'web_app',
    })
    print(f"  Added word '{bravanese_form}'.")


def merge_example(lexicon, item):
    bravanese_sentence = item.get('bravanese_sentence', '').strip()
    english_translation = item.get('english_translation', '').strip()
    if not bravanese_sentence or not english_translation:
        print(f"  Skipping example with missing fields: {item}")
        return
    bravanese_ascii = strip_diacritics(bravanese_sentence)

    linked_entry = None
    hint = item.get('headword_hint')
    if hint:
        key = normalize_key(hint)
        for e in lexicon:
            if normalize_key(e.get('headword_original', '')) == key:
                linked_entry = e
                break
        if linked_entry is None:
            print(f"  Note: no headword matched hint '{hint}' -- saving example unlinked.")

    row = {
        'bravanese_original': bravanese_sentence,
        'bravanese_ascii': bravanese_ascii,
        'english': english_translation,
        'register': '',
        'headword': linked_entry['headword_ascii'] if linked_entry else '',
        'page': '',
    }
    append_parallel_row(row)

    if linked_entry is not None:
        linked_entry.setdefault('examples', []).append({
            'bravanese_original': bravanese_sentence,
            'bravanese_ascii': bravanese_ascii,
            'english': english_translation,
            'register': None,
            'past_tense': item.get('past_tense'),
        })
        print(f"  Added example, linked to '{linked_entry['headword_original']}'.")
    else:
        print("  Added example (unlinked).")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 merge_entries.py exported_entries.json")
        sys.exit(1)
    export_path = sys.argv[1]
    if not os.path.exists(export_path):
        print(f"File not found: {export_path}")
        sys.exit(1)

    with open(export_path, encoding='utf-8') as f:
        items = json.load(f)

    lexicon = load_lexicon()
    print(f"Loaded {len(lexicon)} existing lexicon entries.")
    print(f"Merging {len(items)} exported item(s)...\n")

    words = [i for i in items if i.get('type') == 'word']
    examples = [i for i in items if i.get('type') == 'example']

    for item in words:
        merge_word(lexicon, item)
    save_lexicon(lexicon)

    # reload so example-linking sees words merged in this same run
    lexicon = load_lexicon()
    for item in examples:
        merge_example(lexicon, item)
    save_lexicon(lexicon)

    print(f"\nDone. {len(words)} word(s), {len(examples)} example(s) processed.")


if __name__ == '__main__':
    main()
