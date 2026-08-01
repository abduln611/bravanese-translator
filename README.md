# Chimiini (Bravanese) Translator Dataset

Built from *Chimiini-Lexicon-and-Chrestomathy-February-2016.pdf* (C.W. Kisseberth et al.), 1438 pages.

## Files

- **lexicon.json** — 6,040 structured dictionary entries (headword, POS, etymology, gloss, related/derived verb forms, example sentences).
- **parallel_sentences.csv / .jsonl** — 36,413 ChimiiniEnglish sentence/phrase pairs pulled out of every dictionary example. This is the file to use for MT fine-tuning, few-shot prompting, or retrieval-augmented translation.

## How it was built

The PDF has a real embedded text layer (not scanned), so I extracted every line of text along with its **font style** (plain / bold / italic / bold-italic) and **indentation level**, then used that formatting — not just the words — to tell headwords, derived/related verb forms, and example sentences apart, since the dictionary consistently uses:
- bold-italic or italic for headwords and cited source-language forms,
- plain text for POS tags, etymology brackets, and glosses,
- bold for the Chimiini half of an example, followed by plain text for the quoted English translation.

Diacritics (ṭ, d, , etc.) are preserved in `*_original` fields and stripped to plain ASCII in `*_ascii` fields for easier matching/search. `register: "steenzi"` marks examples the dictionary flags `[st.]` (a register/dialect tag, not etymology). Front-matter pages (intro essay, phonology sketch, abbreviations key — the first ~24 pages) were excluded since they aren't dictionary entries.

## Known limitations (worth a manual pass before production use)

- **Fixed since the first pass:** examples were originally split on the presence of a literal opening quote mark (‘), but a chunk of translations in the source are missing that character (a typesetting/extraction quirk), which caused some adjacent example pairs to merge into one record. The splitter now tracks bold-vs-plain text style token by token instead, which is what the dictionary actually uses to distinguish Chimiini from English — this caught and fixed those merges. A targeted re-scan afterward found residual merge-like patterns in **~0.7% of pairs**, nearly all of them genuine editorial notes ("Or:", "Cf.") that introduce an alternate phrasing without its own separate translation, rather than mis-splits.
- **`gloss`/`etymology_raw` fields are regex-based**, not hand-verified — some entries with unusual punctuation may have a slightly malformed split between etymology bracket and gloss.
- **`related_forms[].gloss`** is often `null` — many derived verb forms in the source only give the derivation type (causative, applicative, etc.) without a separate translation, since the meaning is compositional from the base verb.
- This is dictionary example data, not naturalistic running text — great for vocabulary/phrase coverage and for teaching a model tense/derivation patterns, but on its own it's too small to train a translation model from scratch (best used as retrieval context or fine-tuning data layered on a larger Swahili-aware base model, since Chimiini/Bravanese is a Swahili dialect).
