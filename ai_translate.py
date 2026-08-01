"""
AI-assisted Chimiini (Bravanese) <-> English translator.

Unlike translate.py (pure word-substitution), this version retrieves the
relevant dictionary entries and example sentences for your sentence, then
sends that as grounding context to Claude via the real Anthropic API, so the
translation accounts for grammar, word order, and general language knowledge
instead of just swapping words one-for-one.

Requires your own Anthropic API key (this makes real, billed API calls):
  1. Get a key at https://console.anthropic.com
  2. Set it as an environment variable before running:
       export ANTHROPIC_API_KEY=sk-ant-...      (macOS/Linux)
       set ANTHROPIC_API_KEY=sk-ant-...         (Windows cmd)
  3. Run: python3 ai_translate.py

No extra packages needed -- this uses only Python's standard library.
"""

import json
import os
import re
import sys
import unicodedata
import urllib.request
import urllib.error

LEXICON_PATH = "lexicon.json"
PARALLEL_JSONL_PATH = "parallel_sentences.jsonl"
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"

# Never put a real key on this line if this file is tracked by git -- use a
# local .env file (see load_dotenv() below) or the ANTHROPIC_API_KEY
# environment variable instead. Leave this blank.
HARDCODED_API_KEY = ""


def load_dotenv(path=".env"):
    """Load KEY=VALUE lines from a local .env file into os.environ, without
    overwriting anything already set. This file should be in .gitignore and
    never committed -- it's the recommended place to keep your real key."""
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

STOPWORDS = {
    'a', 'an', 'the', 'to', 'of', 'in', 'on', 'at', 'is', 'are', 'was',
    'were', 'be', 'been', 'and', 'or', 'but', 'it', 'its', 's', 'lit', 'also',
}

GRAMMAR_NOTES = (
    "Chimiini (Bravanese) noun classes, from the dictionary's own conventions: "
    "Class 1/2: people, animals, animate beings (e.g. muke 'woman' / wake 'women'). The class 1 prefix is "
    "full mu- only on monosyllabic stems or stems with an initial consonant cluster (muke, mubli); otherwise "
    "it reduces to m- (e.g. m-tooro 'thief'). "
    "Class 3/4: inanimate, m-/mu- singular, mi- plural (e.g. muti 'tree' / miti 'trees'). "
    "Class 5/6: i- singular (often augmentative), ma- plural (e.g. ijiwe 'stone' / majiwe 'stones'). "
    "Class 7/8: chi- singular (often diminutive), z(i)- plural (e.g. chiti 'chair' / ziti 'chairs'). "
    "Class 9/10: singular and plural forms are identical (e.g. mbuzi 'goat(s)'). "
    "Class 11: l- singular, m-/n- plural (e.g. lkuta 'wall' / nkuta 'walls'). "
    "Class 14: u- prefix, abstract states/conditions/qualities, usually no plural (e.g. uvivo 'ripeness'). "
    "Class 15: verbal nouns / infinitives, marked with ku- (or kh-/chi- variants) plus a final -a "
    "(e.g. kuviva 'to be ripe'). "
    ""
    "Definiteness ('the X') is marked by a suffix that REPLACES the noun's final vowel, based on what that "
    "final vowel is: -a -> -aani, -e -> -eeni, -i -> -iini, -o -> -ooni, -u -> -uuni. Examples: skoola "
    "'school' -> skolaani 'the school', kazi 'work' -> kaziini 'the work', suuqu 'market' -> suuquuni "
    "'the market'. "
    ""
    "Possessives ('my/your/his-her/our/their X') agree with the possessed noun's class. For 1st singular, 2nd "
    "person, and 3rd singular, the possessive is a SUFFIX attached directly to the noun; for 1st plural and "
    "3rd plural, the possessive is a SEPARATE following word. "
    "1st singular ('my'), suffix -a: class 7 -> cha, class 15 -> ka, class 11 -> la, classes 1/2/3/14 -> wa, "
    "classes 4/5/6/9 -> ya, classes 8/10 -> za. "
    "2nd person ('your'), suffix -o: class 7 -> cho, class 15 -> ko, class 11 -> lo, classes 1/2/3/14 -> wo, "
    "classes 4/5/6/9 -> yo, classes 8/10 -> zo. "
    "3rd singular ('his/her'), suffix -e: class 7 -> che, classes 15/17 -> ke, class 11 -> le, "
    "classes 1/2/3/14 -> we, classes 4/5/6/9 -> ye, classes 8/10 -> ze. "
    "1st plural ('our'), separate word ending in -iitu: classes 1/2/14 -> wiitu, class 9 -> yiitu, "
    "classes 8/10 -> ziitu, class 17 (locative, 'place') -> kiitu (following its own k- pattern like ka/ko/ke/"
    "kaawo elsewhere, NOT grouped with class 15), all other classes (3, 4, 5, 6, 7, 11, 15) -> ndiitu (note "
    "this is NOT the same class-consonant pattern as the other persons -- most classes take the fixed form "
    "ndiitu here). "
    "kiitu 'our place' and kaawo 'their place' (class 17, locative) can refer to any place -- a house or "
    "anywhere else -- not just a home specifically. "
    "3rd plural ('their'), separate word ending in -aawo: class 7 -> chaawo, classes 15/17 -> kaawo, "
    "class 11 -> laawo, classes 1/2/3/14 -> waawo, classes 4/5/6/9 -> yaawo, classes 8/10 -> zaawo. "
    ""
    "Verb extensions (these stack onto the CVC root, roughly in this order -- extension, causative, "
    "reciprocal): "
    "Causative is -ish/-esh (ku-waandra 'get fat' -> ku-waandrisha 'fatten'); stems ending in -uk/-ok mutate "
    "the k to sh instead (k-oondroka 'wake up' -> k-oondrosha 'wake s.o. up'). "
    "Applied (benefactive/instrumental/directional) is -il/-el, or -iliz/-elez in combination with causative. "
    "Reciprocal is -an- (ku-'ahidana 'promise one another', from ku-'ahada), and stacks freely onto applied "
    "stems (kh-pikilana 'cook for one another'). "
    "A common transitive/causative/intransitive triplet is root+il/el (transitive), root+iz/ez "
    "(transitive-causative), root+ik/ek (intransitive); the same pattern recurs as ul/ol, uz/oz, uk/ok. Vowel "
    "harmony picks the high (i/u) or mid (e/o) form based on the root's final vowel. "
    "Some Somali-derived roots take a semantically-empty -at- extension directly on the root. "
    ""
    "Tense/mood is built from subject-prefix + auxiliary/marker + stem, not just a past-tense suffix: "
    "infinitive is ku-stem-a (ku- becomes kh- before a voiceless-obstruent-initial stem, is dropped before a "
    "stem already starting kh-/q-, and lengthens/merges with a vowel-initial stem, e.g. k-aala 'to plant'). "
    "Affirmative habitual is invariant hu-stem-a with no subject agreement (hu-biga 'x hits'). "
    "The chi- subject prefix marks 3rd person narrative/continuous past in storytelling. Ordinary past tense "
    "commonly ends in an -ile/-iile suffix on the verb stem. "
    "Negative tenses use a negative subject-prefix set distinct from the affirmative one, and vary by tense "
    "(present, past, future, habitual, imperative, subjunctive all have distinct negative paradigms). "
    "The copula is irregular: present ni (affirmative) / siwo (negative), invariant; future is "
    "SubjectPrefix-taa-ku-wa; past is SubjectPrefix-waaliko. Possession ('have') uses "
    "SubjectPrefix-na-cho/na-ye/etc. + the possessed noun, not a separate verb. "
    ""
    "Separate from that, there is a LOCATIVE copula ('to be at/in/on [a place]'), built from the root -ko, "
    "with a -pi suffix added for 'where' questions. Attested forms -- note several are homophonous across "
    "person/class, so context or an explicit subject is needed to disambiguate: "
    "1st singular: niiko 'I am at' (negative siiko 'I am not at'). "
    "2nd singular: uko 'you are at' (homophonous with 3rd singular). "
    "3rd singular (person): uko 'he/she is at' (negative ntaako). "
    "1st plural: chiiko 'we are at' (negative ntachiiko; where-question chikopi 'where are we'; homophonous "
    "with the class 7 form below). "
    "2nd plural: niiko 'you (pl.) are at' (homophonous with 1st singular; where-question niikopi 'where are "
    "you (pl.)'). "
    "3rd plural (people): waako 'they are at' (negative ntawaako; where-question waakopi 'where are they'). "
    "Noun-class locative forms ('it/they [class] is/are at'): class 3 -> wiiko/wuuko (where-question "
    "wuukopi); class 4/6 -> yaako (where-question yaakopi); class 5/9 -> yiiko (where-question yiikopi); "
    "class 7 -> chiiko (negative ntachiiko; homophonous with 1st plural above); class 8/10 -> ziiko "
    "(where-question ziikopi); class 11 -> liiko (where-question liikopi). "
    ""
    "These are general patterns, not exhaustive rules -- prefer the specific lexicon entries and example "
    "sentences provided below over these generalizations whenever they conflict."
)


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
    s = re.sub(r'\(.*?\)', '', s)
    s = s.replace('-', '')
    s = strip_diacritics(s)
    s = re.sub(r'\s+', '', s)
    return s.lower().strip()


def tokenize(s):
    return re.findall(r"[a-zA-Z']+", s.lower())


def clean_gloss(gloss):
    if not gloss:
        return ''
    gloss = re.sub(r'^\([^)]*\)\s*', '', gloss.strip())
    gloss = re.sub(r'^\d+(/\d+)?\.?\s+', '', gloss)
    for p in re.split(r'[;,(]', gloss):
        p = p.strip()
        if p:
            return p
    return gloss.strip()


class Index:
    def __init__(self):
        self.bra_to_eng = {}
        self.eng_to_bra_exact = {}
        self.eng_to_bra_partial = {}
        self.phrase_bra_to_eng = {}
        self.phrase_eng_to_bra = {}

    def add_bra(self, key, gloss, note):
        if key and gloss and key not in self.bra_to_eng:
            self.bra_to_eng[key] = (gloss, note)

    def add_eng(self, gloss, bra_original, note):
        words = tokenize(gloss)
        target_map = self.eng_to_bra_exact if len(words) == 1 else self.eng_to_bra_partial
        for w in words:
            if w in STOPWORDS or len(w) < 3:
                continue
            bucket = target_map.setdefault(w, [])
            if not any(existing[0] == bra_original for existing in bucket):
                bucket.append((bra_original, note))

    def add_phrase(self, bra_original, bra_ascii, english):
        if not bra_original or not english:
            return
        bra_ascii = bra_ascii or strip_diacritics(bra_original)
        eng_key = re.sub(r'[^a-z0-9 ]', '', english.lower()).strip()
        bra_key = bra_ascii.lower().strip()
        if bra_key and bra_key not in self.phrase_bra_to_eng:
            self.phrase_bra_to_eng[bra_key] = english
        if eng_key and eng_key not in self.phrase_eng_to_bra:
            self.phrase_eng_to_bra[eng_key] = bra_original

    def build(self, lexicon, parallel_rows):
        for e in lexicon:
            headword_original = e.get('headword_original', '')
            headword_key = normalize_key(headword_original)
            gloss = clean_gloss(e.get('gloss') or '')
            if headword_key and gloss:
                self.add_bra(headword_key, gloss, '')
                self.add_eng(gloss, headword_original, '')
            plural = e.get('plural_form')
            if plural:
                self.add_bra(normalize_key(plural), gloss, '(plural)')
            past = e.get('past_tense')
            if past:
                self.add_bra(normalize_key(past), gloss, '(past tense)')
            for rel in e.get('related_forms', []):
                form = rel.get('form_raw') or rel.get('form')
                if not form:
                    continue
                rel_gloss = clean_gloss(rel.get('gloss') or '') or gloss
                deriv = rel.get('derivation') or []
                note = f"({'/'.join(deriv)})" if deriv else ''
                if rel_gloss:
                    self.add_bra(normalize_key(form), rel_gloss, note)
                rel_past = rel.get('past_tense')
                if rel_past:
                    self.add_bra(normalize_key(rel_past), rel_gloss, '(past tense)')
            for ex in e.get('examples', []):
                self.add_phrase(ex.get('bravanese_original'), ex.get('bravanese_ascii'), ex.get('english'))
        for row in parallel_rows:
            self.add_phrase(row.get('bravanese_original'), row.get('bravanese_ascii'), row.get('english'))

    def closest_examples(self, tokens, direction, n=5):
        table = self.phrase_bra_to_eng if direction == 'b2e' else self.phrase_eng_to_bra
        token_set = set(tokens)
        scored = []
        for key, val in table.items():
            key_tokens = tokenize(key)
            overlap = sum(1 for t in key_tokens if t in token_set)
            if overlap:
                scored.append((overlap / max(len(key_tokens), len(tokens), 1), key, val))
        scored.sort(key=lambda x: -x[0])
        return scored[:n]

    def build_context(self, sentence, direction):
        tokens = tokenize(strip_diacritics(sentence)) if direction == 'b2e' else tokenize(sentence)
        lex_lines = []
        unknown = []
        if direction == 'b2e':
            for t in tokens:
                hit = self.bra_to_eng.get(normalize_key(t))
                if hit:
                    gloss, note = hit
                    lex_lines.append(f'{t} = "{gloss}" {note}'.strip())
                else:
                    unknown.append(t)
        else:
            for t in tokens:
                if t in STOPWORDS:
                    continue
                hits = self.eng_to_bra_exact.get(t) or self.eng_to_bra_partial.get(t)
                if hits:
                    shown = [h[0] + (f' {h[1]}' if h[1] else '') for h in hits[:3]]
                    lex_lines.append(f"{t} = {' / '.join(shown)}")
                else:
                    unknown.append(t)
        examples = self.closest_examples(tokens, direction)
        return lex_lines, unknown, examples


def load_data():
    lexicon = []
    if os.path.exists(LEXICON_PATH):
        with open(LEXICON_PATH, encoding='utf-8') as f:
            lexicon = json.load(f)
    else:
        print(f"Warning: {LEXICON_PATH} not found in this folder.")

    parallel_rows = []
    if os.path.exists(PARALLEL_JSONL_PATH):
        with open(PARALLEL_JSONL_PATH, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    parallel_rows.append(json.loads(line))
    else:
        print(f"Warning: {PARALLEL_JSONL_PATH} not found in this folder.")

    idx = Index()
    idx.build(lexicon, parallel_rows)
    print(f"Loaded {len(idx.bra_to_eng)} Bravanese word forms, "
          f"{len(idx.eng_to_bra_exact) + len(idx.eng_to_bra_partial)} English word forms, "
          f"{len(idx.phrase_bra_to_eng)} example sentences.\n")
    return idx


def build_prompt(sentence, direction, lex_lines, unknown, examples):
    dir_label = "Chimiini/Bravanese into natural English" if direction == 'b2e' else "English into Chimiini/Bravanese"
    lines = []
    lines.append(f"You are a linguistic assistant helping translate {dir_label}.")
    lines.append("Use the dictionary matches and example sentences below as ground truth for vocabulary and "
                  "grammar -- they come directly from a real Chimiini/Bravanese dictionary and corpus, retrieved "
                  "specifically for this sentence.")
    lines.append("If a word in the input has no matching lexicon entry below, say so explicitly rather than "
                  "inventing a translation for it.")
    lines.append("")
    lines.append(f"GRAMMAR BACKGROUND: {GRAMMAR_NOTES}")
    lines.append("")
    lines.append("DICTIONARY MATCHES for words in this sentence:")
    lines.append('\n'.join(lex_lines) if lex_lines else '(none found)')
    if unknown:
        lines.append(f"\nWords with NO dictionary match: {', '.join(unknown)}")
    lines.append("\nRELEVANT EXAMPLE SENTENCES from the corpus (for grammar/word-order reference):")
    if examples:
        lines.append('\n'.join(f"{key}  =  {val}" for _, key, val in examples))
    else:
        lines.append('(none found)')
    lines.append("")
    lines.append(f'SENTENCE TO TRANSLATE: "{sentence}"')
    lines.append("")
    lines.append("Give: 1) your best translation, 2) a one-sentence note on any word you could not ground in "
                  "the dictionary matches above, if any. Keep it concise.")
    return '\n'.join(lines)


def call_claude(prompt, api_key):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode('utf-8')
    req = urllib.request.Request(
        API_URL,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f"API error {e.code}: {err_body}") from e
    text_blocks = [b['text'] for b in data.get('content', []) if b.get('type') == 'text']
    return '\n'.join(text_blocks) if text_blocks else '(no text in response)'


def main():
    load_dotenv()
    api_key = HARDCODED_API_KEY or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("No API key set (checked .env, HARDCODED_API_KEY, and ANTHROPIC_API_KEY).")
        api_key = input("Paste your Anthropic API key (or press Enter to quit): ").strip()
        if not api_key:
            print("No API key given, exiting.")
            sys.exit(1)

    print("Chimiini <-> English AI-assisted translator\n")
    idx = load_data()

    while True:
        direction = input("Translate (b)ravanese->english, (e)nglish->bravanese, or (q)uit? ").strip().lower()
        if direction in ('q', 'quit', 'exit'):
            print("Goodbye.")
            break
        elif direction in ('b', 'bravanese'):
            d = 'b2e'
        elif direction in ('e', 'english'):
            d = 'e2b'
        else:
            print("  Please type 'b', 'e', or 'q'.")
            continue

        sentence = input("  Sentence: ").strip()
        if not sentence:
            continue

        lex_lines, unknown, examples = idx.build_context(sentence, d)
        prompt = build_prompt(sentence, d, lex_lines, unknown, examples)

        print("  Asking Claude, using the retrieved dictionary context...")
        try:
            answer = call_claude(prompt, api_key)
        except Exception as e:
            print(f"  Error calling the API: {e}")
            continue

        print()
        print(answer)
        print()


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
        sys.exit(0)