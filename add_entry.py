"""
Interactive entry tool for the Chimiini (Bravanese) lexicon dataset.

Run it in the same folder as lexicon.json, parallel_sentences.jsonl, and
parallel_sentences.csv (the files from the earlier extraction). It will
create them if they don't exist yet. It also keeps a running tally of
noun classes in noun_class_stats.json in the same folder.

Usage:
    python3 add_entry.py

At each prompt, type your answer and press Enter. Leave a field blank and
press Enter to skip it. Type 'q' at the main menu to quit at any time.
Every entry is saved to disk immediately, so nothing is lost if you stop
partway through.
"""

import json
import csv
import os
import re
import unicodedata
import sys

LEXICON_PATH = "lexicon.json"
PARALLEL_JSONL_PATH = "parallel_sentences.jsonl"
PARALLEL_CSV_PATH = "parallel_sentences.csv"
NOUN_CLASS_STATS_PATH = "noun_class_stats.json"

PARALLEL_FIELDS = ["bravanese_original", "bravanese_ascii", "english", "register", "headword", "page"]

# Chimiini/Bravanese noun class reference.
# key -> (label shown in lexicon.json, short description, plural rule)
#   plural rule: 'same'  -> plural form equals singular form (classes 9/10)
#                'none'  -> no regular plural (classes 14, 15)
#                'ask'   -> prompt separately for the plural form
NOUN_CLASSES = {
    '1':     {'label': '1/2',  'desc': 'people, animals, animate objects (singular)',              'plural_rule': 'ask'},
    '2':     {'label': '1/2',  'desc': 'people, animals, animate objects (plural)',                 'plural_rule': 'ask'},
    '3':     {'label': '3/4',  'desc': "inanimate, starts with m-/mu- (singular, e.g. muti 'tree')", 'plural_rule': 'ask'},
    '4':     {'label': '3/4',  'desc': "inanimate, plural mi- (e.g. miti 'trees')",                  'plural_rule': 'ask'},
    '5':     {'label': '5/6',  'desc': "starts with i-, usually augmentative (e.g. ijiwe 'stone')",  'plural_rule': 'ask'},
    '6':     {'label': '5/6',  'desc': "plural ma- (e.g. majiwe 'stones')",                          'plural_rule': 'ask'},
    '7':     {'label': '7/8',  'desc': "starts with chi-, usually diminutive (e.g. chiti 'chair')",  'plural_rule': 'ask'},
    '8':     {'label': '7/8',  'desc': "plural z- (e.g. ziti 'chairs')",                              'plural_rule': 'ask'},
    '9/10':  {'label': '9/10', 'desc': 'singular and plural forms are identical',                    'plural_rule': 'same'},
    '11':    {'label': '11',   'desc': "starts with l-, plural m-/n- (e.g. lkuta/nkuta 'wall(s)')",  'plural_rule': 'ask'},
    '14':    {'label': '14',   'desc': "starts with u-, states/conditions/qualities (e.g. uvivo 'ripeness')", 'plural_rule': 'none'},
    '15':    {'label': '15',   'desc': "verbal noun / infinitive (e.g. kuviva 'to be ripe')",        'plural_rule': 'none'},
}

NOUN_CLASS_MENU = """  Chimiini noun classes:
    1   - class 1  (person/animal, singular, e.g. muke 'woman')
    2   - class 2  (person/animal, plural,   e.g. wake 'women')
    3   - class 3  (m-/mu- inanimate, singular, e.g. muti 'tree')
    4   - class 4  (mi- inanimate, plural,      e.g. miti 'trees')
    5   - class 5  (i- singular, often augmentative, e.g. ijiwe 'stone')
    6   - class 6  (ma- plural,                  e.g. majiwe 'stones')
    7   - class 7  (chi- singular, often diminutive, e.g. chiti 'chair')
    8   - class 8  (z- plural,                   e.g. ziti 'chairs')
    9   - class 9/10 (singular = plural form)
    11  - class 11 (l- singular, m-/n- plural,   e.g. lkuta/nkuta 'wall(s)')
    14  - class 14 (u- abstract/state,           e.g. uvivo 'ripeness')
    15  - class 15 (verbal noun / infinitive,    e.g. kuviva 'to be ripe')
    n   - not applicable / skip"""


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


def load_lexicon():
    if os.path.exists(LEXICON_PATH):
        with open(LEXICON_PATH, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_lexicon(data):
    with open(LEXICON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def load_noun_class_stats():
    if os.path.exists(NOUN_CLASS_STATS_PATH):
        with open(NOUN_CLASS_STATS_PATH, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_noun_class_stats(stats):
    with open(NOUN_CLASS_STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)


def record_noun_class(class_key):
    stats = load_noun_class_stats()
    label = NOUN_CLASSES[class_key]['label']
    stats[label] = stats.get(label, 0) + 1
    save_noun_class_stats(stats)
    print(f"  (class {label} count is now {stats[label]})")
    return stats


def append_parallel_row(row):
    write_header = not os.path.exists(PARALLEL_CSV_PATH)
    with open(PARALLEL_CSV_PATH, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=PARALLEL_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)
    with open(PARALLEL_JSONL_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def prompt(label, required=False):
    while True:
        val = input(f"  {label}: ").strip()
        if val or not required:
            return val
        print("    (this field is required)")


def ask_yes_no(label):
    val = input(f"  {label} (y/n): ").strip().lower()
    return val in ('y', 'yes')


def ask_size_class():
    val = input("  Is this an augmentative or diminutive noun form? (a)ugmentative / (d)iminutive / (n)either: ").strip().lower()
    if val in ('a', 'aug', 'augmentative'):
        return 'augmentative'
    if val in ('d', 'dim', 'diminutive'):
        return 'diminutive'
    return None


def ask_noun_class():
    print(NOUN_CLASS_MENU)
    while True:
        val = input("  Noun class: ").strip().lower()
        if val in ('n', 'none', ''):
            return None
        if val in ('9', '10', '9/10'):
            return '9/10'
        if val in NOUN_CLASSES:
            return val
        print("    Please enter one of: 1 2 3 4 5 6 7 8 9 11 14 15 n")


def ask_plural_form(bravanese_form, class_key):
    if class_key is None:
        return None
    if class_key == '9/10':
        return bravanese_form
    rule = NOUN_CLASSES[class_key]['plural_rule']
    if rule == 'none':
        return None
    return prompt("Plural form (leave blank if unknown)") or None


def normalize_infinitive_gloss(english_form):
    e = english_form.strip()
    if not re.match(r'^to\b', e, re.IGNORECASE):
        e = 'to ' + e
    return e


def annotate_size_class(english_form, size_class):
    e = english_form.strip()
    tag = f"({size_class})"
    if size_class not in e.lower() and tag not in e:
        e = f"{e} {tag}"
    return e


def find_entry(lexicon, headword_ascii):
    for e in lexicon:
        if e.get('headword_ascii') == headword_ascii:
            return e
    return None


def add_word(lexicon):
    print("\n--- New word entry ---")
    bravanese_form = prompt("Bravanese form (the headword itself)", required=True)
    english_form = prompt("English form / gloss", required=True)
    is_infinitive = ask_yes_no("Is this a to-infinitive verb? (e.g. kuabirisata = 'to measure')")

    size_class = None
    noun_class = None
    plural_form = None

    if is_infinitive:
        noun_class = '15'  # infinitives are class-15 verbal nouns
    else:
        is_noun = ask_yes_no("Is this a noun?")
        if is_noun:
            size_class = ask_size_class()
            noun_class = ask_noun_class()
            if noun_class:
                plural_form = ask_plural_form(bravanese_form, noun_class)

    past_tense = prompt("Past tense form (leave blank if not applicable)")

    pos = None
    if is_infinitive:
        pos = 'v'
        normalized = normalize_infinitive_gloss(english_form)
        if normalized != english_form:
            print(f"  (gloss recorded as '{normalized}')")
        english_form = normalized
    elif noun_class is not None or size_class:
        pos = 'n'
        if size_class:
            annotated = annotate_size_class(english_form, size_class)
            if annotated != english_form:
                print(f"  (gloss recorded as '{annotated}')")
            english_form = annotated

    if noun_class is not None:
        record_noun_class(noun_class)

    headword_ascii = strip_diacritics(bravanese_form)

    existing = find_entry(lexicon, headword_ascii)
    if existing is not None:
        print(f"  Note: '{bravanese_form}' already exists in the lexicon (page {existing.get('page')}).")
        overwrite = prompt("  Update its gloss/past tense instead of adding a duplicate? (y/n)").lower()
        if overwrite == 'y':
            existing['gloss'] = english_form
            existing['pos'] = pos or existing.get('pos')
            existing['past_tense'] = past_tense or existing.get('past_tense')
            existing['is_infinitive_verb'] = is_infinitive or existing.get('is_infinitive_verb', False)
            existing['size_class'] = size_class or existing.get('size_class')
            existing['noun_class'] = NOUN_CLASSES[noun_class]['label'] if noun_class else existing.get('noun_class')
            existing['plural_form'] = plural_form or existing.get('plural_form')
            save_lexicon(lexicon)
            print("  Updated existing entry and saved.")
            return

    entry = {
        'headword_original': bravanese_form,
        'headword_ascii': headword_ascii,
        'pos': pos,
        'is_infinitive_verb': is_infinitive,
        'size_class': size_class,
        'noun_class': NOUN_CLASSES[noun_class]['label'] if noun_class else None,
        'plural_form': plural_form,
        'etymology_raw': [],
        'gloss': english_form,
        'past_tense': past_tense or None,
        'related_forms': [],
        'examples': [],
        'page': None,
        'source': 'user_added',
    }
    lexicon.append(entry)
    save_lexicon(lexicon)
    print(f"  Added '{bravanese_form}' to lexicon.json and saved.")


def add_example(lexicon):
    print("\n--- New example sentence ---")
    bravanese_form = prompt("Bravanese sentence", required=True)
    english_form = prompt("English translation", required=True)
    past_tense = prompt("Past tense form used in this sentence (leave blank if not applicable)")
    headword_ascii_input = prompt("Headword this example belongs to, if any (leave blank to skip)")

    bravanese_ascii = strip_diacritics(bravanese_form)
    linked_entry = None
    if headword_ascii_input:
        key = strip_diacritics(headword_ascii_input)
        linked_entry = find_entry(lexicon, key)
        if linked_entry is None:
            print(f"  Note: no existing headword matched '{headword_ascii_input}'; saving the example unlinked.")

    row = {
        'bravanese_original': bravanese_form,
        'bravanese_ascii': bravanese_ascii,
        'english': english_form,
        'register': '',
        'headword': linked_entry['headword_ascii'] if linked_entry else '',
        'page': '',
    }
    append_parallel_row(row)

    if linked_entry is not None:
        linked_entry['examples'].append({
            'bravanese_original': bravanese_form,
            'bravanese_ascii': bravanese_ascii,
            'english': english_form,
            'register': None,
            'past_tense': past_tense or None,
        })
        save_lexicon(lexicon)
        print(f"  Added example, linked to '{linked_entry['headword_original']}', and saved.")
    else:
        print("  Added example to parallel_sentences.jsonl/.csv (not linked to a lexicon entry) and saved.")


def show_noun_class_stats():
    stats = load_noun_class_stats()
    if not stats:
        print("  No noun classes recorded yet.")
        return
    print("  Noun class tally so far:")
    for label, count in sorted(stats.items()):
        print(f"    {label}: {count}")


def main():
    print("Chimiini lexicon entry tool")
    print(f"Lexicon file: {os.path.abspath(LEXICON_PATH)}")
    lexicon = load_lexicon()
    print(f"Loaded {len(lexicon)} existing entries.\n")

    while True:
        choice = input("Add a (w)ord, (e)xample sentence, (s)how noun class stats, or (q)uit? ").strip().lower()
        if choice in ('q', 'quit', 'exit'):
            print("Done. Files are saved.")
            break
        elif choice in ('w', 'word'):
            add_word(lexicon)
        elif choice in ('e', 'example'):
            add_example(lexicon)
        elif choice in ('s', 'stats'):
            show_noun_class_stats()
        else:
            print("  Please type 'w', 'e', 's', or 'q'.")


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Anything already entered has been saved.")
        sys.exit(0)