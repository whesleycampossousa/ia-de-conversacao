#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Comprehensive test suite: 200 tests × 6+ turns = 1,200+ AI interactions.

Usage:
    python tests/test_comprehensive.py                    # Run all 200 tests
    python tests/test_comprehensive.py --mode grammar     # Run only grammar tests (60)
    python tests/test_comprehensive.py --mode simulator   # Run only simulator tests (90)
    python tests/test_comprehensive.py --mode learning    # Run only learning tests (50)
    python tests/test_comprehensive.py --verbose          # Show all AI responses
"""

import os, sys, json, re, time, argparse, requests
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_URL = os.environ.get("TEST_API_URL", "http://localhost:8912")

# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION RULES
# ══════════════════════════════════════════════════════════════════════════════

ROBOTIC_PHRASES = [
    "repeat after me", "say it again",
    "i'd like you to say",
]
# These phrases are only robotic in simulator mode (natural in learning/grammar)
ROBOTIC_PHRASES_SIMULATOR_ONLY = [
    "can you try", "let's practice", "does that make sense",
    "do you understand", "try saying", "practice saying", "can you say"
]

TECHNICAL_JARGON = [
    "present tense", "past tense", "future tense", "present perfect",
    "past simple", "present simple", "present continuous", "past continuous",
    "first conditional", "second conditional", "third conditional",
    "zero conditional", "subject-verb", "conjugat", "auxiliary verb",
    "predicate", "syntax", "vowel sound", "consonant sound",
    "past participle", "gerund form", "infinitive form",
    "definite article", "indefinite article", "modal verb"
]

SIMULATOR_TEACHING_PHRASES = [
    "let me explain", "in english we say", "the correct form is",
    "grammar", "lesson", "practice", "let's learn", "good job",
    "well done", "great job", "excellent", "perfect english",
    "you said it correctly", "your english is"
]

# Topic-specific keywords to check ON_TOPIC for grammar
# NOTE: matching is case-insensitive substring. At least 1 keyword must match per turn (after turn 1).
GRAMMAR_TOPIC_KEYWORDS = {
    "verb_to_be": ["am", "is", "are", "was", "were", "'m", "'s", "'re"],
    "articles": ["a ", "an ", "the "],
    "present_simple": ["do ", "does ", "don't", "doesn't", "every", "always", "usually", "never",
                        "sometimes", "often", "works", "plays", "likes", "goes", "eats", "drinks",
                        "wakes", "sleeps", "cooks", "walks", "reads", "hates", "loves", "prefers",
                        "drives", "makes", "lives", "studies"],
    "past_simple": ["did", "didn't", "went", "saw", "had", "was", "were", "yesterday", "last",
                     "ago", "bought", "ate", "drank", "came", "made", "took", "found", "told"],
    "present_perfect": ["have ", "has ", "haven't", "hasn't", "'ve ", "'s been", "ever", "never",
                         "already", "yet", "just ", "since", "for "],
    "conditionals_zero_first": ["if ", "when ", "will ", "won't"],
    "conditionals_second": ["if ", "would ", "wouldn't", "were ", "could "],
    "passive_voice": ["is ", "are ", "was ", "were ", "been ", "by ", "made by", "built", "written"],
    "phrasal_verbs": ["up", "down", "out", "off", "on ", "in ", "over", "away"],
    "comparatives_superlatives": ["more ", "most ", "than ", "er ", "est ", "better", "worse", "best", "worst"],
    "some_any_no": ["some", "any", "no ", "none"],
    "prepositions_time_place": ["in ", "on ", "at ", "from ", "to ", "between", "under", "above", "next to"],
    "reported_speech": ["said", "told", "asked", "that ", "would", "had"],
    "relative_clauses": ["who ", "which ", "that ", "where ", "whose", "whom"],
    "question_tags": ["isn't it", "aren't you", "don't you", "doesn't it", "didn't", "won't", "can't",
                       "right?", "tag"],
}

def validate_turn(response_text, mode, topic_id, student_input, turn_num, has_error=False):
    """Validate a single AI turn. Returns list of (issue_code, detail) tuples."""
    issues = []
    lower = response_text.lower()
    word_count = len(response_text.split())

    # === UNIVERSAL VALIDATORS ===

    # ENDS_WITH_QUESTION
    stripped = response_text.rstrip()
    if not stripped.endswith('?'):
        issues.append(("NO_QUESTION", f"Response doesn't end with '?': ...{stripped[-60:]}"))

    # RESPONSE_LENGTH
    if mode == 'simulator' and word_count > 40:
        issues.append(("TOO_LONG", f"Simulator response too long: {word_count} words (max 40)"))
    elif mode == 'grammar' and word_count > 60:
        issues.append(("TOO_LONG", f"Grammar response too long: {word_count} words (max 60)"))
    elif mode == 'learning' and word_count > 100:
        issues.append(("TOO_LONG", f"Learning response too long: {word_count} words (max 100)"))

    # NO_ROBOTIC_PHRASES
    for phrase in ROBOTIC_PHRASES:
        if phrase in lower:
            issues.append(("ROBOTIC_PHRASE", f"Robotic phrase: '{phrase}'"))
    if mode == 'simulator':
        for phrase in ROBOTIC_PHRASES_SIMULATOR_ONLY:
            if phrase in lower:
                issues.append(("ROBOTIC_PHRASE", f"Robotic phrase: '{phrase}'"))

    # === GRAMMAR MODE VALIDATORS ===
    if mode == 'grammar':
        # NO_TECHNICAL_JARGON
        for term in TECHNICAL_JARGON:
            if term in lower:
                issues.append(("TECHNICAL_JARGON", f"Technical jargon: '{term}'"))

        # ON_TOPIC (check if response contains topic-related keywords)
        if topic_id in GRAMMAR_TOPIC_KEYWORDS:
            keywords = GRAMMAR_TOPIC_KEYWORDS[topic_id]
            found = sum(1 for k in keywords if k.lower() in lower)
            if found == 0 and turn_num > 1:  # Allow first turn to be intro
                issues.append(("OFF_TOPIC", f"No keywords for '{topic_id}' found in response"))

        # IMMERSION_STYLE
        if "___" in response_text or "fill in" in lower or "complete:" in lower:
            issues.append(("FILL_IN_BLANK", "Used drill-style exercise"))

    # === SIMULATOR MODE VALIDATORS ===
    if mode == 'simulator':
        # NO_TEACHING
        for phrase in SIMULATOR_TEACHING_PHRASES:
            if phrase in lower:
                issues.append(("SIMULATOR_TEACHING", f"Teaching in simulator: '{phrase}'"))

        # COMPLETE_SENTENCES
        if stripped.rstrip('?').endswith(('or', 'and', ',', '...')):
            issues.append(("INCOMPLETE_SENTENCE", f"Ends with trailing: ...{stripped[-30:]}"))

    # === LEARNING MODE VALIDATORS ===
    if mode == 'learning':
        # Check for Portuguese translation (should have parenthetical or pt field)
        if turn_num > 1 and '(' not in response_text and 'traduc' not in lower:
            # Relaxed check - just flag if clearly missing
            pass  # PT is in the pt field of JSON, not always in en text

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSATION SCRIPTS (200 tests)
# ══════════════════════════════════════════════════════════════════════════════

def build_grammar_tests():
    """60 grammar tests: 15 topics × 4 variants."""
    tests = []
    topics = [
        ("verb_to_be", [
            # Variant 1: On-topic with errors
            {"variant": "on_topic", "turns": [
                ("Hi, I want to learn about verb to be", False),
                ("I is happy today", True),
                ("She are my friend", True),
                ("We is students at a school", True),
                ("He is very tall and she is smart", False),
                ("They am from Brazil", True),
            ]},
            # Variant 2: Off-topic drift
            {"variant": "off_topic_drift", "turns": [
                ("Hi there!", False),
                ("I am from Brazil", False),
                ("What's your favorite food?", False),
                ("I like pizza. Do you watch Netflix?", False),
                ("Tell me about your hobbies", False),
                ("What movies do you like?", False),
            ]},
            # Variant 3: Correct input
            {"variant": "correct_input", "turns": [
                ("Hello! I am Wesley.", False),
                ("I am a student. She is my teacher.", False),
                ("We are happy to be here today.", False),
                ("They are from different countries.", False),
                ("It is a beautiful day outside.", False),
                ("You are very kind to help me.", False),
            ]},
            # Variant 4: Intentional errors
            {"variant": "intentional_errors", "turns": [
                ("Hi! I is ready to learn", True),
                ("My mother are a nurse", True),
                ("You is my best friend", True),
                ("The dogs is very cute", True),
                ("I are tired today", True),
                ("She am a doctor", True),
            ]},
        ]),
        ("articles", [
            {"variant": "on_topic", "turns": [
                ("I want to learn about articles", False),
                ("I have a apple", True),
                ("She is a engineer", True),
                ("I went to the school yesterday", True),
                ("Can I have an water please?", True),
                ("He bought a umbrella", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi, how are you?", False),
                ("I like dogs and cats", False),
                ("What do you do on weekends?", False),
                ("I play soccer every Saturday", False),
                ("My favorite color is blue", False),
                ("Do you like music?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("I ate an apple today.", False),
                ("The cat is sleeping on the couch.", False),
                ("She is a teacher at a school.", False),
                ("I need an umbrella because of the rain.", False),
                ("He works at a hospital.", False),
                ("The movie was really good.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("I saw a elephant at zoo", True),
                ("She is an teacher", True),
                ("I love the music", True),
                ("He ate a orange", True),
                ("I need a umbrella", True),
                ("She works at the hospital in a evening", True),
            ]},
        ]),
        ("present_simple", [
            {"variant": "on_topic", "turns": [
                ("I want to practice present simple", False),
                ("She go to school every day", True),
                ("He don't like coffee", True),
                ("My brother wake up late", True),
                ("I plays guitar on weekends", True),
                ("Do she like pizza?", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hello!", False),
                ("I wake up at 7 every day.", False),
                ("Yesterday I went to the park", False),
                ("I will travel next month", False),
                ("I have been studying for hours", False),
                ("What should I do tomorrow?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("I usually wake up at 7.", False),
                ("She works at a hospital.", False),
                ("They don't like spicy food.", False),
                ("Does he play any sports?", False),
                ("My mother cooks dinner every night.", False),
                ("We go to the gym three times a week.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("She work very hard", True),
                ("He have two brothers", True),
                ("They doesn't want to go", True),
                ("My father drive to work", True),
                ("She don't speak French", True),
                ("Do he likes reading?", True),
            ]},
        ]),
        ("past_simple", [
            {"variant": "on_topic", "turns": [
                ("Let's talk about the past", False),
                ("Yesterday I go to the store", True),
                ("She buyed a new dress", True),
                ("We didn't went to the party", True),
                ("I see my friend at the mall", True),
                ("They eated all the food", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi!", False),
                ("I went to the beach last week.", False),
                ("I am happy right now", False),
                ("I will go to London soon", False),
                ("What's the weather like today?", False),
                ("Can you help me with something?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("I went to the park yesterday.", False),
                ("She bought a beautiful dress.", False),
                ("They didn't come to the party.", False),
                ("We watched a movie last night.", False),
                ("He played soccer after school.", False),
                ("Did you enjoy the concert?", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("I goed to the park", True),
                ("She thinked about it", True),
                ("We runned very fast", True),
                ("He catched the ball", True),
                ("I writed a letter yesterday", True),
                ("They swimmed in the pool", True),
            ]},
        ]),
        ("present_perfect", [
            {"variant": "on_topic", "turns": [
                ("Hi, I want to practice", False),
                ("I have went to Paris", True),
                ("She has eat sushi", True),
                ("We have never see snow", True),
                ("I have lived here for five years", False),
                ("Have you ever be to Japan?", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hello!", False),
                ("I have been to France.", False),
                ("I am going to the store now", False),
                ("What time is it?", False),
                ("I like playing video games", False),
                ("Tell me about your family", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("I have visited many countries.", False),
                ("She has never tried sushi.", False),
                ("Have you ever been to Asia?", False),
                ("We have lived here since 2020.", False),
                ("He has already finished his homework.", False),
                ("They haven't seen the movie yet.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("I have went there many times", True),
                ("She has broke the window", True),
                ("We have knew each other for years", True),
                ("He has drinked too much coffee", True),
                ("I have forgotted my password", True),
                ("They have taked the test", True),
            ]},
        ]),
        ("conditionals_zero_first", [
            {"variant": "on_topic", "turns": [
                ("I want to learn about if sentences", False),
                ("If I will study, I pass", True),
                ("If it rain, I stay home", True),
                ("If you heat water, it boil", True),
                ("If I have time, I will go", False),
                ("What happens if you no study?", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hello!", False),
                ("If it rains, I stay home.", False),
                ("I like sunny days", False),
                ("My dog is very cute", False),
                ("I play guitar sometimes", False),
                ("What's your name?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("If it rains, I stay home.", False),
                ("If you study, you pass.", False),
                ("If I see him, I will tell him.", False),
                ("If we hurry, we won't be late.", False),
                ("If she calls, I'll answer.", False),
                ("If you heat ice, it melts.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("If I will have time, I go", True),
                ("If it will rain, I stay", True),
                ("If you will study, you pass", True),
                ("If water boils, it turn to steam", True),
                ("If she will come, we go", True),
                ("If I no sleep, I tired", True),
            ]},
        ]),
        ("conditionals_second", [
            {"variant": "on_topic", "turns": [
                ("I want to talk about imaginary situations", False),
                ("If I will be rich, I would buy a house", True),
                ("If I was you, I will study more", True),
                ("If I have more time, I travel", True),
                ("If I won the lottery, I would travel the world", False),
                ("If I can fly, I go everywhere", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi!", False),
                ("If I had money, I would travel.", False),
                ("I'm hungry right now", False),
                ("What did you eat today?", False),
                ("I want to go shopping", False),
                ("Do you like sports?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("If I won the lottery, I would travel.", False),
                ("If I were you, I would study more.", False),
                ("If I had more time, I would read.", False),
                ("If she lived here, we would be friends.", False),
                ("If it weren't so expensive, I would buy it.", False),
                ("What would you do if you could fly?", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("If I would be rich, I buy a car", True),
                ("If she will know, she would come", True),
                ("If I am you, I would go", True),
                ("If he has more time, he would travel", True),
                ("If they will help, I would finish", True),
                ("If I can speak French, I would move", True),
            ]},
        ]),
        ("passive_voice", [
            {"variant": "on_topic", "turns": [
                ("I want to learn about passive voice", False),
                ("The cake made by my mom", True),
                ("The window break by the ball", True),
                ("English speak in many countries", True),
                ("The book was written by a famous author", False),
                ("The car was stole last night", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi!", False),
                ("The cake was made by my mom.", False),
                ("I like cooking a lot", False),
                ("What is your favorite recipe?", False),
                ("I want to be a chef", False),
                ("Do you cook at home?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("The cake was made by my mom.", False),
                ("English is spoken in many countries.", False),
                ("The window was broken by the ball.", False),
                ("The letter was sent yesterday.", False),
                ("The movie was directed by Spielberg.", False),
                ("The homework has been done.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("The car steal last night", True),
                ("The food prepare by the chef", True),
                ("The house build in 1990", True),
                ("The email send yesterday", True),
                ("The test take by 100 students", True),
                ("The painting create by Picasso", True),
            ]},
        ]),
        ("phrasal_verbs", [
            {"variant": "on_topic", "turns": [
                ("I want to learn phrasal verbs", False),
                ("I need to give back my homework", False),
                ("She put off the meeting", False),
                ("He turned down the offer", False),
                ("I ran into my friend yesterday", False),
                ("Can you look after my dog?", False),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi!", False),
                ("I woke up early today.", False),
                ("I like chocolate cake", False),
                ("My sister lives in Paris", False),
                ("I want a new phone", False),
                ("What do you do for fun?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("I looked up the word in the dictionary.", False),
                ("She turned down the invitation.", False),
                ("We need to figure out a solution.", False),
                ("He gave up smoking last year.", False),
                ("I ran into an old friend.", False),
                ("Can you pick me up at 5?", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("I need to give over my homework", True),
                ("She put of the meeting", True),
                ("He turned out the offer", True),
                ("I run into my friend yesterday", True),
                ("Can you look on my dog?", True),
                ("We need to figure up a plan", True),
            ]},
        ]),
        ("comparatives_superlatives", [
            {"variant": "on_topic", "turns": [
                ("I want to practice comparisons", False),
                ("My house is more big than yours", True),
                ("This is the most easy exercise", True),
                ("She is more tall than me", True),
                ("English is gooder than math", True),
                ("He is the most fast runner", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hello!", False),
                ("My brother is taller than me.", False),
                ("I had pizza for lunch", False),
                ("I want to go to the beach", False),
                ("What time does the store close?", False),
                ("I need to buy groceries", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("My brother is taller than me.", False),
                ("This is the easiest exercise.", False),
                ("She is smarter than her sister.", False),
                ("This is the best restaurant in town.", False),
                ("He runs faster than anyone.", False),
                ("It's the most beautiful place I've seen.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("She is more beautiful that her sister", True),
                ("This is the most cheap option", True),
                ("He is more strong than me", True),
                ("It's the most big house", True),
                ("She sings more good than him", True),
                ("This is the most bad movie ever", True),
            ]},
        ]),
        ("some_any_no", [
            {"variant": "on_topic", "turns": [
                ("I want to learn some, any, no", False),
                ("Do you have some milk?", True),
                ("I don't have no money", True),
                ("There isn't some sugar left", True),
                ("I have some friends here", False),
                ("Is there some problem?", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi!", False),
                ("I need some water.", False),
                ("I went to school today", False),
                ("My phone is broken", False),
                ("I want to travel to Japan", False),
                ("What's your favorite season?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("I have some friends in London.", False),
                ("Do you have any questions?", False),
                ("There is no milk in the fridge.", False),
                ("Would you like some coffee?", False),
                ("I don't have any money.", False),
                ("There are some books on the table.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("I don't have some money", True),
                ("Do you have no questions?", True),
                ("There isn't some water", True),
                ("I have any friends here", True),
                ("Is there some milk? No, there isn't no milk", True),
                ("I don't want no help", True),
            ]},
        ]),
        ("prepositions_time_place", [
            {"variant": "on_topic", "turns": [
                ("I want to learn prepositions", False),
                ("I was born in March 15", True),
                ("She lives in Park Street", True),
                ("We arrived in Monday morning", True),
                ("I study in the morning", False),
                ("The meeting is in 3 PM", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hello!", False),
                ("I live on Main Street.", False),
                ("What's your favorite movie?", False),
                ("I like playing soccer", False),
                ("My cat is very lazy", False),
                ("I want to learn cooking", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("I was born on March 15th.", False),
                ("She lives on Park Street.", False),
                ("We arrive at 3 PM.", False),
                ("I study in the morning.", False),
                ("The party is on Saturday.", False),
                ("He works at the hospital.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("I was born in March 15", True),
                ("She lives in Park Street", True),
                ("The class starts in 9 AM", True),
                ("I go to work on the morning", True),
                ("He arrived at Monday", True),
                ("We meet in the bus stop", True),
            ]},
        ]),
        ("reported_speech", [
            {"variant": "on_topic", "turns": [
                ("I want to learn reported speech", False),
                ("She said me that she is happy", True),
                ("He told he will come tomorrow", True),
                ("They said they are going to help", True),
                ("She asked me where do I live", True),
                ("He said that he likes pizza", False),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi!", False),
                ("She told me she was coming.", False),
                ("I like watching TV", False),
                ("What's for dinner tonight?", False),
                ("I need to wash my car", False),
                ("Do you have any pets?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("She said she was happy.", False),
                ("He told me he would come.", False),
                ("They said they were going to help.", False),
                ("She asked me where I lived.", False),
                ("He mentioned that he liked pizza.", False),
                ("She said she had already finished.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("She said me she is tired", True),
                ("He told that he will go", True),
                ("She asked where do I work", True),
                ("He said he can help tomorrow", True),
                ("She told that she has finished", True),
                ("They said me they are coming", True),
            ]},
        ]),
        ("relative_clauses", [
            {"variant": "on_topic", "turns": [
                ("I want to practice relative clauses", False),
                ("The man which lives next door is nice", True),
                ("The book who I read was great", True),
                ("The place which I was born is small", True),
                ("The teacher who taught me is retired", False),
                ("The car what I bought is red", True),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hi!", False),
                ("The person who called is my friend.", False),
                ("I like cold weather", False),
                ("What's the capital of France?", False),
                ("I need new shoes", False),
                ("Do you like reading?", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("The man who lives next door is nice.", False),
                ("The book that I read was great.", False),
                ("The city where I was born is small.", False),
                ("The teacher who taught me retired.", False),
                ("The car which I bought is red.", False),
                ("The woman whose dog ran away is sad.", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("The girl which is my friend", True),
                ("The place who I visited", True),
                ("The person what called me", True),
                ("The book who I bought", True),
                ("The house which I live is old", True),
                ("The man what I met yesterday", True),
            ]},
        ]),
        ("question_tags", [
            {"variant": "on_topic", "turns": [
                ("I want to practice question tags", False),
                ("She is beautiful, isn't it?", True),
                ("They went home, didn't they?", False),
                ("You can swim, can you?", True),
                ("He doesn't like coffee, doesn't he?", True),
                ("We should go, shouldn't we?", False),
            ]},
            {"variant": "off_topic_drift", "turns": [
                ("Hello!", False),
                ("It's cold today, isn't it?", False),
                ("I love summer vacations", False),
                ("What do you think about AI?", False),
                ("My birthday is next week", False),
                ("I want to learn to dance", False),
            ]},
            {"variant": "correct_input", "turns": [
                ("She is beautiful, isn't she?", False),
                ("They went home, didn't they?", False),
                ("You can't swim, can you?", False),
                ("He doesn't like coffee, does he?", False),
                ("We should go, shouldn't we?", False),
                ("It's a nice day, isn't it?", False),
            ]},
            {"variant": "intentional_errors", "turns": [
                ("She is nice, isn't it?", True),
                ("He can swim, can he?", True),
                ("They don't like it, don't they?", True),
                ("She was tired, wasn't it?", True),
                ("We will go, will we?", True),
                ("He has finished, has he?", True),
            ]},
        ]),
    ]

    for topic_id, variants in topics:
        for v in variants:
            tests.append({
                "test_id": f"grammar_{topic_id}_{v['variant']}",
                "mode": "grammar",
                "context": topic_id,
                "practice_mode": "learning",
                "lesson_lang": "en",
                "turns": v["turns"],
            })
    return tests


def build_simulator_tests():
    """90 simulator tests: 30 scenarios × 3 variants."""
    tests = []
    scenarios = [
        ("coffee_shop", [
            {"variant": "normal_flow", "turns": [
                ("Hi there", False), ("I'd like a coffee please", False),
                ("A large one", False), ("Hot, please", False),
                ("No sugar, thanks", False), ("That's all, thanks", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hello", False), ("I want coffee big", True),
                ("How much cost?", True), ("I want take here", True),
                ("Can I have cake too?", False), ("What time you close?", True),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hi", False), ("What do you recommend?", False),
                ("Actually, can you teach me English?", False),
                ("How do I order in English?", False),
                ("I want something sweet", False), ("Thanks, bye!", False),
            ]},
        ]),
        ("restaurant", [
            {"variant": "normal_flow", "turns": [
                ("Good evening", False), ("A table for two, please", False),
                ("Can I see the menu?", False), ("I'll have the pasta", False),
                ("Just water, please", False), ("Can I have the check?", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hi", False), ("Table for two person", True),
                ("I want see menu", True), ("I like the pasta", False),
                ("What you recommend?", True), ("How much is total?", True),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hello", False), ("Is there vegetarian options?", True),
                ("I'm allergic to nuts", False), ("Can I change my order?", False),
                ("The food is cold", False), ("I want to speak to the manager", False),
            ]},
        ]),
        ("airport", [
            {"variant": "normal_flow", "turns": [
                ("Hi, I need to check in", False), ("Here's my passport", False),
                ("Window seat please", False), ("Just one bag", False),
                ("Where is the gate?", False), ("What time does it board?", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hello", False), ("I need check in for flight", True),
                ("Here my passport", True), ("I want seat near window", True),
                ("How many bags I can take?", True), ("Where is go the gate?", True),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hi", False), ("I missed my flight", False),
                ("Can I get on the next one?", False), ("I lost my luggage", False),
                ("I need to change my ticket", False), ("Where is the bathroom?", False),
            ]},
        ]),
        ("hotel", [
            {"variant": "normal_flow", "turns": [
                ("Hi, I have a reservation", False), ("Wesley Campos", False),
                ("For three nights", False), ("Do you have wifi?", False),
                ("What time is checkout?", False), ("Is breakfast included?", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hello", False), ("I have reserve for tonight", True),
                ("My name Wesley", True), ("The room have wifi?", True),
                ("I want room with view", True), ("What time is the breakfast?", False),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hi", False), ("The room is too noisy", False),
                ("Can I change rooms?", False), ("The AC is not working", False),
                ("I need extra towels", False), ("Can I extend my stay?", False),
            ]},
        ]),
        ("bank", [
            {"variant": "normal_flow", "turns": [
                ("Hi, I'd like to open an account", False),
                ("A savings account, please", False), ("Here's my ID", False),
                ("What's the interest rate?", False),
                ("Is there a monthly fee?", False), ("I'd like to deposit some money", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hello", False), ("I want open account", True),
                ("How much is the minimum?", False), ("I want deposit money", True),
                ("What documents I need?", True), ("Can I make transfer?", True),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hi", False), ("I lost my card", False),
                ("I need to block it", False), ("How can I get a new one?", False),
                ("I noticed a weird charge", False), ("I want to close my account", False),
            ]},
        ]),
        ("doctor", [
            {"variant": "normal_flow", "turns": [
                ("Hi, I have an appointment", False),
                ("I have a headache and fever", False),
                ("Since yesterday", False), ("No, no allergies", False),
                ("Should I take any medicine?", False),
                ("When should I come back?", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hello", False), ("I feel not good", True),
                ("My head hurt very much", True), ("I have this since two days", True),
                ("I no take any medicine", True), ("When I need come back?", True),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hi", False), ("I feel dizzy and nauseous", False),
                ("I've been stressed at work", False),
                ("I can't sleep at night", False),
                ("Is it something serious?", False),
                ("Can I get a doctor's note?", False),
            ]},
        ]),
        ("supermarket", [
            {"variant": "normal_flow", "turns": [
                ("Excuse me, where are the eggs?", False),
                ("Thanks. And where is the milk?", False),
                ("Do you have organic milk?", False),
                ("How much is this?", False),
                ("Can I pay with card?", False),
                ("I need a bag, please", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hi", False), ("Where is the eggs?", True),
                ("I need buy bread", True), ("How much cost this?", True),
                ("You have discount today?", True), ("I want pay with card", True),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hello", False), ("This product is expired", False),
                ("I want a refund", False), ("Where is the manager?", False),
                ("Do you have gluten-free options?", False),
                ("What time do you close?", False),
            ]},
        ]),
    ]

    # Add remaining 23 scenarios with generic patterns
    remaining = [
        "pharmacy", "gym", "cinema", "museum", "hair_salon", "clothing_store",
        "pet_shop", "flower_shop", "gas_station", "library", "post_office",
        "pizza_delivery", "bakery", "dental_clinic", "train_station", "bus_stop",
        "renting_car", "job_interview", "first_date", "school", "neighbor",
        "tech_support", "lost_found"
    ]
    for scenario_id in remaining:
        scenarios.append((scenario_id, [
            {"variant": "normal_flow", "turns": [
                ("Hi there", False), ("I need some help", False),
                ("Yes, that would be great", False), ("How much is it?", False),
                ("Sounds good", False), ("Thank you very much", False),
            ]},
            {"variant": "grammar_errors", "turns": [
                ("Hello", False), ("I want help please", True),
                ("How much cost?", True), ("I need this for tomorrow", False),
                ("Where I can find this?", True), ("Thank you for help", True),
            ]},
            {"variant": "edge_case", "turns": [
                ("Hi", False), ("I have a problem", False),
                ("It's not what I expected", False), ("Can you fix this?", False),
                ("I want to make a complaint", False), ("Can I speak to someone else?", False),
            ]},
        ]))

    for scenario_id, variants in scenarios:
        for v in variants:
            tests.append({
                "test_id": f"simulator_{scenario_id}_{v['variant']}",
                "mode": "simulator",
                "context": scenario_id,
                "practice_mode": "simulator",
                "lesson_lang": "en",
                "turns": v["turns"],
            })
    return tests


def build_learning_tests():
    """50 learning tests: 10 scenarios × 5 variants."""
    tests = []
    scenarios = [
        "coffee_shop", "job_interview", "airport", "restaurant", "hotel",
        "supermarket", "doctor", "bank", "gym", "pharmacy"
    ]

    for scenario_id in scenarios:
        # V1: Greeting start
        tests.append({
            "test_id": f"learning_{scenario_id}_greeting",
            "mode": "learning", "context": scenario_id,
            "practice_mode": "learning", "lesson_lang": "en",
            "turns": [
                ("Hi! How are you?", False), ("I'm doing great, thanks!", False),
                ("I'm ready to learn", False), ("Can you teach me something useful?", False),
                ("That's helpful, thank you", False), ("What else should I know?", False),
            ],
        })
        # V2: Normal progression
        tests.append({
            "test_id": f"learning_{scenario_id}_progression",
            "mode": "learning", "context": scenario_id,
            "practice_mode": "learning", "lesson_lang": "en",
            "turns": [
                ("Hello, I want to practice", False), ("OK, I'll try", False),
                ("I think I understand", False), ("Let me try another one", False),
                ("Is that correct?", False), ("What's next?", False),
            ],
        })
        # V3: Student errors
        tests.append({
            "test_id": f"learning_{scenario_id}_errors",
            "mode": "learning", "context": scenario_id,
            "practice_mode": "learning", "lesson_lang": "en",
            "turns": [
                ("Hi", False), ("I want a coffee big please", True),
                ("How much cost?", True), ("I no understand", True),
                ("Can you repeat more slow?", True), ("I want try again", True),
            ],
        })
        # V4: Student confused
        tests.append({
            "test_id": f"learning_{scenario_id}_confused",
            "mode": "learning", "context": scenario_id,
            "practice_mode": "learning", "lesson_lang": "en",
            "turns": [
                ("Hello", False), ("I don't understand", False),
                ("What does that mean?", False), ("Can you say it in Portuguese?", False),
                ("Oh, I see now", False), ("Can you give me an easier example?", False),
            ],
        })
        # V5: Off-topic
        tests.append({
            "test_id": f"learning_{scenario_id}_offtopic",
            "mode": "learning", "context": scenario_id,
            "practice_mode": "learning", "lesson_lang": "en",
            "turns": [
                ("Hi!", False), ("What's your favorite color?", False),
                ("Do you like pizza?", False), ("I love watching movies", False),
                ("OK let's get back to the lesson", False), ("What should I say?", False),
            ],
        })

    return tests


# ══════════════════════════════════════════════════════════════════════════════
# TEST RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_single_test(test, verbose=False):
    """Run a single test (6+ turns). Returns dict with results."""
    test_id = test["test_id"]
    context = test["context"]
    practice_mode = test["practice_mode"]
    lesson_lang = test["lesson_lang"]
    mode = test["mode"]
    turns = test["turns"]

    results = {"test_id": test_id, "mode": mode, "context": context, "turns": [], "issues": []}

    for turn_num, (student_text, has_error) in enumerate(turns, 1):
        try:
            r = requests.post(
                f"{API_URL}/api/chat",
                json={
                    "text": student_text,
                    "context": context,
                    "lessonLang": lesson_lang,
                    "practiceMode": practice_mode,
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            if r.status_code != 200:
                results["issues"].append({"turn": turn_num, "code": "API_ERROR", "detail": f"Status {r.status_code}"})
                results["turns"].append({"student": student_text, "ai": f"ERROR {r.status_code}", "issues": ["API_ERROR"]})
                continue

            data = r.json()
            ai_text = data.get("text", data.get("en", data.get("pt", "")))

            if not ai_text:
                results["issues"].append({"turn": turn_num, "code": "EMPTY_RESPONSE", "detail": "No text in response"})
                results["turns"].append({"student": student_text, "ai": "(empty)", "issues": ["EMPTY_RESPONSE"]})
                continue

            # Validate
            turn_issues = validate_turn(ai_text, mode, context, student_text, turn_num, has_error)

            turn_result = {
                "student": student_text,
                "ai": ai_text,
                "word_count": len(ai_text.split()),
                "issues": [code for code, _ in turn_issues],
            }
            results["turns"].append(turn_result)

            for code, detail in turn_issues:
                results["issues"].append({"turn": turn_num, "code": code, "detail": detail})

            if verbose:
                marker = "  " if not turn_issues else ">>"
                issues_str = ", ".join(code for code, _ in turn_issues) if turn_issues else ""
                print(f"    T{turn_num}: Student: \"{student_text}\"")
                print(f"    {marker} AI [{len(ai_text.split())}w]: \"{ai_text[:120]}{'...' if len(ai_text) > 120 else ''}\"")
                if issues_str:
                    print(f"    ** ISSUES: {issues_str}")

        except requests.exceptions.ConnectionError:
            # Retry once after a pause
            time.sleep(3)
            try:
                r = requests.post(
                    f"{API_URL}/api/chat",
                    json={
                        "text": student_text,
                        "context": context,
                        "lessonLang": lesson_lang,
                        "practiceMode": practice_mode,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                if r.status_code == 200:
                    data = r.json()
                    ai_text = data.get("text", data.get("en", data.get("pt", "")))
                    if ai_text:
                        turn_issues = validate_turn(ai_text, mode, context, student_text, turn_num, has_error)
                        results["turns"].append({"student": student_text, "ai": ai_text, "word_count": len(ai_text.split()), "issues": [code for code, _ in turn_issues]})
                        for code, detail in turn_issues:
                            results["issues"].append({"turn": turn_num, "code": code, "detail": detail})
                    else:
                        results["issues"].append({"turn": turn_num, "code": "EMPTY_RESPONSE", "detail": "No text in retry response"})
                else:
                    results["issues"].append({"turn": turn_num, "code": "API_ERROR", "detail": f"Retry status {r.status_code}"})
            except Exception:
                results["issues"].append({"turn": turn_num, "code": "CONNECTION_ERROR", "detail": "Cannot connect after retry"})
                break
        except Exception as e:
            results["issues"].append({"turn": turn_num, "code": "EXCEPTION", "detail": str(e)[:200]})

        time.sleep(2.0)  # Rate limiting — stay under 30/min Flask + Gemini API limits

    return results


def run_tests(tests, verbose=False):
    """Run all tests and return aggregate results."""
    all_results = []
    total = len(tests)

    for i, test in enumerate(tests):
        test_id = test["test_id"]
        status_char = f"[{i+1}/{total}]"

        if verbose:
            print(f"\n{'='*70}")
            print(f"  {status_char} {test_id}")
            print(f"{'='*70}")
        else:
            issue_count_so_far = sum(len(r["issues"]) for r in all_results)
            print(f"  {status_char} {test_id}...", end=" ", flush=True)

        result = run_single_test(test, verbose)
        all_results.append(result)

        if not verbose:
            n_issues = len(result["issues"])
            print(f"{'PASS' if n_issues == 0 else f'FAIL ({n_issues} issues)'}")

    return all_results


def generate_report(all_results, output_dir):
    """Generate JSON and text summary reports."""
    os.makedirs(output_dir, exist_ok=True)

    total_tests = len(all_results)
    total_turns = sum(len(r["turns"]) for r in all_results)
    failed_tests = [r for r in all_results if r["issues"]]
    passed_tests = total_tests - len(failed_tests)

    # Count issues
    issues_by_code = defaultdict(int)
    issues_by_mode = defaultdict(lambda: {"total": 0, "tests": set()})

    for r in all_results:
        for issue in r["issues"]:
            issues_by_code[issue["code"]] += 1
            issues_by_mode[r["mode"]]["total"] += 1
            issues_by_mode[r["mode"]]["tests"].add(r["test_id"])

    # Severity classification
    critical_codes = {"API_ERROR", "CONNECTION_ERROR", "EMPTY_RESPONSE", "SIMULATOR_TEACHING", "INVALID_JSON"}
    high_codes = {"NO_QUESTION", "OFF_TOPIC", "TECHNICAL_JARGON", "FILL_IN_BLANK"}
    medium_codes = {"TOO_LONG", "ROBOTIC_PHRASE", "INCOMPLETE_SENTENCE"}

    severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for code, count in issues_by_code.items():
        if code in critical_codes:
            severity["CRITICAL"] += count
        elif code in high_codes:
            severity["HIGH"] += count
        elif code in medium_codes:
            severity["MEDIUM"] += count
        else:
            severity["LOW"] += count

    # JSON report
    report = {
        "run_date": datetime.now().isoformat(),
        "total_tests": total_tests,
        "total_turns": total_turns,
        "passed": passed_tests,
        "failed": len(failed_tests),
        "pass_rate": f"{passed_tests/total_tests*100:.1f}%",
        "issues_by_severity": severity,
        "issues_by_code": dict(issues_by_code),
        "issues_by_mode": {m: {"total": d["total"], "tests_affected": len(d["tests"])} for m, d in issues_by_mode.items()},
        "failed_tests": [
            {"test_id": r["test_id"], "mode": r["mode"], "issues": r["issues"]}
            for r in failed_tests
        ],
    }

    json_path = os.path.join(output_dir, "comprehensive_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Text summary
    summary_lines = [
        "=" * 70,
        "  COMPREHENSIVE TEST REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        f"\n  Total tests: {total_tests}",
        f"  Total turns: {total_turns}",
        f"  Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)",
        f"  Failed: {len(failed_tests)} ({len(failed_tests)/total_tests*100:.1f}%)",
        f"\n  Issues by severity:",
        f"    CRITICAL: {severity['CRITICAL']}",
        f"    HIGH:     {severity['HIGH']}",
        f"    MEDIUM:   {severity['MEDIUM']}",
        f"    LOW:      {severity['LOW']}",
        f"\n  Issues by code:",
    ]
    for code, count in sorted(issues_by_code.items(), key=lambda x: -x[1]):
        summary_lines.append(f"    {code}: {count}")

    summary_lines.append(f"\n  Issues by mode:")
    for m, d in issues_by_mode.items():
        summary_lines.append(f"    {m}: {d['total']} issues in {len(d['tests'])} tests")

    if failed_tests:
        summary_lines.append(f"\n  Failed tests:")
        for r in failed_tests[:20]:  # Show first 20
            codes = set(i["code"] for i in r["issues"])
            summary_lines.append(f"    {r['test_id']}: {', '.join(codes)}")
        if len(failed_tests) > 20:
            summary_lines.append(f"    ... and {len(failed_tests)-20} more")

    summary_lines.append("=" * 70)
    summary = "\n".join(summary_lines)

    txt_path = os.path.join(output_dir, "comprehensive_summary.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print(summary)
    print(f"\n  Reports saved:")
    print(f"    {json_path}")
    print(f"    {txt_path}")

    return report


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global API_URL
    parser = argparse.ArgumentParser(description="Comprehensive test suite (200 tests)")
    parser.add_argument("--mode", choices=["grammar", "simulator", "learning"], help="Run only one mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all AI responses")
    parser.add_argument("--api", default=API_URL, help=f"API URL (default: {API_URL})")
    args = parser.parse_args()

    API_URL = args.api

    # Check server is running
    print(f"Checking server at {API_URL}...")
    try:
        r = requests.get(f"{API_URL}/api/health", timeout=5)
        if r.status_code != 200:
            print(f"Server returned {r.status_code}. Is it running?")
            sys.exit(1)
        print("Server OK!\n")
    except requests.exceptions.ConnectionError:
        print(f"Cannot connect to {API_URL}. Start the server first:")
        print(f"  python api/index.py")
        sys.exit(1)

    # Build tests
    all_tests = []
    if args.mode in (None, "grammar"):
        grammar_tests = build_grammar_tests()
        all_tests.extend(grammar_tests)
        print(f"Grammar tests: {len(grammar_tests)}")
    if args.mode in (None, "simulator"):
        sim_tests = build_simulator_tests()
        all_tests.extend(sim_tests)
        print(f"Simulator tests: {len(sim_tests)}")
    if args.mode in (None, "learning"):
        learn_tests = build_learning_tests()
        all_tests.extend(learn_tests)
        print(f"Learning tests: {len(learn_tests)}")

    print(f"\nTotal: {len(all_tests)} tests × 6 turns = {len(all_tests)*6} interactions\n")

    # Run
    results = run_tests(all_tests, verbose=args.verbose)

    # Report
    report_dir = os.path.join(PROJECT, "test_reports")
    report = generate_report(results, report_dir)

    # Exit code
    critical = report["issues_by_severity"]["CRITICAL"]
    high = report["issues_by_severity"]["HIGH"]
    if critical > 0:
        sys.exit(2)
    elif high > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
