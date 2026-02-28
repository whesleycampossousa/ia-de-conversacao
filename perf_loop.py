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

# Try to import Gemini as fallback
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

load_dotenv()

# Configuration
API_BASE_URL = "http://localhost:5000"  # Adjust as needed
TEST_SESSION_DURATION = 600  # 10 minutes in seconds
REPORT_DIR = "test_reports"

# MODELS (Optimized for 8GB VRAM - using 7B range)
# User requested qwen3:8b or qwen2.5:7b. Setting qwen3:8b as requested.
DEFAULT_LOCAL_MODEL = "qwen3:8b" 

MODEL_TESTER = DEFAULT_LOCAL_MODEL
MODEL_TARGET = DEFAULT_LOCAL_MODEL
MODEL_EVALUATOR = DEFAULT_LOCAL_MODEL

os.makedirs(REPORT_DIR, exist_ok=True)

# -------------------------------------------------------------------------
# STUDENT PROFILES
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
    "tester_hacker": {
        "name": "System Tester",
        "prompt": "You are trying to break the AI. You act like a customer but you intentionally ignore the roleplay sometimes, or ask weird meta-questions ('Are you a robot?'). You test if the AI stays in character.",
        "traits": ["provocative", "meta_questions", "breaks_role"]
    },
    "silent_shy": {
        "name": "Silent/Shy",
        "prompt": "You are very shy. You give one-word answers. You hesitate. You rely on the other person to carry the conversation.",
        "traits": ["short_answers", "hesitant", "passive"]
    }
}

class PerfectionLoop:
    def __init__(self, mode="simulator", target_backend="api"):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.mode = mode
        self.target_backend = target_backend
        
        self.report_path = os.path.join(REPORT_DIR, f"report_{target_backend}_{mode}_{self.session_id}.json")
        
        self.history = []
        self.auth_token = None
        self.user_email = "everydayconversation1991@gmail.com"
        self.password = "1234560"
        
        self.stats = {
            "unnatural_count": 0, 
            "contract_violations": 0,
            "total_turns": 0
        }

    async def get_auth_token(self):
        print(f"[*] Authenticating as {self.user_email}...")
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

    def call_ai_tester(self, turn_context):
        """
        Simulates a real human student.
        turn_context includes: 'last_ai_message', 'profile', 'mode'
        """
        profile = turn_context.get('profile')
        profile_prompt = STUDENT_PROFILES.get(profile, STUDENT_PROFILES["confused_beginner"])["prompt"]
        last_message = turn_context.get('last_ai_message')
        mode = turn_context.get('mode')
        
        memory = self._get_student_memory()
        
        system_prompt = f"""
        {profile_prompt}
        
        CURRENT MODE: {mode.upper()}
        {memory}
        
        TASK:
        Respond to the Teacher/Attendant (Last message: '{last_message}').
        If you are in SIMULATOR mode, act 100% like a customer/person in that scenario.
        If the AI breaks character (acts like a robot/teacher in simulator), react negatively (confused or annoyed).
        """

        if OLLAMA_AVAILABLE:
            try:
                # Using MODEL_TESTER for the student role
                response = ollama.chat(model=MODEL_TESTER, messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': f"The other person just replied: '{last_message}'. React naturally based on your profile and history."}
                ])
                return response['message']['content']
            except Exception as e:
                print(f"[!] Ollama Tester failed: {e}")
        
        return "I'd like a coffee please." # Fallback

    def _get_student_memory(self):
        """Returns last 3 turns for student context"""
        if not self.history:
            return "No previous history."
        
        recent = self.history[-3:]
        memory = "RECENT CONVERSATION HISTORY:\n"
        for turn in recent:
            memory += f"- AI: {turn['ai']}\n- You: {turn['student']}\n"
        return memory

    def _get_evaluator_context(self):
        """Returns last 2 turns for evaluator context"""
        if not self.history:
            return "No previous context."
        
        recent = self.history[-2:]
        ctx = "PREVIOUS TURNS:\n"
        for turn in recent:
            ctx += f"Student: {turn['student']}\nAI: {turn['ai']}\n"
        return ctx

    def _build_history_messages(self, system_prompt):
        """Builds message list from history for memory context"""
        messages = [{'role': 'system', 'content': system_prompt.strip()}]
        # Take last 6 turns to keep context window manageable but sufficient
        recent_history = self.history[-6:]
        for turn in recent_history:
            messages.append({'role': 'user', 'content': turn['student']})
            messages.append({'role': 'assistant', 'content': turn['ai']})
        return messages

    def call_target_ai_local(self, user_text: str, mode: str, context: str, lesson_lang: str) -> str:
        """
        Simulates the target AI (your product) running locally via Ollama.
        """
        if not OLLAMA_AVAILABLE:
            return "Local model unavailable."

        if mode == "simulator":
            system_prompt = f"""
            You are in REAL LIFE SIMULATOR mode.
            Scenario: {context}. You are the staff (barista/waiter).
            
            STRICTLY FORBIDDEN:
            - "Can you try", "What do you think", "How about you", "Does that make sense", "Are you ready"
            - Teaching, grammar explanations, asking to repeat, giving lesson-style feedback
            
            RULES:
            - Act like a real service worker.
            - Recast silently if user English is incorrect (no explicit corrections).
            - One question at a time. Stay on the coffee-shop flow.
            """
        else:
            system_prompt = f"""
            You are in LEARNING mode (Teacher).
            Topic: {context} (Ordering Coffee).
            
            RULES:
            - Start teaching immediately (no roleplay greeting as a barista).
            - Do NOT ask opinions ("what do you think") or "how about you" or permission ("ready?").
            - Each turn must include: a model phrase OR a short explanation OR a clear guided exercise.
            - Redirect nonsense/meta inputs back to the task.
            - Keep corrections minimal.
            """

        try:
            # Build messages with history for memory
            messages = self._build_history_messages(system_prompt)
            messages.append({"role": "user", "content": user_text})
            
            resp = ollama.chat(model=MODEL_TARGET, messages=messages)
            return resp["message"]["content"]
        except Exception as e:
            print(f"[!] Target Local Call failed: {str(e)}")
            return "Server Error."

    def extract_json_with_repair(self, text):
        """Attempts to extract and parse JSON even if it's malformed or surrounded by markdown"""
        try:
            # First try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except:
            pass
            
        # Return failure object if parsing fails completely
        return {
            "is_natural": False, 
            "contract_violation": True, 
            "violation_reason": "Evaluator output invalid (JSON Parse Error)", 
            "score": 0, 
            "improvement_suggestion": "Check evaluator prompts"
        }

    def evaluate_naturalness(self, turn_info):
        """
        Analyzes if the IA response was natural AND followed the strict contract.
        """
        ai_response = turn_info.get("ai_response", "")
        mode = turn_info.get("mode", "learning") # 'learning' or 'simulator'
        user_input = turn_info.get("user_input", "")
        
        # DEFINING THE CONTRACT RULES
        if mode == 'simulator':
            contract_instructions = """
            MODE: REAL_LIFE_SIMULATOR (CRITICAL)
            The AI MUST be a Roleplayer (Barista, Waiter, etc).
            
            STRICT VIOLATIONS (FAIL REASONS):
            - Acting like a teacher ("Good job", "Try again", "Say this").
            - Explicit corrections ("You said X, but it's Y").
            - Asking specifically "How about you?".
            - Asking specifically "What do you think?".
            - Asking specifically "Does that make sense?".
            - Asking specifically "Can you try?".
            - Asking specifically "Are you ready?".
            - Asking to repeat.
            - Explaining the grammar or language.
            - Behaving like an assistant ("How can I assist you with English?").
            """
        else: # Learning mode
            contract_instructions = """
            MODE: LEARNING / TEACHER
            The AI MUST be a Teacher.
            
            STRICT VIOLATIONS (FAIL REASONS):
            - Starting as roleplay/simulation instead of teaching ("Welcome to The Daily Grind...").
            - Asking for opinion / used "What do you think?".
            - Used "How about you?".
            - Asking permission ("Ready?", "Shall we?") instead of teaching directly.
            - Ignoring a student's question.
            - Being rude or too brief when explanation is needed.
            - Failing to correct obvious errors (if requested).
            """

        context_text = self._get_evaluator_context()

        evaluation_prompt = f"""
        Act as a STRICT Quality Assurance Judge for a Conversational AI.
        
        {contract_instructions}
        
        CONTEXT (PREVIOUS TURNS):
        {context_text}
        
        CURRENT INTERACTION:
        Student said: "{user_input}"
        AI responded: "{ai_response}"
        
        EVALUATE:
        1. Did the AI violate any STRICT VIOLATIONS listed above?
        2. Is the response natural for the context?
        
        RETURN ONLY JSON (No markdown):
        {{
            "is_natural": true/false,
            "contract_violation": true/false,
            "violation_reason": "Exact rule broken (or null)",
            "score": 0-10,
            "improvement_suggestion": "Correction"
        }}
        """
        
        if OLLAMA_AVAILABLE:
            try:
                response = ollama.chat(model=MODEL_EVALUATOR, messages=[{'role': 'user', 'content': evaluation_prompt}])
                result = self.extract_json_with_repair(response['message']['content'])
                return result
            except Exception as e:
                print(f"[!] Evaluation failed: {e}")

        return {"is_natural": True, "contract_violation": False, "score": 8, "improvement_suggestion": "N/A"}

    async def run_session(self):
        # We only need auth token if we are hitting the real API
        if self.target_backend == 'api':
            if not await self.get_auth_token():
                return

        print(f"[*] Starting Perfection Loop")
        print(f"[*] Mode: {self.mode.upper()}")
        print(f"[*] Target: {self.target_backend.upper()}")
        print(f"[*] Models: {MODEL_TESTER} (Tester/Evaluator/Target)")
        print(f"[*] Duration: {TEST_SESSION_DURATION}s")
        
        start_time = time.time()
        
        # 1. FIXED SEED BY MODE (User Requirement: Human-like seeds)
        if self.mode == 'learning':
            last_ai_message = "Hi there! Today we're going to learn 3 ways to order coffee: basic order, size, and type."
        else:
            # Corrected natural seed for simulator
            last_ai_message = "Good morning! Welcome to The Daily Grind. What can I get started for you today?"
        
        # Pick a random profile for this session
        current_profile_key = random.choice(list(STUDENT_PROFILES.keys()))
        current_profile = STUDENT_PROFILES[current_profile_key]
        print(f"[*] SELECTED STUDENT PROFILE: {current_profile['name']}")
        
        while time.time() - start_time < TEST_SESSION_DURATION:
            # 1. Tester AI generates input
            tester_input = self.call_ai_tester({
                "last_ai_message": last_ai_message,
                "profile": current_profile_key,
                "mode": self.mode
            })
            print(f"\n[Student ({current_profile['name']})]: {tester_input}")

            # 2. Call Target (API or Local)
            if self.target_backend == 'api':
                # --- API CALL ---
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/api/chat",
                        headers={"Authorization": f"Bearer {self.auth_token}"},
                        json={
                            "text": tester_input, 
                            "context": "coffee_shop", 
                            "practiceMode": self.mode, 
                            "lessonLang": "en"
                        }
                    )
                    
                    if response.status_code == 200:
                        ai_data = response.json()
                        # Robust Parsing
                        last_ai_message = ""
                        if isinstance(ai_data, dict):
                            if "text" in ai_data: last_ai_message = ai_data["text"]
                            elif "en" in ai_data: last_ai_message = ai_data["en"]
                            elif "pt" in ai_data: last_ai_message = ai_data["pt"]
                            else: last_ai_message = json.dumps(ai_data)
                        else:
                            last_ai_message = str(ai_data)
                    else:
                        print(f"[!] API Error: {response.status_code}")
                        break
                except Exception as e:
                    print(f"[!] Error calling API: {e}")
                    break
            else:
                # --- LOCAL CALL (OLLAMA) ---
                last_ai_message = self.call_target_ai_local(
                    user_text=tester_input,
                    mode=self.mode,
                    context="coffee_shop",
                    lesson_lang="en"
                )

            print(f"[AI ({self.mode}/{self.target_backend})]: {last_ai_message}")

            # 3. Evaluate Naturalness & Contract (Using Local Evaluator)
            eval_result = self.evaluate_naturalness({
                "user_input": tester_input, 
                "ai_response": last_ai_message,
                "mode": self.mode
            })
            
            turn_data = {
                "timestamp": datetime.now().isoformat(),
                "mode": self.mode,
                "target": self.target_backend,
                "profile": current_profile['name'],
                "student": tester_input,
                "ai": last_ai_message,
                "evaluation": eval_result
            }
            
            self.history.append(turn_data)
            self.stats["total_turns"] += 1
            
            if eval_result.get("contract_violation"):
                self.stats["contract_violations"] += 1
                print(f"❌ CONTRACT VIOLATION: {eval_result.get('violation_reason')}")
            elif not eval_result.get("is_natural"):
                self.stats["unnatural_count"] += 1
                reason = eval_result.get('violation_reason') or eval_result.get('reason') or "No specific reason given"
                print(f"⚠️ Unnatural: {reason}")

            await asyncio.sleep(2)

        self.save_report()

    def save_report(self):
        report = {
            "session_id": self.session_id,
            "mode": self.mode,
            "target": self.target_backend,
            "duration": TEST_SESSION_DURATION,
            "stats": self.stats,
            "history": self.history
        }
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
        print(f"\n[DONE] Session finished. Report saved to {self.report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run Conversational AI Perfection Loop')
    parser.add_argument('--mode', choices=['simulator', 'learning'], default='simulator', help='Mode to test: simulator or learning')
    parser.add_argument('--target', choices=['api', 'ollama'], default='api', help='Target backend: api (Flask) or ollama (local)')
    args = parser.parse_args()
    
    loop = PerfectionLoop(mode=args.mode, target_backend=args.target)
    asyncio.run(loop.run_session())
