"""
Comprehensive test suite for STT context-aware correction functions.
Run: python test_stt_correction.py
"""
import re
import sys
import unicodedata
from difflib import SequenceMatcher


# ─────────────────────────────────────────────
# Copy functions from api/index.py for testing
# ─────────────────────────────────────────────

def _stt_context_correct(user_text, context_text):
    if not user_text or not context_text:
        return user_text, False
    context_words_raw = re.findall(r"[a-zA-Z']+", context_text)
    context_vocab = {}
    for w in context_words_raw:
        low = w.lower().strip("'")
        if len(low) < 3:
            continue
        context_vocab[low] = w
        if low.endswith('s') and len(low) > 3:
            singular = low[:-1]
            if singular not in context_vocab:
                context_vocab[singular] = w[:-1] if w[-1].lower() == 's' else w
        plural = low + 's'
        if plural not in context_vocab:
            context_vocab[plural] = w + 's'
    function_words = {
        'yes', 'not', 'but', 'can', 'the', 'for', 'and', 'are', 'its',
        'this', 'that', 'with', 'from', 'they', 'been', 'some', 'all',
        'any', 'each', 'than', 'then', 'them', 'into', 'only', 'also',
        'just', 'very', 'too', 'much', 'many', 'here', 'there',
    }
    tokens = re.findall(r"[a-zA-Z']+|[^a-zA-Z']+", user_text)
    result = []
    was_corrected = False
    for token in tokens:
        low = token.lower().strip("'")
        if not re.match(r'[a-zA-Z]', token) or len(low) < 3:
            result.append(token)
            continue
        if low in context_vocab:
            result.append(token)
            continue
        best_match_key = None
        best_ratio = 0.0
        best_len_diff = 999
        for ctx_low in context_vocab:
            if low == ctx_low:
                continue
            if (low.startswith(ctx_low) or ctx_low.startswith(low)
                    or low in ctx_low or ctx_low in low):
                continue
            _pfx = 0
            for _ci in range(min(len(low), len(ctx_low))):
                if low[_ci] == ctx_low[_ci]:
                    _pfx += 1
                else:
                    break
            if _pfx >= 4:
                continue
            ratio = SequenceMatcher(None, low, ctx_low).ratio()
            is_match = ratio >= 0.6
            if not is_match and len(low) <= 4 and len(ctx_low) <= 4:
                _vowels = 'aeiou'
                if (low[0] == ctx_low[0]
                        and len(low) == len(ctx_low)
                        and (low[-1] in _vowels) == (ctx_low[-1] in _vowels)):
                    is_match = True
                    ratio = max(ratio, 0.6)
            if is_match:
                len_diff = abs(len(low) - len(ctx_low))
                if (ratio > best_ratio) or (ratio == best_ratio and len_diff < best_len_diff):
                    best_match_key = ctx_low
                    best_ratio = ratio
                    best_len_diff = len_diff
        if best_match_key and low not in function_words:
            replacement = context_vocab[best_match_key]
            if token[0].isupper():
                replacement = replacement[0].upper() + replacement[1:]
            else:
                replacement = replacement.lower()
            result.append(replacement)
            was_corrected = True
        else:
            result.append(token)
    return ''.join(result), was_corrected


def _stt_context_correct_against_target(user_text, target_phrase):
    if not user_text or not target_phrase:
        return user_text
    target_words = re.findall(r"[a-zA-Z']+", target_phrase)
    target_low = {}
    for w in target_words:
        low = w.lower().strip("'")
        if len(low) >= 2:
            target_low[low] = w
    tokens = re.findall(r"[a-zA-Z']+|[^a-zA-Z']+", user_text)
    result = []
    for token in tokens:
        low = token.lower().strip("'")
        if not re.match(r"[a-zA-Z]", token) or len(low) < 2:
            result.append(token)
            continue
        if low in target_low:
            result.append(token)
            continue
        best_match = None
        best_ratio = 0.0
        for t_low, t_orig in target_low.items():
            if low == t_low:
                continue
            if (low.startswith(t_low) or t_low.startswith(low)
                    or low in t_low or t_low in low):
                continue
            _pfx = 0
            for _ci in range(min(len(low), len(t_low))):
                if low[_ci] == t_low[_ci]:
                    _pfx += 1
                else:
                    break
            if _pfx >= 4:
                continue
            ratio = SequenceMatcher(None, low, t_low).ratio()
            is_match = ratio >= 0.6
            if not is_match and len(low) <= 4 and len(t_low) <= 4:
                _vowels = 'aeiou'
                if (low[0] == t_low[0]
                        and len(low) == len(t_low)
                        and (low[-1] in _vowels) == (t_low[-1] in _vowels)):
                    is_match = True
                    ratio = max(ratio, 0.6)
            if is_match and ratio > best_ratio:
                best_match = t_orig
                best_ratio = ratio
        if best_match:
            if token[0].isupper():
                replacement = best_match[0].upper() + best_match[1:]
            else:
                replacement = best_match.lower()
            result.append(replacement)
        else:
            result.append(token)
    return ''.join(result)


# ─────────────────────────────────────────────
# Contraction normalization
# ─────────────────────────────────────────────

_CONTRACTION_MAP = {
    "what's": "what is", "where's": "where is", "who's": "who is",
    "how's": "how is", "that's": "that is", "there's": "there is",
    "here's": "here is", "it's": "it is", "he's": "he is",
    "she's": "she is", "let's": "let us", "i'm": "i am",
    "you're": "you are", "we're": "we are", "they're": "they are",
    "i've": "i have", "you've": "you have", "we've": "we have",
    "they've": "they have", "i'd": "i would", "you'd": "you would",
    "he'd": "he would", "she'd": "she would", "we'd": "we would",
    "they'd": "they would", "i'll": "i will", "you'll": "you will",
    "he'll": "he will", "she'll": "she will", "we'll": "we will",
    "they'll": "they will", "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "weren't": "were not", "won't": "will not",
    "wouldn't": "would not", "don't": "do not", "doesn't": "does not",
    "didn't": "did not", "can't": "cannot", "couldn't": "could not",
    "shouldn't": "should not", "haven't": "have not", "hasn't": "has not",
    "hadn't": "had not",
}

def _normalize_for_match(text):
    lowered = str(text).lower()
    normalized = unicodedata.normalize('NFD', lowered)
    return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')

def _normalize_question_text(text):
    normalized = _normalize_for_match(text)
    normalized = normalized.replace('\u2019', "'").replace('\u2018', "'")
    for contraction, expansion in _CONTRACTION_MAP.items():
        normalized = re.sub(r'\b' + re.escape(contraction) + r'\b', expansion, normalized)
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


# ═══════════════════════════════════════════════
# TEST SUITES
# ═══════════════════════════════════════════════

total_pass = 0
total_fail = 0

def check(name, condition, detail=""):
    global total_pass, total_fail
    if condition:
        total_pass += 1
        print(f"  PASS: {name}")
    else:
        total_fail += 1
        print(f"  FAIL: {name}")
        if detail:
            print(f"        {detail}")


# ──────────────────────────────────────────
print("=" * 60)
print("SUITE 1: Core STT correction (airport scenario)")
print("=" * 60)

ctx_airport = "Are you checking any bags today?"

c, w = _stt_context_correct("Yes. I have one bed to check.", ctx_airport)
check("bed -> bag", w and "bag" in c.lower(), f"got: {c}")

c, w = _stt_context_correct("Yes. I have one bag to check.", ctx_airport)
check("bag stays bag (no change)", not w, f"got: {c}")

c, w = _stt_context_correct("I want to check my bags.", ctx_airport)
check("check stays check (root match)", not w, f"got: {c}")

c, w = _stt_context_correct("I am checking two bags.", ctx_airport)
check("checking stays (exact match)", not w, f"got: {c}")

c, w = _stt_context_correct("Yes.", ctx_airport)
check("single word 'Yes' unchanged", not w, f"got: {c}")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 2: Coffee shop scenarios")
print("=" * 60)

ctx_coffee = "Would you like that hot or iced?"

c, w = _stt_context_correct("I want hat please.", ctx_coffee)
check("hat -> hot", w and "hot" in c.lower(), f"got: {c}")

c, w = _stt_context_correct("I want hot please.", ctx_coffee)
check("hot stays (correct)", not w, f"got: {c}")

c, w = _stt_context_correct("I want iced please.", ctx_coffee)
check("iced stays (correct)", not w, f"got: {c}")

ctx_coffee2 = "What kind of coffee would you like?"
c, w = _stt_context_correct("I would like a latte.", ctx_coffee2)
check("latte unrelated to context (no change)", not w, f"got: {c}")

ctx_size = "What size would you like?"
c, w = _stt_context_correct("A large one please.", ctx_size)
check("large not in context, no bad match", not w, f"got: {c}")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 3: Restaurant scenarios")
print("=" * 60)

ctx_steak = "Would you like a steak or a salad?"

c, w = _stt_context_correct("I would like a stake please.", ctx_steak)
check("stake -> steak", w and "steak" in c.lower(), f"got: {c}")

c, w = _stt_context_correct("I would like a salad please.", ctx_steak)
check("salad correct (no change)", not w, f"got: {c}")

ctx_order = "What would you like to order?"
c, w = _stt_context_correct("I need a doctor please.", ctx_order)
check("doctor unrelated (no change)", not w, f"got: {c}")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 4: Hotel scenarios")
print("=" * 60)

ctx_hotel = "Do you have a reservation?"
c, w = _stt_context_correct("Yes I have a reservation for two nights.", ctx_hotel)
check("reservation correct (no change)", not w, f"got: {c}")

ctx_room = "What kind of room do you need?"
c, w = _stt_context_correct("I need a single room.", ctx_room)
check("room correct (no change)", not w, f"got: {c}")

ctx_checkin = "Can I set up an appointment?"
c, w = _stt_context_correct("Can I sit up an appointment?", ctx_checkin)
check("sit -> set", w and "set" in c.lower(), f"got: {c}")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 5: Edge cases & boundaries")
print("=" * 60)

c, w = _stt_context_correct("", "Any context here")
check("empty user text", c == "" and not w)

c, w = _stt_context_correct("Hello", "")
check("empty context", c == "Hello" and not w)

c, w = _stt_context_correct("", "")
check("both empty", c == "" and not w)

c, w = _stt_context_correct(None, "Something")
check("None user text", c is None and not w)

c, w = _stt_context_correct("Hello", None)
check("None context", c == "Hello" and not w)

# Punctuation preservation
c, w = _stt_context_correct("I have one bed.", "Do you have bags?")
check("period preserved", w and c.endswith("."), f"got: {c}")

c, w = _stt_context_correct("Yes, one bed please.", "Do you have bags?")
check("comma preserved", w and "," in c, f"got: {c}")

c, w = _stt_context_correct("Is it one bed?", "Do you have bags?")
check("question mark preserved", w and c.endswith("?"), f"got: {c}")

# Capitalisation
c, w = _stt_context_correct("Bed is what I have.", "Are you checking bags?")
check("capitalised Bed -> Bag", w and c.startswith("Bag"), f"got: {c}")

# Numbers mixed in
c, w = _stt_context_correct("I have 2 bed.", "How many bags do you have?")
check("numbers preserved, bed->bag", w and "2" in c and "bag" in c.lower(), f"got: {c}")

# Long input
c, w = _stt_context_correct(
    "I think that I would like to say that I have one bed to check in today.",
    "Are you checking any bags today?"
)
check("long sentence: bed->bag", w and "bag" in c.lower(), f"got: {c}")
check("long sentence: rest unchanged", w and "I think" in c and "today" in c, f"got: {c}")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 6: False positive prevention")
print("=" * 60)

# Function words must NOT be corrected
c, w = _stt_context_correct("Yes this is my first time.", "Is this your first time here?")
check("function word 'this' not changed", not w, f"got: {c}")

c, w = _stt_context_correct("Yes that is correct.", "Is that correct?")
check("function word 'that' not changed", not w, f"got: {c}")

# Greeting words must not be mangled
c, w = _stt_context_correct("Good morning, I need help.", "Good morning, how can I help you?")
check("greeting unchanged", not w, f"got: {c}")

c, w = _stt_context_correct("No thank you.", "Is there anything else?")
check("'no thank you' unchanged", not w, f"got: {c}")

c, w = _stt_context_correct("Thank you, goodbye.", "Have a nice day!")
check("goodbye unchanged", not w, f"got: {c}")

# Substring protection: 'hat' should NOT match 'that'
c, w = _stt_context_correct("I left my hat at home.", "Is that your seat?")
check("'hat' not -> 'that' (substring)", not w, f"got: {c}")

# Root/prefix protection
c, w = _stt_context_correct("I want to reserve a table.", "Do you have a reservation?")
check("'reserve' not -> 'reservation' (prefix)", not w, f"got: {c}")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 7: _stt_context_correct_against_target (structured lessons)")
print("=" * 60)

r = _stt_context_correct_against_target("Yes I have one bed to check", "Yes I have one bag to check")
check("lesson: bed->bag", r == "Yes I have one bag to check", f"got: {r}")

r = _stt_context_correct_against_target("I would like a coffee please", "I would like a coffee please")
check("lesson: exact match unchanged", r == "I would like a coffee please", f"got: {r}")

r = _stt_context_correct_against_target("I would like a hat coffee", "I would like a hot coffee")
check("lesson: hat->hot", "hot" in r.lower(), f"got: {r}")

r = _stt_context_correct_against_target("I want to check in", "I want to check in")
check("lesson: check stays", r == "I want to check in", f"got: {r}")

r = _stt_context_correct_against_target("", "Hello there")
check("lesson: empty input", r == "", f"got: {r}")

r = _stt_context_correct_against_target("Hello there", "")
check("lesson: empty target", r == "Hello there", f"got: {r}")

# Multiple words wrong
r = _stt_context_correct_against_target(
    "I would lake a beg to check",
    "I would like a bag to check"
)
check("lesson: lake->like, beg->bag", "like" in r.lower() and "bag" in r.lower(), f"got: {r}")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 8: Contraction normalization (_normalize_question_text)")
print("=" * 60)

# Same question, different form
n1 = _normalize_question_text("What's your name?")
n2 = _normalize_question_text("What is your name?")
check("what's == what is", n1 == n2, f"'{n1}' vs '{n2}'")

n1 = _normalize_question_text("Don't you have a bag?")
n2 = _normalize_question_text("Do not you have a bag?")
check("don't == do not", n1 == n2, f"'{n1}' vs '{n2}'")

n1 = _normalize_question_text("I can't find it")
n2 = _normalize_question_text("I cannot find it")
check("can't == cannot", n1 == n2, f"'{n1}' vs '{n2}'")

# Smart quotes (Unicode)
n1 = _normalize_question_text("Where\u2019s the gate?")
n2 = _normalize_question_text("Where is the gate?")
check("smart-quote where\u2019s == where is", n1 == n2, f"'{n1}' vs '{n2}'")

n1 = _normalize_question_text("It\u2019s hot today")
n2 = _normalize_question_text("It is hot today")
check("smart-quote it\u2019s == it is", n1 == n2, f"'{n1}' vs '{n2}'")

# More contractions
n1 = _normalize_question_text("You're checking bags?")
n2 = _normalize_question_text("You are checking bags?")
check("you're == you are", n1 == n2, f"'{n1}' vs '{n2}'")

n1 = _normalize_question_text("We'll help you.")
n2 = _normalize_question_text("We will help you.")
check("we'll == we will", n1 == n2, f"'{n1}' vs '{n2}'")

n1 = _normalize_question_text("I've been here before.")
n2 = _normalize_question_text("I have been here before.")
check("i've == i have", n1 == n2, f"'{n1}' vs '{n2}'")

# Accented chars
n1 = _normalize_question_text("Voce esta bem?")
n2 = _normalize_question_text("Você está bem?")
check("accented chars normalized", n1 == n2, f"'{n1}' vs '{n2}'")


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 9: Fuzzy question dedup (SequenceMatcher >= 0.85)")
print("=" * 60)

# Simulate the dedup check
def is_fuzzy_duplicate(q1, q2):
    n1 = _normalize_question_text(q1)
    n2 = _normalize_question_text(q2)
    if n1 == n2:
        return True
    return SequenceMatcher(None, n1, n2).ratio() >= 0.85

check("exact dup", is_fuzzy_duplicate("What size?", "What size?"))
check("contraction dup", is_fuzzy_duplicate("What's your name?", "What is your name?"))
# These have ratio < 0.85 — by design they are NOT duplicates (different wording)
check("different wording NOT dup (ratio~0.79)", not is_fuzzy_duplicate(
    "Would you like to check any bags?",
    "Do you want to check any bags?"
), f"ratio={SequenceMatcher(None, _normalize_question_text('Would you like to check any bags?'), _normalize_question_text('Do you want to check any bags?')).ratio():.2f}")
check("different phrasing NOT dup (ratio~0.71)", not is_fuzzy_duplicate(
    "What size would you like?",
    "What size do you want?"
), f"ratio={SequenceMatcher(None, _normalize_question_text('What size would you like?'), _normalize_question_text('What size do you want?')).ratio():.2f}")
check("different questions NOT dup", not is_fuzzy_duplicate(
    "What size would you like?",
    "Would you like sugar or milk?"
))
check("very different NOT dup", not is_fuzzy_duplicate(
    "How can I help you?",
    "What is your destination?"
))


# ──────────────────────────────────────────
print()
print("=" * 60)
print("SUITE 10: Real-world STT confusions (common for Brazilian learners)")
print("=" * 60)

# Brazilian Portuguese speakers commonly confuse these sounds
c, w = _stt_context_correct("I need a sick room.", "Is this a single or a double room?")
check("sick NOT -> single (too different)", not w or "single" not in c.lower(), f"got: {c}")

c, w = _stt_context_correct("I want to sit down.", "Can I see the menu?")
check("sit unrelated to see/menu (no change)", not w, f"got: {c}")

# beach/bitch - should NOT overcorrect normal words
c, w = _stt_context_correct("I went to the beach.", "Let's go to the beach!")
check("beach stays beach", not w, f"got: {c}")

# ship/sheep
ctx_farm = "Did you see the sheep on the farm?"
c, w = _stt_context_correct("Yes I saw the ship on the farm.", ctx_farm)
check("ship -> sheep (farm context)", w and "sheep" in c.lower(), f"got: {c}")

# ──────────────────────────────────────────
print()
print("=" * 60)
total = total_pass + total_fail
print(f"GRAND TOTAL: {total_pass} passed, {total_fail} failed out of {total}")
if total_fail == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"WARNING: {total_fail} test(s) failed!")
print("=" * 60)

sys.exit(0 if total_fail == 0 else 1)
