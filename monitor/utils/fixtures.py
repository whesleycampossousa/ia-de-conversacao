"""
Test data fixtures (phrases, scenarios, expected responses)
"""

# Common test phrases for different scenarios
TEST_PHRASES = {
    "greetings": [
        "Hello, how are you?",
        "Good morning!",
        "Hi there!",
    ],
    "coffee_shop": [
        "I'd like a cappuccino, please.",
        "Can I have a latte with almond milk?",
        "Do you have any pastries?",
        "How much is that?",
        "I'll pay by card.",
    ],
    "airport": [
        "Where is gate B12?",
        "Is this flight delayed?",
        "I need to check in.",
        "Can I see your passport?",
        "Do I need to remove my shoes?",
    ],
    "restaurant": [
        "Can I see the menu?",
        "I'd like to make a reservation.",
        "What do you recommend?",
        "I'm allergic to nuts.",
        "The check, please.",
    ],
    "job_interview": [
        "Tell me about yourself.",
        "Why do you want to work here?",
        "What are your strengths?",
        "Do you have any questions for us?",
        "When can you start?",
    ],
    "hotel": [
        "I have a reservation.",
        "I'd like to check in.",
        "Is breakfast included?",
        "Can I have a wake-up call?",
        "What time is checkout?",
    ],
    "doctor": [
        "I'm not feeling well.",
        "I have a headache.",
        "How long have you had this pain?",
        "Take this medicine twice a day.",
        "Come back in a week.",
    ],
}

# Phrases with intentional errors for testing corrections
TEST_PHRASES_WITH_ERRORS = {
    "grammar": [
        "I goes to the store yesterday.",  # Wrong tense
        "She don't like coffee.",  # Subject-verb agreement
        "I am here since morning.",  # Wrong tense (should be "have been")
        "He can speaks English.",  # Incorrect modal usage
        "They was very happy.",  # Subject-verb agreement
    ],
    "vocabulary": [
        "I want to do a photo.",  # Should be "take"
        "The weather is very hot cold.",  # Contradictory
        "I have 25 years old.",  # Should be "I am"
        "I will make a party.",  # Should be "throw/host"
    ],
}

# Common scenarios to test
SCENARIOS = [
    "coffee_shop",
    "airport",
    "restaurant",
    "job_interview",
    "hotel",
    "doctor",
    "bank",
    "supermarket",
    "gym",
    "pharmacy",
]

# Grammar topics
GRAMMAR_TOPICS = [
    "verb_to_be",
    "articles",
    "present_simple",
    "past_simple",
    "present_perfect",
    "future_simple",
    "present_continuous",
    "past_continuous",
    "conditionals_zero_first",
    "conditionals_second",
    "modal_verbs",
    "passive_voice",
    "reported_speech",
    "relative_clauses",
    "phrasal_verbs",
    "comparatives_superlatives",
    "quantifiers",
    "prepositions",
]

# Practice sentences for each grammar topic
GRAMMAR_PRACTICE = {
    "verb_to_be": [
        ("I am a student.", True),
        ("She is happy.", True),
        ("They is tired.", False),  # Error
        ("We are from Brazil.", True),
    ],
    "present_simple": [
        ("I work every day.", True),
        ("She goes to school.", True),
        ("He don't like pizza.", False),  # Error
        ("They plays football.", False),  # Error
    ],
    "past_simple": [
        ("I went to the park yesterday.", True),
        ("She eated lunch.", False),  # Error (ate)
        ("We saw a movie.", True),
        ("He go to work yesterday.", False),  # Error
    ],
    "present_perfect": [
        ("I have lived here for 5 years.", True),
        ("She has ate already.", False),  # Error (eaten)
        ("They have been to Paris.", True),
        ("I have saw that movie.", False),  # Error (seen)
    ],
}

# Expected response patterns for validation
EXPECTED_PATTERNS = {
    "greeting_response": {
        "should_contain": ["hi", "hello", "how are you", "good"],
        "should_not_contain": ["error", "failed", "broken"],
    },
    "correction_response": {
        "should_contain": ["correct", "try", "should", "better"],
        "should_not_contain": [],
        "must_have_fields": ["corrections", "feedback"],
    },
    "simulator_response": {
        "max_words": 40,
        "should_end_with": "?",
        "should_not_contain": [
            "can you try",
            "please repeat",
            "that's correct",
        ],
    },
    "learning_response": {
        "max_words": 100,
        "should_contain_one_of": ["?", ".", "!"],
        "may_contain": ["remember", "practice", "good"],
    },
}

# API endpoint test data
ENDPOINT_TEST_DATA = {
    "/api/health": {
        "method": "GET",
        "expected_status": 200,
        "required_fields": ["status"],
    },
    "/api/scenarios": {
        "method": "GET",
        "expected_status": 200,
        "expected_type": "array",
        "required_item_fields": ["id", "title"],
    },
    "/api/grammar-topics": {
        "method": "GET",
        "expected_status": 200,
        "expected_type": "array",
        "required_item_fields": ["id", "title"],
    },
    "/api/chat": {
        "method": "POST",
        "expected_status": [200, 429],
        "known_policy_429": True,
        "required_fields": ["text"],
        "payload": {
            "text": "Hello, how are you?",
            "context": "coffee_shop",
            "practiceMode": "learning",
            "lessonLang": "en",
        },
    },
    "/api/free-conversation": {
        "method": "POST",
        "expected_status": [200, 429],
        "known_policy_429": True,
        "required_fields": ["text"],
        "payload": {
            "action": "followup",
            "main_question": "What do you do on weekends?",
            "student_answer": "I play football with friends.",
        },
    },
    "/api/tts": {
        "method": "POST",
        "expected_status": 200,
        "expected_binary": True,
        "content_type_prefix": "audio/",
        "payload": {
            "text": "Hello, how are you?",
            "speed": 1.0,
            "lessonLang": "en",
        },
    },
    "/api/report": {
        "method": "POST",
        "expected_status": 200,
        "required_any_fields": [["report"], ["feedback"]],
        "timeout": 45,
        "payload": {
            "conversation": [
                {"sender": "Student", "text": "Hello"},
                {"sender": "Teacher", "text": "Hi! How are you?"},
            ],
            "context": "coffee_shop",
        },
    },
}

# User profiles for E2E testing
USER_PROFILES = {
    "beginner": {
        "level": "beginner",
        "phrases": [
            "Hello.",
            "I want coffee.",
            "How much?",
            "Thank you.",
        ],
        "expected_help": True,
    },
    "intermediate": {
        "level": "intermediate",
        "phrases": [
            "Good morning! I'd like a cappuccino, please.",
            "Do you have any sugar-free options?",
            "I'll take that one, thanks.",
            "Can I pay by card?",
        ],
        "expected_help": False,
    },
    "advanced": {
        "level": "advanced",
        "phrases": [
            "Good morning! I was wondering if you could recommend something from your seasonal menu.",
            "I'm quite particular about my coffee - could you make it with oat milk and an extra shot?",
            "Actually, I'd also like to inquire about your loyalty program.",
        ],
        "expected_help": False,
    },
}

def get_test_phrase(scenario: str, index: int = 0) -> str:
    """Get a test phrase for a specific scenario"""
    phrases = TEST_PHRASES.get(scenario, ["Hello, how are you?"])
    return phrases[index % len(phrases)]

def get_error_phrase(error_type: str = "grammar", index: int = 0) -> str:
    """Get a phrase with intentional errors"""
    phrases = TEST_PHRASES_WITH_ERRORS.get(error_type, ["I goes to store."])
    return phrases[index % len(phrases)]

def get_grammar_practice(topic: str) -> list:
    """Get practice sentences for a grammar topic"""
    return GRAMMAR_PRACTICE.get(topic, [("I am here.", True)])
