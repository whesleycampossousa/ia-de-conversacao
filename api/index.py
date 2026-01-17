import os
import io
import json
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

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except Exception as e:
    DOTENV_AVAILABLE = False
    DOTENV_ERROR = str(e)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

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

# Configure Gemini
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
model = None
if GOOGLE_API_KEY and GENAI_AVAILABLE:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
        print("[OK] Gemini model initialized successfully")
    except Exception as e:
        print(f"Gemini Init Error: {e}")
elif not GENAI_AVAILABLE:
    print(f"WARNING: Google GenAI not available: {globals().get('GENAI_ERROR')}")
else:
    print("WARNING: GOOGLE_API_KEY not set!")

# Configure Groq Whisper for speech-to-text
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

if GROQ_API_KEY:
    print("[OK] Groq API key configured for speech-to-text")
else:
    print("[WARNING] GROQ_API_KEY not set - transcription will not be available")

# Session storage (in production, use Redis or database)
user_sessions = {}
user_conversations = {}  # Store conversations per user
user_daily_usage = {}  # Track daily usage per email: {email: {date: str, seconds_used: int, session_start: timestamp}}

# Authentication decorator
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
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

SCENARIOS = load_json_file(SCENARIOS_PATH)
GRAMMAR_TOPICS = load_json_file(GRAMMAR_PATH)

# Retrieve grammar topics endpoint
@app.route('/api/grammar-topics', methods=['GET'])
def get_grammar_topics():
    return jsonify(GRAMMAR_TOPICS)

# Merge prompts
CONTEXT_PROMPTS = {s['id']: s['prompt'] for s in SCENARIOS}
CONTEXT_PROMPTS.update({g['id']: g['prompt'] for g in GRAMMAR_TOPICS})

# Email whitelist configuration
AUTHORIZED_EMAILS_FILE = os.path.join(BASE_DIR, 'authorized_emails.json')
ADMIN_EMAIL = 'everydayconversation1991@gmail.com'
ADMIN_PASSWORD = '1234567'

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
    if not GOOGLE_API_KEY or not model:
        return jsonify({"error": "AI service not configured"}), 500

    # Check daily usage limit
    user_email = request.user_email
    if not check_usage_limit(user_email):
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

    # Validate input
    is_valid, result = validate_text_input(user_text, max_length=500)
    if not is_valid:
        return jsonify({"error": result}), 400

    user_text = result

    # Get System Prompt based on context
    system_prompt = CONTEXT_PROMPTS.get(context_key, CONTEXT_PROMPTS.get('coffee_shop', ''))

    # Check if this is a grammar/learning topic
    is_grammar_topic = context_key in ['verb_to_be', 'greetings', 'articles', 'plurals', 
                                        'demonstratives', 'subject_pronouns', 'possessives',
                                        'present_simple', 'present_continuous', 'basic_questions']

    if is_grammar_topic:
        if lesson_lang == 'pt':
            # PORTUGUESE MODE: Explanations in PT-BR with English examples marked
            full_prompt = f"""{system_prompt}

### MODO PORTUGUÊS-INGLÊS (BILINGUAL)
Você é uma professora de inglês carismática e acolhedora. Você fala em PORTUGUÊS BRASILEIRO, mas sempre que mostrar exemplos em inglês, você envolve eles em tags: [EN]exemplo em inglês[/EN]

### SITUAÇÃO ATUAL
O aluno disse: "{user_text}"

### ESTRATÉGIA DE RESPOSTA
1. Se o aluno mostrar confusão ou cometer um erro:
   - **Valide:** Tranquilize ele carinhosamente ("Isso é super normal! 😊")
   - **Micro-Explique:** Uma frase simples explicando o conceito EM PORTUGUÊS
   - **Exemplo:** Dê um exemplo em inglês: [EN]I am happy[/EN] significa "eu estou feliz"
   - **Prática Guiada:** Peça para ele tentar algo simples

2. Se o aluno acertar:
   - **Celebre:** Reconheça o sucesso com entusiasmo!
   - **Avance:** Faça uma pergunta um pouco mais desafiadora

### REGRAS CRÍTICAS
- Fale PORTUGUÊS para explicações
- Envolva TODAS as frases/palavras em inglês em [EN]...[/EN]
- Seja acolhedor(a), paciente e motivador(a)
- Mantenha respostas curtas (1-2 frases no máximo)
- Retorne APENAS um JSON: {{"pt": "sua resposta com [EN]exemplos[/EN]"}}

EXEMPLO DE RESPOSTA:
{{"pt": "Muito bem! Agora tente dizer como você está se sentindo. Por exemplo: [EN]I am excited[/EN] significa 'estou animado'. Como você está agora?"}}
"""
        else:
            # ENGLISH MODE: Original immersion-based approach
            full_prompt = f"""{system_prompt}

### CURRENT SITUATION
The student just said: "{user_text}"

### YOUR RESPONSE STRATEGY
1. If they show confusion or make a mistake:
   - **Validate:** Reassure them warmly ("That's totally normal! 😊")
   - **Micro-Explain:** One simple sentence explaining the concept
   - **Example:** One clear, relatable example
   - **Guided Practice:** Ask a simple question with a sentence starter if needed

2. If they answer correctly:
   - **Celebrate:** Acknowledge their success enthusiastically!
   - **Build on it:** Ask a slightly harder follow-up question to keep practicing

### CRITICAL RULES
- Speak ONLY in English (use very simple words for beginners)
- Keep your response to 1-2 sentences MAX
- Be warm, patient, and encouraging
- Focus on making them USE English, not just study it
- Return ONLY a JSON object: {{"en": "your response"}}

Note: NO Portuguese translation needed for learning mode - immersion is key for beginners!
"""
    else:
        # Standard conversation mode - with Portuguese translation
        full_prompt = f"""{system_prompt}

IMPORTANT: You are also an English teacher. Evaluate the user's grammar and vocabulary.

User says: "{user_text}"

Response rules:
1. Respond naturally in English to continue the conversation.
2. Provide a Portuguese translation of your response.
3. Mentally note any grammar/vocabulary errors for later feedback.
4. Return ONLY a JSON object in this exact format: {{"en": "your response", "pt": "tradução"}}

Keep responses to 1-2 sentences maximum.
"""

    try:
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

        return jsonify({"text": ai_text, "translation": ai_trans, "lessonLang": lesson_lang})
    except Exception as e:
        print(f"[CHAT] Error: {e}")
        return jsonify({"error": "Failed to generate response. Please try again."}), 500


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
2. Depois: Identifique apenas os 2-3 erros MAIS IMPORTANTES (se houver)
3. Dicas práticas e construtivas para evoluir

Gere um relatório em português e retorne APENAS um JSON válido seguindo EXATAMENTE este formato:
{{
  "titulo": "Frase MUITO MOTIVADORA e positiva sobre o progresso (ex: 'Você está indo muito bem!', 'Ótimo progresso!')",
  "emoji": "emoji positivo (🎉, ✨, 🌟, 👏, 💪)",
  "tom": "positivo e encorajador",
  "correcoes": [
    {{"ruim": "frase EXATA como o aluno falou", "boa": "versão corrigida", "explicacao": "breve explicação do erro (1 frase)"}}
  ],
  "elogios": ["elogio específico 1", "elogio específico 2", "elogio específico 3", "elogio específico 4"],
  "dicas": ["dica construtiva 1", "dica construtiva 2"],
  "frase_pratica": "próxima frase em inglês para o aluno treinar neste contexto"
}}

REGRAS CRÍTICAS PARA TOM ENCORAJADOR:
- SEMPRE comece com 3-4 elogios ANTES das correções
- Máximo 3 correções (foque apenas nos erros mais importantes)
- Se houver 3 correções, DEVE haver pelo menos 4 elogios
- Tom SEMPRE positivo e motivador
- Elogios devem ser ESPECÍFICOS sobre o que o aluno fez bem
- Correções devem incluir "explicacao" do porquê está errado
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

def convert_to_bilingual_ssml(text):
    """Convert text with [EN]...[/EN] tags to SSML with language switching"""
    import re
    
    # First clean the text of emojis and formatting
    text = clean_text_for_tts(text)
    
    # Start building SSML
    ssml_parts = ['<speak>']
    
    # Split text by [EN]...[/EN] tags
    # Pattern matches [EN]content[/EN] and captures the content
    pattern = r'\[EN\](.*?)\[/EN\]'
    
    last_end = 0
    for match in re.finditer(pattern, text):
        # Add Portuguese text before this match
        pt_text = text[last_end:match.start()].strip()
        if pt_text:
            ssml_parts.append(f'<lang xml:lang="pt-BR">{pt_text}</lang>')
        
        # Add English text (the matched content)
        en_text = match.group(1).strip()
        if en_text:
            ssml_parts.append(f'<lang xml:lang="en-US">{en_text}</lang>')
        
        last_end = match.end()
    
    # Add any remaining Portuguese text after the last match
    remaining = text[last_end:].strip()
    if remaining:
        ssml_parts.append(f'<lang xml:lang="pt-BR">{remaining}</lang>')
    
    ssml_parts.append('</speak>')
    
    return ''.join(ssml_parts)

@app.route('/api/tts', methods=['POST'])
@limiter.limit("60 per minute")
@require_auth
def tts():
    """Text-to-Speech endpoint using Google Cloud TTS REST API with bilingual SSML support"""
    data = request.json or {}
    text = data.get('text')
    speed = float(data.get('speed', 1.0))
    lesson_lang = data.get('lessonLang', 'en')  # 'en', 'pt', or auto-detect

    # Validate input
    is_valid, result = validate_text_input(text, max_length=500)
    if not is_valid:
        return jsonify({"error": result}), 400

    text = result

    # Check if Google API key is available
    if not GOOGLE_API_KEY:
        return jsonify({"error": "TTS service not configured - missing API key"}), 503

    # Check if requests library is available
    if not REQUESTS_AVAILABLE:
        return jsonify({"error": "TTS service not available - missing dependencies"}), 503

    try:
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_API_KEY}"
        
        # Check if text contains [EN]...[/EN] tags (bilingual mode)
        has_bilingual_tags = '[EN]' in text and '[/EN]' in text
        
        # Debug logging
        print(f"[TTS] lessonLang: {lesson_lang}, has_bilingual_tags: {has_bilingual_tags}")
        print(f"[TTS] Text preview: {text[:100]}...")
        
        # Portuguese always uses natural 1.0x speed (native speakers)
        pt_speed = 1.0
        
        # Determine if we should use Portuguese voice
        # Use PT voice if: has bilingual tags OR lessonLang is 'pt'
        use_portuguese = has_bilingual_tags or lesson_lang == 'pt'
        
        if has_bilingual_tags:
            # BILINGUAL MODE: Convert to SSML with language switching
            ssml_text = convert_to_bilingual_ssml(text)
            
            payload = {
                "input": {"ssml": ssml_text},
                "voice": {
                    "languageCode": "pt-BR",
                    "name": "pt-BR-Journey-F",  # Chirp HD/Journey - most natural voice
                    "ssmlGender": "FEMALE"
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": pt_speed  # Always 1.0x for Portuguese
                }
            }
        elif lesson_lang == 'pt':
            # Pure Portuguese (no tags, but PT mode selected)
            payload = {
                "input": {"text": clean_text_for_tts(text)},
                "voice": {
                    "languageCode": "pt-BR",
                    "name": "pt-BR-Journey-F",  # Chirp HD/Journey - most natural voice
                    "ssmlGender": "FEMALE"
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": pt_speed  # Always 1.0x for Portuguese
                }
            }
        else:
            # ENGLISH MODE (default): Use English voice
            payload = {
                "input": {"text": clean_text_for_tts(text)},
                "voice": {
                    "languageCode": "en-US",
                    "name": "en-US-Studio-O",
                    "ssmlGender": "FEMALE"
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": speed
                }
            }

        response = requests.post(url, json=payload, timeout=15)
        
        # Fallback voice hierarchy for English mode only
        if response.status_code != 200 and not has_bilingual_tags and lesson_lang != 'pt':
            print(f"[TTS] Studio voice failed ({response.status_code}), trying Journey voice...")
            payload["voice"]["name"] = "en-US-Journey-F"
            response = requests.post(url, json=payload, timeout=15)
        
        # If Journey voice fails, try Neural2 voice
        if response.status_code != 200:
            print(f"[TTS] Journey voice failed ({response.status_code}), trying Neural2 voice...")
            payload["voice"]["name"] = "en-US-Neural2-C"
            response = requests.post(url, json=payload, timeout=15)
        
        # If Neural2 fails, try Standard voice (most compatible)
        if response.status_code != 200:
            print(f"[TTS] Neural2 voice failed ({response.status_code}), trying Standard voice...")
            payload["voice"]["name"] = "en-US-Standard-C"
            response = requests.post(url, json=payload, timeout=15)
        
        if response.status_code != 200:
            error_msg = response.text[:500] if response.text else "Unknown error"
            print(f"[TTS] All voices failed. Status: {response.status_code}, Error: {error_msg}")
            return jsonify({
                "error": "Text-to-speech temporarily unavailable",
                "details": f"API returned status {response.status_code}"
            }), 503

        # Extract audio content from response
        response_data = response.json()
        audio_content = response_data.get('audioContent')
        
        if not audio_content:
            return jsonify({"error": "No audio content received from TTS API"}), 503

        # Decode base64 audio
        audio_data = base64.b64decode(audio_content)

        mp3_fp = io.BytesIO(audio_data)
        mp3_fp.seek(0)
        
        return send_file(
            mp3_fp,
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="response.mp3"
        )

    except requests.exceptions.Timeout:
        print("[TTS] Request timeout")
        return jsonify({"error": "Text-to-speech request timed out"}), 504
    except requests.exceptions.RequestException as e:
        print(f"[TTS] Request error: {e}")
        return jsonify({
            "error": "Text-to-speech temporarily unavailable",
            "details": str(e)
        }), 503
    except Exception as e:
        print(f"[TTS] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": "Text-to-speech temporarily unavailable",
            "details": str(e)
        }), 503

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
    """Transcribe audio using Groq Whisper API"""
    if not GROQ_API_KEY:
        return jsonify({"error": "Transcription service not configured"}), 503
    
    if not REQUESTS_AVAILABLE:
        return jsonify({"error": "Transcription service not available - missing dependencies"}), 503
    
    # Check daily usage limit
    user_email = request.user_email
    if not check_usage_limit(user_email):
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
    
    if audio_file.filename == '':
        return jsonify({"error": "Empty audio file"}), 400
    
    try:
        # Read audio data
        audio_data = audio_file.read()
        
        if len(audio_data) == 0:
            return jsonify({"error": "Audio file is empty"}), 400
        
        # Prepare request to Groq
        files = {
            'file': ('audio.webm', audio_data, 'audio/webm')
        }
        
        data = {
            'model': 'whisper-large-v3',  # Best Whisper model - supports auto language detection
            # 'language' omitted to enable automatic detection (supports Portuguese + English)
            'response_format': 'verbose_json',  # Get confidence scores and detected language
            'temperature': 0.0  # More deterministic
        }
        
        headers = {
            'Authorization': f'Bearer {GROQ_API_KEY}'
        }
        
        # Call Groq API
        response = requests.post(
            GROQ_API_URL,
            files=files,
            data=data,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Extract transcript
        transcript = result.get('text', '').strip()
        
        if not transcript:
            return jsonify({"error": "Could not transcribe audio - no speech detected"}), 400
        
        # Calculate average confidence if available
        confidence = 0.95  # Groq doesn't provide per-word confidence, use default high value
        if 'segments' in result and result['segments']:
            # If segments are available, we could calculate from them
            # but for simplicity, we'll use a default high confidence
            confidence = 0.95
        
        return jsonify({
            "transcript": transcript,
            "confidence": confidence,
            "success": True,
            "language": result.get('language', 'en')
        })
        
    except requests.exceptions.Timeout:
        return jsonify({"error": "Transcription timeout - please try again"}), 504
    except requests.exceptions.RequestException as e:
        print(f"Groq API error: {e}")
        return jsonify({
            "error": "Transcription failed",
            "message": f"Connection error: {str(e)}",
            "type": type(e).__name__
        }), 500
    except Exception as e:
        print(f"Transcription error: {e}")
        return jsonify({
            "error": "Transcription failed",
            "message": str(e)
        }), 500

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
        return send_from_directory(BASE_DIR, path)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    # CHANGED: PORT 7910
    app.run(debug=True, port=7910)
