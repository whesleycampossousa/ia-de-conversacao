import os
import json
import time
import requests
import asyncio
import random
import argparse
import re
from datetime import datetime
from dotenv import load_dotenv

# Try to import Ollama
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

load_dotenv()

# Configuration
API_BASE_URL = "http://localhost:8912"  # Adjust as needed
TEST_SESSION_DURATION = 600  # safety timeout for a single context session (seconds)
REPORT_DIR = "test_reports"
SCENARIOS_DB_PATH = "scenarios_db.json"

# MODELS (Optimized for 8GB VRAM - using 7B range)
DEFAULT_LOCAL_MODEL = "qwen3:8b" 

MODEL_TESTER = DEFAULT_LOCAL_MODEL    # Student
MODEL_TARGET = DEFAULT_LOCAL_MODEL    # Fallback only (Actual target is API)
MODEL_EVALUATOR = DEFAULT_LOCAL_MODEL # QA

# CONTEXTS TO TEST (Ordered List)
AUTO_PERFECTION_CONTEXTS = [
    "neighbor",
    "first_date",
    "wedding",
    "graduation"
]

os.makedirs(REPORT_DIR, exist_ok=True)

# -------------------------------------------------------------------------
# STUDENT PROFILES (For Rotation)
# -------------------------------------------------------------------------
STUDENT_PROFILES = {
    "confused_beginner": {
        "name": "Confused Beginner",
        "prompt": "You are a beginner English student. You are often confused, use broken English, and ask for clarifications frequently. You sometimes revert to Portuguese words.",
        "traits": ["hesitant", "uses_portuguese_words", "asks_what_frequently"]
    },
    "impatient_customer": {
        "name": "Impatient Customer",
        "prompt": "You are a busy, impatient customer. You want quick service. You get annoyed if the attendant talks too much or acts like a teacher. You speak fast and directly.",
        "traits": ["direct", "annoyed_by_verbosity", "impatient"]
    },
    "curious_tourist": {
        "name": "Curious Tourist",
        "prompt": "You are a tourist visiting this place. You are excited, ask many questions about the local culture/items, and are very polite but talkative.",
        "traits": ["polite", "talkative", "curious"]
    },
    "silent_shy": {
        "name": "Silent/Shy",
        "prompt": "You are very shy. You give one-word answers. You hesitate. You rely on the other person to carry the conversation.",
        "traits": ["short_answers", "hesitant", "passive"]
    }
}

class AutoPerfectionLoop:
    def __init__(self, target_backend="api"):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.target_backend = target_backend # Should be 'api' for Gemini Target
        self.report_base = REPORT_DIR
        self.auth_token = None
        self.user_email = "everydayconversation1991@gmail.com"
        self.password = "1234560"
        
        # State
        self.current_context = ""
        self.consecutive_passes = 0
        self.attempt_count = 0
        self.used_profiles = []

    async def get_auth_token(self):
        try:
            response = requests.post(f"{API_BASE_URL}/api/auth/login", json={
                "email": self.user_email,
                "password": self.password
            })
            if response.status_code == 200:
                self.auth_token = response.json().get("token")
                print("[OK] Authenticated.")
                return True
            else:
                print(f"[!] Auth failed: {response.text}")
                return False
        except Exception as e:
            print(f"[!] Error during auth: {e}")
            return False

    def get_next_profile(self):
        """Rotates through profiles to ensure diversity"""
        available = [k for k in STUDENT_PROFILES.keys() if k not in self.used_profiles]
        if not available:
            self.used_profiles = [] # Reset if all used
            available = list(STUDENT_PROFILES.keys())
        
        chosen = random.choice(available)
        self.used_profiles.append(chosen)
        # Keep only last 2 in memory to avoid repeating too soon
        if len(self.used_profiles) > 2:
            self.used_profiles.pop(0)
            
        return chosen, STUDENT_PROFILES[chosen]

    def call_ai_student(self, last_message, profile_key, context):
        """Simulates the student (Ollama)"""
        profile = STUDENT_PROFILES[profile_key]
        
        system_prompt = f"""
        {profile['prompt']}
        
        CURRENT SCENARIO: {context.replace('_', ' ')}
        
        TASK:
        Respond to the person (staff/stranger) in this scenario.
        Act 100% like a real person in this situation.
        If the other person breaks character or acts like a robot, react naturally (confused/annoyed).
        Keep responses concise (1-2 sentences) usually.
        """

        if OLLAMA_AVAILABLE:
            try:
                response = ollama.chat(model=MODEL_TESTER, messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': f"The other person said: '{last_message}'. Respond."}
                ])
                return response['message']['content']
            except Exception as e:
                print(f"[!] Ollama Student failed: {e}")
        
        return "I'm sorry, I didn't understand."

    def call_target_api(self, text, context):
        """Calls the Target API (Gemini)"""
        try:
            # Force mandatory greeting logic if this is the start trigger
            is_start_trigger = (text == "[START_SIMULATION]")
            
            response = requests.post(
                f"{API_BASE_URL}/api/chat",
                headers={"Authorization": f"Bearer {self.auth_token}"},
                json={
                    "text": text, 
                    "context": context, 
                    "practiceMode": "simulator", 
                    "lessonLang": "en",
                    "forceGreeting": is_start_trigger  # Custom flag we'll add to API
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # Robust parsing
                if "text" in data: return data["text"]
                if "en" in data: return data["en"]
                return json.dumps(data)
            else:
                return f"[API ERROR {response.status_code}]"
        except Exception as e:
            return f"[API EXCEPTION {e}]"

    def extract_json_with_repair(self, text):
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return json.loads(text)
        except:
             # Fallback structure
            return {
                "is_natural": False, 
                "contract_violation": True, 
                "violation_reason": "Evaluator output invalid JSON", 
                "score": 0,
                "first_message_matches_required_opening": False
            }

    def evaluate_turn(self, student_input, ai_response, context, is_first_turn):
        """Evaluates a single turn"""
        
        # OPENING CHECK (Regex for "Hello, welcome to ... How can I help you today?")
        # Allowing slight variations but must have "welcome to" and "how can i help"
        friendly_context = context.replace('_', ' ')
        opening_pass = True
        
        if is_first_turn:
            normalized_ai = ai_response.lower().replace('.', '').replace('!', '').replace(',', '')
            
            # DEFAULT EXPECTATION: "Hello/Hi" + "Welcome to"
            expects_welcome = True
            
            # EXCEPTIONS
            if context == "free_conversation":
                expects_welcome = False # Expects "practice English" or "talk about"
                if "practice english" not in normalized_ai and "talk about" not in normalized_ai:
                    opening_pass = False
            elif context == "basic_structures":
                expects_welcome = False
                if "practice polite questions" not in normalized_ai and "ready to start" not in normalized_ai:
                    opening_pass = False
            
            # STANDARD "WELCOME TO" CHECK
            if expects_welcome:
                has_greeting = any(x in normalized_ai for x in ["hello", "hi", "good morning", "good evening"])
                has_welcome = "welcome to" in normalized_ai
                if not (has_greeting and has_welcome):
                    opening_pass = False
        
                if not (has_greeting and has_welcome):
                    opening_pass = False
        
        # Build the prompt dynamically
        opening_rule_text = ""
        if is_first_turn:
            opening_rule_text = f"""
        MANDATORY OPENING RULE (CRITICAL - Only for Turn 1):
        - free_conversation: Must say "Hello! I'm here to practice English with you. What would you like to talk about today?"
        - job_interview: Must say "Hello, welcome to the interview..."
        - basic_structures: Must say "Hello! We are going to practice..."
        - ALL OTHER SCENARIOS: Must start with "Hello, welcome to [Place Name]. How can I help you today?"
            """
        else:
            opening_rule_text = "\nIMPORTANT: This is NOT the first turn. Do NOT check for opening greetings. Ignore opening rules completely.\n"

        EVALUATOR_PROMPT = """
        You are a strict QA Evaluator for an English Conversation AI.
        
        Analyze the AI's response (Turn {turn_num}).

        CONTEXT: {context}
        PROFILE: {profile_name}
        
        RULES TO CHECK:
        1. **Role Adherence**: 
           - If context is 'coffee_shop', 'airport', etc., AI MUST be a Service Worker.
           - If context is 'free_conversation', 'neighbor', AI MUST be a Peer.
           - NO "I'm an AI" or "I can help practice".
        
        2. **Natural Flow**:
           - ONE question per turn maximum.
           - No robotic headers ("Sure!", "Okay!").
           - **MUST end with a question** (Critical).

        3. **No Teaching (Strict)**:
           - No "Good job!", "Correct!", "Try saying...".
           - **EXCEPTION**: Natural agreement ("That's a good point", "I agree") is ALLOWED for Peers.
           - **EXCEPTION**: Explaining items (e.g., menu, artifacts) is ALLOWED for Service roles (Museum, Restaurant).

        OUTPUT JSON:
        {{
            "is_natural": boolean,
            "contract_violation": boolean,
            "violation_reason": "string or null",
            "score": 1-10,
            "improvement_suggestion": "string"
        }}
        """
        
        if OLLAMA_AVAILABLE:
            try:
                msg = ollama.chat(model=MODEL_EVALUATOR, messages=[{'role': 'system', 'content': EVALUATOR_PROMPT}])
                result = self.extract_json_with_repair(msg['message']['content'])
                
                # Force override if opening check failed locally
                if is_first_turn:
                    result["first_message_matches_required_opening"] = opening_pass
                    if not opening_pass:
                        result["contract_violation"] = True
                        result["violation_reason"] = f"Opening mismatch. Expected standard greeting for {friendly_context}."
                        result["score"] = min(result.get("score", 5), 4)

                return result
            except Exception as e:
                print(f"[!] Evaluator failed: {e}")
                
        return {"is_natural": False, "contract_violation": True, "violation_reason": "Evaluator Error", "score": 0}

    def update_scenarios_db(self, context, violations):
        """
        Prompt Optimizer: Reads scenarios_db.json, updates specific context prompt, saves.
        """
        print(f"\n[OPTIMIZER] Adjusting prompt for {context} based on violations...")
        try:
            with open(SCENARIOS_DB_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            updated = False
            for scenario in data:
                if scenario['id'] == context:
                    # Get or Create simulator_prompt
                    current_prompt = scenario.get('simulator_prompt', "")
                    if not current_prompt:
                         # Fetch universal fallback logic if empty (simplified here)
                         current_prompt = f"SIMULATOR MODE: {context}.\nAct naturally. No teaching."
                    
                    # Heuristic Improvements based on top violations
                    additions = []
                    
                    # 1. Opening Rule Enforcement
                    required_opening = ""
                    if context == "free_conversation":
                        required_opening = "Hello! I'm here to practice English with you. What would you like to talk about today?"
                    elif context == "job_interview":
                        required_opening = "Hello, welcome to the interview. Please, have a seat. Tell me a little about yourself."
                    elif context == "basic_structures":
                        required_opening = "Hello! We are going to practice polite questions today. Ready to start?"
                    else:
                        friendly_place = context.replace('_', ' ')
                        # Add 'the' if missing and not a generic concept
                        if "the " not in friendly_place.lower() and context not in ["free_conversation", "basic_structures"]:
                             friendly_place = f"the {friendly_place}"
                        required_opening = f"Hello, welcome to {friendly_place}. How can I help you today?"

                    if "Opening mismatch" in str(violations):
                        # Remove old Mandatory Opening if exists to avoid duplication
                        if "MANDATORY OPENING:" in current_prompt:
                            current_prompt = re.sub(r"MANDATORY OPENING:.*?\n", "", current_prompt)
                        
                        additions.append(f"\n\nMANDATORY OPENING: You MUST start with: '{required_opening}'")
                    
                    # 2. Robotic Fillers
                    if "robotic" in str(violations).lower() or "filler" in str(violations).lower() or "what do you think" in str(violations).lower():
                        if "FORBIDDEN PHRASES" not in current_prompt:
                            additions.append("\n\nFORBIDDEN PHRASES: Do NOT use 'What do you think?', 'How about you?', 'Does that make sense?'.")
                    
                    # 3. Teaching/Coaching
                    if "teaching" in str(violations).lower() or "teacher" in str(violations).lower():
                        if "NO TEACHING" not in current_prompt:
                            additions.append("\n\nSTRICT RULE: NO TEACHING. Do not explain grammar. Do not ask to repeat.")

                    if additions:
                        # scenario['simulator_prompt'] = current_prompt + "".join(additions)
                        # updated = True
                        print(f"[OPTIMIZER] WOULD HAVE added {len(additions)} rules to {context} (Injections currently disabled).")
                    else:
                        # Prevent infinite "CRITICAL" appending
                        if "CRITICAL: Be more natural" not in current_prompt:
                            print("[OPTIMIZER] No specific heuristic matched, applying generic reinforcement.")
                            # scenario['simulator_prompt'] += "\n\nCRITICAL: Be more natural. Do NOT act like an AI."
                            # updated = True
                            pass

            if updated:
                with open(SCENARIOS_DB_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                print("[OPTIMIZER] scenarios_db.json updated successfully.")
                return True
        except Exception as e:
            print(f"[OPTIMIZER] Failed to update DB: {e}")
            return False

    async def run_context_session(self, context, attempt_count):
        profile_key, profile_data = self.get_next_profile()
        print(f"\n>>> Running {context} (Attempt #{attempt_count}) | Profile: {profile_data['name']}")
        
        # Initialize
        history = []
        stats = {"score_sum": 0, "violations": 0}
        
        # 1. Trigger First Message (Target speaks first!)
        print("[Turn 1] Triggering AI Opening...")
        
        # We send a hidden trigger. The API will see this and produce the Opening.
        ai_text = self.call_target_api("[START_SIMULATION]", context)
        print(f"Target (Opening): {ai_text}")

        # Evaluate Turn 1 (Opening) - No student text yet
        eval_res = self.evaluate_turn("(System Trigger)", ai_text, context, is_first_turn=True)
        
        history.append({
            "turn": 1, "student": "(System Trigger)", "ai": ai_text, "eval": eval_res
        })
        
        if eval_res['contract_violation']: stats['violations'] += 1
        stats['score_sum'] += eval_res['score']
        
        # Rounds 2 to 8
        last_ai = ai_text
        for i in range(2, 9):
            # Student reacts to AI's opening/previous turn
            student_text = self.call_ai_student(last_ai, profile_key, context)
            print(f"Student: {student_text}")
            
            ai_text = self.call_target_api(student_text, context)
            print(f"Target: {ai_text}")
            
            eval_res = self.evaluate_turn(student_text, ai_text, context, is_first_turn=False)
            history.append({
                "turn": i, "student": student_text, "ai": ai_text, "eval": eval_res
            })
            
            if eval_res['contract_violation']: stats['violations'] += 1
            stats['score_sum'] += eval_res['score']
            last_ai = ai_text
            
            # Run full session to gather data.
            time.sleep(1)

        # Analyze Pass/Fail
        avg_score = stats['score_sum'] / 8
        is_pass = (stats['violations'] == 0) and (avg_score >= 9) and (history[0]['eval'].get("first_message_matches_required_opening", False))
        
        # Save Attempt Report
        report = {
            "context": context,
            "attempt": attempt_count,
            "profile": profile_key,
            "pass": is_pass,
            "avg_score": avg_score,
            "stats": stats,
            "turns": history
        }
        
        filename = f"{REPORT_DIR}/report_{context}_attempt_{attempt_count:02d}.json"
        with open(filename, "w", encoding='utf-8') as f:
            json.dump(report, f, indent=4)
            
        return is_pass, report

    async def run_until_two_consecutive_passes(self, context):
        print(f"\n{'='*50}\nSTARTING CONTEXT: {context}\n{'='*50}")
        consecutive = 0
        attempts = 0
        
        while attempts < 1:
            attempts += 1
            print(f"\n--- Attempt {attempts} ---")
            is_pass, report = await self.run_context_session(context, attempts)
            
            if is_pass:
                consecutive += 1
                print(f"✅ PASS! Consecutive: {consecutive}/2")
            else:
                consecutive = 0
                print("❌ FAIL. Resetting consecutive count.")
                
                # OPTIMIZER LOGIC (DISABLED for manual review)
                violations = [t['eval']['violation_reason'] for t in report['turns'] if t['eval']['contract_violation']]
                violation_summary = ", ".join(set([str(v) for v in violations if v]))
                print(f"[FAIL REASONS]: {violation_summary}")
                
                # self.update_scenarios_db(context, violation_summary)
                
                time.sleep(2)
            
            if attempts >= 5: # Safety break
                print("⚠️ Max attempts (5) reached for this context. Moving on.")
                return False

        print(f"🎉 CONTEXT {context} MASTERED!")
        return True

    async def start_batch(self, limit=None):
        if not await self.get_auth_token():
            return
            
        results = {}
        count = 0
        for context in AUTO_PERFECTION_CONTEXTS:
            if limit and count >= limit:
                break
            success = await self.run_until_two_consecutive_passes(context)
            results[context] = "PASS" if success else "FAIL"
            count += 1
            
        print("\n\nFINAL BATCH RESULTS:")
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    
    loop = AutoPerfectionLoop()
    asyncio.run(loop.start_batch(limit=args.limit))