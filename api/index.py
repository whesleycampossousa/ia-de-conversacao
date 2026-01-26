import os
import io
import json
import re
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

# Daily usage limit helpers
DAILY_LIMIT_SECONDS = 600  # 10 minutes

def get_current_date():
    """Get current date in UTC as string"""
    return datetime.utcnow().strftime('%Y-%m-%d')

def get_user_usage_data(email):
    """Get or initialize usage data for user, reset if new day"""
    current_date = get_current_date()
    
    if email not in user_daily_usage:
        user_daily_usage[email] = {
            'date': current_date,
            'seconds_used': 0,
            'session_start': None
        }
    else:
        # Check if it's a new day - reset counter
        if user_daily_usage[email]['date'] != current_date:
            user_daily_usage[email] = {
                'date': current_date,
                'seconds_used': 0,
                'session_start': None
            }
    
    return user_daily_usage[email]

def get_remaining_seconds(email):
    """Get remaining seconds for user today"""
    usage_data = get_user_usage_data(email)
    used = usage_data['seconds_used']
    remaining = max(0, DAILY_LIMIT_SECONDS - used)
    return remaining

def track_usage_time(email, seconds):
    """Add seconds to user's daily usage"""
    usage_data = get_user_usage_data(email)
    usage_data['seconds_used'] += seconds
    usage_data['seconds_used'] = min(usage_data['seconds_used'], DAILY_LIMIT_SECONDS)

def check_usage_limit(email):
    """Check if user is within daily limit"""
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
    global SCENARIOS, GRAMMAR_TOPICS, GRAMMAR_TOPIC_IDS, CONTEXT_PROMPTS, SIMULATOR_PROMPTS
    SCENARIOS = load_json_file(SCENARIOS_PATH)
    GRAMMAR_TOPICS = load_json_file(GRAMMAR_PATH)
    GRAMMAR_TOPIC_IDS = {g.get('id') for g in GRAMMAR_TOPICS}
    CONTEXT_PROMPTS = {s.get('id'): s.get('prompt', '') for s in SCENARIOS}
    CONTEXT_PROMPTS.update({g.get('id'): g.get('prompt', '') for g in GRAMMAR_TOPICS})
    # Load simulator prompts (realistic roleplay mode)
    SIMULATOR_PROMPTS = {s.get('id'): s.get('simulator_prompt', '') for s in SCENARIOS if s.get('simulator_prompt')}
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
                "daily_limit_seconds": DAILY_LIMIT_SECONDS,
                "is_blocked": remaining <= 0
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
            "error": "Daily practice limit reached",
            "message": "You've used your 10 minutes for today. Come back tomorrow!",
            "remaining_seconds": remaining
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

### HOW TO RESPOND
- React to what they said and keep the conversation flowing.
- If there's a REAL error, correct it: "Instead of <short snippet>, say: <corrected>."
- Speak in English (simple, natural, friendly).
- 1-2 short sentences.
- **MANDATORY RULE**: Your response MUST ALWAYS end with a QUESTION for the student. NEVER end with just a statement! The student needs to know what to respond.
- suggested_words: ONLY when there is a REAL GRAMMAR ERROR; otherwise [].
- must_retry: true ONLY if suggested_words is not empty; else false.
- Return JSON: {{"en": "...", "suggested_words": [], "must_retry": false}}
"""
    else:
        # Standard scenario mode (Learning mode = structured teaching)
        if practice_mode == 'learning':
            # LEARNING MODE: Teacher with absolute leadership - NO ROLEPLAY
            full_prompt = f"""{system_prompt}

### YOU ARE A TEACHER — NOT A CONVERSATION PARTNER — NOT A SERVICE WORKER
You give STRUCTURED LESSONS. You do NOT chat. You do NOT ask opinions. You do NOT roleplay.
{conversation_history}
Student just said: "{user_text}"

### MANDATORY OPENING (First message only)
Your FIRST message MUST be: "Today you will learn how to [topic] in English."
NEVER start with roleplay greeting ("Welcome to...", "Good morning!", "What can I get you?")
NEVER act as barista/waiter/receptionist in Learning mode.

### ABSOLUTE FORBIDDEN PHRASES (NEVER USE - CRITICAL!)
- "What about you?" (BANNED - casual chat)
- "What do you think?" (BANNED - opinion question)
- "How about you?" (BANNED - casual chat)
- "Do you like...?" (BANNED - irrelevant to lesson)
- "Does that make sense?" (BANNED - condescending)
- "Ready?" / "Shall we start?" / "Would you like to learn?" (BANNED - don't ask permission)
- "Now that we've..." (BANNED - don't presume previous actions)
- "Can you try?" without clear instruction (BANNED)
- "Good morning! Welcome to..." (BANNED - this is roleplay)
- Any roleplay greeting or service worker language
- Any question asking for OPINION
- Any small talk or casual conversation

### GOLDEN RULE
If your sentence doesn't TEACH something or REQUEST PRACTICE, delete it.
Every response must contain:
- A useful phrase to learn, OR
- A model sentence, OR
- A clear practice command ("Repeat this." / "Now order using size + type.")

### LESSON FLOW (Fixed Order)
1. TEACH: Show vocabulary/options first
2. MODEL: Give example sentence
3. PRACTICE: Clear command ("Repeat this sentence." / "Order a coffee with size.")

NEVER ask before teaching. NEVER skip steps.

### NOISE HANDLING (Critical!)
If student writes nonsense, tests limits, or goes off-topic:
- IGNORE the content completely
- DO NOT react emotionally ("Oh dear!", "That sounds awful!")
- DO NOT engage with off-topic content
- REDIRECT immediately: "Let's focus on [topic]. [Practice command]."
Example: "Let's focus on ordering coffee. Repeat: I'd like a coffee, please."

### STAY ON TOPIC
If topic is "Ordering Coffee" → ONLY teach coffee ordering:
- Basic order (I'd like... / Can I have...)
- Sizes (small, medium, large)
- Types (latte, cappuccino, espresso)
- Polite expressions (please, thank you)
NOTHING ELSE. No tangents.

### RESPONSE FORMAT
- English + Portuguese translation
- End with PRACTICE COMMAND (never opinion question)
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
1-2 short sentences (max ~16 words each), end with one question.
If you correct, use: "Instead of <short snippet>, say: <corrected>." (max 4 words from the student).
Do not repeat the full student sentence.
suggested_words: 4 short words/phrases when there is a mistake or clear improvement; otherwise [].
must_retry: true if suggested_words is not empty; else false.
Return only JSON: {{"en": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.
"""
            else:
                if practice_mode == 'learning':
                    # LEARNING MODE: Strict teacher - NO ROLEPLAY - NO CONVERSATION
                    minimal_prompt = f"""{conversation_history}
Student said: "{user_text}"

YOU ARE A TEACHER. NOT a conversation partner. NOT a service worker.

BANNED PHRASES (NEVER USE):
- "What about you?" / "How about you?" / "What do you think?" (BANNED)
- "Does that make sense?" / "Do you like...?" (BANNED)
- "Ready?" / "Shall we start?" / "Would you like to learn?" (BANNED)
- "Good morning! Welcome to..." (BANNED - this is roleplay)
- Any roleplay greeting or service worker language (BANNED)
- Any opinion questions or casual chat

FIRST MESSAGE: "Today you will learn how to [topic] in English."
NEVER start with roleplay greeting.

NOISE HANDLING:
If nonsense/off-topic → IGNORE and redirect: "Let's focus on [topic]. [Practice command]."
NEVER react emotionally ("Oh dear!", "That sounds awful!").

LESSON FLOW:
1. TEACH first (show options/vocabulary)
2. MODEL (example sentence)
3. PRACTICE command ("Repeat this." / "Order using size + type.")

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
            
            # Follow-up questions by language
            follow_up_questions_en = [
                "What about you?",
                "What do you think?",
                "How about you?",
                "Does that make sense?",
                "Can you try?"
            ]
            follow_up_questions_pt = [
                "E você?",
                "O que você acha?",
                "Quer tentar?",
                "Faz sentido?",
                "O que me diz?"
            ]
            
            import random
            if lang == 'pt' or '[EN]' in text:
                question = random.choice(follow_up_questions_pt)
            else:
                question = random.choice(follow_up_questions_en)
            
            # Append the question
            return f"{text} {question}"
        
        # Apply question enforcement ONLY for learning mode (NOT simulator)
        # Simulator mode should have natural roleplay flow without forced generic questions
        if practice_mode != 'simulator':
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
            "error": "Daily practice limit reached",
            "message": "You've used your 10 minutes for today. Come back tomorrow!",
            "remaining_seconds": remaining
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
  "elogios": ["estrutura que usou bem 1", "estrutura que usou bem 2", "estrutura que usou bem 3"],
  "dicas": ["estude esta estrutura: ...", "pratique usar: ..."],
  "frase_pratica": "How would you politely ask someone to open the window?"
}}

REGRAS:
- Máximo 3 correções (foque nas mais importantes)
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
      "comentarioBreve": "Comentário de 1 frase explicando se a frase foi boa ou não e por quê",
      "tag": "Estrutura Incorreta|Incorreta, mas Compreensível|Correta, mas Pouco Natural",
      "explicacaoDetalhada": "Explicação detalhada do erro e como corrigir (se houver erro)"
    }}
  ],
  "elogios": ["elogio específico 1", "elogio específico 2", "elogio específico 3", "elogio específico 4"],
  "dicas": ["dica construtiva 1", "dica construtiva 2"],
  "frase_pratica": "próxima frase em inglês para o aluno treinar neste contexto"
}}

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
        return f'<voice name="pt-BR-Wavenet-C"><lang xml:lang="pt-BR">{safe}</lang></voice>'

    def en_segment(value):
        safe = escape_ssml(value)
        # Slightly slower English for clarity
        return f'<voice name="en-US-Neural2-F"><lang xml:lang="en-US"><prosody rate="95%">{safe}</prosody></lang></voice>'

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
        selected_voice = data.get('voice', 'female1')  # Default voice

        # Available voices configuration
        VOICE_OPTIONS = {
            # English voices
            'female1': {'en': 'en-US-Neural2-F', 'pt': 'pt-BR-Neural2-C', 'gender': 'FEMALE', 'name': 'Sarah'},
            'female2': {'en': 'en-US-Neural2-C', 'pt': 'pt-BR-Neural2-A', 'gender': 'FEMALE', 'name': 'Emma'},
            'male1': {'en': 'en-US-Neural2-D', 'pt': 'pt-BR-Neural2-B', 'gender': 'MALE', 'name': 'James'}
        }
        
        # Validate voice selection
        if selected_voice not in VOICE_OPTIONS:
            selected_voice = 'female1'
        
        voice_config = VOICE_OPTIONS[selected_voice]
        print(f"[TTS] Selected voice: {selected_voice} ({voice_config['name']})")

        # Validate input
        is_valid, result = validate_text_input(text, max_length=500)
        if not is_valid:
            return jsonify({"error": result}), 400
        text = result

        if not text:
            return jsonify({"error": "No text provided"}), 400

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
                print(f"[CACHE] 💾 Saved audio to cache: {os.path.basename(cache_path)}")

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
        "daily_limit_seconds": DAILY_LIMIT_SECONDS,
        "is_blocked": remaining <= 0,
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
    """Transcribe audio using Deepgram Nova-2 or Groq Whisper"""
    if not (DEEPGRAM_API_KEY or GROQ_API_KEY):
        return jsonify({"error": "Transcription service not configured"}), 503
    
    if not REQUESTS_AVAILABLE:
        return jsonify({"error": "Transcription service not available - missing dependencies"}), 503
    
    # Check daily usage limit
    user_email = request.user_email
    if not is_local_request() and not check_usage_limit(user_email):
        remaining = get_remaining_seconds(user_email)
        return jsonify({
            "error": "Daily practice limit reached",
            "message": "You've used your 10 minutes for today. Come back tomorrow!",
            "remaining_seconds": remaining
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
        # "Portuguese Mode" (Bilingual) -> Groq Whisper (Best for mixed En/Pt)
        # "English Mode" (Immersion) -> Deepgram Nova-2 (Best for speed/cost)
        
        prefer_groq_for_mixed = (language_hint != 'en') # True if PT or default
        
        transcript = None
        confidence = 0.0
        provider = "none"

        # 1. Try DEEPGRAM if it's the preferred strategy checks out (English Mode) OR if it's the only option
        should_use_deepgram = DEEPGRAM_API_KEY and (not prefer_groq_for_mixed or not GROQ_API_KEY)
        
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
        
        # 2. Try GROQ if needed (Preferred for PT, or Fallback for Deepgram failure)
        # Condition: (Prefer Groq AND Groq exists) OR (Deepgram failed/skipped AND Groq exists)
        if not transcript and GROQ_API_KEY:
            # Just logs to see why we are here
            if prefer_groq_for_mixed and not transcript:
                print("[Transcription] Using Groq Whisper for Mixed/Bilingual mode...")
            elif DEEPGRAM_API_KEY:
                print("[Transcription] Falling back to Groq Whisper after Deepgram failure...")

            files = {
                'file': ('audio.webm', audio_data, 'audio/webm')
            }
            # ... rest of Groq logic follows in existing code (we just flow into it)
            
            data = {
                'model': 'whisper-large-v3',
                'response_format': 'verbose_json',
                'temperature': 0.0,
                'prompt': "Transcreva a fala do usuário exatamente."
            }
            
            if language_hint:
                data['language'] = language_hint
            
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
