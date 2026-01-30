import os
import io
import json
import re
from difflib import SequenceMatcher
try:
    import jwt
    JWT_AVAILABLE = True
except Exception as e:
    JWT_AVAILABLE = False
    JWT_ERROR = str(e)
    # Dummy jwt
    class jwt:
        def encode(self, *args, **kwargs): return "dummy_token"
        def decode(self, *args, **kwargs): return {"user_id": "dummy", "email": "dummy", "is_admin": False}
        class ExpiredSignatureError(Exception): pass
        class InvalidTokenError(Exception): pass

from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_file, send_from_directory, session

# Safe Imports Pattern
# This prevents the entire app from crashing if a dependency is missing/failed on Vercel
app = Flask(__name__, static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), static_url_path='/')

# 1. CORS
try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except Exception as e:
    CORS_AVAILABLE = False
    CORS_ERROR = str(e)
    # Dummy CORS to prevent crash
    def CORS(*args, **kwargs): pass

# 2. Limiter
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except Exception as e:
    LIMITER_AVAILABLE = False
    LIMITER_ERROR = str(e)
    # Dummy Limiter
    class Limiter:
        def __init__(self, *args, **kwargs): pass
        def limit(self, *args, **kwargs):
            def decorator(f): return f
            return decorator
    def get_remote_address(): return "127.0.0.1"

# 3. Google GenAI
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except Exception as e:
    GENAI_AVAILABLE = False
    GENAI_ERROR = str(e)

# 4. TextToSpeech
try:
    from google.cloud import texttospeech
    TEXTTOSPEECH_AVAILABLE = True
except Exception as e:
    TEXTTOSPEECH_AVAILABLE = False
    TEXTTOSPEECH_ERROR = str(e)

# 4.5. Google Cloud Speech-to-Text
try:
    from google.cloud import speech
    from google.oauth2 import service_account
    SPEECH_AVAILABLE = True
except Exception as e:
    SPEECH_AVAILABLE = False
    SPEECH_ERROR = str(e)

# 5. ReportLab
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except Exception as e:
    REPORTLAB_AVAILABLE = False
    REPORTLAB_ERROR = str(e)

# 6. Requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception as e:
    REQUESTS_AVAILABLE = False
    REQUESTS_ERROR = str(e)

# 7. Base64 for TTS REST API
import base64
import hashlib

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except Exception as e:
    DOTENV_AVAILABLE = False
    DOTENV_ERROR = str(e)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Cache directories (use /tmp on Vercel to avoid read-only filesystem issues)
CACHE_ROOT = os.environ.get('CACHE_DIR')
if not CACHE_ROOT:
    CACHE_ROOT = '/tmp' if os.environ.get('VERCEL') else BASE_DIR

def _build_cache_dirs(root):
    audio_dir = os.path.join(root, 'audio_cache')
    return audio_dir, os.path.join(audio_dir, 'common_phrases'), os.path.join(audio_dir, 'dynamic')

AUDIO_CACHE_DIR, COMMON_PHRASES_DIR, DYNAMIC_CACHE_DIR = _build_cache_dirs(CACHE_ROOT)

# Create cache directories (fallback to /tmp if needed)
try:
    for cache_dir in [AUDIO_CACHE_DIR, COMMON_PHRASES_DIR, DYNAMIC_CACHE_DIR]:
        os.makedirs(cache_dir, exist_ok=True)
except Exception as e:
    if CACHE_ROOT != '/tmp':
        CACHE_ROOT = '/tmp'
        AUDIO_CACHE_DIR, COMMON_PHRASES_DIR, DYNAMIC_CACHE_DIR = _build_cache_dirs(CACHE_ROOT)
        for cache_dir in [AUDIO_CACHE_DIR, COMMON_PHRASES_DIR, DYNAMIC_CACHE_DIR]:
            os.makedirs(cache_dir, exist_ok=True)
    else:
        print(f"[WARNING] Failed to create cache directories: {e}")

# Security Configuration
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-change-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Init CORS
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '')
# Handle empty or malformed ALLOWED_ORIGINS
if ALLOWED_ORIGINS and ALLOWED_ORIGINS.strip():
    origins_list = [o.strip() for o in ALLOWED_ORIGINS.split(',') if o.strip()]
else:
    # If no specific origins, allow all (for Vercel)
    origins_list = '*'

if CORS_AVAILABLE:
    try:
        CORS(app, origins=origins_list, supports_credentials=True)
        print(f"[OK] CORS initialized with origins: {origins_list}")
    except Exception as e:
        print(f"[WARNING] CORS init failed: {e}")
        # Fallback to wildcard if specific origins fail
        try:
            CORS(app, origins='*', supports_credentials=False)
            print("[OK] CORS initialized with wildcard fallback")
        except:
            pass

# Init Limiter
try:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[f"{os.environ.get('RATE_LIMIT_REQUESTS', 30)} per {os.environ.get('RATE_LIMIT_WINDOW', 60)} seconds"],
        storage_uri="memory://"
    )
except Exception as e:
    print(f"Limiter Init Error: {e}")
    # Fallback to dummy
    class LimiterDummy:
        def __init__(self, *args, **kwargs): pass
        def limit(self, *args, **kwargs):
            def decorator(f): return f
            return decorator
    limiter = LimiterDummy()

# Configure Gemini with Caching Support
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
DEFAULT_GEN_CONFIG = {"temperature": 0.8}
model = None
cached_models = {}  # Store cached models by context

if GOOGLE_API_KEY and GENAI_AVAILABLE:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        # Fallback basic model (no cache)
        model = genai.GenerativeModel(
            'gemini-3-flash-preview',
            generation_config=DEFAULT_GEN_CONFIG
        )
        print("[OK] Gemini model initialized successfully")
        print("[OK] Prompt caching enabled - will cache system prompts per context")
    except Exception as e:
        print(f"Gemini Init Error: {e}")
elif not GENAI_AVAILABLE:
    print(f"WARNING: Google GenAI not available: {globals().get('GENAI_ERROR')}")
else:
    print("WARNING: GOOGLE_API_KEY not set!")

# Configure Groq Whisper for speech-to-text
# Configure Groq Whisper for speech-to-text
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Configure Deepgram Nova-2 (Cheaper & Fast)
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen?model=nova-2-general&smart_format=true&language=pt-BR"

if DEEPGRAM_API_KEY:
    print("[OK] Deepgram API key configured (Nova-2)")
elif GROQ_API_KEY:
    print("[OK] Groq API key configured (Whisper)")
else:
    print("[WARNING] No Transcription API key set (Deepgram/Groq) - transcription will not be available")

# Session storage (in production, use Redis or database)
user_sessions = {}
user_conversations = {}  # Store conversations per user
user_daily_usage = {}  # Track daily usage per email: {email: {date: str, seconds_used: int, session_start: timestamp}}

# Authentication decorator
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        allow_guest = os.environ.get('ALLOW_GUEST', '1') == '1'
        if not auth_header and allow_guest:
            # Guest fallback (no login) - limited, non-admin
            request.user_id = "guest"
            request.user_email = "guest@guest"
            request.is_admin = False
        else:
            if not auth_header:
                return jsonify({"error": "No authorization token provided"}), 401
            try:
                token = auth_header.replace('Bearer ', '')
                payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
                request.user_id = payload['user_id']
                request.user_email = payload['email']
                request.is_admin = payload.get('is_admin', False)
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated_function

# Admin-only decorator
def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check authentication
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({"error": "No authorization token provided"}), 401

        try:
            token = auth_header.replace('Bearer ', '')
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user_id = payload['user_id']
            request.user_email = payload['email']
            request.is_admin = payload.get('is_admin', False)
            
            if not request.is_admin:
                return jsonify({"error": "Admin access required"}), 403
                
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated_function

# Validation helpers
def validate_text_input(text, max_length=1000):
    """Validate user text input"""
    if not text or not isinstance(text, str):
        return False, "Text is required and must be a string"

    text = text.strip()
    if len(text) == 0:
        return False, "Text cannot be empty"

    if len(text) > max_length:
        return False, f"Text too long (max {max_length} characters)"

    return True, text

# Weekend usage limit helpers (available Saturday-Sunday, 48h window)
WEEKEND_LIMIT_SECONDS = 2400  # 40 minutes per weekend

def is_weekend():
    """Check if today is Saturday or Sunday (UTC)"""
    return datetime.utcnow().weekday() in (5, 6)  # 5=Sat, 6=Sun

def get_weekend_key():
    """Get the Saturday date for the current weekend period.
    Returns the Saturday date string if it's a weekend, None otherwise."""
    now = datetime.utcnow()
    weekday = now.weekday()
    if weekday == 5:  # Saturday
        return now.strftime('%Y-%m-%d')
    elif weekday == 6:  # Sunday - use yesterday (Saturday)
        saturday = now - timedelta(days=1)
        return saturday.strftime('%Y-%m-%d')
    return None

def get_user_usage_data(email):
    """Get or initialize usage data for user, reset each weekend"""
    weekend_key = get_weekend_key()

    if weekend_key is None:
        # Weekday - return empty data (will be blocked by check_usage_limit)
        return {'date': None, 'seconds_used': 0, 'session_start': None}

    if email not in user_daily_usage:
        user_daily_usage[email] = {
            'date': weekend_key,
            'seconds_used': 0,
            'session_start': None
        }
    else:
        # Check if it's a new weekend - reset counter
        if user_daily_usage[email]['date'] != weekend_key:
            user_daily_usage[email] = {
                'date': weekend_key,
                'seconds_used': 0,
                'session_start': None
            }

    return user_daily_usage[email]

def get_remaining_seconds(email):
    """Get remaining seconds for user this weekend"""
    if not is_weekend():
        return 0
    usage_data = get_user_usage_data(email)
    used = usage_data['seconds_used']
    remaining = max(0, WEEKEND_LIMIT_SECONDS - used)
    return remaining

def track_usage_time(email, seconds):
    """Add seconds to user's weekend usage"""
    usage_data = get_user_usage_data(email)
    usage_data['seconds_used'] += seconds
    usage_data['seconds_used'] = min(usage_data['seconds_used'], WEEKEND_LIMIT_SECONDS)

def check_usage_limit(email):
    """Check if user is within weekend limit"""
    if not is_weekend():
        return False
    remaining = get_remaining_seconds(email)
    return remaining > 0

def is_local_request():
    """Bypass usage limits for local testing."""
    try:
        host = (request.host or "").lower()
        addr = (request.remote_addr or "").lower()
        return (
            addr in ("127.0.0.1", "::1")
            or host.startswith("localhost")
            or host.startswith("127.0.0.1")
        )
    except Exception:
        return False

# Load Scenarios and Grammar Topics
SCENARIOS_PATH = os.path.join(BASE_DIR, 'scenarios_db.json')
GRAMMAR_PATH = os.path.join(BASE_DIR, 'grammar_topics.json')
LESSONS_PATH = os.path.join(BASE_DIR, 'lessons_db.json')

def load_json_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return []

SCENARIOS = []
GRAMMAR_TOPICS = []
GRAMMAR_TOPIC_IDS = set()
CONTEXT_PROMPTS = {}
SIMULATOR_PROMPTS = {}  # Simulator mode prompts for realistic roleplay
LESSONS_DB = {}  # Structured lessons for Learning mode

def get_cached_model_for_context(context_key, system_prompt):
    """Get or create a cached Gemini model for a specific context.
    This uses system_instruction which gets cached automatically by Gemini,
    reducing token costs by ~90% for the system prompt portion."""
    global cached_models
    
    if not GENAI_AVAILABLE or not GOOGLE_API_KEY:
        return model  # Fallback to basic model
    
    # Check if we already have a cached model for this context
    if context_key in cached_models:
        return cached_models[context_key]
    
    try:
        # Create model with system_instruction (automatically cached by Gemini)
        cached_model = genai.GenerativeModel(
            model_name='gemini-3-flash-preview',
            system_instruction=system_prompt,
            generation_config=DEFAULT_GEN_CONFIG
        )
        cached_models[context_key] = cached_model
        print(f"[CACHE] Created cached model for context: {context_key}")
        return cached_model
    except Exception as e:
        print(f"[CACHE] Error creating cached model for {context_key}: {e}")
        return model  # Fallback to basic model

def load_context_data():
    """Reload scenarios/grammar so new topics are available without restart."""
    global SCENARIOS, GRAMMAR_TOPICS, GRAMMAR_TOPIC_IDS, CONTEXT_PROMPTS, SIMULATOR_PROMPTS, LESSONS_DB
    SCENARIOS = load_json_file(SCENARIOS_PATH)
    GRAMMAR_TOPICS = load_json_file(GRAMMAR_PATH)
    GRAMMAR_TOPIC_IDS = {g.get('id') for g in GRAMMAR_TOPICS}
    CONTEXT_PROMPTS = {s.get('id'): s.get('prompt', '') for s in SCENARIOS}
    CONTEXT_PROMPTS.update({g.get('id'): g.get('prompt', '') for g in GRAMMAR_TOPICS})
    # Load simulator prompts (realistic roleplay mode)
    SIMULATOR_PROMPTS = {s.get('id'): s.get('simulator_prompt', '') for s in SCENARIOS if s.get('simulator_prompt')}
    # Load structured lessons for Learning mode
    lessons_data = load_json_file(LESSONS_PATH)
    LESSONS_DB = lessons_data if isinstance(lessons_data, dict) else {}
    return GRAMMAR_TOPICS

# Initial load
load_context_data()

# Retrieve grammar topics endpoint
@app.route('/api/grammar-topics', methods=['GET'])
def get_grammar_topics():
    topics = load_context_data()
    return jsonify(topics)

# Merge prompts handled in load_context_data

# Email whitelist configuration
AUTHORIZED_EMAILS_FILE = os.path.join(BASE_DIR, 'authorized_emails.json')
ADMIN_EMAIL = 'everydayconversation1991@gmail.com'
ADMIN_PASSWORD = '1234560'

def load_authorized_emails():
    """Load authorized emails from JSON file"""
    try:
        # Check if file exists first
        if not os.path.exists(AUTHORIZED_EMAILS_FILE):
             print(f"[WARNING] Authorized emails file not found at: {AUTHORIZED_EMAILS_FILE}")
             return {ADMIN_EMAIL}
             
        with open(AUTHORIZED_EMAILS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return {ADMIN_EMAIL}
            
            data = json.loads(content)
            emails = set(data.get('authorized_emails', []))
            # Always include admin email
            emails.add(ADMIN_EMAIL)
            return emails
    except Exception as e:
        print(f"[ERROR] Error loading authorized emails: {e}")
        # Return set with just admin email as fallback
        return {ADMIN_EMAIL}

def save_authorized_emails(emails_set):
    """Save authorized emails to JSON file"""
    emails_list = sorted(list(emails_set))
    data = {
        'admin': ADMIN_EMAIL,
        'authorized_emails': emails_list
    }
    try:
        with open(AUTHORIZED_EMAILS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving authorized emails: {e}")
        return False

def is_email_authorized(email):
    """Check if email is in whitelist"""
    return email.lower() in authorized_emails

def is_admin_credentials(email, password):
    """Check if admin email and password are correct"""
    return email.lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD

# Load authorized emails on startup
authorized_emails = load_authorized_emails()
print(f"[OK] Loaded {len(authorized_emails)} authorized emails")

@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """Authentication endpoint with email whitelist"""
    try:
        data = request.json
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()

        # Validate email format
        if not email or '@' not in email or len(email) > 200:
            return jsonify({"error": "Invalid email format"}), 400

        # Check if email is in authorized list
        if not is_email_authorized(email):
            # Debug log
            print(f"Login failed: Email {email} not in authorized list (size: {len(authorized_emails)})")
            return jsonify({
                "error": "Email not authorized",
                "message": "This email is not registered in our system. Please contact support if you believe this is an error."
            }), 403

        # Check if this is admin login attempt
        is_admin = False
        if email.lower() == ADMIN_EMAIL.lower():
            if password:
                if is_admin_credentials(email, password):
                    is_admin = True
                else:
                    return jsonify({"error": "Invalid admin password"}), 401
        
        # Generate user ID and token
        user_id = f"{email}_{int(datetime.now().timestamp())}"
        
        # Get user name from email (first part before @)
        name = email.split('@')[0].title()
        
        token_payload = {
            'user_id': user_id,
            'name': name,
            'email': email,
            'is_admin': is_admin,
            'exp': datetime.utcnow() + timedelta(days=7)
        }

        token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm='HS256')

        # Store user session
        user_sessions[user_id] = {
            'name': name,
            'email': email,
            'is_admin': is_admin,
            'created_at': datetime.now().isoformat()
        }

        # Initialize conversation storage
        user_conversations[user_id] = []

        # Get usage data for this email
        usage_data = get_user_usage_data(email)
        remaining = get_remaining_seconds(email)

        return jsonify({
            "token": token,
            "user": {
                "user_id": user_id,
                "name": name,
                "email": email,
                "is_admin": is_admin
            },
            "usage": {
                "remaining_seconds": remaining,
                "seconds_used": usage_data['seconds_used'],
                "weekend_limit_seconds": WEEKEND_LIMIT_SECONDS,
                "is_blocked": remaining <= 0,
                "is_weekend": is_weekend()
            }
        })
    except Exception as e:
        import traceback
        print(f"LOGIN CRASH: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "error": "Internal Server Error (Debug Mode)",
            "details": str(e),
            "trace": traceback.format_exc()
        }), 500

@app.route('/api/scenarios', methods=['GET'])
def get_scenarios():
    load_context_data()
    return jsonify(SCENARIOS)


@app.route('/')
def serve_index():
    try:
        return send_file(os.path.join(BASE_DIR, 'index.html'))
    except Exception as e:
        return f"Error serving index.html: {str(e)}", 500

@app.route('/favicon.ico')
def favicon():
    # Return 204 No Content to settle the 404 error silently
    return '', 204


@app.route('/api/chat', methods=['POST'])
@limiter.limit("30 per minute")
@require_auth
def chat():
    # Reload topics so newly added grammar lessons are immediately available
    load_context_data()

    if not GOOGLE_API_KEY or not model:
        return jsonify({"error": "AI service not configured"}), 500

    # Check daily usage limit
    user_email = request.user_email
    if not is_local_request() and not check_usage_limit(user_email):
        remaining = get_remaining_seconds(user_email)
        return jsonify({
            "error": "Weekend practice limit reached",
            "message": "Practice is available on weekends only (Saturday-Sunday), 40 minutes per weekend." if not is_weekend() else "You've used your 40 minutes for this weekend. See you next Saturday!",
            "remaining_seconds": remaining,
            "is_weekend": is_weekend()
        }), 429

    data = request.json
    user_text = data.get('text')
    context_key = data.get('context', 'coffee_shop')
    lesson_lang = data.get('lessonLang', 'en')  # 'en' or 'pt'
    practice_mode = data.get('practiceMode', 'learning')  # 'learning' or 'simulator'

    # Validate input
    is_valid, result = validate_text_input(user_text, max_length=500)
    if not is_valid:
        return jsonify({"error": result}), 400

    user_text = result

    # Get conversation history for context (last 6 messages = 3 turns)
    user_id = request.user_id
    conversation_history = ""
    if user_id in user_conversations:
        recent = user_conversations[user_id][-6:]  # Last 6 messages
        if recent:
            history_lines = []
            for msg in recent:
                if msg.get('user'):
                    history_lines.append(f"Student: {msg['user']}")
                if msg.get('ai'):
                    history_lines.append(f"You: {msg['ai']}")
            if history_lines:
                conversation_history = "\n### CONVERSATION HISTORY (for context):\n" + "\n".join(history_lines) + "\n"

    # Get System Prompt based on context and practice mode
    if practice_mode == 'simulator' and context_key in SIMULATOR_PROMPTS:
        system_prompt = SIMULATOR_PROMPTS.get(context_key)
        print(f"[CHAT] Using SIMULATOR mode for {context_key}")
    else:
        system_prompt = CONTEXT_PROMPTS.get(context_key, CONTEXT_PROMPTS.get('coffee_shop', ''))
        print(f"[CHAT] Using LEARNING mode for {context_key}")
    
    # Get cached model for this context (saves ~90% on system prompt tokens)
    context_model = get_cached_model_for_context(context_key, system_prompt)

    # Check if this is a grammar/learning topic
    is_grammar_topic = context_key in GRAMMAR_TOPIC_IDS
    is_demonstratives = context_key in ['demonstratives', 'this_that_these_those']

    # SIMULATOR MODE: REAL LIFE SIMULATOR - NO TEACHING
    if practice_mode == 'simulator' and context_key in SIMULATOR_PROMPTS:
        full_prompt = f"""{system_prompt}
{conversation_history}

YOU ARE IN REAL LIFE SIMULATOR MODE.
The customer just said: "{user_text}"

CORE RULE:
You must ALWAYS act like a real service worker (barista, waiter, receptionist, etc).
You must NEVER act like a teacher, tutor, or language coach.
This is NOT a lesson. This is NOT practice. This is NOT teaching.

ABSOLUTE PROHIBITIONS (CRITICAL - if you do any of these, the simulation FAILS):
- "Can you try?"
- "Repeat after me"
- "I'd like you to say..."
- "Let's practice"
- "How about you?"
- "What do you think?"
- "Does that make sense?"
- "Good job!" or any praise for language
- Any sentence asking user to repeat or practice English
- Any explanation about language, grammar, or learning

ALLOWED BEHAVIOR:
- Ask only questions a real service worker would ask
- Respond naturally to what the customer says
- Confirm orders naturally (recast silently)
- Offer real options that exist in the scenario
- Handle misunderstandings like a human (ask to repeat or clarify)
- Ignore nonsense or redirect politely back to the order

SIMPLE LANGUAGE (CRITICAL):
- Use the SIMPLEST words possible. Avoid phrasal verbs when a simpler word exists.
- Only use context-specific vocabulary that is truly necessary (e.g., "check-in", "boarding pass").
- Replace advanced words with simple ones:
  - "incidental charges" → "extra charges"
  - "identification" → "ID"
  - "beverage" → "drink"
  - "accommodate" → "help"
  - "inquire" → "ask"
  - "proceed" → "go"
  - "assist you with" → "help you with"
  - "purchase" → "buy"
  - "regarding" → "about"
- The student is a beginner/intermediate learner. Speak clearly and simply.

COMPLETE SENTENCES (CRITICAL):
- NEVER end a sentence with "or", "and", a comma, or an ellipsis.
- NEVER split options across multiple turns. List ALL options in one complete sentence.
- WRONG: "I can take your ID, process your payment, or..."
- RIGHT: "I can take your ID, process your payment, or give you your room keys."

PROACTIVE SERVICE (CRITICAL):
- NEVER ask generic questions like "Is there anything else I can assist you with?"
- ALWAYS offer 2-3 concrete options relevant to the context
- Guide the conversation by suggesting specific next steps
Examples:
- Hotel: "I can help with check-in, room service, or local recommendations."
- Coffee: "Would you like that hot or iced? Small, medium, or large?"
- Restaurant: "Would you prefer a table by the window, or our quieter section?"

CONVERSATION FLOW (MOST CRITICAL RULE):
- Your response MUST ALWAYS end with a question mark (?). NO EXCEPTIONS.
- NEVER end with just a statement or affirmation. NEVER leave the customer with nothing to respond to.
- The question must be RELEVANT to the current context and advance the interaction toward the goal.
- You must LEAD the conversation by asking for the next piece of information needed.
- WRONG: "I'd be happy to get you checked in." (dead end — no question!)
- WRONG: "Sure, I can help with that." (dead end — no question!)
- RIGHT: "I'd be happy to help with check-in. May I see your ID, please?"
- RIGHT: "Sure! Would you like a window seat or an aisle seat?"
- WRONG: "Is there anything else?" (too generic)
- RIGHT: "Your room is on the 5th floor. Would you like help with your bags?"

RECAST RULE (VERY IMPORTANT):
If the user says something incorrect in English:
- DO NOT correct explicitly
- DO NOT explain
- Simply respond using the correct, natural version

Examples:
- User: "Like a hot coffee." → You: "Sure, a hot coffee. What size?"
- User: "Can we small?" → You: "No problem — a small coffee."
- User: "How much cost?" → You: "That'll be $4.50."

CONFIRMATION RULE:
When confirming an order, do NOT turn it into practice.
- CORRECT: "Alright, one large hot coffee."
- WRONG: "I'd like a large hot coffee, please! Can you say that?"

META QUESTIONS FROM USER:
If the user questions the simulation or asks meta questions:
- Answer briefly (1 sentence)
- Reaffirm the role
- Immediately return to the scenario
Example: User: "This is a simulator, not a lesson." → You: "Exactly — I'm the barista. What else can I get for you?"

RESPONSE LENGTH (CRITICAL):
- Keep responses short: 1-2 sentences max (under 30 words).
- Structure: brief reaction/confirmation + one question. Like a real person, not an interrogation.
- WRONG (too robotic): "Window seat or aisle seat?"
- RIGHT (natural): "Sure thing. Would you prefer a window seat or an aisle seat?"
- WRONG (too long): "That's a great choice. The grilled chicken is one of our most popular dishes. It comes with a side of vegetables and rice. Would you like to add a drink to your order?"
- RIGHT (natural): "Great choice, the grilled chicken. Would you like fries or salad with that?"

FLOW CONTROL:
- One question at a time
- Never repeat a question already answered
- Never explain what you are doing

END CONDITION:
When order is complete: Ask about payment → Confirm method → Close politely

Your ONLY goal: Simulate a real interaction so naturally that the user forgets this is an AI.

### RESPONSE FORMAT
Return JSON: {{"en": "your response", "pt": "traducao em portugues"}}
"""
    elif is_grammar_topic:
        if is_demonstratives and lesson_lang == 'pt':
            full_prompt = f"""{system_prompt}

### MODO PORTUGUES-INGLES (BILINGUAL)
Voce e uma professora de ingles humana, proxima e natural. Fale como em uma conversa real.
Quando usar exemplos em ingles, marque com [EN]exemplo em ingles[/EN].

### TEACHER MODE — DEMONSTRATIVOS (INTERMEDIARIO)
REGRAS DURAS:
- Cada mensagem deve terminar com uma tarefa/pergunta aberta que obrigue o aluno a responder.
- Cada mensagem deve ter entre 40 e 110 palavras.
- Estrutura obrigatoria: (A) 1 frase amigavel curta + (B) 1 frase curta de ensino + (C) 1 tarefa/pergunta.
- Depois de cumprimentar, volte ao tema na mesma mensagem.
- Em cada turno, exija que o aluno use pelo menos um de: [EN]this[/EN], [EN]that[/EN], [EN]these[/EN], [EN]those[/EN].
- No maximo 2 exemplos por turno.
- Nao repita a frase inteira do aluno. Se corrigir, use: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]."

### MICRO-ENSINO
[EN]This/These[/EN] = perto (singular/plural)
[EN]That/Those[/EN] = longe (singular/plural)
Tambem pode ser distancia no tempo: [EN]that day[/EN], [EN]those years[/EN].

### SITUACAO ATUAL
O aluno disse: "{user_text}"

### FORMATO DE SAIDA
Retorne APENAS JSON: {{"pt": "...", "suggested_words": ["word1","word2","word3","word4"], "must_retry": true}}
"""
        elif is_demonstratives and lesson_lang != 'pt':
            full_prompt = f"""{system_prompt}

### TEACHER MODE — DEMONSTRATIVES (INTERMEDIATE)
HARD RULES:
- Every message must end with a task or an open question that requires the student to answer.
- Keep each message between 40 and 110 words.
- Structure each turn as: (A) 1 short friendly line + (B) 1 short teaching line + (C) 1 task/question.
- After greetings, immediately move into the lesson topic.
- In each turn, require the student to use at least one of: this, that, these, those.
- Provide at most 2 examples per turn.
- Do not repeat the student's full sentence. If correcting, use: "Instead of <short snippet>, say: <corrected>."

### MICRO-TEACHING
This/These = near (singular/plural)
That/Those = far (singular/plural)
Distance in time is ok: that day, those years.

### CURRENT SITUATION
The student just said: "{user_text}"

### OUTPUT FORMAT
Return ONLY JSON: {{"en": "...", "suggested_words": ["word1","word2","word3","word4"], "must_retry": true}}
"""
        elif lesson_lang == 'pt':
            # PORTUGUESE MODE: Explanations in PT-BR with English examples marked
            full_prompt = f"""{system_prompt}

### MODO PORTUGUES-INGLES (BILINGUAL)
Voce e uma professora de ingles humana, proxima e natural. Fale como em uma conversa real.
Quando usar exemplos em ingles, marque com [EN]exemplo em ingles[/EN].
{conversation_history}
### SITUACAO ATUAL
O aluno disse: "{user_text}"

### REGRAS CRITICAS (MUITO IMPORTANTE!)
1. Se o aluno fizer uma PERGUNTA, voce DEVE responder PRIMEIRO antes de continuar. Nunca ignore perguntas!
2. Seja uma parceira de conversa REAL, nao uma maquina de correcao.
3. So corrija ERROS GRAMATICAIS REAIS (tempo verbal errado, concordancia errada, preposicao errada).
4. NAO corrija alternativas validas! Ex: [EN]doing great[/EN] e [EN]doing well[/EN] sao AMBOS corretos - nao "corrija" um para o outro.
5. Se o ingles do aluno estiver correto, apenas continue a conversa naturalmente SEM correcoes.

### COMO RESPONDER
- Reaja ao conteudo e mantenha a conversa fluindo.
- Se houver ERRO REAL, corrija: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]."
- Responda em PORTUGUES BRASILEIRO. Ingles sempre em [EN]...[/EN].
- 1 a 2 frases curtas.
- **REGRA OBRIGATORIA**: Sua resposta DEVE SEMPRE terminar com uma PERGUNTA para o aluno. NUNCA termine apenas com uma afirmacao! O aluno precisa saber o que responder.
- suggested_words: APENAS quando houver ERRO GRAMATICAL REAL; senao [].
- must_retry: true APENAS se suggested_words nao estiver vazio; senao false.
- Retorne JSON: {{"pt": "...", "suggested_words": [], "must_retry": false}}
"""
        else:
            # ENGLISH MODE: Original immersion-based approach
            full_prompt = f"""{system_prompt}
{conversation_history}
### CURRENT SITUATION
The student just said: "{user_text}"

### CRITICAL RULES (VERY IMPORTANT!)
1. If the student asks you a QUESTION, you MUST answer it FIRST before continuing. Never ignore questions!
2. Be a REAL conversation partner, NOT a correction machine.
3. Only correct REAL GRAMMAR ERRORS (wrong verb tense, subject-verb disagreement, wrong preposition).
4. Do NOT correct valid alternatives! "doing great" and "doing well" are BOTH correct - don't "fix" one to the other.
5. If their English is correct, just continue the conversation naturally WITHOUT corrections.

### NO TECHNICAL GRAMMAR TERMS (CRITICAL)
- NEVER use grammar terminology like: "first conditional", "zero conditional", "present perfect",
  "past simple", "vowel sound", "subject-verb agreement", "auxiliary verb", "conjugation", etc.
- Instead of explaining rules, just show the correct form naturally.
- WRONG: "That's a good example of a first conditional!"
- RIGHT: "Nice sentence! So, what will you do if it rains?"
- WRONG: "Since 'apple' starts with a vowel sound, we use 'an'."
- RIGHT: "Instead of 'a apple', say: 'an apple'. What kind of apple do you like?"
- The student is learning by DOING, not by studying theory.

### HOW TO RESPOND
- React to what they said and keep the conversation flowing.
- If there's a REAL error, correct it briefly: "Instead of <short snippet>, say: <corrected>."
- Speak in English (simple, natural, friendly).
- Keep responses SHORT: max 2 sentences, under 30 words total. Correction + question.
- **MANDATORY RULE**: Your response MUST ALWAYS end with a QUESTION for the student. NEVER end with just a statement! The student needs to know what to respond.
- suggested_words: ONLY when there is a REAL GRAMMAR ERROR; otherwise [].
- must_retry: true ONLY if suggested_words is not empty; else false.
- Return JSON: {{"en": "...", "suggested_words": [], "must_retry": false}}
"""
    else:
        # Standard scenario mode (Learning mode = structured teaching)
        if practice_mode == 'learning':
            # LEARNING MODE: Warm teacher who LEADS the conversation
            full_prompt = f"""{system_prompt}

### YOU ARE A FRIENDLY ENGLISH TEACHER WHO LEADS THE LESSON
You are warm and natural, but you are ALWAYS in control. You DRIVE the lesson forward.
Think of yourself as a private tutor: friendly, but every response teaches something and moves to the next step.
{conversation_history}
Student just said: "{user_text}"

### THE 3-PART RULE (EVERY RESPONSE MUST HAVE ALL 3!)
1. REACT briefly to what the student said (MAX 1 short sentence — then MOVE ON)
2. TEACH something useful (a phrase, vocabulary, correction with Portuguese translation)
3. ASK a question that ADVANCES the lesson to the next topic (not opinion, not confirmation)

CRITICAL: Keep reactions SHORT. Never spend more than 1 sentence reacting. The bulk of your response must be TEACHING + ADVANCING.

EXAMPLE (Job Interview):
Student: "I work in education for two years."
AI: "Good start! Just a small tweak — instead of 'I work for two years', say 'I have two years of experience in education' (Eu tenho dois anos de experiência em educação). Now, imagine the interviewer asks: 'Why are you interested in this position?' How would you answer that?"

### GREETING HANDLING (CRITICAL!)
If the student greets you ("Hi", "I'm doing great", "How are you?"):
- DO NOT engage in small talk. DO NOT answer "How are you?" with more than 3 words.
- IMMEDIATELY jump into the lesson.
- Example: Student: "I'm doing great, how are you?" → AI: "Great to hear! So, let's jump right in — today we're going to practice job interviews. Imagine you're sitting in front of the interviewer and they say: 'Tell me about yourself.' A strong opening is: 'I have X years of experience in Y' (Eu tenho X anos de experiência em Y). How would you introduce yourself?"

### FIRST MESSAGE
Your FIRST message must:
1. React to greeting in MAX 3 words ("Great to hear!")
2. Immediately set the scene ("Imagine you're at a job interview...")
3. Teach the first useful phrase with Portuguese translation
4. Ask the student to practice using it about THEIR life

Example: "Great to hear! So, today we're going to practice job interviews in English. Imagine you just sat down and the interviewer says: 'Tell me about yourself.' A professional way to start is: 'I have X years of experience in Y' (Eu tenho X anos de experiência em Y). So tell me — what do you do, and how long have you been doing it?"

After the first message, NEVER repeat "Today we're going to practice..." — just keep advancing.

### HOW TO LEAD
- ALWAYS end with a question that moves to the NEXT interview topic (not the same one)
- After "Tell me about yourself" → move to "Why do you want this job?"
- After "Why this job?" → move to "What are your strengths?"
- After "Strengths" → move to "Where do you see yourself in 5 years?"
- NEVER stay on the same topic for more than 2 exchanges
- NEVER end with just an affirmation ("Great!", "You nailed it!") without advancing

### CORRECTIONS (BE NATURAL!)
- WRONG: "Repeat: 'I have five years of experience.'"
- RIGHT: "Instead of 'I work for two years', say 'I have two years of experience' (Eu tenho dois anos de experiência) — it sounds more professional. Now, the interviewer asks about your motivation..."
- Always include Portuguese translation for key phrases
- No technical grammar terms (say "it sounds more professional" not "use present perfect")

### WHEN STUDENT DOESN'T UNDERSTAND
- Simplify with Portuguese: "No worries! 'experience' = experiência. So 'I have 5 years of experience' = 'Eu tenho 5 anos de experiência.'"
- Give a simpler example and move on — don't get stuck

### AVOID
- Ending with statements/affirmations without a question
- "Does that make sense?" / "Can you try?" / "What do you think?"
- Staying on the same point for too long
- Acting as a waiter/receptionist
- Casual chat that doesn't teach anything

### RESPONSE FORMAT
- English + Portuguese translation for key phrases
- MUST end with a question that advances to the next lesson topic
- suggested_words: only for real errors, otherwise []
- Return JSON: {{"en": "...", "pt": "...", "suggested_words": [], "must_retry": false}}
"""
        else:
            # FREE CONVERSATION MODE: Casual conversation partner
            full_prompt = f"""{system_prompt}

IMPORTANT: You are a friendly English conversation partner.
{conversation_history}
User just said: "{user_text}"

CRITICAL RULES:
1. If the student asks you a QUESTION, you MUST answer it first before continuing. Never ignore their questions!
2. Be a real conversation partner, NOT a correction machine. If their English is correct, just chat naturally.
3. Only correct REAL GRAMMAR ERRORS (wrong verb tense, subject-verb disagreement, wrong preposition, etc).
4. Do NOT correct valid alternatives! "doing great" and "doing well" are BOTH correct - don't "fix" one to the other.
5. **MANDATORY**: Your response MUST ALWAYS end with a QUESTION. NEVER end with just a statement or affirmation! The student needs a prompt to respond.

Response format:
- Respond naturally in English, provide Portuguese translation.
- If correcting a REAL error, use: "Instead of <short snippet>, say: <corrected>."
- **CRITICAL**: Every response MUST end with a question mark (?). Examples: "What do you think?", "How about you?", "What happened next?"
- suggested_words: ONLY when there is a REAL GRAMMAR ERROR; otherwise [].
- must_retry: true ONLY if suggested_words is not empty; else false.
- Return JSON: {{"en": "...", "pt": "...", "suggested_words": [], "must_retry": false}}

Keep responses to 1-2 short sentences (about 20 words). The LAST sentence MUST be a question.
"""

    try:
        # Use cached model with just the user-specific prompt (system already cached)
        # For cached models, only send the dynamic part (user text + current situation)
        if context_model != model:
            # Using cached model - send minimal prompt
            if practice_mode == 'simulator' and context_key in SIMULATOR_PROMPTS:
                # SIMULATOR MODE: REAL LIFE - NO TEACHING
                minimal_prompt = f"""{conversation_history}
Customer just said: "{user_text}"

REAL LIFE SIMULATOR. You are a REAL service worker. NOT a teacher.
This is NOT a lesson. NOT practice. NOT teaching.

ABSOLUTE PROHIBITIONS (simulation FAILS if you do these):
- "Can you try?" / "Repeat after me" / "Let's practice"
- "How about you?" / "What do you think?" / "Does that make sense?"
- "Good job!" / Any praise for language
- Any request to repeat or practice English

RECAST RULE:
If user says incorrect English → respond using correct form naturally. NO explanation.
Example: "Can we small?" → "No problem — a small coffee."

CONFIRMATION RULE:
- CORRECT: "Alright, one large hot coffee."
- WRONG: "Can you say that?"

META QUESTIONS:
Answer briefly → reaffirm role → return to scenario.
Example: "Exactly — I'm the barista. What else can I get for you?"

FLOW: One question at a time. Never repeat answered questions.

RESPONSE LENGTH: 1-2 sentences max (under 30 words). Brief reaction + one question. Natural, not an interrogation.

PROACTIVE SERVICE:
- NEVER say "Is there anything else I can assist you with?"
- ALWAYS offer 2-3 concrete options (e.g., "I can help with check-in, room service, or local recommendations.")

CONVERSATION FLOW (MOST CRITICAL):
- EVERY response MUST end with a question mark (?). NO EXCEPTIONS.
- NEVER end with just a statement. Always ask a RELEVANT follow-up question.
- WRONG: "I'd be happy to get you checked in." → RIGHT: "I'd be happy to help with check-in. May I see your ID?"
- Lead the conversation toward the goal with specific, contextual questions.

SIMPLE LANGUAGE: Use simple words. No phrasal verbs when a simpler word exists.
"incidental charges" → "extra charges", "identification" → "ID", "beverage" → "drink".

COMPLETE SENTENCES: NEVER end with "or", "and", comma, or "...". Always finish the full list of options.

Return JSON: {{"en": "your response", "pt": "traducao em portugues"}}"""
            elif is_grammar_topic:
                if is_demonstratives and lesson_lang == 'pt':
                    minimal_prompt = f"""### SITUACAO ATUAL
O aluno disse: "{user_text}"

Teacher mode (demonstrativos):
- 40-110 palavras.
- Estrutura: 1 frase amigavel + 1 frase de ensino + 1 tarefa/pergunta.
- Exigir uso de [EN]this/that/these/those[/EN] pelo aluno.
- No maximo 2 exemplos.
- Se corrigir, use: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]."
Retorne apenas JSON: {{"pt": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.
"""
                elif is_demonstratives and lesson_lang != 'pt':
                    minimal_prompt = f"""### CURRENT SITUATION
The student just said: "{user_text}"

Teacher mode (demonstratives):
- 40-110 words.
- Structure: 1 friendly line + 1 teaching line + 1 task/question.
- Require the student to use this/that/these/those.
- Max 2 examples.
- If correcting, use: "Instead of <short snippet>, say: <corrected>."
Return only JSON: {{"en": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.
"""
                elif lesson_lang == 'pt':
                    minimal_prompt = f"""### SITUACAO ATUAL
O aluno disse: "{user_text}"

Responda de forma humana e conversacional. Use portugues e marque ingles com [EN]...[/EN].
Evite "aula/licao/exercicio/gramatica".
1-2 frases curtas (max ~16 palavras cada) e termine com uma pergunta.
Se corrigir, use: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]." (max 4 palavras do aluno).
Nao repita a frase inteira do aluno.
suggested_words: 4 palavras/expressoes curtas quando houver erro ou oportunidade; senao [].
must_retry: true se suggested_words nao estiver vazio; senao false.
Retorne apenas JSON: {{"pt": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.
"""
                else:
                    minimal_prompt = f"""### CURRENT SITUATION
The student just said: "{user_text}"

Respond like a real conversation partner. Use simple English and avoid "lesson/grammar/exercise".
NEVER use grammar terms (conditional, present perfect, vowel sound, etc). Just show the correct form.
1-2 short sentences (max 30 words total), end with one question.
If you correct, use: "Instead of <short snippet>, say: <corrected>." (max 4 words from the student).
Do not repeat the full student sentence. Do not explain grammar rules.
suggested_words: 4 short words/phrases when there is a mistake or clear improvement; otherwise [].
must_retry: true if suggested_words is not empty; else false.
Return only JSON: {{"en": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.
"""
            else:
                if practice_mode == 'learning':
                    # LEARNING MODE: Teacher who LEADS naturally
                    minimal_prompt = f"""{conversation_history}
Student said: "{user_text}"

You are a friendly English teacher who LEADS the lesson. Every response MUST have 3 parts:
1. REACT briefly (1 sentence: acknowledge, correct, or praise)
2. TEACH (a useful phrase + Portuguese translation)
3. ASK a question that ADVANCES to the next lesson topic

CRITICAL: NEVER end with just a statement. ALWAYS end with a question that moves forward.
WRONG: "Great job! You nailed it." (no question, no advancement)
RIGHT: "Great! Now imagine the interviewer asks: 'What are your strengths?' How would you answer?"

Include Portuguese translations for key phrases.
Correct naturally: "Instead of X, say Y (tradução) — it sounds more professional."
No grammar jargon. No "Can you try?" / "Does that make sense?"
If student doesn't understand: simplify + Portuguese translation.

Return JSON: {{"en": "...", "pt": "...", "suggested_words": [], "must_retry": false}}."""
                else:
                    # FREE CONVERSATION MODE: Casual conversation partner
                    minimal_prompt = f"""{conversation_history}
User just said: "{user_text}"

CRITICAL RULES:
1. If user asks a QUESTION, answer it first! Never ignore questions.
2. Be a friendly conversation partner with MEMORY of the conversation above.
3. Only correct REAL GRAMMAR ERRORS. Do NOT "fix" valid alternatives.
4. Keep 1-2 short sentences (~20 words).
5. **MANDATORY**: Your FINAL sentence MUST be a QUESTION ending with "?". NEVER end with just a statement! Examples: "What about you?", "How was yours?", "What do you think?"

suggested_words: ONLY for real grammar errors; otherwise [].
must_retry: true ONLY if suggested_words not empty; else false.
Return JSON: {{"en": "...", "pt": "...", "suggested_words": [], "must_retry": false}}."""
            response = context_model.generate_content(minimal_prompt)
        else:
            # Fallback to basic model with full prompt
            response = model.generate_content(full_prompt)
        
        print(f"[CHAT] User: {user_text[:50]}... | Response: {response.text[:100]}...")

        try:
            raw_text = response.text.strip()
        except (AttributeError, ValueError):
            raw_text = "I'm sorry, I couldn't process that. Could you say it again?"

        # JSON parsing attempts first
        try:
            # Robust JSON extraction
            # First try standard markdown block removal
            cleaned = raw_text.replace('```json', '').replace('```', '').strip()
            # If that failed to find JSON structure, try regex
            if not (cleaned.startswith('{') and cleaned.endswith('}')):
                json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)

            parsed = json.loads(cleaned)

            suggested_words = parsed.get('suggested_words', [])
            must_retry = parsed.get('must_retry', False)
            retry_prompt = parsed.get('retry_prompt', '')
            
            # Handle response based on lesson language mode
            if lesson_lang == 'pt' and is_grammar_topic:
                # PT mode: Use Portuguese text as primary (contains [EN] tags for English examples)
                ai_text = parsed.get('pt', raw_text)
                ai_trans = ''  # No separate translation needed in PT mode
            else:
                # EN mode: Use English as primary, Portuguese as translation
                ai_text = parsed.get('en', raw_text)
                ai_trans = parsed.get('pt', '')
            
            # NOW clean asterisks from the extracted content (but preserve [EN][/EN] tags)
            if ai_text:
                ai_text = ai_text.replace('*', '').replace('_', '').replace('~', '').replace('`', '')
                ai_text = ' '.join(ai_text.split())
            if ai_trans:
                ai_trans = ai_trans.replace('*', '').replace('_', '').replace('~', '').replace('`', '')
                ai_trans = ' '.join(ai_trans.split())

            # Normalize suggested_words
            if isinstance(suggested_words, str):
                suggested_words = [w.strip() for w in suggested_words.split(',') if w.strip()]
            if not isinstance(suggested_words, list):
                suggested_words = []
            suggested_words = [str(w).strip() for w in suggested_words if str(w).strip()]
            suggested_words = suggested_words[:4]

            # ONLY set must_retry if AI explicitly corrected an error
            has_correction = bool(ai_text and re.search(r'(Instead of|Em vez de)', ai_text, re.IGNORECASE))

            if suggested_words and has_correction:
                if not retry_prompt:
                    retry_prompt = "Tente reformular sua resposta usando pelo menos uma dessas 4 palavras abaixo:"
                must_retry = True
            elif suggested_words and not has_correction:
                # Suggestions without correction = just vocabulary help, NOT retry
                suggested_words = []  # Clear suggestions if no actual error
                must_retry = False
            if is_demonstratives and not suggested_words and re.search(r'(Instead of|Em vez de)', ai_text or '', re.IGNORECASE):
                suggested_words = ["this", "that", "these", "those"]
                must_retry = True
                if not retry_prompt:
                    retry_prompt = "Tente reformular sua resposta usando pelo menos uma dessas 4 palavras abaixo:"

            # Guardrail for demonstratives: enforce structure + length + task
            if is_demonstratives:
                def _needs_demo_repair(value):
                    if not value:
                        return True
                    if not re.search(r'\b(this|that|these|those)\b', value, re.IGNORECASE):
                        return True
                    if '?' not in value:
                        return True
                    wc = len(re.findall(r"[A-Za-z0-9']+", value))
                    return wc < 40 or wc > 110

                if _needs_demo_repair(ai_text):
                    try:
                        repair_model = context_model if context_model else model
                        if lesson_lang == 'pt':
                            repair_prompt = f"""Reescreva a mensagem do assistente para seguir TODAS as regras:
- Tema: demonstrativos (this/that/these/those).
- 40 a 110 palavras.
- Estrutura: 1 frase amigavel + 1 frase de ensino + 1 tarefa/pergunta.
- Termine com pergunta/tarefa obrigatoria.
- Use [EN]this/that/these/those[/EN].
- Nao repita a frase inteira do aluno. Se corrigir, use: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]."
- Maximo 2 exemplos.
- Retorne apenas JSON: {{"pt": "...", "suggested_words": ["word1","word2","word3","word4"], "must_retry": true}}

Mensagem original: "{ai_text}"
"""
                        else:
                            repair_prompt = f"""Rewrite the assistant message to satisfy ALL rules:
- Topic: this/that/these/those.
- 40 to 110 words.
- Structure: 1 friendly line + 1 teaching line + 1 task/question.
- End with an open question/task.
- Include this/that/these/those.
- Do not repeat the student's full sentence. If correcting, use: "Instead of <short snippet>, say: <corrected>."
- Max 2 examples.
- Return ONLY JSON: {{"en": "...", "suggested_words": ["word1","word2","word3","word4"], "must_retry": true}}

Original message: "{ai_text}"
"""
                        if repair_model:
                            repaired = repair_model.generate_content(repair_prompt)
                            repaired_text = (repaired.text or '').strip()
                            cleaned_repair = repaired_text.replace('```json', '').replace('```', '').strip()
                            if not (cleaned_repair.startswith('{') and cleaned_repair.endswith('}')):
                                json_match = re.search(r'\{.*\}', repaired_text, re.DOTALL)
                                if json_match:
                                    cleaned_repair = json_match.group(0)
                            repaired_obj = json.loads(cleaned_repair)
                            ai_text = repaired_obj.get('pt' if lesson_lang == 'pt' else 'en', ai_text)
                            suggested_words = repaired_obj.get('suggested_words', suggested_words)
                            must_retry = repaired_obj.get('must_retry', must_retry)
                            retry_prompt = repaired_obj.get('retry_prompt', retry_prompt)
                    except Exception:
                        # Fallback deterministic teacher message
                        if lesson_lang == 'pt':
                            ai_text = "Legal! Hoje vamos praticar [EN]this/that/these/those[/EN]. Regra rapida: [EN]this/these[/EN] = perto, [EN]that/those[/EN] = longe. Olhe ao seu redor e diga: o que e [EN]this[/EN] perto de voce e o que e [EN]that[/EN] mais longe? Responda com duas frases curtas."
                        else:
                            ai_text = "Nice! Today we're practicing this/that/these/those. Quick rule: this/these = near, that/those = far. Look around you and tell me: what is this near you and what is that far from you? Answer with two short sentences."
                        suggested_words = ["this", "that", "these", "those"]
                        must_retry = True
                        retry_prompt = "Tente reformular sua resposta usando pelo menos uma dessas 4 palavras abaixo:"
                
        except (json.JSONDecodeError, AttributeError):
            # Fallback: regex extraction or raw text
            ai_text = raw_text
            ai_trans = ""
            
            # Try to rescue via regex if JSON parse failed
            try:
                if lesson_lang == 'pt' and is_grammar_topic:
                    # PT mode: look for pt field first
                    pt_match = re.search(r'"pt"\s*:\s*"([^"]*)"', raw_text)
                    if pt_match:
                        ai_text = pt_match.group(1)
                else:
                    # EN mode: look for en field, then pt for translation
                    en_match = re.search(r'"en"\s*:\s*"([^"]*)"', raw_text)
                    pt_match = re.search(r'"pt"\s*:\s*"([^"]*)"', raw_text)
                    if en_match:
                        ai_text = en_match.group(1)
                    if pt_match:
                        ai_trans = pt_match.group(1)
            except:
                pass

            # Clean the fallback text
            if ai_text:
                ai_text = ai_text.replace('*', '').replace('_', '').replace('~', '').replace('`', '')
                # Remove markdown json artifacts if they remain in raw text
                ai_text = ai_text.replace('```json', '').replace('```', '').replace('{', '').replace('}', '')
                ai_text = ' '.join(ai_text.split())

        if 'suggested_words' not in locals():
            suggested_words = []
            must_retry = False
            retry_prompt = ""

        # Enforce shorter AI responses (avoid long monologues)
        def _word_count(value):
            return len(re.findall(r"[A-Za-zÀ-ÿ0-9']+", value or ""))

        def _trim_sentences(value, max_sentences=2):
            parts = re.split(r'(?<=[.!?])\s+', value.strip()) if value else []
            return ' '.join(parts[:max_sentences]).strip()

        def _trim_words(value, max_words):
            if not value:
                return value
            words = value.split()
            if len(words) <= max_words:
                return value
            return ' '.join(words[:max_words]).rstrip() + '...'

        user_words = _word_count(user_text)
        max_words = max(20, int(user_words * 2.0)) if user_words else 20

        if ai_text and '[EN]' not in ai_text and not is_demonstratives:
            if _word_count(ai_text) > max_words:
                ai_text = _trim_sentences(ai_text, 2)
                # Only trim words if response doesn't end with a question
                if _word_count(ai_text) > max_words and not ai_text.rstrip().endswith('?'):
                    ai_text = _trim_words(ai_text, max_words)

            if ai_trans:
                if _word_count(ai_trans) > max_words:
                    ai_trans = _trim_sentences(ai_trans, 2)
                    if _word_count(ai_trans) > max_words and not ai_trans.rstrip().endswith('?'):
                        ai_trans = _trim_words(ai_trans, max_words)

        # CRITICAL: Ensure response ALWAYS ends with a question
        # If AI failed to include a question, append a follow-up question
        def _ensure_ends_with_question(text, lang='en', context=''):
            if not text:
                return text
            text = text.strip()
            # Check if already ends with a question
            if text.endswith('?'):
                return text
            
            # Practice commands (NOT banned questions)
            follow_up_questions_en = [
                "Now repeat this sentence.",
                "Say this phrase out loud.",
                "Try saying this in English.",
                "Now practice this phrase.",
                "Repeat after me."
            ]
            follow_up_questions_pt = [
                "Agora repita essa frase.",
                "Diga essa frase em voz alta.",
                "Tente dizer isso em inglês.",
                "Agora pratique essa frase.",
                "Repita comigo."
            ]
            
            import random
            if lang == 'pt' or '[EN]' in text:
                question = random.choice(follow_up_questions_pt)
            else:
                question = random.choice(follow_up_questions_en)
            
            # Append the question
            return f"{text} {question}"
        
        # Strip "Today you will learn" from non-first messages in learning mode
        if practice_mode == 'learning' and conversation_history:
            import re as _re
            ai_text = _re.sub(r'Today you will learn[^.]*\.?\s*', '', ai_text, flags=_re.IGNORECASE).strip()
            if ai_trans:
                ai_trans = _re.sub(r'Hoje você (vai|irá) aprender[^.]*\.?\s*', '', ai_trans, flags=_re.IGNORECASE).strip()

        # Apply question enforcement ONLY for free conversation mode
        # Learning mode: prompt already handles conversational endings
        # Simulator mode: natural roleplay flow without forced questions
        if practice_mode not in ('simulator', 'learning'):
            ai_text = _ensure_ends_with_question(ai_text, lesson_lang if is_grammar_topic else 'en', context_key)
            if ai_trans:
                ai_trans = _ensure_ends_with_question(ai_trans, 'pt', context_key)

        # Store conversation for the user
        user_id = request.user_id
        if user_id not in user_conversations:
            user_conversations[user_id] = []

        user_conversations[user_id].append({
            "timestamp": datetime.now().isoformat(),
            "user": user_text,
            "ai": ai_text,
            "context": context_key
        })

        return jsonify({
            "text": ai_text,
            "translation": ai_trans,
            "lessonLang": lesson_lang,
            "suggested_words": suggested_words,
            "retry_prompt": retry_prompt,
            "must_retry": must_retry
        })
    except Exception as e:
        import traceback
        print(f"[CHAT] Error: {e}")
        print(f"[CHAT] Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Failed to generate response: {str(e)}"}), 500


@app.route('/api/free-conversation', methods=['POST'])
@limiter.limit("30 per minute")
@require_auth
def free_conversation_action():
    if not GOOGLE_API_KEY or not model:
        return jsonify({"error": "AI service not configured"}), 500

    # Check daily usage limit
    user_email = request.user_email
    if not is_local_request() and not check_usage_limit(user_email):
        remaining = get_remaining_seconds(user_email)
        return jsonify({
            "error": "Weekend practice limit reached",
            "message": "Practice is available on weekends only (Saturday-Sunday), 40 minutes per weekend." if not is_weekend() else "You've used your 40 minutes for this weekend. See you next Saturday!",
            "remaining_seconds": remaining,
            "is_weekend": is_weekend()
        }), 429

    data = request.json or {}
    action = data.get('action', '').strip()
    main_question = data.get('main_question', '')
    student_answer = data.get('student_answer', '')
    followup_question = data.get('followup_question', '')
    followup_answer = data.get('followup_answer', '')
    student_question = data.get('student_question', '')

    if not action:
        return jsonify({"error": "No action provided"}), 400

    system_prompt = (
        "You are a friendly English conversation partner for speaking practice. "
        "Do NOT correct grammar or comment on mistakes. "
        "Be natural, warm, and helpful. "
        "Respond ONLY in English. Do not include translations or Portuguese. "
        "Return only the requested content in plain English."
    )

    context_model = get_cached_model_for_context('free_conversation_guided', system_prompt)
    active_model = context_model if context_model else model

    if action == 'followup':
        prompt = f"""{system_prompt}

Task: Create ONE short follow-up question in English based on the student's answer.
- Use 1 sentence.
- Max 15 words.
- Do not correct grammar.
- Use English only; no translations or other languages.
- Output ONLY the question text.

Main question: "{main_question}"
Student answer: "{student_answer}"
"""
    elif action == 'opinion':
        prompt = f"""{system_prompt}

Task: Write a response that starts with "In my opinion," and sounds natural.
- 4 to 7 sentences (about 80-140 words).
- Mention 1-2 points from the student's answers.
- Do not correct grammar.
- Use English only; no translations or other languages.
- Do NOT end with a question.
- Output ONLY the response text.

Main question: "{main_question}"
Student answer: "{student_answer}"
Follow-up question: "{followup_question}"
Follow-up answer: "{followup_answer}"
"""
    elif action == 'answer':
        prompt = f"""{system_prompt}

Task: Answer the student's question in English.
- 2 to 5 sentences.
- Be direct and helpful.
- Do not correct grammar.
- Use English only; no translations or other languages.
- Do NOT end with a question.
- Output ONLY the response text.

Student question: "{student_question}"
Main question context: "{main_question}"
Student answer context: "{student_answer}"
"""
    else:
        return jsonify({"error": "Invalid action"}), 400

    try:
        response = active_model.generate_content(prompt)
        raw_text = response.text.strip() if response and response.text else ""
        cleaned = raw_text.replace('```', '').replace('json', '').strip()

        # Try to recover JSON if model returns it
        if cleaned.startswith('{'):
            try:
                parsed = json.loads(cleaned)
                cleaned = parsed.get('text', cleaned)
            except json.JSONDecodeError:
                pass

        cleaned = cleaned.strip().strip('"').strip("'")

        # Enforce formatting rules
        if action == 'followup':
            if cleaned and not cleaned.endswith('?'):
                cleaned = cleaned.rstrip('.') + '?'
        if action == 'opinion':
            if cleaned and not cleaned.lower().startswith('in my opinion'):
                cleaned = f"In my opinion, {cleaned}"

        return jsonify({"text": cleaned})
    except Exception as e:
        print(f"FREE CONVERSATION ERROR: {str(e)}")
        return jsonify({"error": "Failed to generate response. Please try again."}), 500



@app.route('/api/suggestions', methods=['POST'])
@limiter.limit("30 per minute")
@require_auth
def get_suggestions():
    """Generate contextual response suggestions based on AI's last message"""
    if not GOOGLE_API_KEY or not model:
        return jsonify({"error": "AI service not configured"}), 500
    
    data = request.json
    ai_last_message = data.get('aiMessage', '')
    context_key = data.get('context', 'coffee_shop')
    lesson_lang = data.get('lessonLang', 'en')
    
    if not ai_last_message:
        return jsonify({"error": "No AI message provided"}), 400
    
    # Get topic name for context
    # Extract just the topic name/title from prompts for better suggestions
    context_info = ""
    for topic in GRAMMAR_TOPICS:
        if topic.get('id') == context_key:
            context_info = topic.get('title', context_key)
            break
    
    if not context_info:
        context_info = context_key.replace('_', ' ').title()
    
    # Prompt to generate suggestions
    if lesson_lang == 'pt':
        prompt = f"""Você é um assistente gerando RESPOSTAS VÁLIDAS para um aluno de inglês.

Tópico sendo praticado: {context_info}
A IA disse: "{ai_last_message}"

Gere 4 respostas curtas (máx 10 palavras cada) que o aluno poderia dar em INGLÊS.
- As respostas DEVEM fazer sentido como resposta à fala da IA
- Use estruturas apropriadas do tópico quando possível
- Seja natural e conversacional
- Formato: JSON com array "suggestions", cada item tem "en" (inglês) e "pt" (tradução)

Exemplo se IA perguntou "My day was busy. How is your day?":
{{"suggestions": [
  {{"en": "My day is great, thanks!", "pt": "Meu dia está ótimo, obrigado!"}},
  {{"en": "It's been pretty busy too.", "pt": "Também tem sido bem ocupado."}},
  {{"en": "Not bad! What did you do?", "pt": "Nada mal! O que você fez?"}},
  {{"en": "Good! Yours sounds hectic.", "pt": "Bom! O seu parece agitado."}}
]}}

CRÍTICO: As respostas DEVEM ser válidas para a fala da IA. Retorne APENAS o JSON.
"""
    else:
        prompt = f"""You are generating VALID RESPONSE OPTIONS for an English learner.

Topic being practiced: {context_info}
The AI just said: "{ai_last_message}"

Generate 4 short response options (max 10 words each) the student could say in ENGLISH.
- Responses MUST make sense as replies to the AI's message
- Use appropriate structures from the topic when possible
- Be natural and conversational
- Format: JSON with "suggestions" array, each item has "en" (English) and "pt" (Portuguese translation)

Example if AI said "My day was busy. How is your day?":
{{"suggestions": [
  {{"en": "My day is great, thanks!", "pt": "Meu dia está ótimo, obrigado!"}},
  {{"en": "It's been pretty busy too.", "pt": "Também tem sido bem ocupado."}},
  {{"en": "Not bad! What did you do?", "pt": "Nada mal! O que você fez?"}},
  {{"en": "Good! Yours sounds hectic.", "pt": "Bom! O seu parece agitado."}}
]}}

CRITICAL: Responses MUST be valid answers to the AI's statement/question. Return ONLY the JSON.
"""
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        # Clean markdown if present
        cleaned = raw_text.replace('```json', '').replace('```', '').strip()
        result = json.loads(cleaned)
        
        return jsonify(result)
    except Exception as e:
        print(f"[SUGGESTIONS] Error: {e}")
        # Fallback to generic but contextual suggestions
        return jsonify({
            "suggestions": [
                {"en": "That's interesting!", "pt": "Que interessante!"},
                {"en": "I agree with you.", "pt": "Concordo com você."},
                {"en": "Tell me more about that.", "pt": "Me conte mais sobre isso."},
                {"en": "I think so too.", "pt": "Eu também acho."}
            ]
        })

# =============================================
# STRUCTURED LESSON ENDPOINT (Learning Mode)
# =============================================
@app.route('/api/lesson', methods=['POST'])
@limiter.limit("30 per minute")
@require_auth
def lesson():
    """
    Handles structured lessons with predefined layers and options.
    Actions: start, show_options, select_option, evaluate_practice, next_layer
    """
    if not GOOGLE_API_KEY or not model:
        return jsonify({"error": "AI service not configured"}), 500

    data = request.json or {}
    context = data.get('context', 'coffee_shop')
    action = data.get('action', 'start')
    current_layer = data.get('layer', 0)
    selected_option = data.get('option')
    user_text = data.get('text', '')

    # Check if lesson exists for this context
    lesson_data = LESSONS_DB.get(context)
    if not lesson_data:
        return jsonify({"error": f"No structured lesson found for '{context}'"}), 404

    layers = lesson_data.get('layers', [])
    total_layers = len(layers)

    # ACTION: START - Show welcome message
    if action == 'start':
        welcome = lesson_data.get('welcome', {})
        resp = {
            "type": "welcome",
            "text": welcome.get('en', 'Welcome to the lesson!'),
            "translation": welcome.get('pt', 'Bem-vindo à aula!'),
            "lesson_title": lesson_data.get('title', context),
            "total_layers": total_layers,
            "next_action": "show_options"
        }
        # Include composite template info if lesson uses cumulative phrase building
        if 'composite_template' in lesson_data:
            resp['composite_template'] = lesson_data['composite_template']
        if 'composite_layers' in lesson_data:
            resp['composite_layers'] = lesson_data['composite_layers']
        return jsonify(resp)

    # ACTION: SHOW_OPTIONS - Display layer options
    if action == 'show_options':
        if current_layer >= total_layers:
            # Lesson complete - show conclusion
            conclusion = lesson_data.get('conclusion', {})
            return jsonify({
                "type": "conclusion",
                "text": conclusion.get('en', 'Congratulations! You completed the lesson!'),
                "translation": conclusion.get('pt', 'Parabéns! Você completou a aula!'),
                "layer": current_layer,
                "total_layers": total_layers,
                "next_action": "finished"
            })

        layer = layers[current_layer]
        instruction = layer.get('instruction', {})
        options = layer.get('options', [])

        return jsonify({
            "type": "options",
            "text": instruction.get('en', 'Choose an option:'),
            "translation": instruction.get('pt', 'Escolha uma opção:'),
            "layer_title": layer.get('title', f'Layer {current_layer + 1}'),
            "options": options,
            "layer": current_layer,
            "total_layers": total_layers,
            "next_action": "select_option"
        })

    # ACTION: SELECT_OPTION - User clicked an option, show practice prompt
    if action == 'select_option':
        if current_layer >= total_layers:
            return jsonify({"error": "Invalid layer"}), 400

        layer = layers[current_layer]
        practice_prompt = layer.get('practice_prompt', {})
        options = layer.get('options', [])

        # Get the selected phrase
        selected_phrase = None
        skip_to_layer = None
        if selected_option is not None and 0 <= selected_option < len(options):
            selected_phrase = options[selected_option]
            # Check if this option has skip_to_layer (for branching)
            if isinstance(selected_phrase, dict):
                skip_to_layer = selected_phrase.get('skip_to_layer')

        response_data = {
            "type": "practice",
            "text": practice_prompt.get('en', 'Now try using this phrase!'),
            "translation": practice_prompt.get('pt', 'Agora tente usar essa frase!'),
            "selected_phrase": selected_phrase,
            "layer": current_layer,
            "total_layers": total_layers,
            "next_action": "evaluate_practice"
        }

        # Include skip_to_layer if present (for layer skipping after practice)
        if skip_to_layer is not None:
            response_data["skip_to_layer"] = skip_to_layer

        return jsonify(response_data)

    # ACTION: EVALUATE_PRACTICE - Keyword-based evaluation (no Gemini)
    # Uses pre-defined feedback templates from lessons_db.json so all audio
    # can be pre-generated with the same voice (Vivian).
    if action == 'evaluate_practice':
        if current_layer >= total_layers:
            return jsonify({"error": "Invalid layer"}), 400

        layer = layers[current_layer]
        selected_phrase = data.get('selected_phrase', {})
        target_phrase = selected_phrase.get('en', '') if isinstance(selected_phrase, dict) else ''
        # Use composite phrase if provided (cumulative phrase from previous layers)
        composite_phrase = data.get('composite_phrase', '')
        if composite_phrase:
            target_phrase = composite_phrase
        feedback_templates = layer.get('feedback', {})

        # Robust evaluation with Unicode normalization and fuzzy matching
        def normalize_for_eval(t):
            t = t.lower().strip()
            # Normalize curly/smart quotes and apostrophes to ASCII
            t = t.replace('\u2019', "'").replace('\u2018', "'")
            t = t.replace('\u201c', '"').replace('\u201d', '"')
            # Remove punctuation
            t = t.replace(",", "").replace(".", "").replace("?", "").replace("!", "").replace('"', '').replace("'", " ")
            # Collapse whitespace
            return ' '.join(t.split())

        user_norm = normalize_for_eval(user_text)
        target_norm = normalize_for_eval(target_phrase)

        # Minimal stop words (only articles/prepositions, keep verbs like "like", "have", "get")
        stop_words = {'i', 'a', 'the', 'an', 'my', 'me', 'to', 'for', 'and', 'or', 'in', 'on', 'of'}
        target_words = set(target_norm.split()) - stop_words
        user_words = set(user_norm.split()) - stop_words

        # Calculate word overlap
        if target_words:
            overlap = len(target_words & user_words) / len(target_words)
        else:
            overlap = 0

        # Substring match (normalized)
        contains_target = (target_norm and user_norm and
                           (target_norm in user_norm or user_norm in target_norm))

        # Character-level similarity as fallback (handles STT typos)
        char_similarity = SequenceMatcher(None, user_norm, target_norm).ratio() if user_norm and target_norm else 0

        # Adaptive threshold: stricter for long phrases, lenient for short ones
        min_overlap = 0.3 if len(target_words) <= 2 else 0.4

        if contains_target or overlap >= min_overlap or char_similarity >= 0.6:
            # SUCCESS - student used the phrase correctly
            fb = feedback_templates.get('success', {})
            ready_for_next = True
        elif overlap > 0 or char_similarity >= 0.3 or len(user_words) >= 2:
            # RETRY - attempted but needs improvement
            fb = feedback_templates.get('retry', {})
            ready_for_next = False
        else:
            # REDIRECT - completely off topic (single word, dot, unrelated)
            fb = feedback_templates.get('redirect', {})
            ready_for_next = False

        # Fallback text if feedback templates not defined in lessons_db.json
        text_en = fb.get('en', "Good try! Let's continue.")
        text_pt = fb.get('pt', 'Boa tentativa! Vamos continuar.')

        # Determine next layer
        next_layer = current_layer
        if ready_for_next:
            skip_to = data.get('skip_to_layer')
            if skip_to is not None:
                # Convert layer ID to index (layer IDs are 1-based)
                next_layer = skip_to - 1 if skip_to > 0 else skip_to
            else:
                next_layer = current_layer + 1

        print(f"[LESSON] evaluate_practice: target='{target_phrase}', user='{user_text}', overlap={overlap:.2f}, char_sim={char_similarity:.2f}, ready={ready_for_next}")

        return jsonify({
            "type": "feedback",
            "text": text_en,
            "translation": text_pt,
            "ready_for_next": ready_for_next,
            "layer": current_layer,
            "next_layer": next_layer,
            "total_layers": total_layers,
            "next_action": "show_options" if next_layer < total_layers else "conclusion"
        })

    return jsonify({"error": f"Unknown action: {action}"}), 400


@app.route('/api/report', methods=['POST'])
@limiter.limit("10 per minute")
@require_auth
def report():
    if not GOOGLE_API_KEY or not model:
        return jsonify({"error": "AI service not configured"}), 500

    data = request.json or {}
    conversation = data.get('conversation', [])
    context_key = data.get('context', 'coffee_shop')

    if not conversation:
        return jsonify({"error": "No conversation provided"}), 400

    system_prompt = CONTEXT_PROMPTS.get(context_key, CONTEXT_PROMPTS.get('coffee_shop', ''))

    transcript_lines = []
    for item in conversation:
        sender = item.get("sender", "User")
        text = item.get("text", "").strip()
        if not text:
            continue
        transcript_lines.append(f"{sender}: {text}")

    transcript_text = "\n".join(transcript_lines) if transcript_lines else "Sem falas registradas."

    # Different prompts for different contexts
    if context_key == 'basic_structures':
        # Special prompt for Basic Structures training
        prompt = f"""
Você é um professor de inglês analisando uma sessão de TREINAMENTO DE ESTRUTURAS BÁSICAS.

O aluno praticou responder a 6 perguntas sobre como fazer pedidos educados em inglês.

Transcrição completa:
{transcript_text}

Analise cada resposta do aluno e gere um relatório focado em:
1. Quais estruturas educadas o aluno já domina bem
2. Quais estruturas precisam de mais prática
3. Alternativas de como expressar a mesma coisa

Retorne APENAS um JSON válido seguindo EXATAMENTE este formato:
{{
  "titulo": "Ótimo treino de estruturas básicas!",
  "emoji": "📖",
  "tom": "educacional e encorajador",
  "correcoes": [
    {{"ruim": "frase EXATA do aluno", "boa": "forma mais natural/educada", "explicacao": "por que essa forma é melhor"}}
  ],
  "analise_frases": [
    {{
      "frase_aluno": "frase EXATA como o aluno falou",
      "naturalidade": 50,
      "nivel": "Compreensível, mas não natural",
      "frase_natural": "como um nativo diria a mesma coisa",
      "explicacao": "breve explicação de por que a versão natural é melhor"
    }}
  ],
  "elogios": ["estrutura que usou bem 1", "estrutura que usou bem 2", "estrutura que usou bem 3"],
  "dicas": ["estude esta estrutura: ...", "pratique usar: ..."],
  "frase_pratica": "How would you politely ask someone to open the window?"
}}

REGRAS:
- Máximo 3 correções (foque nas mais importantes)
- Analise TODAS as falas do aluno em "analise_frases" (não apenas erros)
- "naturalidade": 0-100 (90-100=perfeita, 60-89=boa, 40-59=compreensível mas não natural, 0-39=erro grave)
- Pelo menos 3 elogios sobre estruturas que usou bem
- Dicas devem sugerir estruturas específicas para estudar
- Tom sempre positivo e motivador
- SEM texto fora do JSON
"""
    else:
        # Standard prompt for conversation scenarios
        prompt = f"""
Você é um professor de inglês MUITO ENCORAJADOR analisando a performance de um aluno em uma conversa prática.

Contexto da conversa: {context_key}
System prompt do cenário: {system_prompt}

Transcrição completa (ordem cronológica):
{transcript_text}

Analise CUIDADOSAMENTE cada fala do usuário seguindo estas prioridades:
1. PRIMEIRO: Identifique 3-4 PONTOS POSITIVOS (o que o aluno fez bem)
2. Depois: Para CADA frase do aluno, avalie e classifique
3. Dicas práticas e construtivas para evoluir

Gere um relatório em português e retorne APENAS um JSON válido seguindo EXATAMENTE este formato:
{{
  "titulo": "Frase MUITO MOTIVADORA e positiva sobre o progresso (ex: 'Você está indo muito bem!', 'Ótimo progresso!')",
  "emoji": "emoji positivo (🎉, ✨, 🌟, 👏, 💪)",
  "tom": "positivo e encorajador",
  "correcoes": [
    {{
      "fraseOriginal": "frase EXATA como o aluno falou",
      "fraseCorrigida": "versão corrigida da frase",
      "avaliacaoGeral": "Correta|Aceitável|Incorreta",
      "comentarioBreve": "Comentário de 1 frase simples, como um professor explicaria na sala de aula",
      "tag": "Estrutura Incorreta|Incorreta, mas Compreensível|Correta, mas Pouco Natural",
      "explicacaoDetalhada": "Explicação DIDÁTICA e SIMPLES como um professor falaria para o aluno em sala de aula. SEM termos técnicos de gramática. Use exemplos do dia-a-dia, analogias e linguagem acessível. Ex: 'Em inglês, quando você quer pedir algo educadamente, é como dizer Eu gostaria em vez de Eu quero - soa mais gentil!'"
    }}
  ],
  "analise_frases": [
    {{
      "frase_aluno": "frase EXATA como o aluno falou",
      "naturalidade": 50,
      "nivel": "Compreensível, mas não natural",
      "frase_natural": "como um nativo diria a mesma coisa",
      "explicacao": "breve explicação de por que a versão natural é melhor"
    }}
  ],
  "elogios": ["elogio específico 1", "elogio específico 2", "elogio específico 3", "elogio específico 4"],
  "dicas": ["dica construtiva 1", "dica construtiva 2"],
  "frase_pratica": "próxima frase em inglês para o aluno treinar neste contexto"
}}

ANÁLISE FRASE A FRASE (use em "analise_frases"):
- Analise TODAS as falas do aluno, não apenas as com erro
- "naturalidade" é um número de 0 a 100 representando quão natural a frase soa para um nativo
- Escala: 90-100 = perfeita/natural, 60-89 = boa mas pode melhorar, 40-59 = compreensível mas não natural, 0-39 = erro grave
- "nivel" deve descrever o nível em português (ex: "Perfeita!", "Boa, mas pode melhorar", "Compreensível, mas não natural", "Precisa de correção")
- "frase_natural" deve ser EXATAMENTE como um nativo falaria (mesmo que a original já esteja correta, repita-a)
- Se a frase do aluno já for perfeita, dê 90-100% e elogie na explicação

TAGS DE CLASSIFICAÇÃO (use em "tag"):
- "Estrutura Incorreta": Erro gramatical grave que compromete a compreensão
- "Incorreta, mas Compreensível": Erro pequeno ou de concordância que não impede o entendimento
- "Correta, mas Pouco Natural": Não é erro gramatical, mas um nativo não falaria assim (estranho ou formal demais)
- Se a frase estiver 100% correta e natural, não inclua o campo "tag"

AVALIAÇÃO GERAL (use em "avaliacaoGeral"):
- "Correta": Frase gramaticalmente correta e natural
- "Aceitável": Tem pequenos erros mas comunica bem a mensagem
- "Incorreta": Tem erros significativos que precisam ser corrigidos

REGRAS CRÍTICAS:
- SEMPRE inclua "avaliacaoGeral" e "comentarioBreve" para CADA correção
- O "comentarioBreve" deve dar ao aluno uma noção rápida do status da frase
- SEMPRE comece com 3-4 elogios ANTES das correções
- Tom SEMPRE positivo e motivador
- Elogios devem ser ESPECÍFICOS sobre o que o aluno fez bem
- Dicas devem ser construtivas, não críticas
- Se o aluno estiver muito bem, elogie ainda mais!
- SEM texto fora do JSON
"""

    try:
        response = model.generate_content(prompt)
        raw_feedback = response.text.strip()

        # Try to extract JSON
        cleaned = raw_feedback.replace('```json', '').replace('```', '').strip()
        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')

        parsed_feedback = None
        if start_idx != -1 and end_idx != -1:
            try:
                json_part = cleaned[start_idx:end_idx+1]
                parsed_feedback = json.loads(json_part)
            except json.JSONDecodeError as e:
                print(f"[REPORT] JSON Decode Error: {e}")
                parsed_feedback = None

        if parsed_feedback and isinstance(parsed_feedback, dict):
            # Store report for user
            user_id = request.user_id
            if user_id not in user_conversations:
                user_conversations[user_id] = []

            # Add report to conversation history
            user_conversations[user_id].append({
                "timestamp": datetime.now().isoformat(),
                "type": "report",
                "data": parsed_feedback
            })

            return jsonify({"report": parsed_feedback, "raw": raw_feedback})

        return jsonify({"feedback": raw_feedback, "raw": raw_feedback})
    except Exception as e:
        print(f"[REPORT] Error: {e}")
        return jsonify({"error": "Failed to generate report. Please try again."}), 500

@app.route('/api/export/pdf', methods=['POST'])
@limiter.limit("5 per minute")
@require_auth
def export_pdf():
    """Export conversation report as PDF"""
    data = request.json or {}
    report_data = data.get('report')
    user_name = data.get('user_name', 'Student')

    if not report_data:
        return jsonify({"error": "No report data provided"}), 400

    try:
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Title
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(50, height - 50, "Conversation Practice Report")

        # Student name and date
        pdf.setFont("Helvetica", 12)
        pdf.drawString(50, height - 80, f"Student: {user_name}")
        pdf.drawString(50, height - 100, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Report content
        y_position = height - 140

        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(50, y_position, f"{report_data.get('emoji', '')} {report_data.get('titulo', 'Report')}")
        y_position -= 30

        pdf.setFont("Helvetica", 10)
        pdf.drawString(50, y_position, f"Tone: {report_data.get('tom', 'N/A')}")
        y_position -= 30

        # Corrections
        if report_data.get('correcoes'):
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(50, y_position, "Corrections:")
            y_position -= 20
            pdf.setFont("Helvetica", 10)
            for corr in report_data.get('correcoes', []):
                pdf.drawString(70, y_position, f"Before: {corr.get('ruim', '')}")
                y_position -= 15
                pdf.drawString(70, y_position, f"Better: {corr.get('boa', '')}")
                y_position -= 25

        # Compliments
        if report_data.get('elogios'):
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(50, y_position, "Compliments:")
            y_position -= 20
            pdf.setFont("Helvetica", 10)
            for elogio in report_data.get('elogios', []):
                pdf.drawString(70, y_position, f"- {elogio}")
                y_position -= 20

        y_position -= 10

        # Tips
        if report_data.get('dicas'):
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(50, y_position, "Tips:")
            y_position -= 20
            pdf.setFont("Helvetica", 10)
            for dica in report_data.get('dicas', []):
                pdf.drawString(70, y_position, f"- {dica}")
                y_position -= 20

        y_position -= 10

        # Practice phrase
        if report_data.get('frase_pratica'):
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(50, y_position, "Next phrase to practice:")
            y_position -= 20
            pdf.setFont("Helvetica-Oblique", 10)
            pdf.drawString(70, y_position, report_data.get('frase_pratica', ''))

        pdf.save()
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    except Exception as e:
        print(f"[PDF] Error: {e}")
        return jsonify({"error": "Failed to generate PDF"}), 500

# Helper function to clean text for TTS (remove emojis, asterisks, symbols)
def clean_text_for_tts(text):
    """Remove emojis, asterisks, and other symbols from text for natural TTS"""
    import re
    
    # Remove emojis using regex
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub('', text)
    
    # Remove asterisks and common formatting symbols
    text = text.replace('*', '')
    text = text.replace('_', '')
    text = text.replace('~', '')
    text = text.replace('`', '')
    
    # Remove markdown bold/italic markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)  # *italic*
    text = re.sub(r'__(.+?)__', r'\1', text)  # __bold__
    text = re.sub(r'_(.+?)_', r'\1', text)  # _italic_
    
    # Clean up extra whitespace
    text = ' '.join(text.split())
    
    return text.strip()

def get_audio_cache_path(text, speed, lesson_lang, voice_name):
    """Generate cache path for audio based on text content and parameters"""
    # Create unique hash from text + parameters
    cache_key = f"{text}_{speed}_{lesson_lang}_{voice_name}"
    hash_obj = hashlib.md5(cache_key.encode('utf-8'))
    filename = hash_obj.hexdigest() + '.mp3'
    
    # Use common phrases dir for short, simple texts
    if len(text) < 50 and not '[EN]' in text:
        return os.path.join(COMMON_PHRASES_DIR, filename)
    else:
        return os.path.join(DYNAMIC_CACHE_DIR, filename)

def save_audio_to_cache(audio_content, cache_path):
    """Save audio content to cache file"""
    try:
        with open(cache_path, 'wb') as f:
            f.write(audio_content)
        return True
    except Exception as e:
        print(f"[CACHE] Error saving audio to cache: {e}")
        return False

def get_audio_from_cache(cache_path):
    """Retrieve audio from cache if exists"""
    try:
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"[CACHE] Error reading audio from cache: {e}")
        return None


# Lesson audio cache directory (pre-generated audio for structured lessons)
LESSON_AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'audio_cache', 'lessons')

def get_lesson_audio_cache(text):
    """Check if pre-generated lesson audio exists for this text.

    Pre-generated audio files are stored in audio_cache/lessons/ with filenames
    containing a hash of the text content. This allows instant playback of
    lesson content without TTS generation latency.

    Args:
        text: The text to look up in the lesson cache

    Returns:
        Tuple (full_path, filename) if found, (None, None) otherwise
    """
    if not os.path.exists(LESSON_AUDIO_CACHE_DIR):
        return None, None

    # Generate hash to search for
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]

    try:
        # Search for file with matching hash in filename
        for filename in os.listdir(LESSON_AUDIO_CACHE_DIR):
            if text_hash in filename and filename.endswith('.mp3'):
                full_path = os.path.join(LESSON_AUDIO_CACHE_DIR, filename)
                if os.path.exists(full_path):
                    return full_path, filename
    except Exception as e:
        print(f"[LESSON CACHE] Error searching cache: {e}")

    return None, None


def convert_to_bilingual_ssml(text):
    """Convert text with [EN]...[/EN] tags to SSML with language + voice switching"""
    import re

    # First clean the text of emojis and formatting
    text = clean_text_for_tts(text)

    def escape_ssml(value):
        return (value.replace('&', '&amp;')
                     .replace('<', '&lt;')
                     .replace('>', '&gt;'))

    def pt_segment(value):
        safe = escape_ssml(value)
        return f'<voice name="pt-BR-Chirp3-HD-Achernar"><lang xml:lang="pt-BR">{safe}</lang></voice>'

    def en_segment(value):
        safe = escape_ssml(value)
        # Slightly slower English for clarity
        return f'<voice name="en-US-Chirp3-HD-Achernar"><lang xml:lang="en-US"><prosody rate="95%">{safe}</prosody></lang></voice>'

    switch_pause_ms = 250

    def add_break():
        if ssml_parts and ssml_parts[-1].startswith('<break'):
            return
        ssml_parts.append(f'<break time="{switch_pause_ms}ms"/>')

    # Start building SSML
    ssml_parts = ['<speak>']

    # Split text by [EN]...[/EN] tags
    pattern = r'\[EN\](.*?)\[/EN\]'

    last_end = 0
    has_content = False
    for match in re.finditer(pattern, text):
        # Portuguese text before this match
        pt_text = text[last_end:match.start()].strip()
        if pt_text:
            if has_content:
                add_break()
            ssml_parts.append(pt_segment(pt_text))
            has_content = True

        # English text (the matched content)
        en_text = match.group(1).strip()
        if en_text:
            if has_content:
                add_break()
            ssml_parts.append(en_segment(en_text))
            add_break()
            has_content = True

        last_end = match.end()

    # Remaining Portuguese text after last match
    remaining = text[last_end:].strip()
    if remaining:
        if has_content:
            add_break()
        ssml_parts.append(pt_segment(remaining))

    ssml_parts.append('</speak>')

    return ''.join(ssml_parts)


import requests
import base64

@app.route('/api/tts', methods=['POST'])
@limiter.limit("50 per minute")
@require_auth
def tts_endpoint():
    """Text-to-Speech endpoint using Google Cloud TTS with bilingual SSML support"""
    try:
        data = request.json
        text = data.get('text')
        speed = data.get('speed', 1.0) # Default to normal speed
        lesson_lang = data.get('lessonLang', 'en')
        # Single voice for all interactions: Chirp3-HD-Achernar (natural female)
        voice_config = {
            'en': 'en-US-Chirp3-HD-Achernar',
            'pt': 'pt-BR-Chirp3-HD-Achernar',
            'gender': 'FEMALE',
            'name': 'Achernar'
        }
        print(f"[TTS] Voice: Chirp3-HD-Achernar")

        # Validate input
        is_valid, result = validate_text_input(text, max_length=500)
        if not is_valid:
            return jsonify({"error": result}), 400
        text = result

        if not text:
            return jsonify({"error": "No text provided"}), 400

        # Check lesson audio cache first (pre-generated audio for structured lessons)
        lesson_cache_path, lesson_cache_filename = get_lesson_audio_cache(text)
        if lesson_cache_path:
            print(f"[LESSON CACHE] HIT - serving pre-generated audio: {lesson_cache_filename}")
            # On Vercel, redirect to static CDN path for better performance
            if os.environ.get('VERCEL'):
                from flask import redirect
                return redirect(f"/audio_cache/lessons/{lesson_cache_filename}?v=4", code=302)
            else:
                return send_file(
                    lesson_cache_path,
                    mimetype="audio/mp3",
                    as_attachment=False,
                    download_name="tts.mp3"
                )

        # Check if Google API key is available
        if not GOOGLE_API_KEY:
            return jsonify({"error": "TTS service not configured - missing API key"}), 503

        try:
            # Check if text contains [EN]...[/EN] tags (bilingual mode)
            has_bilingual_tags = '[EN]' in text and '[/EN]' in text
            
            # Debug logging
            print(f"[TTS] lessonLang: {lesson_lang}, has_bilingual_tags: {has_bilingual_tags}")
            print(f"[TTS] Text preview: {text[:100]}...")
            
            # Portuguese always uses natural 1.0x speed (native speakers)
            pt_speed = 1.0
            
            # Determine voice name and parameters
            if has_bilingual_tags:
                voice_name = "bilingual_v2"
                effective_speed = pt_speed
            elif lesson_lang == 'pt':
                voice_name = voice_config['pt']  # Use selected PT voice (Neural2)
                effective_speed = pt_speed
            else:
                voice_name = voice_config['en']  # Use selected EN voice (Neural2)
                effective_speed = speed
            
            # Check cache first
            cache_path = get_audio_cache_path(text, effective_speed, lesson_lang, voice_name)
            cached_audio = get_audio_from_cache(cache_path)
            
            if cached_audio:
                print(f"[CACHE] ? Audio cache HIT - saved TTS API call")
                return send_file(
                    io.BytesIO(cached_audio),
                    mimetype="audio/mp3",
                    as_attachment=False,
                    download_name="tts.mp3"
                )
            print(f"[CACHE] Audio cache MISS - generating new audio")

            # --- TRY QWEN3-TTS FIRST (Local GPU Server) ---
            qwen_tts_url = os.environ.get("QWEN_TTS_URL", "").strip()
            if qwen_tts_url:
                try:
                    # Single voice: serena (closest match to Achernar)
                    qwen_voice = 'serena'

                    clean_text = clean_text_for_tts(text)

                    qwen_response = requests.post(
                        f"{qwen_tts_url}/v1/audio/speech",
                        json={
                            "model": "tts-1",
                            "input": clean_text,
                            "voice": qwen_voice,
                            "response_format": "mp3",
                            "speed": effective_speed
                        },
                        timeout=15
                    )

                    if qwen_response.status_code == 200 and len(qwen_response.content) > 100:
                        audio_data = qwen_response.content
                        save_audio_to_cache(audio_data, cache_path)
                        print(f"[Qwen3-TTS] Success! {len(audio_data)} bytes, voice: {qwen_voice}")
                        return send_file(
                            io.BytesIO(audio_data),
                            mimetype="audio/mp3",
                            as_attachment=False,
                            download_name="tts.mp3"
                        )
                    else:
                        print(f"[Qwen3-TTS] Failed: status={qwen_response.status_code}, falling back to Google")
                except Exception as e:
                    print(f"[Qwen3-TTS] Error: {e}, falling back to Google Cloud TTS")

            # --- FALLBACK: GOOGLE CLOUD TTS ---
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_API_KEY}"
            
            # USE SELECTED VOICE FROM USER PREFERENCE
            if has_bilingual_tags:
                # BILINGUAL MODE: Convert to SSML with language switching
                ssml_text = convert_to_bilingual_ssml(text)
                voice_name = voice_config['pt']  # Use PT voice for bilingual
                
                payload = {
                    "input": {"ssml": ssml_text},
                    "voice": {
                        "languageCode": "pt-BR",
                        "name": voice_name,
                        "ssmlGender": voice_config['gender']
                    },
                    "audioConfig": {
                        "audioEncoding": "MP3",
                        "speakingRate": pt_speed
                    }
                }
            elif lesson_lang == 'pt':
                # Pure Portuguese - use selected PT voice
                voice_name = voice_config['pt']
                
                payload = {
                    "input": {"text": clean_text_for_tts(text)},
                    "voice": {
                        "languageCode": "pt-BR",
                        "name": voice_name,
                        "ssmlGender": voice_config['gender']
                    },
                    "audioConfig": {
                        "audioEncoding": "MP3",
                        "speakingRate": pt_speed
                    }
                }
            else:
                # ENGLISH MODE - use selected EN voice
                voice_name = voice_config['en']
                
                payload = {
                    "input": {"text": clean_text_for_tts(text)},
                    "voice": {
                        "languageCode": "en-US",
                        "name": voice_name,
                        "ssmlGender": voice_config['gender']
                    },
                    "audioConfig": {
                        "audioEncoding": "MP3",
                        "speakingRate": speed
                    }
                }
            
            print(f"[TTS] Using voice: {voice_name}")

            response = requests.post(url, json=payload, timeout=15)
            
            # Fallback mechanism
            if response.status_code != 200:
                 # Logic to handle fallback if premium voice fails (omitted for brevity, can be re-added if needed)
                 pass

            if response.status_code == 200:
                # Success! Save to cache for future use
                audio_content = base64.b64decode(response.json()['audioContent'])
                save_audio_to_cache(audio_content, cache_path)
                print(f"[CACHE] Saved audio to cache: {os.path.basename(cache_path)}")

            if response.status_code != 200:
                error_msg = response.text[:500] if response.text else "Unknown error"
                
                # Detailed error logging for diagnosis
                print(f"[TTS] GOOGLE TTS API ERROR")
                print(f"[TTS] Status Code: {response.status_code}")
                print(f"[TTS] Voice Attempted: {voice_name}")
                print(f"[TTS] Error Message: {error_msg}")
                print(f"[TTS] Possible causes:")
                if response.status_code == 400:
                    print(f"[TTS]   - Invalid request or unsupported voice")
                elif response.status_code == 403:
                    print(f"[TTS]   - API key restrictions or billing disabled")
                elif response.status_code == 429:
                    print(f"[TTS]   - Quota exceeded")
                else:
                    print(f"[TTS]   - Check Google Cloud Console for details")
                
                return jsonify({
                    "error": "Text-to-speech service error",
                    "status_code": response.status_code,
                    "voice": voice_name,
                    "details": error_msg,
                    "help": "Check backend logs for detailed diagnosis"
                }), 503

            # Extract audio content from response
            response_data = response.json()
            audio_content = response_data.get('audioContent')
            
            if not audio_content:
                return jsonify({"error": "No audio content received from TTS API"}), 503

            # Decode base64 audio
            audio_data = base64.b64decode(audio_content)

            return send_file(
                io.BytesIO(audio_data),
                mimetype="audio/mp3",
                as_attachment=False,
                download_name="tts.mp3"
            )

        except Exception as e:
            print(f"TTS Error: {e}")
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        print(f"TTS Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/tts/clone', methods=['POST'])
def tts_clone():
    """TTS with voice cloning using Qwen3-TTS.

    This endpoint generates speech using a cloned voice from a reference audio.
    The reference audio and transcription are loaded from voice_references/config.json.

    Request body:
        {
            "text": "Text to synthesize",
            "speed": 0.85  (optional, default 0.85)
        }

    Returns:
        audio/mp3 file
    """
    try:
        data = request.json or {}
        text = data.get('text', '')
        speed = data.get('speed', 0.85)

        if not text:
            return jsonify({"error": "No text provided"}), 400

        # Check for Qwen3-TTS server
        qwen_tts_url = os.environ.get("QWEN_TTS_URL", "").strip()
        if not qwen_tts_url:
            return jsonify({"error": "QWEN_TTS_URL not configured"}), 500

        # Load voice reference configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'voice_references', 'config.json')
        if not os.path.exists(config_path):
            return jsonify({"error": "Voice reference config not found. Run scripts/download_voice_reference.py first."}), 500

        with open(config_path, 'r', encoding='utf-8') as f:
            voice_config = json.load(f)

        # Check if ref_audio exists
        ref_audio_path = os.path.join(os.path.dirname(__file__), '..', voice_config['ref_audio'])
        if not os.path.exists(ref_audio_path):
            return jsonify({"error": f"Reference audio not found: {voice_config['ref_audio']}. Run scripts/download_voice_reference.py first."}), 500

        # Check if ref_text is still placeholder
        if 'PLACEHOLDER' in voice_config.get('ref_text', 'PLACEHOLDER'):
            return jsonify({"error": "Voice reference transcription not set. Edit voice_references/config.json and add the transcription."}), 500

        # Read reference audio as base64
        with open(ref_audio_path, 'rb') as f:
            ref_audio_b64 = base64.b64encode(f.read()).decode('utf-8')

        print(f"[TTS/Clone] Generating audio for: {text[:50]}...")
        print(f"[TTS/Clone] Using voice reference: {voice_config['ref_audio']}")
        print(f"[TTS/Clone] Speed: {speed}x")

        # Call Qwen3-TTS voice cloning endpoint
        try:
            response = requests.post(
                f"{qwen_tts_url}/v1/audio/speech/clone",
                json={
                    "input": text,
                    "ref_audio": ref_audio_b64,
                    "ref_text": voice_config['ref_text'],
                    "language": voice_config.get('language', 'English'),
                    "speed": speed
                },
                timeout=60
            )

            if response.status_code == 200 and len(response.content) > 100:
                print(f"[TTS/Clone] Success! {len(response.content)} bytes")
                return send_file(
                    io.BytesIO(response.content),
                    mimetype="audio/mp3",
                    as_attachment=False,
                    download_name="tts_clone.mp3"
                )
            else:
                print(f"[TTS/Clone] Failed: status={response.status_code}")

                # Fallback to regular TTS with speed adjustment
                print("[TTS/Clone] Falling back to regular Qwen3-TTS...")
                fallback_response = requests.post(
                    f"{qwen_tts_url}/v1/audio/speech",
                    json={
                        "model": "tts-1",
                        "input": text,
                        "voice": "serena",  # Default female voice
                        "response_format": "mp3",
                        "speed": speed
                    },
                    timeout=15
                )

                if fallback_response.status_code == 200 and len(fallback_response.content) > 100:
                    print(f"[TTS/Clone] Fallback success! {len(fallback_response.content)} bytes")
                    return send_file(
                        io.BytesIO(fallback_response.content),
                        mimetype="audio/mp3",
                        as_attachment=False,
                        download_name="tts_clone.mp3"
                    )

                return jsonify({"error": f"TTS clone failed: {response.status_code}"}), 503

        except requests.exceptions.Timeout:
            return jsonify({"error": "TTS clone request timed out"}), 504
        except requests.exceptions.ConnectionError:
            return jsonify({"error": "Cannot connect to Qwen3-TTS server"}), 503

    except Exception as e:
        print(f"[TTS/Clone] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversations', methods=['GET'])
@require_auth
def get_conversations():
    """Get user's conversation history"""
    user_id = request.user_id
    conversations = user_conversations.get(user_id, [])
    return jsonify({"conversations": conversations})

@app.route('/api/conversations', methods=['DELETE'])
@require_auth
def clear_conversations():
    """Clear user's conversation history"""
    user_id = request.user_id
    user_conversations[user_id] = []
    return jsonify({"message": "Conversations cleared"})

@app.route('/api/usage/status', methods=['GET'])
@require_auth
def get_usage_status():
    """Get current usage status for user"""
    user_email = request.user_email
    usage_data = get_user_usage_data(user_email)
    remaining = get_remaining_seconds(user_email)
    
    return jsonify({
        "seconds_used": usage_data['seconds_used'],
        "remaining_seconds": remaining,
        "weekend_limit_seconds": WEEKEND_LIMIT_SECONDS,
        "is_blocked": remaining <= 0,
        "is_weekend": is_weekend(),
        "date": usage_data['date']
    })

@app.route('/api/usage/track', methods=['POST'])
@require_auth
def track_usage():
    """Track session usage time"""
    try:
        user_email = request.user_email
        data = request.json or {}
        seconds = data.get('seconds', 0)
        
        if not isinstance(seconds, (int, float)) or seconds < 0 or seconds > 3600:
            return jsonify({"error": "Invalid seconds value"}), 400
        
        track_usage_time(user_email, int(seconds))
        remaining = get_remaining_seconds(user_email)
        
        return jsonify({
            "success": True,
            "remaining_seconds": remaining,
            "is_blocked": remaining <= 0
        })
    except Exception as e:
        print(f"[USAGE/TRACK] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to track usage", "details": str(e)}), 500

# Admin-only endpoints
@app.route('/api/admin/emails', methods=['GET'])
@require_admin
def get_authorized_emails():
    """Get list of all authorized emails (admin only)"""
    return jsonify({
        "emails": sorted(list(authorized_emails)),
        "total": len(authorized_emails),
        "admin_email": ADMIN_EMAIL
    })

@app.route('/api/admin/emails', methods=['POST'])
@require_admin
def add_authorized_email():
    """Add email to authorized list (admin only)"""
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    
    if not email or '@' not in email:
        return jsonify({"error": "Invalid email format"}), 400
    
    if email in authorized_emails:
        return jsonify({"error": "Email already authorized"}), 400
    
    # Add to set
    authorized_emails.add(email)
    
    # Save to file
    success = save_authorized_emails(authorized_emails)
    
    if success:
        return jsonify({
            "success": True,
            "message": f"Email {email} added successfully",
            "total": len(authorized_emails)
        })
    else:
        return jsonify({"error": "Failed to save emails"}), 500

@app.route('/api/admin/emails/<email>', methods=['DELETE'])
@require_admin
def remove_authorized_email(email):
    """Remove email from authorized list (admin only)"""
    email = email.strip().lower()
    
    # Prevent removing admin email
    if email == ADMIN_EMAIL.lower():
        return jsonify({"error": "Cannot remove admin email"}), 400
    
    if email not in authorized_emails:
        return jsonify({"error": "Email not in authorized list"}), 404
    
    # Remove from set
    authorized_emails.discard(email)
    
    # Save to file
    success = save_authorized_emails(authorized_emails)
    
    if success:
        return jsonify({
            "success": True,
            "message": f"Email {email} removed successfully",
            "total": len(authorized_emails)
        })
    else:
        return jsonify({"error": "Failed to save emails"}), 500

@app.route('/api/admin/emails/reload', methods=['POST'])
@require_admin
def reload_authorized_emails():
    """Reload emails from file (admin only)"""
    global authorized_emails
    authorized_emails = load_authorized_emails()
    
    return jsonify({
        "success": True,
        "message": "Email list reloaded successfully",
        "total": len(authorized_emails)
    })

@app.route('/api/transcribe', methods=['POST'])
@limiter.limit("30 per minute")
@require_auth
def transcribe_audio():
    """Transcribe audio using Google Speech-to-Text, Deepgram Nova-2, or Groq Whisper"""
    if not (GOOGLE_API_KEY or DEEPGRAM_API_KEY or GROQ_API_KEY):
        return jsonify({"error": "Transcription service not configured"}), 503
    
    if not REQUESTS_AVAILABLE:
        return jsonify({"error": "Transcription service not available - missing dependencies"}), 503
    
    # Check daily usage limit
    user_email = request.user_email
    if not is_local_request() and not check_usage_limit(user_email):
        remaining = get_remaining_seconds(user_email)
        return jsonify({
            "error": "Weekend practice limit reached",
            "message": "Practice is available on weekends only (Saturday-Sunday), 40 minutes per weekend." if not is_weekend() else "You've used your 40 minutes for this weekend. See you next Saturday!",
            "remaining_seconds": remaining,
            "is_weekend": is_weekend()
        }), 429
    
    # Get audio file from request
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    language_hint = request.form.get('language', 'pt-BR')  # Default to PT for Nova-2 if not specified
    
    if audio_file.filename == '':
        return jsonify({"error": "Empty audio file"}), 400
    
    try:
        # Read audio data
        audio_data = audio_file.read()
        
        if len(audio_data) == 0:
            return jsonify({"error": "Audio file is empty"}), 400
        
        print(f"[Transcription] Received audio: {len(audio_data)} bytes, hint: {language_hint}")
        
        # --- INTELLIGENT ROUTING ---
        # Priority: Google Speech-to-Text (Service Account) > Deepgram > Groq

        transcript = None
        confidence = 0.0
        provider = "none"

        # 1. Try GOOGLE SPEECH-TO-TEXT with Service Account
        google_sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if SPEECH_AVAILABLE and google_sa_json and not transcript:
            try:
                # Parse service account JSON from environment
                sa_info = json.loads(google_sa_json)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
                client = speech.SpeechClient(credentials=credentials)

                # Determine language code
                lang_code = 'en-US' if language_hint == 'en' else 'pt-BR'

                # Configure recognition
                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                    sample_rate_hertz=48000,
                    language_code=lang_code,
                    enable_automatic_punctuation=True,
                    model="latest_short"
                )

                audio = speech.RecognitionAudio(content=audio_data)

                # Perform recognition
                response = client.recognize(config=config, audio=audio)

                if response.results:
                    result = response.results[0]
                    if result.alternatives:
                        transcript = result.alternatives[0].transcript
                        confidence = result.alternatives[0].confidence
                        if transcript:
                            provider = "google-speech-sa"
                            print(f"[Google STT SA] Success: '{transcript[:50]}...', Conf: {confidence}")
                        else:
                            print("[Google STT SA] Empty transcript")
                else:
                    print("[Google STT SA] No results in response")

            except Exception as e:
                print(f"[Google STT SA] Exception: {e}")

        # 2. Try DEEPGRAM as fallback
        prefer_groq_for_mixed = (language_hint != 'en')
        should_use_deepgram = not transcript and DEEPGRAM_API_KEY and (not prefer_groq_for_mixed or not GROQ_API_KEY)
        
        if should_use_deepgram:
            try:
                # Deepgram Nova-2 Implementation
                headers = {
                    'Authorization': f'Token {DEEPGRAM_API_KEY}',
                    'Content-Type': 'audio/webm'
                }
                
                # If we are here, we are likely in EN mode or forced to use Deepgram
                if language_hint == 'en':
                    dg_url = "https://api.deepgram.com/v1/listen?model=nova-2-general&smart_format=true&punctuate=true&language=en-US"
                else:
                    # Fallback for PT if Groq missing: Use auto-detect
                    dg_url = "https://api.deepgram.com/v1/listen?model=nova-2-general&smart_format=true&punctuate=true&detect_language=true"
                
                response = requests.post(
                    dg_url,
                    data=audio_data,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    try:
                        alternatives = result['results']['channels'][0]['alternatives'][0]
                        transcript = alternatives['transcript']
                        confidence = alternatives['confidence']
                        if transcript:
                            provider = "deepgram-nova-2"
                            print(f"[Deepgram] Success: '{transcript[:50]}...', Conf: {confidence}")
                        else:
                            print("[Deepgram] Returned empty transcript")
                    except (KeyError, IndexError):
                        print("[Deepgram] Error parsing response")
                else:
                    print(f"[Deepgram] Request failed: {response.status_code}")

            except Exception as e:
                print(f"[Deepgram] Exception: {e}")
        
        # 3. Try GROQ as final fallback
        if not transcript and GROQ_API_KEY:
            print("[Transcription] Falling back to Groq Whisper...")

            files = {
                'file': ('audio.webm', audio_data, 'audio/webm')
            }
            # ... rest of Groq logic follows in existing code (we just flow into it)
            
            # English prompt when student is practicing English (most common case)
            if language_hint == 'en' or not language_hint:
                whisper_prompt = "Transcribe the user's speech exactly as spoken in English."
            else:
                whisper_prompt = "Transcreva a fala do usuário exatamente."

            data = {
                'model': 'whisper-large-v3',
                'response_format': 'verbose_json',
                'temperature': 0.0,
                'prompt': whisper_prompt
            }

            if language_hint:
                data['language'] = language_hint
            else:
                data['language'] = 'en'
            
            headers = {
                'Authorization': f'Bearer {GROQ_API_KEY}'
            }
            
            response = requests.post(
                GROQ_API_URL,
                files=files,
                data=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                transcript = result.get('text', '')
                confidence = 1.0
                provider = "groq-whisper"
                print(f"[Groq] Success: '{transcript[:50]}...'")
            else:
                print(f"[Groq] Error {response.status_code}: {response.text}")
        
        # --- FINAL CHECK ---
        if not transcript:
             return jsonify({"error": "No speech detected"}), 400
             
        return jsonify({
            "text": transcript,
            "confidence": confidence,
            "provider": provider
        })
            
    except Exception as e:
        print(f"Transcription Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "google_api_configured": bool(GOOGLE_API_KEY),
        "groq_api_configured": bool(GROQ_API_KEY),
        "genai_available": GENAI_AVAILABLE,
        "requests_available": REQUESTS_AVAILABLE
    })

@app.route('/api/debug_imports', methods=['GET'])
def debug_imports():
    return jsonify({
        "google-cloud-texttospeech": {
            "available": globals().get('TEXTTOSPEECH_AVAILABLE'),
            "error": globals().get('TEXTTOSPEECH_ERROR')
        },
        "reportlab": {
            "available": globals().get('REPORTLAB_AVAILABLE'),
            "error": globals().get('REPORTLAB_ERROR')
        },
        "flask-cors": {
            "available": globals().get('CORS_AVAILABLE'),
            "error": globals().get('CORS_ERROR')
        },
        "flask-limiter": {
            "available": globals().get('LIMITER_AVAILABLE'),
            "error": globals().get('LIMITER_ERROR')
        },
        "google-generativeai": {
            "available": globals().get('GENAI_AVAILABLE'),
            "error": globals().get('GENAI_ERROR')
        },
        "requests": {
            "available": globals().get('REQUESTS_AVAILABLE'),
            "error": globals().get('REQUESTS_ERROR')
        },
        "jwt": {
            "available": globals().get('JWT_AVAILABLE'),
            "error": globals().get('JWT_ERROR')
        }
    })

@app.route('/<path:path>')
def serve_static(path):
    try:
        response = send_from_directory(BASE_DIR, path)
        # No cache for HTML files to ensure fresh content
        if path.endswith('.html'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    # PORT 8912
    app.run(debug=True, port=8912)
