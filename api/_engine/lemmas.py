"""
Inflection handling.

The GSE list stores base forms. Student writing contains inflected ones. This
module turns a surface form into an ORDERED list of candidate base forms.

THE ORDER IS A CONTRACT. Callers take the first candidate that resolves, so the
exact surface form must always come first and the most likely base must come
before less likely ones. Get this wrong and lookups succeed on the wrong word:

    writes  -> writ    (a legal document, C1)
    fires   -> fir     (the tree, C1)
    putting -> putt    (the golf stroke, B2+)

Deliberately dependency-free: no spaCy, no NLTK, no downloads. Runs on a plain
Python install.
"""

# ---------------------------------------------------------------------------
# Irregular forms. Includes the cases that generic lemmatisers get wrong:
# comparative/superlative suppletion (better -> good) and irregular plurals.
# ---------------------------------------------------------------------------
IRREGULAR = {
    # be / have / do
    "was": "be", "were": "be", "is": "be", "are": "be", "am": "be", "been": "be", "being": "be",
    "had": "have", "has": "have", "having": "have",
    "did": "do", "does": "do", "done": "do", "doing": "do",
    # high-frequency irregular verbs
    "went": "go", "gone": "go", "going": "go", "said": "say", "saying": "say",
    "made": "make", "making": "make", "got": "get", "gotten": "get",
    "came": "come", "coming": "come", "took": "take", "taken": "take", "taking": "take",
    "saw": "see", "seen": "see", "knew": "know", "known": "know",
    "thought": "think", "bought": "buy", "brought": "bring", "caught": "catch",
    "taught": "teach", "found": "find", "left": "leave", "felt": "feel",
    "kept": "keep", "told": "tell", "became": "become", "began": "begin", "begun": "begin",
    "ran": "run", "wrote": "write", "written": "write", "spoke": "speak", "spoken": "speak",
    "broke": "break", "broken": "break", "chose": "choose", "chosen": "choose",
    "sat": "sit", "ate": "eat", "eaten": "eat", "drank": "drink", "drunk": "drink",
    "swam": "swim", "swum": "swim", "sang": "sing", "sung": "sing", "sent": "send",
    "slept": "sleep", "met": "meet", "paid": "pay", "flew": "fly", "flown": "fly",
    "drove": "drive", "driven": "drive", "gave": "give", "given": "give",
    "won": "win", "lost": "lose", "built": "build", "held": "hold", "stood": "stand",
    "understood": "understand", "grew": "grow", "grown": "grow",
    "threw": "throw", "thrown": "throw", "drew": "draw", "drawn": "draw",
    "fell": "fall", "fallen": "fall", "rose": "rise", "risen": "rise",
    "wore": "wear", "worn": "wear", "sold": "sell", "heard": "hear",
    "stole": "steal", "stolen": "steal", "hid": "hide", "hidden": "hide",
    "forgot": "forget", "forgotten": "forget", "fought": "fight", "sought": "seek",
    "dealt": "deal", "dug": "dig", "hung": "hang", "shot": "shoot", "shone": "shine",
    "slid": "slide", "crept": "creep", "swept": "sweep", "wept": "weep",
    "swung": "swing", "stuck": "stick", "stung": "sting", "struck": "strike",
    "spun": "spin", "sped": "speed", "fled": "flee", "flung": "fling", "clung": "cling",
    "sprang": "spring", "sprung": "spring", "sank": "sink", "sunk": "sink",
    "shrank": "shrink", "shrunk": "shrink", "swore": "swear", "sworn": "swear",
    "tore": "tear", "torn": "tear", "rode": "ride", "ridden": "ride",
    "blew": "blow", "blown": "blow", "bit": "bite", "bitten": "bite",
    "bent": "bend", "bound": "bind", "bred": "breed", "bled": "bleed",
    "froze": "freeze", "frozen": "freeze", "shook": "shake", "shaken": "shake",
    "knelt": "kneel", "leapt": "leap", "learnt": "learn", "lent": "lend",
    "burnt": "burn", "dreamt": "dream", "smelt": "smell", "spelt": "spell",
    "spilt": "spill", "spoilt": "spoil", "leant": "lean", "spent": "spend",
    "meant": "mean", "lit": "light", "led": "lead", "fed": "feed",
    "woke": "wake", "woken": "wake", "rang": "ring", "rung": "ring",
    "lay": "lie", "lain": "lie", "laid": "lay", "beaten": "beat",
    "wound": "wind", "wrung": "wring", "ground": "grind",
    "arose": "arise", "arisen": "arise", "awoke": "awake", "awoken": "awake",
    "forgave": "forgive", "forgiven": "forgive", "mistook": "mistake", "mistaken": "mistake",
    "overcame": "overcome", "withdrew": "withdraw", "withdrawn": "withdraw",
    "wove": "weave", "woven": "weave", "strode": "stride", "stridden": "stride",
    # irregular plurals
    "men": "man", "women": "woman", "children": "child", "people": "person",
    "teeth": "tooth", "feet": "foot", "mice": "mouse", "geese": "goose",
    "lives": "life", "wives": "wife", "knives": "knife", "leaves": "leaf",
    "wolves": "wolf", "shelves": "shelf", "halves": "half", "thieves": "thief",
    # suppletive comparatives — the class generic lemmatisers fail hardest on
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "further": "far", "furthest": "far", "farther": "far", "farthest": "far",
    "more": "much", "most": "much", "less": "little", "least": "little",
    "earlier": "early", "earliest": "early",
}

# US -> UK. The GSE list is British throughout.
US_TO_UK = {
    "color": "colour", "colors": "colours", "colored": "coloured", "colorful": "colourful",
    "favorite": "favourite", "favorites": "favourites", "favor": "favour", "favors": "favour",
    "neighbor": "neighbour", "neighbors": "neighbours", "neighborhood": "neighbourhood",
    "behavior": "behaviour", "behaviors": "behaviours", "humor": "humour",
    "labor": "labour", "honor": "honour", "flavor": "flavour", "flavors": "flavours",
    "rumor": "rumour", "center": "centre", "centers": "centres",
    "theater": "theatre", "theaters": "theatres", "meter": "metre", "meters": "metres",
    "liter": "litre", "liters": "litres", "fiber": "fibre",
    "traveling": "travelling", "traveled": "travelled", "traveler": "traveller",
    "canceled": "cancelled", "canceling": "cancelling", "modeling": "modelling",
    "labeled": "labelled", "jewelry": "jewellery", "program": "programme",
    "programs": "programmes", "gray": "grey", "practiced": "practised",
    "practicing": "practising", "defense": "defence", "offense": "offence",
    "license": "licence", "catalog": "catalogue", "dialog": "dialogue",
    "tire": "tyre", "tires": "tyres", "pajamas": "pyjamas", "mom": "mum", "moms": "mums",
}

import re

# -ise / -ize both directions. A bare suffix test is wrong: size, prize, seize,
# noise and rise end in -ise/-ize without carrying the suffix. Requiring a stem
# of 3+ characters separates organ|ise and real|ise from s|ize and pr|ize.
_ISE_IZE = re.compile(r"^(.{3,}?)(is|iz)(e|es|ed|ing|ation|ations)$")
_YSE_YZE = re.compile(r"^(.{2,}?)(ys|yz)(e|es|ed|ing)$")

_VOWELS = set("aeiou")


def spelling_variants(w):
    """British/American -ise/-ize and -yse/-yze pairs, both directions."""
    out = []
    m = _ISE_IZE.match(w)
    if m:
        out.append(m.group(1) + ("iz" if m.group(2) == "is" else "is") + m.group(3))
    y = _YSE_YZE.match(w)
    if y:
        out.append(y.group(1) + ("yz" if y.group(2) == "ys" else "ys") + y.group(3))
    return out


def lemma_candidates(w):
    """Ordered candidate base forms for a surface form. Surface form is always first."""
    w = w.lower()
    out = [w]
    if w in CONTRACTIONS:
        out.append(CONTRACTIONS[w])

    def add(s):
        if len(s) >= 2:
            out.append(s)

    if w in US_TO_UK:
        add(US_TO_UK[w])
    for v in spelling_variants(w):
        add(v)
    if w in IRREGULAR:
        add(IRREGULAR[w])

    # ---- plural / 3rd person singular ----
    if w.endswith("s") and not w.endswith("ss"):
        if re.search(r"(?:s|x|z|ch|sh)es$", w):
            add(w[:-2])            # boxes -> box
            add(w[:-1])
        elif re.search(r"[^aeiou]ies$", w):
            add(w[:-3] + "y")      # studies -> study
            add(w[:-1])
        elif re.search(r"[^aeiou]oes$", w):
            add(w[:-2])            # potatoes -> potato
            add(w[:-1])
        else:
            add(w[:-1])            # cats -> cat
            # No blanket "-es" strip. Stripping -es off a non-sibilant stem is not
            # English morphology, and it re-opens the fault this rule exists to
            # close: "minets" would resolve to "mine" and be credited as A1.

    # ---- past / past participle ----
    if w.endswith("ed"):
        if re.search(r"[^aeiou]ied$", w):
            add(w[:-3] + "y")                                   # tried -> try
        st = w[:-2]
        if len(st) > 2 and st[-1] == st[-2] and st[-1] not in _VOWELS:
            add(st[:-1])                                        # stopped -> stop
        add(w[:-1])                                             # hoped -> hope
        add(w[:-2])                                             # walked -> walk

    # ---- -ing ----
    if w.endswith("ing"):
        st = w[:-3]
        if len(st) > 2 and st[-1] == st[-2] and st[-1] not in _VOWELS:
            add(st[:-1])                                        # putting -> put
        add(st + "e")                                           # hoping -> hope
        add(st)                                                 # walking -> walk

    # ---- comparative / superlative / adverb ----
    if w.endswith("iest"):
        add(w[:-4] + "y")          # happiest -> happy
    elif w.endswith("ier"):
        add(w[:-3] + "y")          # happier -> happy
    if w.endswith("est"):
        add(w[:-2])                # largest -> large
        add(w[:-3])                # tallest -> tall
    elif w.endswith("er"):
        add(w[:-1])                # larger -> large
        add(w[:-2])                # taller -> tall
    if w.endswith("ly"):
        add(w[:-2])                # quickly -> quick
        if w.endswith("ily"):
            add(w[:-3] + "y")      # happily -> happy
        if w.endswith("bly"):
            add(w[:-1] + "e")      # probably -> probable

    # Variants apply to DERIVED candidates too: "organised" needs
    # strip-d -> "organise" -> variant -> "organize". Appended last so they can
    # never displace a real match.
    for c in list(out):
        for v in spelling_variants(c):
            out.append(v)
        if c in US_TO_UK:
            out.append(US_TO_UK[c])

    seen = set()
    ordered = []
    for c in out:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def inflect(lemma):
    """Rough forward inflection — used only to widen the spelling-candidate pool."""
    out = {lemma}
    if re.search(r"[^aeiou]y$", lemma):
        out.add(lemma[:-1] + "ies")
        out.add(lemma[:-1] + "ied")
        out.add(lemma[:-1] + "ier")
        out.add(lemma[:-1] + "iest")
        out.add(lemma[:-1] + "ily")
    elif re.search(r"(s|x|z|ch|sh)$", lemma):
        out.add(lemma + "es")
    else:
        out.add(lemma + "s")
    cvc = bool(re.search(r"[^aeiou][aeiou][^aeiouwxy]$", lemma))
    if lemma.endswith("e") and not lemma.endswith("ee"):
        out.add(lemma[:-1] + "ing")
        out.add(lemma + "d")
        out.add(lemma + "r")
        out.add(lemma + "st")
    elif cvc:
        out.add(lemma + lemma[-1] + "ing")
        out.add(lemma + lemma[-1] + "ed")
        out.add(lemma + lemma[-1] + "er")
        out.add(lemma + lemma[-1] + "est")
    else:
        out.add(lemma + "ing")
        out.add(lemma + "ed")
        out.add(lemma + "er")
        out.add(lemma + "est")
    if lemma.endswith("le"):
        out.add(lemma[:-1] + "y")
    else:
        out.add(lemma + "ly")
    return {w for w in out if len(w) >= 2}


# ---------------------------------------------------------------------------
# British spellings. The GSE list is British throughout, and the general English
# word list used for non-word DETECTION is American-derived. Without this,
# "travelling", "colours" and "organised" are read as misspellings and quietly
# corrected to their American forms -- turning correct British spelling into a
# fake error, on a British exam board's own reference list.
# ---------------------------------------------------------------------------

_OUR_STEMS = ("col", "fav", "hon", "lab", "hum", "neighb", "behavi", "flav",
              "rum", "vap", "harb", "arm", "od", "sav", "val", "splend",
              "endeav", "vig", "clam", "parl", "rig")
_RE_STEMS = ("cent", "theat", "met", "lit", "fib", "somb", "calib", "lust",
             "sabot", "spect", "sceptic")


def british_variants(w):
    """American spelling -> its British counterpart(s). Additive, never a swap."""
    out = []
    # -ize / -yze families
    out.extend(spelling_variants(w))
    # -or -> -our  (color -> colour, colored -> coloured)
    for stem in _OUR_STEMS:
        if w.startswith(stem) and w[len(stem):len(stem) + 2] == "or":
            out.append(w[:len(stem)] + "our" + w[len(stem) + 2:])
            break
    # -er -> -re  (center -> centre, centers -> centres)
    for stem in _RE_STEMS:
        rest = w[len(stem):]
        if w.startswith(stem) and rest in ("er", "ers"):
            out.append(stem + "re" + rest[2:])
            break
    # single -l doubling before a vowel suffix (traveling -> travelling)
    for suf in ("ing", "ed", "er", "ers", "or", "ors"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            stem = w[:-len(suf)]
            if stem.endswith("l") and not stem.endswith("ll") and stem[-2] in "aeiou":
                out.append(stem + "l" + suf)
            break
    # -og -> -ogue, -se -> -ce, misc
    if w.endswith("og") and len(w) > 4:
        out.append(w + "ue")
    for a, b in (("defense", "defence"), ("offense", "offence"),
                 ("pretense", "pretence"), ("license", "licence"),
                 ("practice", "practise"), ("gray", "grey"),
                 ("plow", "plough"), ("mold", "mould"), ("smolder", "smoulder"),
                 ("skeptic", "sceptic"), ("aluminum", "aluminium"),
                 ("jewelry", "jewellery"), ("draft", "draught"),
                 ("tire", "tyre"), ("pajama", "pyjama"), ("ax", "axe")):
        if w.startswith(a):
            out.append(b + w[len(a):])
    return [v for v in dict.fromkeys(out) if v != w]


# ---------------------------------------------------------------------------
# Contractions written without an apostrophe.
#
# Two things make this necessary. Students very often drop the apostrophe, and
# the tokeniser strips it anyway -- so "don't" and "dont" both arrive here as
# "dont" and neither matches anything in the GSE list. Left alone, every
# contraction in every script counts as unmatched, which drags the profile down
# for a spelling habit that has nothing to do with vocabulary.
#
# Each form maps to the lexical word the GSE list actually carries, so one token
# in stays one token out and no counts are inflated.
# ---------------------------------------------------------------------------
CONTRACTIONS = {
    "dont": "do", "doesnt": "does", "didnt": "did", "cant": "can",
    "couldnt": "could", "wont": "will", "wouldnt": "would",
    "shouldnt": "should", "shant": "shall", "mustnt": "must",
    "isnt": "is", "arent": "are", "wasnt": "was", "werent": "were",
    "aint": "is", "havent": "have", "hasnt": "has", "hadnt": "had",
    "im": "am", "ive": "have", "ill": "will", "id": "would",
    "hes": "is", "shes": "is", "its": "it", "thats": "that",
    "whats": "what", "wheres": "where", "whos": "who", "theres": "there",
    "heres": "here", "hows": "how", "lets": "let",
    "theyre": "are", "theyve": "have", "theyll": "will", "theyd": "would",
    "youre": "are", "youve": "have", "youll": "will", "youd": "would",
    "weve": "have", "well": "will", "wed": "would", "were": "are",
    "hed": "would", "hell": "will", "shed": "would", "shell": "will",
    "itll": "will", "itd": "would", "thatll": "will", "gonna": "going",
    "wanna": "want", "gotta": "got", "kinda": "kind", "cuz": "because",
    "ok": "okay",
}
