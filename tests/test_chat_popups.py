"""
Comprehensive test battery for Chat popups (corrections & suggestions).
Tests Learning and Simulator modes with correct AND incorrect English answers.
Scenario: Coffee Shop (coffee_shop)
"""
import json
import os
import sys
import time
import requests

BASE_URL = "http://127.0.0.1:4344"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "whesleycampos@hotmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# ── helpers ─────────────────────────────────────────────────────────
session = requests.Session()

def login():
    """Get JWT token via admin login."""
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    })
    if resp.status_code != 200:
        print(f"[LOGIN FAILED] {resp.status_code}: {resp.text}")
        sys.exit(1)
    token = resp.json()["token"]
    session.headers["Authorization"] = f"Bearer {token}"
    print(f"[OK] Logged in as {ADMIN_EMAIL}\n")
    return token

def chat(text, context="coffee_shop", practice_mode="learning", turn=1,
         recent_corrections=None, difficulty="intermediate", retries=2):
    """Send a /api/chat request and return parsed response."""
    payload = {
        "text": text,
        "context": context,
        "lessonLang": "en",
        "practiceMode": practice_mode,
        "studentLevel": "intermediate",
        "turnCount": turn,
        "recentCorrections": recent_corrections or [],
        "difficulty": difficulty,
    }
    for attempt in range(retries + 1):
        try:
            t0 = time.perf_counter()
            resp = session.post(f"{BASE_URL}/api/chat", json=payload, timeout=120)
            elapsed = time.perf_counter() - t0
            if resp.status_code != 200:
                return {"_error": resp.status_code, "_body": resp.text, "_ms": int(elapsed*1000)}
            data = resp.json()
            data["_ms"] = int(elapsed * 1000)
            return data
        except requests.exceptions.ReadTimeout:
            elapsed = time.perf_counter() - t0
            if attempt < retries:
                print(f"  [RETRY] Timeout after {int(elapsed)}s, retrying ({attempt+1}/{retries})...")
                time.sleep(2)
            else:
                return {"_error": "TIMEOUT", "_body": f"All {retries+1} attempts timed out", "_ms": int(elapsed*1000)}


def fmt(data):
    """Pretty-print the relevant fields from a chat response."""
    if "_error" in data:
        return f"  ERROR {data['_error']}: {data['_body'][:200]}"
    lines = []
    lines.append(f"  AI text : {data.get('text','')[:200]}")
    lines.append(f"  PT trans: {data.get('translation','')[:200]}")
    sw = data.get("suggested_words", [])
    lines.append(f"  Suggested words: {sw}")
    lines.append(f"  must_retry: {data.get('must_retry', False)}")
    lines.append(f"  retry_prompt: {data.get('retry_prompt','')[:120]}")
    fb = data.get("feedback", "")
    if fb:
        lines.append(f"  feedback (sim): {fb[:200]}")
    tf = data.get("turn_feedback")
    if tf:
        lines.append(f"  turn_feedback.kind: {tf.get('kind')}")
        lines.append(f"  turn_feedback.user_text: {tf.get('user_text','')[:100]}")
        lines.append(f"  turn_feedback.suggested: {tf.get('suggested_text','')[:100]}")
        lines.append(f"  turn_feedback.reason: {tf.get('reason','')[:150]}")
        lines.append(f"  turn_feedback.retry_req: {tf.get('retry_required')}")
    tc = data.get("turn_correction")
    if tc and tc.get("frase_aluno"):
        lines.append(f"  turn_correction.aluno: {tc.get('frase_aluno','')[:100]}")
        lines.append(f"  turn_correction.natural: {tc.get('frase_natural','')[:100]}")
        lines.append(f"  turn_correction.explicacao: {tc.get('explicacao','')[:150]}")
    lines.append(f"  latency: {data['_ms']}ms")
    return "\n".join(lines)


# ── test definitions ─────────────────────────────────────────────────
TESTS = []

def test(name, text, mode, turn=1, difficulty="intermediate", expect_correction=None, context="coffee_shop"):
    """Register a test case."""
    TESTS.append({
        "name": name,
        "text": text,
        "mode": mode,
        "turn": turn,
        "difficulty": difficulty,
        "expect_correction": expect_correction,  # True/False/None(don't check)
        "context": context,
    })

# ── LEARNING MODE ────────────────────────────────────────────────────

# 1. Correct answers
test("L01 – Correct greeting",
     "Hi, I would like to order a coffee, please.",
     "learning", turn=1, expect_correction=False)

test("L02 – Correct follow-up",
     "Can I have a medium latte with oat milk?",
     "learning", turn=2, expect_correction=False)

test("L03 – Correct polite request",
     "Could you also add a blueberry muffin to my order?",
     "learning", turn=3, expect_correction=False)

# 2. Wrong answers — grammar errors
test("L04 – Subject-verb agreement error",
     "I wants a coffee please",
     "learning", turn=1, expect_correction=True)

test("L05 – Article missing",
     "Give me coffee",
     "learning", turn=2, expect_correction=True)

test("L06 – Wrong preposition",
     "I want coffee on milk",
     "learning", turn=2, expect_correction=True)

test("L07 – Wrong tense",
     "Yesterday I go to this coffee shop and I buyed a latte",
     "learning", turn=3, expect_correction=True)

test("L08 – Word order error",
     "How much costs a cappuccino?",
     "learning", turn=2, expect_correction=True)

test("L09 – Double negative",
     "I don't want nothing else",
     "learning", turn=3, expect_correction=True)

test("L10 – Wrong pronoun / possessive",
     "Me want the biggest cup you has",
     "learning", turn=2, expect_correction=True)

# 3. Style / naturalness issues
test("L11 – Too literal from PT",
     "I want to ask one water, please",
     "learning", turn=2, expect_correction=True)

test("L12 – Awkward but understandable",
     "Make for me one espresso",
     "learning", turn=2, expect_correction=True)

# ── SIMULATOR MODE ──────────────────────────────────────────────────

# 4. Correct answers (should NOT get corrections in simulator)
test("S01 – Correct greeting (sim)",
     "Hi there, could I get a black coffee?",
     "simulator", turn=1, expect_correction=False)

test("S02 – Correct follow-up (sim)",
     "I'll have a croissant as well, thanks.",
     "simulator", turn=2, expect_correction=False)

test("S03 – Correct polite question (sim)",
     "Do you have any dairy-free options?",
     "simulator", turn=3, expect_correction=False)

# 5. Wrong answers in simulator (should get recast, NOT explicit correction)
test("S04 – Grammar error (sim)",
     "I wants two coffee",
     "simulator", turn=1, expect_correction=None)  # recast, not popup

test("S05 – Wrong vocab (sim)",
     "Give me the most big cup",
     "simulator", turn=2, expect_correction=None)

test("S06 – Article error (sim)",
     "Can I have cappuccino with the sugar?",
     "simulator", turn=2, expect_correction=None)

test("S07 – Tense error (sim)",
     "I never drink espresso before, is it good?",
     "simulator", turn=3, expect_correction=None)

# 6. Very broken English
test("L13 – Very broken (learning)",
     "me no understand, what is cost the drink?",
     "learning", turn=2, expect_correction=True)

test("S08 – Very broken (sim)",
     "me no understand, what is cost the drink?",
     "simulator", turn=2, expect_correction=None)

# ── HOTEL SCENARIO (Learning mode) ──────────────────────────────────
# These reproduce the exact issues the user reported in screenshots

test("H01 – Hotel greeting (learning)",
     "Hello. Good morning. My name is Wesley.",
     "learning", turn=1, expect_correction=False, context="hotel")

test("H02 – Hotel correct reservation",
     "I have a reservation under the name Wesley.",
     "learning", turn=2, expect_correction=False, context="hotel")

test("H03 – Hotel grammar error",
     "I wants to check in please",
     "learning", turn=1, expect_correction=True, context="hotel")

test("H04 – Hotel wrong preposition",
     "I stay on the hotel for three nights",
     "learning", turn=2, expect_correction=True, context="hotel")

test("H05 – Hotel broken English",
     "me need room for sleep two night",
     "learning", turn=1, expect_correction=True, context="hotel")

test("H06 – Hotel correct question",
     "Is breakfast included in the room price?",
     "learning", turn=3, expect_correction=False, context="hotel")

test("H07 – Hotel sim with error",
     "I wants room with see for ocean",
     "simulator", turn=2, expect_correction=None, context="hotel")


# ── runner ───────────────────────────────────────────────────────────
def main():
    login()

    results = {"pass": 0, "fail": 0, "warn": 0, "details": []}

    for i, t in enumerate(TESTS, 1):
        print(f"{'='*70}")
        print(f"TEST {i}/{len(TESTS)}: {t['name']}")
        print(f"  Mode: {t['mode']} | Turn: {t['turn']}")
        print(f"  User says: \"{t['text']}\"")
        print()

        data = chat(t["text"], context=t.get("context", "coffee_shop"),
                     practice_mode=t["mode"], turn=t["turn"],
                     difficulty=t["difficulty"])
        print(fmt(data))

        # Evaluate
        verdict = "PASS"
        notes = []

        if "_error" in data:
            verdict = "FAIL"
            notes.append(f"HTTP error {data['_error']}")
        else:
            # Check basic response quality
            ai_text = data.get("text", "")
            if not ai_text or len(ai_text) < 5:
                verdict = "FAIL"
                notes.append("AI response too short or empty")

            # Check if response is valid JSON-parsed (not raw JSON string)
            if ai_text.startswith("{") or ai_text.startswith("```"):
                verdict = "FAIL"
                notes.append("AI response appears to be raw JSON, not parsed text")

            # Check translation present
            translation = data.get("translation", "")
            if not translation and t["mode"] == "learning":
                notes.append("WARNING: No Portuguese translation in learning mode")
                if verdict == "PASS":
                    verdict = "WARN"

            # Check correction expectation
            tf = data.get("turn_feedback", {})
            tf_kind = tf.get("kind", "none") if tf else "none"
            has_correction = tf_kind in ("error_correction", "style_upgrade")
            must_retry = data.get("must_retry", False)
            sw = data.get("suggested_words", [])

            if t["expect_correction"] is True:
                if not has_correction and not must_retry and not sw:
                    verdict = "FAIL"
                    notes.append("Expected correction but got none")
                elif has_correction:
                    # Validate correction content
                    suggested = tf.get("suggested_text", "")
                    reason = tf.get("reason", "")
                    if not suggested:
                        notes.append("WARNING: Correction has no suggested_text")
                        if verdict == "PASS":
                            verdict = "WARN"
                    if not reason:
                        notes.append("WARNING: Correction has no reason/explanation")
                        if verdict == "PASS":
                            verdict = "WARN"

            elif t["expect_correction"] is False:
                if has_correction and tf_kind == "error_correction":
                    notes.append(f"WARNING: Got unexpected error_correction: {tf.get('suggested_text','')[:80]}")
                    if verdict == "PASS":
                        verdict = "WARN"

            # Teaching language check — BOTH modes should act as natural characters
            teaching_phrases = [
                "useful phrase", "in english, we", "try saying",
                "repeat after me", "good job", "let's practice", "can you try",
                "well done", "great job", "frase útil", "em inglês,",
                "i will show you", "today we're going to practice",
                "thanks for practicing",
            ]
            for tp in teaching_phrases:
                if tp.lower() in ai_text.lower():
                    verdict = "FAIL"
                    notes.append(f"Teacher language in AI text: '{tp}'")

            # Simulator-specific checks
            if t["mode"] == "simulator":

                # Should have feedback field
                fb = data.get("feedback", "")
                if fb:
                    notes.append(f"Sim feedback OK: {fb[:80]}")

                # Should NOT have must_retry in simulator
                if must_retry:
                    verdict = "FAIL"
                    notes.append("Simulator should not have must_retry=true")

            # Learning-specific checks
            if t["mode"] == "learning":
                # Check suggested_words format
                if sw and not isinstance(sw, list):
                    verdict = "FAIL"
                    notes.append(f"suggested_words is not a list: {type(sw)}")
                if sw:
                    for w in sw:
                        if not isinstance(w, str) or len(w) > 100:
                            notes.append(f"WARNING: Odd suggested_word: {w}")

        # Record
        if not notes:
            notes.append("All checks passed")

        print(f"\n  >>> {verdict}: {'; '.join(notes)}")
        print()

        results["details"].append({
            "test": t["name"],
            "mode": t["mode"],
            "user_text": t["text"],
            "verdict": verdict,
            "notes": notes,
            "ai_text": data.get("text", "")[:300],
            "translation": data.get("translation", "")[:200],
            "turn_feedback": data.get("turn_feedback"),
            "suggested_words": data.get("suggested_words", []),
            "must_retry": data.get("must_retry", False),
            "feedback": data.get("feedback", ""),
            "latency_ms": data.get("_ms", 0),
        })

        if verdict == "PASS":
            results["pass"] += 1
        elif verdict == "FAIL":
            results["fail"] += 1
        else:
            results["warn"] += 1

        # Small delay between requests
        time.sleep(0.5)

    # ── Summary ──
    total = len(TESTS)
    print(f"\n{'='*70}")
    print(f"SUMMARY: {results['pass']}/{total} PASS, {results['fail']}/{total} FAIL, {results['warn']}/{total} WARN")
    print(f"{'='*70}")

    # Save detailed report
    report_path = os.path.join(os.path.dirname(__file__), "..", "test_reports",
                               f"popup_test_report_{time.strftime('%Y%m%d_%H%M%S')}.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved: {report_path}")

    return results


if __name__ == "__main__":
    main()
