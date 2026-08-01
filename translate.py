"""
Chimiini (Bravanese) <-> English translator, built entirely from your own
data files (lexicon.json and parallel_sentences.jsonl). Run it in the same
folder as those files.

Usage:
    python3 translate.py

How it works, in order, for whatever you type:
  1. Exact match: if your sentence (or its Bravanese/English counterpart)
     already exists word-for-word in the parallel corpus, that translation
     is returned directly.
  2. Close match: if not exact, the closest few sentences already in the
     corpus are shown, in case one of them is what you meant.
  3. Word-by-word: each word in your sentence is looked up individually in
     the lexicon (matching headwords, plural forms, past tense forms, and
     derived/related verb forms) and stitched into a rough translation.
     Any word that isn't found is left in brackets, e.g. [ngoloko?], so you
     can see exactly what the tool doesn't know.

This is a lookup tool, not a real machine-translation model -- word order,
agreement, and grammar are not handled, so word-by-word output should be
read as a rough gloss, not a fluent sentence.
"""

import json
import os
import re
import sys
import unicodedata
import difflib

LEXICON_PATH = "lexicon.json"
PARALLEL_JSONL_PATH = "parallel_sentences.jsonl"

STOPWORDS = {
    'a', 'an', 'the', 'to', 'of', 'in', 'on', 'at', 'is', 'are', 'was',
    'were', 'be', 'been', 'and', 'or', 'but', 'it', 'its', 's', 'lit',
    'e.g', 'i.e', 'cf', 'also',
}


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
    """Turn a dictionary headword/related-form string into the plain surface
    form a person would actually type, e.g. 'mu-ke (wa-)' -> 'muke',
    'ku-dirka' -> 'kudirka', 'chi-n-dila (zi-n-)' -> 'chindila'."""
    if not s:
        return ''
    s = re.sub(r'\(.*?\)', '', s)   # drop parenthetical plural/class notation
    s = s.replace('-', '')          # join morpheme boundaries
    s = strip_diacritics(s)
    s = re.sub(r'\s+', '', s)       # headwords are single surface words
    return s.lower().strip()


def tokenize(s):
    return re.findall(r"[a-zA-Z']+", s.lower())


def clean_gloss_for_display(gloss):
    if not gloss:
        return ''
    gloss = re.sub(r'^\([^)]*\)\s*', '', gloss.strip())  # drop leading (past-tense form) note
    gloss = re.sub(r'^\d+(/\d+)?\.?\s+', '', gloss)       # drop leaked noun-class marker, e.g. '1/2 '
    parts = re.split(r'[;,(]', gloss)
    for p in parts:
        p = p.strip()
        if p:
            return p
    return gloss.strip()


class Translator:
    def __init__(self):
        self.bra_to_eng = {}      # bravanese_ascii word/phrase -> (english gloss, note)
        self.eng_to_bra = {}      # english word -> list of (bravanese_original, note)
        self.phrase_bra_to_eng = {}  # full sentence ascii -> english (exact corpus lookup)
        self.phrase_eng_to_bra = {}  # full sentence lowercase -> bravanese_original
        self.load()

    def load(self):
        lexicon = []
        if os.path.exists(LEXICON_PATH):
            with open(LEXICON_PATH, encoding='utf-8') as f:
                lexicon = json.load(f)
        else:
            print(f"Warning: {LEXICON_PATH} not found in this folder.")

        for e in lexicon:
            headword_original = e.get('headword_original', '')
            headword_key = normalize_key(headword_original)
            gloss = clean_gloss_for_display(e.get('gloss') or '')
            if headword_key and gloss:
                self._add_bra_entry(headword_key, gloss, '')
                self._add_eng_entry(gloss, headword_original, '')

            plural = e.get('plural_form')
            if plural:
                self._add_bra_entry(normalize_key(plural), gloss, '(plural)')

            past = e.get('past_tense')
            if past:
                self._add_bra_entry(normalize_key(past), gloss, '(past tense)')

            for rel in e.get('related_forms', []):
                form = rel.get('form_raw') or rel.get('form')
                if not form:
                    continue
                form_key = normalize_key(form)
                rel_gloss = clean_gloss_for_display(rel.get('gloss') or '') or gloss
                deriv = rel.get('derivation') or []
                note = f"({'/'.join(deriv)})" if deriv else ''
                if rel_gloss:
                    self._add_bra_entry(form_key, rel_gloss, note)
                rel_past = rel.get('past_tense')
                if rel_past:
                    self._add_bra_entry(normalize_key(rel_past), rel_gloss, '(past tense)')

            # exact-sentence lookup from every example attached to this entry
            for ex in e.get('examples', []):
                self._add_phrase(ex.get('bravanese_original'), ex.get('bravanese_ascii'), ex.get('english'))

        if os.path.exists(PARALLEL_JSONL_PATH):
            with open(PARALLEL_JSONL_PATH, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    self._add_phrase(row.get('bravanese_original'), row.get('bravanese_ascii'), row.get('english'))
        else:
            print(f"Warning: {PARALLEL_JSONL_PATH} not found in this folder.")

        print(f"Loaded {len(self.bra_to_eng)} Bravanese word forms, "
              f"{len(self.eng_to_bra)} English word forms, "
              f"{len(self.phrase_bra_to_eng)} full example sentences.\n")

    def _add_bra_entry(self, bra_ascii, gloss, note):
        if not bra_ascii or not gloss:
            return
        key = bra_ascii.lower()
        if key not in self.bra_to_eng:
            self.bra_to_eng[key] = (gloss, note)

    def _add_eng_entry(self, gloss, bra_original, note):
        gloss_words = tokenize(gloss)
        is_single_word_gloss = len(gloss_words) == 1
        for w in gloss_words:
            if w in STOPWORDS or len(w) < 3:
                continue
            bucket = self.eng_to_bra.setdefault(w, {'exact': [], 'partial': []})
            target = bucket['exact'] if is_single_word_gloss else bucket['partial']
            if not any(existing[0] == bra_original for existing in target):
                target.append((bra_original, note))

    def _add_phrase(self, bra_original, bra_ascii, english):
        if not bra_original or not english:
            return
        bra_ascii = bra_ascii or strip_diacritics(bra_original)
        eng_key = re.sub(r'[^a-z0-9 ]', '', english.lower()).strip()
        bra_key = bra_ascii.lower().strip()
        if bra_key and bra_key not in self.phrase_bra_to_eng:
            self.phrase_bra_to_eng[bra_key] = english
        if eng_key and eng_key not in self.phrase_eng_to_bra:
            self.phrase_eng_to_bra[eng_key] = bra_original

    def translate_bra_to_eng(self, sentence):
        bra_ascii = strip_diacritics(sentence).lower().strip()
        exact = self.phrase_bra_to_eng.get(bra_ascii)
        if exact:
            return ('exact', exact, None)

        close = difflib.get_close_matches(bra_ascii, self.phrase_bra_to_eng.keys(), n=3, cutoff=0.6)
        suggestions = [(c, self.phrase_bra_to_eng[c]) for c in close]

        words = tokenize(strip_diacritics(sentence))
        out_words = []
        unknown = []
        for w in words:
            hit = self.bra_to_eng.get(normalize_key(w))
            if hit:
                gloss, note = hit
                out_words.append(gloss + (f' {note}' if note else ''))
            else:
                out_words.append(f'[{w}?]')
                unknown.append(w)
        return ('rough', ' '.join(out_words), (suggestions, unknown))

    def translate_eng_to_bra(self, sentence):
        eng_key = re.sub(r'[^a-z0-9 ]', '', sentence.lower()).strip()
        exact = self.phrase_eng_to_bra.get(eng_key)
        if exact:
            return ('exact', exact, None)

        close = difflib.get_close_matches(eng_key, self.phrase_eng_to_bra.keys(), n=3, cutoff=0.6)
        suggestions = [(c, self.phrase_eng_to_bra[c]) for c in close]

        words = tokenize(sentence)
        out_words = []
        unknown = []
        for w in words:
            if w in STOPWORDS:
                continue
            bucket = self.eng_to_bra.get(w)
            hits = (bucket['exact'] or bucket['partial']) if bucket else None
            if hits:
                bra_original, note = hits[0]
                extra = f' [also: {", ".join(h[0] for h in hits[1:3])}]' if len(hits) > 1 else ''
                out_words.append(bra_original + (f' {note}' if note else '') + extra)
            else:
                out_words.append(f'[{w}?]')
                unknown.append(w)
        return ('rough', ' '.join(out_words), (suggestions, unknown))


def print_result(direction_label, kind, result, extra):
    if kind == 'exact':
        print(f"  Exact match found in the corpus:")
        print(f"  -> {result}")
        return
    print(f"  No exact sentence match -- rough word-by-word {direction_label}:")
    print(f"  -> {result}")
    suggestions, unknown = extra
    if unknown:
        print(f"  ({len(unknown)} word(s) not found: {', '.join(unknown)})")
    if suggestions:
        print("  Closest existing example sentence(s) in the corpus, for reference:")
        for key, val in suggestions:
            print(f"    - {val}")


def main():
    print("Chimiini <-> English translator (built from your lexicon/example data)\n")
    t = Translator()

    while True:
        direction = input("Translate (b)ravanese->english, (e)nglish->bravanese, or (q)uit? ").strip().lower()
        if direction in ('q', 'quit', 'exit'):
            print("Goodbye.")
            break
        elif direction in ('b', 'bravanese'):
            sentence = input("  Bravanese sentence: ").strip()
            if not sentence:
                continue
            kind, result, extra = t.translate_bra_to_eng(sentence)
            print_result('translation', kind, result, extra)
        elif direction in ('e', 'english'):
            sentence = input("  English sentence: ").strip()
            if not sentence:
                continue
            kind, result, extra = t.translate_eng_to_bra(sentence)
            print_result('translation', kind, result, extra)
        else:
            print("  Please type 'b', 'e', or 'q'.")
        print()


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
        sys.exit(0)