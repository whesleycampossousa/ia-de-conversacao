import os



import io



import json



import re



import time



import random



import unicodedata



import sys



from difflib import SequenceMatcher



from collections import Counter, deque



from types import SimpleNamespace



try:



    import jwt



    JWT_AVAILABLE = True



except Exception as e:



    JWT_AVAILABLE = False



    JWT_ERROR = str(e)



    # Provide minimal exception types so handlers don't crash



    class _JwtMissing:



        def encode(self, *args, **kwargs):



            raise RuntimeError("JWT not available")



        def decode(self, *args, **kwargs):



            raise RuntimeError("JWT not available")



        class ExpiredSignatureError(Exception):



            pass



        class InvalidTokenError(Exception):



            pass



    jwt = _JwtMissing()







from datetime import datetime, timedelta, timezone



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



    from google import genai



    GENAI_AVAILABLE = True



    GENAI_PROVIDER = "google.genai"



except Exception as e:



    GENAI_AVAILABLE = False



    GENAI_PROVIDER = None



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



app.json.ensure_ascii = False  # Return UTF-8 characters directly in JSON responses







# Init CORS



ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '')



# Handle empty or malformed ALLOWED_ORIGINS



if ALLOWED_ORIGINS and ALLOWED_ORIGINS.strip():



    origins_list = [o.strip() for o in ALLOWED_ORIGINS.split(',') if o.strip()]



else:
    # Default to the production domain; set ALLOWED_ORIGINS in Vercel env to override.
    origins_list = ['https://ia-de-conversacao.vercel.app', 'http://localhost:4344']







if CORS_AVAILABLE:



    try:



        supports_credentials = origins_list != '*'



        CORS(app, origins=origins_list, supports_credentials=supports_credentials)



        print(f"[OK] CORS initialized with origins: {origins_list}")



    except Exception as e:



        print(f"[WARNING] CORS init failed: {e}")



        # Fallback to wildcard if specific origins fail



        try:



            CORS(app, origins='*', supports_credentials=False)



            print("[OK] CORS initialized with wildcard fallback")



        except:



            pass







@app.after_request
def add_runtime_headers(response):
    """Allow first-party microphone use and keep runtime headers explicit."""
    response.headers.setdefault('Permissions-Policy', 'microphone=(self), camera=()')
    return response


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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL_NAME = os.environ.get("OPENAI_MODEL_NAME", os.environ.get("OPENAI_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"
QWEN_API_KEY = (os.environ.get("QWEN_API_KEY", "") or os.environ.get("DASHSCOPE_API_KEY", "")).strip()



QWEN_TTS_ENDPOINT = os.environ.get(



    "QWEN_TTS_ENDPOINT",



    "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",



).strip()



QWEN_VOICE_ENROLLMENT_ENDPOINT = os.environ.get(



    "QWEN_VOICE_ENROLLMENT_ENDPOINT",



    "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization",



).strip()



QWEN_TTS_MODEL = os.environ.get("QWEN_TTS_MODEL", "qwen3-tts-flash").strip() or "qwen3-tts-flash"



QWEN_TTS_CLONE_MODEL = os.environ.get("QWEN_TTS_CLONE_MODEL", "qwen3-tts-vc-2026-01-22").strip() or "qwen3-tts-vc-2026-01-22"



QWEN_TTS_VOICE = os.environ.get("QWEN_TTS_VOICE", "Cherry").strip() or "Cherry"



QWEN_TTS_CLONE_VOICE = os.environ.get("QWEN_TTS_CLONE_VOICE", "").strip()



QWEN_TTS_CLONE_PREFIX = os.environ.get("QWEN_TTS_CLONE_PREFIX", "clone16").strip() or "clone16"



try:



    QWEN_TTS_TIMEOUT_SEC = int(os.environ.get("QWEN_TTS_TIMEOUT_SEC", "30"))



except Exception:



    QWEN_TTS_TIMEOUT_SEC = 30



QWEN_TTS_TIMEOUT_SEC = max(5, min(QWEN_TTS_TIMEOUT_SEC, 120))



QWEN_VOICE_CACHE_FILE = os.path.join(CACHE_ROOT, "qwen_voice_cache.json")



try:



    GEMINI_THINKING_BUDGET = int(os.environ.get("GEMINI_THINKING_BUDGET", "0"))



except Exception:



    GEMINI_THINKING_BUDGET = 0



DEFAULT_GEN_CONFIG = {"temperature": 0.8}



if GEMINI_THINKING_BUDGET >= 0:



    DEFAULT_GEN_CONFIG["thinking_config"] = {"thinking_budget": GEMINI_THINKING_BUDGET}



GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")).strip() or "gemini-2.0-flash"



LEARNING_CORRECTION_KIND_ENABLED = os.environ.get("LEARNING_CORRECTION_KIND_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")



model = None
genai_client = None
openai_fallback_adapter = None
cached_models = {}  # Store cached models by context







def _extract_text_from_genai_response(response):



    """Best-effort text extraction from google.genai responses."""



    text = getattr(response, 'text', None)



    if text:



        return text







    parts_text = []



    candidates = getattr(response, 'candidates', None) or []



    for candidate in candidates:



        content = getattr(candidate, 'content', None)



        if not content:



            continue



        parts = getattr(content, 'parts', None) or []



        for part in parts:



            part_text = getattr(part, 'text', None)



            if part_text:



                parts_text.append(part_text)



    return "\n".join(parts_text).strip()







def _is_model_not_found_error(error_text):



    err = (error_text or "").lower()



    return any(marker in err for marker in [



        "404",



        "not_found",



        "not found for api version",



        "is not supported for generatecontent",



        "unknown model",



    ])







def _is_model_quota_or_rate_error(error_text):
    err = (error_text or "").lower()
    return any(marker in err for marker in [
        "429",
        "too many requests",
        "resource_exhausted",
        "resource exhausted",
        "quota exceeded",
        "quota",
        "rate limit",
        "ratelimit",
        "free_tier_requests",
    ])


def _is_transient_model_error(error_text):
    err = (error_text or "").lower()
    return _is_model_quota_or_rate_error(err) or any(marker in err for marker in [
        "503",
        "unavailable",
        "overloaded",
        "high demand",
        "deadline exceeded",
        "timeout",
    ])


class OpenAIModelAdapter:



    """Compatibility adapter with a generate_content() interface."""



    def __init__(self, api_key, model_name, system_instruction="", default_generation_config=None):



        self.api_key = (api_key or "").strip()



        self.model_name = (model_name or "gpt-4o-mini").strip() or "gpt-4o-mini"



        self.system_instruction = (system_instruction or "").strip()



        self.default_generation_config = default_generation_config or {}



    def _compose_prompt(self, prompt):



        user_prompt = prompt or ""



        if not self.system_instruction:



            return user_prompt



        return f"{self.system_instruction}\n\n{user_prompt}"



    def _compose_config(self, generation_config=None):



        config = dict(self.default_generation_config)



        if isinstance(generation_config, dict):



            for key, value in generation_config.items():



                if value is not None:



                    config[key] = value



        return config or None



    def generate_content(self, prompt, generation_config=None):



        if not self.api_key:



            raise RuntimeError("OPENAI_API_KEY not configured")



        if not REQUESTS_AVAILABLE:



            raise RuntimeError("requests library not available for OpenAI fallback")



        combined_prompt = self._compose_prompt(prompt)



        config = self._compose_config(generation_config)



        temperature = 0.8



        max_tokens = 2048



        if isinstance(config, dict):



            if "temperature" in config:



                temperature = config.get("temperature")



            if "max_output_tokens" in config:



                max_tokens = config.get("max_output_tokens")



            elif "maxOutputTokens" in config:



                max_tokens = config.get("maxOutputTokens")



        timeout_sec = int(os.environ.get("OPENAI_TIMEOUT_SEC", "25"))



        response = requests.post(



            "https://api.openai.com/v1/chat/completions",



            headers={



                "Authorization": f"Bearer {self.api_key}",



                "Content-Type": "application/json",



            },



            json={



                "model": self.model_name,



                "temperature": temperature,



                "max_tokens": max_tokens,



                "messages": [



                    {"role": "user", "content": combined_prompt}



                ],



            },



            timeout=timeout_sec,



        )



        if response.status_code >= 400:



            raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text}")



        data = response.json()



        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")



        if isinstance(content, list):



            content = "".join(



                part.get("text", "") if isinstance(part, dict) else str(part)



                for part in content



            )



        return SimpleNamespace(text=(content or "").strip())



class GeminiModelAdapter:
    """Compatibility adapter with a generate_content() interface."""







    def __init__(self, client, model_name, system_instruction="", default_generation_config=None, fallback_adapter=None):
        self.client = client



        self.model_name = model_name



        self.system_instruction = (system_instruction or "").strip()



        self.default_generation_config = default_generation_config or {}



        self.fallback_adapter = fallback_adapter




    def _compose_prompt(self, prompt):



        user_prompt = prompt or ""



        if not self.system_instruction:



            return user_prompt



        return f"{self.system_instruction}\n\n{user_prompt}"







    def _compose_config(self, generation_config=None):



        config = dict(self.default_generation_config)



        if isinstance(generation_config, dict):



            for key, value in generation_config.items():



                if value is not None:



                    config[key] = value



        return config or None







    def generate_content(self, prompt, generation_config=None):



        combined_prompt = self._compose_prompt(prompt)



        config = self._compose_config(generation_config)



        kwargs = {



            "model": self.model_name,



            "contents": combined_prompt



        }



        if config:



            kwargs["config"] = config







        # Retry with exponential backoff for 503/UNAVAILABLE errors



        max_retries = 3



        fallback_model = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash").strip()



        last_error = None







        for attempt in range(max_retries):



            try:



                response = self.client.models.generate_content(**kwargs)



                text = _extract_text_from_genai_response(response)



                return SimpleNamespace(text=text or "")



            except Exception as e:



                last_error = e



                err_str = str(e).lower()



                is_quota_or_rate_error = _is_model_quota_or_rate_error(err_str)
                is_retryable = is_quota_or_rate_error or _is_transient_model_error(err_str)



                if not is_retryable:



                    if _is_model_not_found_error(err_str):



                        print(f"[GEMINI] Model '{self.model_name}' not found/unsupported. Trying fallback model...")



                        break



                    raise  # Non-retryable error, raise immediately







                if is_quota_or_rate_error:
                    print(f"[GEMINI] Quota/rate limit on '{self.model_name}'. Trying fallback model/provider...")
                    break

                wait_time = (2 ** attempt) + random.uniform(0, 1)



                print(f"[GEMINI] 503/UNAVAILABLE on attempt {attempt + 1}/{max_retries}, retrying in {wait_time:.1f}s...")



                time.sleep(wait_time)







        # All retries with primary model failed — try fallback model



        if fallback_model and fallback_model != self.model_name:



            try:



                print(f"[GEMINI] Primary model '{self.model_name}' unavailable after {max_retries} retries. Falling back to '{fallback_model}'...")



                fallback_kwargs = dict(kwargs)



                fallback_kwargs["model"] = fallback_model



                # Remove thinking_config if fallback model doesn't support it



                if fallback_kwargs.get("config") and isinstance(fallback_kwargs["config"], dict):



                    fallback_kwargs["config"] = {k: v for k, v in fallback_kwargs["config"].items() if k != "thinking_config"}



                response = self.client.models.generate_content(**fallback_kwargs)



                text = _extract_text_from_genai_response(response)



                print(f"[GEMINI] Fallback model '{fallback_model}' succeeded!")



                return SimpleNamespace(text=text or "")



            except Exception as fallback_err:



                print(f"[GEMINI] Fallback model also failed: {fallback_err}")







        if self.fallback_adapter:



            try:



                print("[GEMINI] Trying OpenAI fallback adapter...")



                return self.fallback_adapter.generate_content(prompt, generation_config=generation_config)



            except Exception as fallback_adapter_err:



                print(f"[OPENAI] Fallback adapter failed: {fallback_adapter_err}")



        # Everything failed — raise the original error
        raise last_error







if OPENAI_API_KEY and REQUESTS_AVAILABLE:



    try:



        openai_fallback_adapter = OpenAIModelAdapter(



            OPENAI_API_KEY,



            OPENAI_MODEL_NAME,



            default_generation_config=DEFAULT_GEN_CONFIG



        )



        print(f"[OK] OpenAI fallback adapter initialized successfully ({OPENAI_MODEL_NAME})")



    except Exception as openai_init_err:



        print(f"OpenAI Init Error: {openai_init_err}")



if GOOGLE_API_KEY and GENAI_AVAILABLE:
    try:



        genai_client = genai.Client(api_key=GOOGLE_API_KEY)



        # Base model (without context-specific system instruction)



        model = GeminiModelAdapter(



            genai_client,



            GEMINI_MODEL_NAME,



            default_generation_config=DEFAULT_GEN_CONFIG,



            fallback_adapter=openai_fallback_adapter



        )
        print(f"[OK] Gemini model initialized successfully ({GENAI_PROVIDER}, {GEMINI_MODEL_NAME})")



        print("[OK] Prompt adapter cache enabled - context prompts are reused per context/mode")



    except Exception as e:



        print(f"Gemini Init Error: {e}")



elif not GENAI_AVAILABLE:



    print(f"WARNING: Google GenAI not available: {globals().get('GENAI_ERROR')}")



else:



    print("WARNING: GOOGLE_API_KEY not set!")



if not model and openai_fallback_adapter:



    model = openai_fallback_adapter



    print(f"[OK] Using OpenAI fallback adapter as active model ({OPENAI_MODEL_NAME})")




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
INCIDENT_USAGE_RESET_DATES = {
    date.strip()
    for date in os.environ.get("INCIDENT_USAGE_RESET_DATES", "2026-06-09").split(",")
    if date.strip()
}



live_activity_events = deque(maxlen=12000)



live_user_activity = {}







def _utc_now():



    # Keep naive UTC for compatibility with existing date math and storage.



    # This avoids datetime.utcnow() deprecation on newer Python versions.



    return datetime.now(timezone.utc).replace(tzinfo=None)







def _trim_live_metrics(now=None):



    now = now or _utc_now()



    cutoff = now - timedelta(hours=24)



    while live_activity_events and live_activity_events[0]['timestamp'] < cutoff:



        live_activity_events.popleft()



    for user_id, info in list(live_user_activity.items()):



        if info.get('last_seen', cutoff) < cutoff:



            del live_user_activity[user_id]







def record_live_activity(user_id, email, endpoint, status='ok', context='', mode='', response_ms=None, extra=None):



    now = _utc_now()



    payload = {



        "timestamp": now,



        "user_id": user_id or "unknown",



        "email": (email or "").lower(),



        "endpoint": endpoint,



        "status": status,



        "context": context or "",



        "mode": mode or "",



        "response_ms": float(response_ms) if isinstance(response_ms, (int, float)) else None



    }



    if extra:



        payload.update(extra)



    live_activity_events.append(payload)







    state = live_user_activity.get(payload["user_id"], {



        "email": payload["email"],



        "first_seen": now,



        "messages": 0



    })



    state["email"] = payload["email"] or state.get("email", "")



    state["last_seen"] = now



    state["last_endpoint"] = endpoint



    state["last_context"] = payload["context"]



    state["last_mode"] = payload["mode"]



    state["last_status"] = status



    if endpoint in ('/api/chat', '/api/free-conversation') and status == 'ok':



        state["messages"] = int(state.get("messages", 0)) + 1



    if payload["response_ms"] is not None:



        state["last_response_ms"] = round(payload["response_ms"], 2)



    live_user_activity[payload["user_id"]] = state



    _update_weekly_activity_from_event(payload)



    _trim_live_metrics(now)







def _int_env(name, default):



    try:



        return int(os.environ.get(name, default))



    except Exception:



        return default







# Max messages to keep for context (each message = user or AI entry)



HISTORY_MAX_MESSAGES = _int_env('CONTEXT_HISTORY_MESSAGES', 12)



HISTORY_MAX_MESSAGES = max(6, min(HISTORY_MAX_MESSAGES, 40))



MAX_OUTPUT_TOKENS_LEARNING = max(128, _int_env('MAX_OUTPUT_TOKENS_LEARNING', 320))



MAX_OUTPUT_TOKENS_SIMULATOR = max(192, _int_env('MAX_OUTPUT_TOKENS_SIMULATOR', 520))



MAX_OUTPUT_TOKENS_GUIDED = max(96, _int_env('MAX_OUTPUT_TOKENS_GUIDED', 240))



MAX_OUTPUT_TOKENS_SUGGESTIONS = max(96, _int_env('MAX_OUTPUT_TOKENS_SUGGESTIONS', 220))



MAX_OUTPUT_TOKENS_REPORT = max(600, _int_env('MAX_OUTPUT_TOKENS_REPORT', 1800))







PORTAL_DAILY_TRIAL_LIMIT_SECONDS = max(60, _int_env('PORTAL_DAILY_TRIAL_LIMIT_SECONDS', 600))


def _portal_trial_today_key():
    try:
        return usage_now().strftime('%Y-%m-%d')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')


def _portal_trial_email():
    email = (request.headers.get('X-Portal-Email') or request.args.get('email') or '').strip().lower()
    if email:
        return email
    # Use IP-derived key to avoid shared bucket across all anonymous users
    ip = (request.headers.get('X-Forwarded-For', '') or request.remote_addr or '').split(',')[0].strip()
    return f'anon@{ip or "unknown"}.portal.local'


def is_portal_daily_trial_request():
    trial = (request.headers.get('X-Portal-Trial') or request.args.get('trial') or '').strip().lower()
    if trial != 'daily-10-min':
        return False
    return True


# Authentication decorator
def require_auth(f):



    @wraps(f)



    def decorated_function(*args, **kwargs):



        auth_header = request.headers.get('Authorization')



        allow_guest = os.environ.get('ALLOW_GUEST', '0') == '1'



        # If the request has a valid JWT, use the real user identity even for trial requests.
        # This prevents admins from losing is_admin and ensures per-user usage buckets.
        if auth_header and JWT_AVAILABLE:
            try:
                _token = auth_header.replace('Bearer ', '')
                _payload = jwt.decode(_token, app.config['SECRET_KEY'], algorithms=['HS256'])
                request.user_id = _payload['user_id']
                request.user_email = _payload['email']
                request.is_admin = _payload.get('is_admin', False)
                request.is_portal_trial = is_portal_daily_trial_request()
                return f(*args, **kwargs)
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                pass  # Fall through to trial / guest / 401

        if is_portal_daily_trial_request():
            trial_email = _portal_trial_email()
            request.user_id = f"portal_trial_{trial_email.replace('@', '_at_').replace('.', '_')}"
            request.user_email = trial_email
            request.is_admin = False
            request.is_portal_trial = True
            return f(*args, **kwargs)

        if not auth_header:
            if allow_guest:



                # Guest fallback (no login) - limited, non-admin



                request.user_id = "guest"



                request.user_email = "guest@guest"



                request.is_admin = False



                return f(*args, **kwargs)



            return jsonify({"error": "No authorization token provided"}), 401







        if not JWT_AVAILABLE:



            return jsonify({"error": "Auth system not available"}), 503







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







        if not JWT_AVAILABLE:



            return jsonify({"error": "Auth system not available"}), 503







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



def _safe_int_env(name, default):



    raw_value = os.environ.get(name, '').strip()



    if not raw_value:



        return default



    try:



        parsed = int(raw_value)



        return parsed if parsed >= 0 else default



    except ValueError:



        return default







# Weekly didactic analytics (persisted daily aggregates)



WEEKLY_ANALYTICS_FILE = os.path.join(CACHE_ROOT, 'weekly_activity_store.json')



WEEKLY_ANALYTICS_RETENTION_DAYS = max(35, _safe_int_env('WEEKLY_ANALYTICS_RETENTION_DAYS', 120))



WEEKLY_ANALYTICS_FLUSH_INTERVAL_SEC = max(5, _safe_int_env('WEEKLY_ANALYTICS_FLUSH_INTERVAL_SEC', 30))



weekly_activity_days = {}



weekly_activity_dirty = False



weekly_activity_last_flush = 0.0







def _empty_daily_activity_bucket():



    return {



        "practice_total": 0,



        "practice_success": 0,



        "practice_errors": 0,



        "chat_success": 0,



        "chat_must_retry": 0,



        "response_ms_sum": 0.0,



        "response_ms_count": 0,



        "mode_counts": {},



        "context_counts": {},



        "unique_users": set()



    }







def _sanitize_counter_payload(raw):



    cleaned = {}



    if not isinstance(raw, dict):



        return cleaned



    for key, value in raw.items():



        label = str(key or '').strip()[:80]



        if not label:



            continue



        try:



            parsed = int(value)



        except Exception:



            continue



        if parsed > 0:



            cleaned[label] = parsed



    return cleaned







def _sanitize_user_list(raw):



    users = set()



    if not isinstance(raw, list):



        return users



    for item in raw:



        value = str(item or '').strip().lower()



        if value and len(value) <= 200:



            users.add(value)



    return users







def _prune_weekly_activity_store(now=None):



    global weekly_activity_dirty



    reference = (now or _utc_now()).date()



    cutoff = reference - timedelta(days=WEEKLY_ANALYTICS_RETENTION_DAYS)



    removed = False



    for day_key in list(weekly_activity_days.keys()):



        try:



            day_date = datetime.strptime(day_key, '%Y-%m-%d').date()



        except Exception:



            del weekly_activity_days[day_key]



            removed = True



            continue



        if day_date < cutoff:



            del weekly_activity_days[day_key]



            removed = True



    if removed:



        weekly_activity_dirty = True







def _serialize_weekly_activity_store():



    payload_days = {}



    for day_key in sorted(weekly_activity_days.keys()):



        bucket = weekly_activity_days.get(day_key) or {}



        payload_days[day_key] = {



            "practice_total": int(bucket.get("practice_total", 0)),



            "practice_success": int(bucket.get("practice_success", 0)),



            "practice_errors": int(bucket.get("practice_errors", 0)),



            "chat_success": int(bucket.get("chat_success", 0)),



            "chat_must_retry": int(bucket.get("chat_must_retry", 0)),



            "response_ms_sum": round(float(bucket.get("response_ms_sum", 0.0)), 2),



            "response_ms_count": int(bucket.get("response_ms_count", 0)),



            "mode_counts": _sanitize_counter_payload(bucket.get("mode_counts", {})),



            "context_counts": _sanitize_counter_payload(bucket.get("context_counts", {})),



            "unique_users": sorted(list(bucket.get("unique_users", set())))



        }



    return {



        "version": 1,



        "updated_at": _utc_now().isoformat() + "Z",



        "days": payload_days



    }







def _flush_weekly_activity_store(force=False):



    global weekly_activity_dirty, weekly_activity_last_flush



    if not weekly_activity_dirty:



        return



    now_ts = time.time()



    if (not force) and (now_ts - weekly_activity_last_flush) < WEEKLY_ANALYTICS_FLUSH_INTERVAL_SEC:



        return



    try:



        directory = os.path.dirname(WEEKLY_ANALYTICS_FILE)



        if directory:



            os.makedirs(directory, exist_ok=True)



        tmp_path = WEEKLY_ANALYTICS_FILE + '.tmp'



        with open(tmp_path, 'w', encoding='utf-8') as handle:



            json.dump(_serialize_weekly_activity_store(), handle, indent=2, ensure_ascii=False)



        os.replace(tmp_path, WEEKLY_ANALYTICS_FILE)



        weekly_activity_last_flush = now_ts



        weekly_activity_dirty = False



    except Exception as e:



        print(f"[WEEKLY] Failed to save analytics store: {e}")







def _load_weekly_activity_store():



    global weekly_activity_days, weekly_activity_dirty, weekly_activity_last_flush



    weekly_activity_days = {}



    if not os.path.exists(WEEKLY_ANALYTICS_FILE):



        return



    try:



        with open(WEEKLY_ANALYTICS_FILE, 'r', encoding='utf-8') as handle:



            payload = json.load(handle)



        raw_days = payload.get('days', {}) if isinstance(payload, dict) else {}



        if not isinstance(raw_days, dict):



            raw_days = {}



        for day_key, raw_bucket in raw_days.items():



            try:



                datetime.strptime(day_key, '%Y-%m-%d')



            except Exception:



                continue



            bucket = _empty_daily_activity_bucket()



            if isinstance(raw_bucket, dict):



                bucket["practice_total"] = max(0, int(raw_bucket.get("practice_total", 0)))



                bucket["practice_success"] = max(0, int(raw_bucket.get("practice_success", 0)))



                bucket["practice_errors"] = max(0, int(raw_bucket.get("practice_errors", 0)))



                bucket["chat_success"] = max(0, int(raw_bucket.get("chat_success", 0)))



                bucket["chat_must_retry"] = max(0, int(raw_bucket.get("chat_must_retry", 0)))



                bucket["response_ms_sum"] = max(0.0, float(raw_bucket.get("response_ms_sum", 0.0)))



                bucket["response_ms_count"] = max(0, int(raw_bucket.get("response_ms_count", 0)))



                bucket["mode_counts"] = _sanitize_counter_payload(raw_bucket.get("mode_counts", {}))



                bucket["context_counts"] = _sanitize_counter_payload(raw_bucket.get("context_counts", {}))



                bucket["unique_users"] = _sanitize_user_list(raw_bucket.get("unique_users", []))



            weekly_activity_days[day_key] = bucket



        _prune_weekly_activity_store(_utc_now())



        weekly_activity_dirty = False



        weekly_activity_last_flush = time.time()



    except Exception as e:



        print(f"[WEEKLY] Failed to load analytics store: {e}")



        weekly_activity_days = {}







def _ensure_daily_activity_bucket(day_key):



    if day_key not in weekly_activity_days:



        weekly_activity_days[day_key] = _empty_daily_activity_bucket()



    return weekly_activity_days[day_key]







def _stable_activity_user(payload):



    email = str(payload.get("email") or '').strip().lower()



    if email and email not in ('guest@guest',):



        return f"email:{email}"



    user_id = str(payload.get("user_id") or '').strip().lower()



    if user_id and user_id not in ('unknown', 'anonymous', 'guest'):



        return f"user:{user_id}"



    return None







def _update_weekly_activity_from_event(payload):



    global weekly_activity_dirty



    endpoint = payload.get("endpoint")



    if endpoint not in ('/api/chat', '/api/free-conversation'):



        return



    event_time = payload.get("timestamp")



    if not isinstance(event_time, datetime):



        return







    day_key = event_time.strftime('%Y-%m-%d')



    _prune_weekly_activity_store(event_time)



    bucket = _ensure_daily_activity_bucket(day_key)







    bucket["practice_total"] += 1



    status = str(payload.get("status") or '')



    if status == 'ok':



        bucket["practice_success"] += 1



    else:



        bucket["practice_errors"] += 1







    if endpoint == '/api/chat' and status == 'ok':



        bucket["chat_success"] += 1



        if payload.get("must_retry"):



            bucket["chat_must_retry"] += 1







    response_ms = payload.get("response_ms")



    if isinstance(response_ms, (int, float)):



        bucket["response_ms_sum"] += float(response_ms)



        bucket["response_ms_count"] += 1







    mode_label = str(payload.get("mode") or 'unknown').strip()[:80] or 'unknown'



    bucket["mode_counts"][mode_label] = int(bucket["mode_counts"].get(mode_label, 0)) + 1







    context_label = str(payload.get("context") or 'unknown').strip()[:80] or 'unknown'



    bucket["context_counts"][context_label] = int(bucket["context_counts"].get(context_label, 0)) + 1







    user_key = _stable_activity_user(payload)



    if user_key:



        bucket["unique_users"].add(user_key)







    weekly_activity_dirty = True



    _flush_weekly_activity_store(force=False)







def _week_start_for(date_value):



    return date_value - timedelta(days=date_value.weekday())







def build_weekly_didactic_report(total_weeks=8):



    total_weeks = max(4, min(int(total_weeks), 16))



    _prune_weekly_activity_store(_utc_now())



    _flush_weekly_activity_store(force=False)







    today = _utc_now().date()



    current_week_start = _week_start_for(today)



    rows = []



    previous_users = None







    for offset in range(total_weeks - 1, -1, -1):



        week_start = current_week_start - timedelta(days=offset * 7)



        week_end = week_start + timedelta(days=6)



        practice_total = 0



        practice_errors = 0



        chat_success = 0



        chat_must_retry = 0



        response_sum = 0.0



        response_count = 0



        mode_counts = Counter()



        context_counts = Counter()



        users = set()







        for day_offset in range(7):



            day = week_start + timedelta(days=day_offset)



            day_key = day.strftime('%Y-%m-%d')



            bucket = weekly_activity_days.get(day_key)



            if not bucket:



                continue



            practice_total += int(bucket.get("practice_total", 0))



            practice_errors += int(bucket.get("practice_errors", 0))



            chat_success += int(bucket.get("chat_success", 0))



            chat_must_retry += int(bucket.get("chat_must_retry", 0))



            response_sum += float(bucket.get("response_ms_sum", 0.0))



            response_count += int(bucket.get("response_ms_count", 0))



            mode_counts.update(_sanitize_counter_payload(bucket.get("mode_counts", {})))



            context_counts.update(_sanitize_counter_payload(bucket.get("context_counts", {})))



            users.update(bucket.get("unique_users", set()))







        active_learners = len(users)



        avg_response_ms = round(response_sum / response_count, 2) if response_count else 0.0



        error_rate = round((practice_errors / practice_total) * 100, 2) if practice_total else 0.0



        must_retry_rate = round((chat_must_retry / chat_success) * 100, 2) if chat_success else 0.0



        avg_messages_per_active = round(practice_total / active_learners, 2) if active_learners else 0.0







        returning_learners = len(users & previous_users) if previous_users is not None else 0



        retention_rate = round((returning_learners / len(previous_users)) * 100, 2) if previous_users else 0.0







        total_mode = sum(mode_counts.values())



        learning_count = sum(count for mode, count in mode_counts.items() if mode.startswith('learning'))



        simulator_count = sum(count for mode, count in mode_counts.items() if mode.startswith('simulator'))



        guided_count = sum(count for mode, count in mode_counts.items() if mode.startswith('guided'))







        week_iso = week_start.isocalendar()



        rows.append({



            "week_id": f"{week_iso.year}-W{week_iso.week:02d}",



            "week_start": week_start.isoformat(),



            "week_end": week_end.isoformat(),



            "week_label": f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}",



            "active_learners": active_learners,



            "returning_learners": returning_learners,



            "retention_rate": retention_rate,



            "practice_messages": practice_total,



            "avg_messages_per_active": avg_messages_per_active,



            "avg_response_ms": avg_response_ms,



            "error_rate": error_rate,



            "must_retry_rate": must_retry_rate,



            "learning_share": round((learning_count / total_mode) * 100, 2) if total_mode else 0.0,



            "simulator_share": round((simulator_count / total_mode) * 100, 2) if total_mode else 0.0,



            "guided_share": round((guided_count / total_mode) * 100, 2) if total_mode else 0.0,



            "top_contexts": [



                {"context": context_name, "count": count}



                for context_name, count in context_counts.most_common(5)



            ],



            "mode_counts": dict(mode_counts)



        })



        previous_users = users







    current_week = rows[-1] if rows else {}



    return {



        "generated_at": _utc_now().isoformat() + "Z",



        "weeks": rows,



        "current_week": current_week,



        "retention_days": WEEKLY_ANALYTICS_RETENTION_DAYS



    }







_load_weekly_activity_store()



print(f"[OK] Weekly analytics loaded: {len(weekly_activity_days)} daily buckets")







WEEKEND_LIMIT_SECONDS = _safe_int_env('WEEKEND_LIMIT_SECONDS', 10800)  # 3 hours per weekend by default



USAGE_TZ_OFFSET_HOURS = _safe_int_env('USAGE_TZ_OFFSET_HOURS', 0)



TEMP_GLOBAL_UNLOCK_ENABLED = os.environ.get('TEMP_GLOBAL_UNLOCK_ENABLED', '').strip().lower() in ('1', 'true', 'yes', 'on')



REQUIRE_WEEKEND_ONLY = os.environ.get('REQUIRE_WEEKEND_ONLY', 'false').strip().lower() in ('1', 'true', 'yes', 'on')



OPEN_ACCESS_ENABLED = os.environ.get('OPEN_ACCESS_ENABLED', 'true').strip().lower() in ('1', 'true', 'yes', 'on')



TEMP_GLOBAL_UNLOCK_UNTIL_UTC_RAW = os.environ.get('TEMP_GLOBAL_UNLOCK_UNTIL_UTC', '').strip()







# --- Per-user maintenance bypass ---



# Comma-separated emails that can bypass maintenance mode with their own time limit.



# E.g. TEMP_BYPASS_EMAILS="alice@example.com,bob@example.com"



_raw_bypass = os.environ.get('TEMP_BYPASS_EMAILS', '').strip()



TEMP_BYPASS_EMAILS = {e.strip().lower() for e in _raw_bypass.split(',') if e.strip() and '@' in e.strip()}



TEMP_BYPASS_LIMIT_SECONDS = _safe_int_env('TEMP_BYPASS_LIMIT_SECONDS', 1800)  # default 30 min



TEMP_BYPASS_UNTIL_UTC_RAW = os.environ.get('TEMP_BYPASS_UNTIL_UTC', '').strip()







if TEMP_BYPASS_EMAILS:



    print(f"[BYPASS] {len(TEMP_BYPASS_EMAILS)} email(s) can bypass maintenance for {TEMP_BYPASS_LIMIT_SECONDS}s")







def parse_utc_iso(value):



    """Parse ISO datetime to naive UTC datetime. Returns None on invalid input."""



    if not value:



        return None



    raw = str(value).strip()



    if not raw:



        return None



    if raw.endswith('Z'):



        raw = raw[:-1] + '+00:00'



    try:



        parsed = datetime.fromisoformat(raw)



    except ValueError:



        return None



    if parsed.tzinfo is not None:



        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)



    return parsed







TEMP_GLOBAL_UNLOCK_UNTIL_UTC = parse_utc_iso(TEMP_GLOBAL_UNLOCK_UNTIL_UTC_RAW)



TEMP_BYPASS_UNTIL_UTC = parse_utc_iso(TEMP_BYPASS_UNTIL_UTC_RAW)







def _is_bypass_email(email):



    """Check if email is in the temporary bypass list and the bypass window is still active."""



    if not TEMP_BYPASS_EMAILS or not email:



        return False



    normalized = str(email).strip().lower()



    if normalized not in TEMP_BYPASS_EMAILS:



        return False



    # If a deadline is set, check it



    if TEMP_BYPASS_UNTIL_UTC is not None:



        return _utc_now() < TEMP_BYPASS_UNTIL_UTC



    return True  # no deadline = always active







def usage_now():



    """Current time for usage windows (supports configurable UTC offset)."""



    return _utc_now() + timedelta(hours=USAGE_TZ_OFFSET_HOURS)







def is_temporary_global_unlock_active(now_utc=None):



    """Global temporary unlock window based on UTC deadline."""



    if not TEMP_GLOBAL_UNLOCK_ENABLED:



        return False



    if TEMP_GLOBAL_UNLOCK_UNTIL_UTC is None:



        return False



    now = now_utc or _utc_now()



    return now < TEMP_GLOBAL_UNLOCK_UNTIL_UTC







def temporary_unlock_meta():



    """Metadata exposed to clients and logs for temporary unlock observability."""



    until_utc = None



    until_brt = None



    if TEMP_GLOBAL_UNLOCK_UNTIL_UTC is not None:



        until_utc = TEMP_GLOBAL_UNLOCK_UNTIL_UTC.strftime('%Y-%m-%dT%H:%M:%SZ')



        brt_deadline = TEMP_GLOBAL_UNLOCK_UNTIL_UTC + timedelta(hours=-3)



        until_brt = brt_deadline.strftime('%Y-%m-%d %H:%M:%S BRT')



    return {



        "temporary_unlock_active": is_temporary_global_unlock_active(),



        "temporary_unlock_until_utc": until_utc,



        "temporary_unlock_until_brt": until_brt



    }







def build_usage_payload(email, usage_data=None):



    """Single source of truth for usage payload across login/status endpoints."""



    is_portal_trial = bool(getattr(request, 'is_portal_trial', False))
    is_bypass = _is_bypass_email(str(email or '').strip().lower())
    usage_data = usage_data or get_user_usage_data(email, force_active=is_bypass or is_portal_trial)
    unlock = temporary_unlock_meta()



    exempt = is_usage_exempt_request()



    limit = _effective_limit(email)



    if exempt:



        remaining = limit



        blocked = False



    else:



        remaining = get_remaining_seconds(email)



        blocked = remaining <= 0



    is_active = True if is_portal_trial else (is_weekend() or is_bypass or unlock["temporary_unlock_active"])
    return {



        "remaining_seconds": remaining,



        "seconds_used": usage_data['seconds_used'],



        "weekend_limit_seconds": limit,



        "is_blocked": blocked,



        "is_weekend": is_active,



        "temporary_unlock_active": unlock["temporary_unlock_active"] or is_bypass or is_portal_trial,
        "temporary_unlock_until_utc": unlock["temporary_unlock_until_utc"],



        "temporary_unlock_until_brt": unlock["temporary_unlock_until_brt"],



        "usage_mode": "portal_daily_trial" if is_portal_trial else ("temporary_bypass" if is_bypass else ("temporary_unlock" if unlock["temporary_unlock_active"] else "normal_weekend")),

        "portal_trial": is_portal_trial
    }







def log_temporary_unlock_status():



    """Startup log for temporary unlock configuration and current state."""



    unlock = temporary_unlock_meta()



    state = "ACTIVE" if unlock["temporary_unlock_active"] else "inactive"



    print(



        "[USAGE] temporary unlock "



        f"{state}; enabled={TEMP_GLOBAL_UNLOCK_ENABLED}; "



        f"until_utc={unlock['temporary_unlock_until_utc']}; "



        f"until_brt={unlock['temporary_unlock_until_brt']}"



    )







def is_weekend():



    """Check if today is Saturday or Sunday in usage timezone, or if weekend restriction is disabled."""



    if not REQUIRE_WEEKEND_ONLY:



        return True



    return usage_now().weekday() in (5, 6)  # 5=Sat, 6=Sun







def get_weekend_key():



    """Get the Saturday date for the current weekend period.



    Returns the Saturday date string if it's a weekend, None otherwise."""



    now = usage_now()



    weekday = now.weekday()



    if weekday == 5:  # Saturday



        return now.strftime('%Y-%m-%d')



    elif weekday == 6:  # Sunday - use yesterday (Saturday)



        saturday = now - timedelta(days=1)



        return saturday.strftime('%Y-%m-%d')



    return None







def weekend_limit_label():



    """Human-readable weekend limit string for UI/messages."""



    minutes = max(1, int(round(WEEKEND_LIMIT_SECONDS / 60)))



    if minutes >= 60:



        hours = minutes / 60



        if float(hours).is_integer():



            hours = int(hours)



            return f"{hours} hour{'s' if hours != 1 else ''}"



        return f"{hours:.1f} hours"



    return f"{minutes} minutes"







def get_user_usage_data(email, force_active=False):
    """Get or initialize usage data for user, reset each weekend.



    force_active=True uses today's date as key even on weekdays (for bypass users)."""



    force_active = force_active or bool(getattr(request, 'is_portal_trial', False))

    weekend_key = get_weekend_key()




    if weekend_key is None and not force_active:



        # Weekday - return empty data (will be blocked by check_usage_limit)



        return {'date': None, 'seconds_used': 0, 'session_start': None}







    # For bypass users on weekdays, use today's date as usage key



    usage_key = weekend_key or usage_now().strftime('%Y-%m-%d')







    if email not in user_daily_usage:



        user_daily_usage[email] = {



            'date': usage_key,



            'seconds_used': 0,



            'session_start': None



        }



    else:



        # Check if it's a new period - reset counter



        if user_daily_usage[email]['date'] != usage_key:



            user_daily_usage[email] = {



                'date': usage_key,



                'seconds_used': 0,



                'session_start': None



            }







    reset_marker = f"incident-reset:{usage_key}"
    if usage_key in INCIDENT_USAGE_RESET_DATES and user_daily_usage[email].get('reset_marker') != reset_marker:
        user_daily_usage[email]['seconds_used'] = 0
        user_daily_usage[email]['session_start'] = None
        user_daily_usage[email]['reset_marker'] = reset_marker

    return user_daily_usage[email]







def _effective_limit(email):
    """Return the usage limit in seconds for this email (bypass users get their own limit)."""



    if bool(getattr(request, 'is_portal_trial', False)):

        return PORTAL_DAILY_TRIAL_LIMIT_SECONDS

    if _is_bypass_email(str(email or '').strip().lower()):
        return TEMP_BYPASS_LIMIT_SECONDS



    return WEEKEND_LIMIT_SECONDS







def get_remaining_seconds(email):
    """Get remaining seconds for user this weekend (or bypass window)"""



    is_portal_trial = bool(getattr(request, 'is_portal_trial', False))

    is_bypass = _is_bypass_email(str(email or '').strip().lower())
    if not is_portal_trial and not is_bypass and not is_weekend():
        return 0



    usage_data = get_user_usage_data(email, force_active=is_bypass or is_portal_trial)
    used = usage_data['seconds_used']



    limit = _effective_limit(email)



    remaining = max(0, limit - used)



    return remaining







def track_usage_time(email, seconds):
    """Add seconds to user's usage"""



    is_portal_trial = bool(getattr(request, 'is_portal_trial', False))

    is_bypass = _is_bypass_email(str(email or '').strip().lower())
    usage_data = get_user_usage_data(email, force_active=is_bypass or is_portal_trial)
    limit = _effective_limit(email)



    usage_data['seconds_used'] += seconds



    usage_data['seconds_used'] = min(usage_data['seconds_used'], limit)







def check_usage_limit(email):
    """Check if user is within usage limit"""



    is_portal_trial = bool(getattr(request, 'is_portal_trial', False))

    is_bypass = _is_bypass_email(str(email or '').strip().lower())
    if not is_portal_trial and not is_bypass and not is_weekend():
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







def is_usage_exempt_request():



    """Admin/local requests and active temporary global unlock are exempt."""



    try:



        if bool(getattr(request, 'is_admin', False)) or is_local_request():



            return True



        if is_temporary_global_unlock_active():



            endpoint = getattr(request, 'path', '')



            user_email = getattr(request, 'user_email', '')



            print(f"[USAGE] request unlocked; reason=temporary_unlock; endpoint={endpoint}; email={user_email}")



            return True



        return False



    except Exception:



        return is_local_request() or is_temporary_global_unlock_active()







log_temporary_unlock_status()







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



GRAMMAR_TOPIC_TITLES = {}



CONTEXT_PROMPTS = {}



SIMULATOR_PROMPTS = {}  # Simulator mode prompts for realistic roleplay



LESSONS_DB = {}  # Structured lessons for Learning mode







COMMUNICATIVE_OBJECTIVES = {



    'coffee_shop': 'Order a drink and confirm options politely.',



    'restaurant': 'Order food, sides, and drinks politely.',



    'airport': 'Check in, confirm flight details, and baggage.',



    'hotel': 'Check in and resolve stay details.',



    'supermarket': 'Ask for items and handle checkout.',



    'doctor': 'Explain symptoms and understand advice.',



    'bank': 'Handle a basic transaction clearly.',



    'pharmacy': 'Describe symptoms and request medicine.',



    'gym': 'Discuss goals and choose a workout.',



    'job_interview': 'Present experience and answer key questions.',



    'tech_support': 'Describe a problem and follow troubleshooting steps.',



    'hair_salon': 'Request a style and confirm details.',



    'clothing_store': 'Ask about size, color, and try-on.',



    'train_station': 'Buy a ticket and confirm schedule.',



    'bus_stop': 'Ask about routes and tickets.',



    'renting_car': 'Choose a car and rental terms.',



    'pizza_delivery': 'Place an order and confirm delivery.',



    'bakery': 'Order items and quantities.',



    'library': 'Ask for materials and rules.',



    'cinema': 'Buy tickets and choose seats.',



    'lost_found': 'Report a lost item with details.'



}







LEARNING_STUDENT_ROLE_BY_CONTEXT = {



    'coffee_shop': 'customer',



    'restaurant': 'customer',



    'airport': 'passenger',



    'hotel': 'guest',



    'supermarket': 'customer',



    'doctor': 'patient',



    'bank': 'customer',



    'pharmacy': 'customer',



    'gym': 'visitor',



    'train_station': 'passenger',



    'bus_stop': 'passenger',



    'cinema': 'customer',



    'library': 'visitor',



    'gas_station': 'customer',



    'hair_salon': 'customer',



    'clothing_store': 'customer',



    'bakery': 'customer',



    'dental_clinic': 'patient',



    'tech_support': 'customer',



    'pizza_delivery': 'customer',



    'renting_car': 'customer',



    'lost_found': 'visitor',



    'post_office': 'customer',



}







LEARNING_STUDENT_MODEL_FALLBACKS = {



    'hotel': (



        "I have a reservation under the name ___.",



        "Eu tenho uma reserva no nome de ___."



    ),



    'airport': (



        "I'd like to check in for my flight to ___.",



        "Eu gostaria de fazer check-in para meu voo para ___."



    ),



    'restaurant': (



        "I'd like to order ___, please.",



        "Eu gostaria de pedir ___, por favor."



    ),



    'coffee_shop': (



        "I'd like a ___ coffee, please.",



        "Eu gostaria de um cafe ___, por favor."



    ),



    'supermarket': (



        "Where can I find the ___?",



        "Onde eu encontro o ___?"



    ),



    'bank': (



        "I'd like to make a deposit, please.",



        "Eu gostaria de fazer um deposito, por favor."



    ),



    'pharmacy': (



        "I have a headache. What do you recommend?",



        "Estou com dor de cabeca. O que você recomenda?"



    ),



    'doctor': (



        "I've had this pain for two days.",



        "Estou com essa dor ha dois dias."



    ),



}







LEARNING_WORKER_ONLY_PHRASE_PATTERNS = {



    'hotel': [



        r'\b(can|could|may)\s+i\s+(see|have)\s+your\s+(id|passport|credit card|name|last name|reservation)\b',



        r'\bdo you have a reservation\b',



        r'\bhow many nights will you stay\b',



        r'\bwould you like help with your bags\b',



        r'\bcould you spell your last name\b',



        r'\bchecking in\b',



    ],



    'airport': [



        r'\b(can|could|may)\s+i\s+(see|have)\s+your\s+(passport|ticket|boarding pass|booking reference)\b',



        r'\bdo you have (a|any)?\s*bag(s)? to check\b',



        r'\bwindow or aisle seat\b',



    ],



    'restaurant': [



        r'\bare you ready to order\b',



        r'\bwhat would you like to order\b',



        r'\bwould you like (a|any)\b',



    ],



    'coffee_shop': [



        r'\bwhat size would you like\b',



        r'\bhot or iced\b',



        r'\bwould you like milk or sugar\b',



    ],



    'bank': [



        r'\bdo you want to deposit or withdraw\b',



        r'\bdo you have your id\b',



    ],



}







LEARNING_GENERIC_WORKER_ONLY_PATTERNS = [



    r'\b(can|could|may)\s+i\s+(see|have)\s+your\s+(id|passport|ticket|name|last name|reservation|booking|credit card)\b',



    r'\bcould you spell your last name\b',



    r'\bhow many nights will you stay\b',



]







PORTUGUESE_HINT_WORDS = {



    'eu', 'você', 'você', 'nao', 'não', 'sim', 'quero', 'queria', 'gosto', 'gostaria',



    'preciso', 'posso', 'pode', 'poderia', 'me', 'meu', 'minha', 'seu', 'sua', 'nos',



    'nós', 'eles', 'elas', 'ela', 'ele', 'de', 'da', 'do', 'em', 'para', 'por', 'com',



    'sobre', 'sem', 'um', 'uma', 'uns', 'umas', 'este', 'esta', 'isso', 'aqui', 'ali',



    'agora', 'hoje', 'amanha', 'amanhã', 'ontem', 'sempre', 'nunca', 'tambem', 'também',



    'porque', 'por que', 'que', 'como', 'onde', 'quando', 'quanto', 'muito', 'pouco'



}











def looks_portuguese(text):



    if not text:



        return False



    tokens = re.findall(r"[A-Za-z\u00C0-\u00FF']+", text.lower())



    if len(tokens) < 3:



        return False



    hits = sum(1 for t in tokens if t in PORTUGUESE_HINT_WORDS)



    if re.search(r'[\u00E3\u00F5\u00E7\u00E1\u00E0\u00E2\u00E9\u00EA\u00ED\u00F3\u00F4\u00FA]', text.lower()):



        hits += 1



    return hits >= max(2, int(len(tokens) * 0.3))











def _normalize_practice_mode(raw_mode):



    mode = str(raw_mode or 'learning').strip().lower()



    if mode not in ('learning', 'simulator'):



        return 'learning'



    return mode











def _clean_learning_output_artifacts(text):



    """Normalize escaped JSON artifacts and broken quote fragments in model text."""



    if not text:



        return text



    cleaned = str(text)



    cleaned = cleaned.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')



    cleaned = cleaned.replace('\\"', '"').replace("\\'", "'")



    # Remove stray backslashes that leak from malformed JSON fragments.



    cleaned = re.sub(r'\\(?=["\'\s])', '', cleaned)







    # Normalize common teaching markers so they are readable.



    cleaned = re.sub(r'Useful phrase\s*:\s*["\']?\s*', 'Useful phrase: ', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r'(useful phrase[^:]{0,120}:\s*)["\']', r'\1', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r"You'll hear from staff:\s*['\"]?\s*", "You'll hear from staff: ", cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r'([.?!])\s*["\']\s*(You\'ll hear from staff:)', r'\1 \2', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r'([.?!])\s*["\'](?=\s|$)', r'\1', cleaned)







    # Remove coaching/meta scaffolding that confuses beginners in the chat UI.



    cleaned = re.sub(r'\bLearning mode:\s*[^.!?]*[.!?]?\s*', '', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r'\bModo Learning:\s*[^.!?]*[.!?]?\s*', '', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r"\bLet'?s\s+(jump|start|get)\s+(right\s+)?(into|in)\s+(today'?s\s+)?(real[- ]life\s+)?(scene|interaction|conversation)[^.!?]*[.!?]\s*", '', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r'\bI\s+will\s+(coach|show|give|share)\s+(easy\s+|simple\s+)?(lines?|sentences?|phrases?)\s+you\s+can\s+(say|use)[^.!?]*[.!?]\s*', '', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r'\b(Eu\s+vou|Vou)\s+(guiar|mostrar|dar)\s+frases?\s+(simples\s+)?que\s+você\s+pode\s+(dizer|usar)[^.!?]*[.!?]\s*', '', cleaned, flags=re.IGNORECASE)



    cleaned = re.sub(r'\bI\s+will\s+coach\s+lines?\s+you\s+can\s+say\b', 'I will show easy sentences you can use', cleaned, flags=re.IGNORECASE)







    # If model merges phrase + staff marker in one quoted block, split them cleanly.



    phrase_staff_pattern = re.compile(



        r"(Useful phrase(?: for you)?\s*:)\s*(.+?)\s*(You'll hear from staff\s*:)",



        flags=re.IGNORECASE



    )







    def _phrase_staff_repl(match):



        phrase = str(match.group(2) or "").strip().strip("'\"")



        phrase = re.sub(r'\s{2,}', ' ', phrase).strip()



        return f"{match.group(1)} '{phrase}' {match.group(3)}"







    cleaned = phrase_staff_pattern.sub(_phrase_staff_repl, cleaned)



    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()



    return cleaned











def _learning_student_role_label(context_key):



    key = (context_key or '').strip().lower()



    return LEARNING_STUDENT_ROLE_BY_CONTEXT.get(key, 'student')











def _extract_learning_model_phrase_candidate(text):



    if not text:



        return ""



    source = _clean_learning_output_artifacts(str(text))



    quoted_patterns = [



        r'(?:a|one)\s+(?:useful|polite|natural)\s+(?:phrase|model)(?:\s+sentence)?\s*(?:is|:)\s*["“]([^"”\n]+)["”]',



        r'(?:another\s+)?(?:a|one)?\s*(?:useful|polite|natural)\s+question\s*(?:is|:)\s*["“]([^"”\n]+)["”]',



        r'you can say\s*:?\s*["“]([^"”\n]+)["”]',



        r'model is\s*:?\s*["“]([^"”\n]+)["”]',



        r'useful phrase\s*:\s*["“]([^"”\n]+)["”]',



    ]



    unquoted_patterns = [



        r'(?:a|one)\s+(?:useful|polite|natural)\s+(?:phrase|model)(?:\s+sentence)?\s*(?:is|:)\s*([^\.\n\?!]+)',



        r'(?:another\s+)?(?:a|one)?\s*(?:useful|polite|natural)\s+question\s*(?:is|:)\s*([^\.\n\?!]+)',



        r'you can say\s*:?\s*([^\.\n\?!]+)',



        r'model is\s*:?\s*([^\.\n\?!]+)',



        r'useful phrase\s*:\s*([^\.\n\?!]+)',



    ]



    for pattern in quoted_patterns + unquoted_patterns:



        match = re.search(pattern, source, re.IGNORECASE)



        if not match:



            continue



        candidate = str(match.group(1) or "").strip().strip("'\"")



        if len(candidate.split()) >= 2:



            return candidate



    return ""







def _looks_worker_only_model_phrase(phrase, context_key):



    if not phrase:



        return False



    normalized = unicodedata.normalize('NFD', str(phrase).lower())



    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')



    key = (context_key or '').strip().lower()



    context_patterns = LEARNING_WORKER_ONLY_PHRASE_PATTERNS.get(key, [])



    for pattern in context_patterns + LEARNING_GENERIC_WORKER_ONLY_PATTERNS:



        if re.search(pattern, normalized):



            return True



    return False











def _learning_student_model_fallback_pair(context_key):



    key = (context_key or '').strip().lower()



    return LEARNING_STUDENT_MODEL_FALLBACKS.get(



        key,



        ("Could you help me with ___, please?", "Você poderia me ajudar com ___, por favor?")



    )











def _repair_learning_phrase_role(ai_text, ai_trans, context_key):



    if not ai_text:



        return ai_text, ai_trans



    candidate = _extract_learning_model_phrase_candidate(ai_text)



    if not candidate:



        return ai_text, ai_trans



    if not _looks_worker_only_model_phrase(candidate, context_key):



        return ai_text, ai_trans







    fallback_en, fallback_pt = _learning_student_model_fallback_pair(context_key)



    repaired = _clean_learning_output_artifacts(str(ai_text))



    repaired = re.sub(r'\bA useful phrase\b', 'A useful phrase for you', repaired, count=1, flags=re.IGNORECASE)



    repaired = re.sub(r'\bAnother useful question\b', 'Another useful phrase for you', repaired, count=1, flags=re.IGNORECASE)



    repaired = re.sub(r'\bA useful question\b', 'A useful phrase for you', repaired, count=1, flags=re.IGNORECASE)



    repaired = re.sub(r'(?<!A )\bUseful phrase\b(?!\s+for you)', 'Useful phrase for you', repaired, count=1, flags=re.IGNORECASE)



    repaired = re.sub(r'\bA useful model\b', 'A useful model for you', repaired, count=1, flags=re.IGNORECASE)



    repaired = re.sub(r'\bA natural model\b', 'A natural model for you', repaired, count=1, flags=re.IGNORECASE)







    marker_pattern = re.compile(



        r'((?:(?:another|a|one)\s+)?(?:useful|polite|natural)\s+'



        r'(?:phrase(?:\s+for\s+you)?|model(?:\s+for\s+you)?|question)'



        r'(?:\s+sentence)?\s*(?:is|:)\s*)["“]?([^"”\n]+?)["”]?(?=\s*(?:\(|[.?!]|$))',



        flags=re.IGNORECASE



    )



    marker_replaced = marker_pattern.sub(lambda m: f'{m.group(1)}"{fallback_en}"', repaired, count=1)



    if marker_replaced != repaired:



        repaired = marker_replaced



    else:



        escaped_candidate = re.escape(candidate)



        repaired_with_slash = re.sub(rf'\\+\s*{escaped_candidate}', fallback_en, repaired, count=1)



        if repaired_with_slash != repaired:



            repaired = repaired_with_slash



        else:



            repaired = re.sub(escaped_candidate, fallback_en, repaired, count=1)







    # If the model embeds a Portuguese parenthetical after the phrase, keep it aligned



    # with the repaired student-side phrase.



    repaired = re.sub(



        rf'({re.escape(fallback_en)}[.?!]*["”]?)\s*\(([^)]{{4,180}})\)',



        rf'\1 ({fallback_pt})',



        repaired,



        count=1



    )



    repaired = re.sub(rf'{re.escape(fallback_en)}\s*\?', fallback_en, repaired, count=1)



    repaired = re.sub(rf'{re.escape(fallback_en)}\.\?', fallback_en, repaired, count=1)







    repaired = re.sub(



        r'(useful phrase for you)\s*is(?=[A-Za-z"“])',



        r'\1 is: ',



        repaired,



        flags=re.IGNORECASE



    )







    key = (context_key or '').strip().lower()



    if key == 'hotel':



        repaired = re.sub(



            r'\bDo you have your ID ready\?',



            'How would you answer if the receptionist asks for your ID?',



            repaired,



            flags=re.IGNORECASE



        )



        repaired = re.sub(



            r'\bHow many nights will you stay\?',



            'How many nights will you say you are staying?',



            repaired,



            flags=re.IGNORECASE



        )



        repaired = re.sub(



            r'\bDo you have a reservation\?',



            'How would you say you already have a reservation?',



            repaired,



            flags=re.IGNORECASE



        )







    repaired = _clean_learning_output_artifacts(repaired)







    repaired_trans = ai_trans



    if repaired_trans:



        repaired_trans = re.sub(r'"[^"]{4,140}"', f'"{fallback_pt}"', str(repaired_trans), count=1)



        repaired_trans = _clean_learning_output_artifacts(repaired_trans)



    return repaired, repaired_trans











def _extract_json_field_value(raw_text, field_name):



    """Extract a JSON string field even when text contains escaped quotes/newlines."""



    if not raw_text or not field_name:



        return ""



    pattern = rf'"{re.escape(field_name)}"\s*:\s*"((?:\\.|[^"\\])*)"'



    match = re.search(pattern, str(raw_text), flags=re.DOTALL)



    if not match:



        return ""



    payload = match.group(1)



    try:



        return json.loads(f'"{payload}"')



    except Exception:



        return _clean_learning_output_artifacts(payload)







def _build_learning_system_prompt(context_key, base_prompt, objective_text=''):



    """Strengthen Learning mode so scenario prompts do not drift into pure simulator behavior."""



    base = (base_prompt or '').strip()



    objective = (objective_text or '').strip()



    objective_line = f"- Session objective: {objective}" if objective else "- Session objective: guide practical communication in this context."



    context_label = (context_key or 'conversation').replace('_', ' ')



    student_role = _learning_student_role_label(context_key)



    return f"""{base}







LEARNING MODE (STRICT):



You are the scenario character (barista, receptionist, waiter, etc.) — NOT a teacher.



Respond naturally as this character in the "{context_label}" setting.



The student speaks as the {student_role}.







CRITICAL RULES:



- Your "en" response must sound like a REAL person in this role — never like a teacher.



- NEVER include corrections, grammar explanations, or teaching in your "en" text.



- NEVER say "Instead of X, say Y", "Useful phrase:", "In English, we...", "Try saying..."



- NEVER model phrases for the student to repeat.



- If the student makes a grammar error, use RECAST: respond using the correct form naturally.



  Example: Student says "I wants coffee" → You say "Sure, I can get that coffee for you."



- All corrections go ONLY in the "correction" JSON field (see format below).



- Keep responses short (1-2 sentences, max 30 words) and end with a question to advance.



- Do not output meta labels like "Learning mode: ..." or "Modo Learning: ...".







{objective_line}



"""











def _resolve_chat_system_prompt(context_key, practice_mode, is_grammar_topic, objective_text=''):



    """Pick system prompt and mode label for chat generation."""



    fallback_prompt = CONTEXT_PROMPTS.get(context_key, CONTEXT_PROMPTS.get('coffee_shop', ''))



    if practice_mode == 'simulator':



        sim_prompt = SIMULATOR_PROMPTS.get(context_key)



        if sim_prompt:



            return sim_prompt, 'simulator', 'simulator_prompt'



        return fallback_prompt, 'simulator', 'fallback_context_prompt'







    prompt = fallback_prompt



    if not is_grammar_topic:



        prompt = _build_learning_system_prompt(context_key, prompt, objective_text)



    return prompt, 'learning', 'learning_prompt'











def _learning_teaching_fallback_pair(context_key):



    key = (context_key or '').lower()



    if 'restaurant' in key or 'pizza' in key or 'bakery' in key:



        return (



            "Nice start. A polite model is: \"I'd like to order the grilled chicken, please.\" Now try your order with \"I'd like..., please\". What would you like as your main dish?",



            "Boa! Um modelo educado e: \"I'd like to order the grilled chicken, please.\" Agora tente seu pedido com \"I'd like..., please\". O que você gostaria como prato principal?"



        )



    if 'hotel' in key:



        return (



            "Good start. A natural model is: \"I have a reservation under [name].\" Now use this model and add your name. How many nights will you stay?",



            "Boa! Um modelo natural e: \"I have a reservation under [name].\" Agora use esse modelo e adicione seu nome. Quantas noites você vai ficar?"



        )



    if 'airport' in key:



        return (



            "Good. A useful model is: \"I'd like to check in for my flight to ___.\" Try this structure now. Do you have a bag to check?",



            "Boa. Um modelo util e: \"I'd like to check in for my flight to ___.\" Tente essa estrutura agora. Você tem mala para despachar?"



        )



    return (



        "Good start. A useful model is: \"I'd like to ___, please.\" Try this model in your next sentence. What would you like to say in this situation?",



        "Boa! Um modelo util e: \"I'd like to ___, please.\" Tente esse modelo na sua proxima frase. O que você gostaria de dizer nessa situacao?"



    )











def _needs_learning_teaching_repair(text):



    if not text:



        return True



    raw = str(text).strip().lower()



    if not raw:



        return True



    words = re.findall(r"[a-z0-9']+", raw)



    if len(words) < 8:



        return True



    teaching_markers = [



        "instead of",



        "you can say",



        "a useful model",



        "a polite model",



        "model is",



        "try this",



        "for example",



    ]



    has_teaching = any(marker in raw for marker in teaching_markers)



    has_question = '?' in raw



    return (not has_teaching) or (not has_question)











def _normalize_feedback_text(value):



    text = (value or "").lower().strip()



    text = re.sub(r'[\[\]()"""\'`.,!?;:]+', ' ', text)



    text = re.sub(r'\s+', ' ', text).strip()



    # Re-join common contractions split by punctuation removal:



    # "don t" → "dont", "doesn t" → "doesnt", "isn t" → "isnt", etc.



    text = re.sub(r"\b(don|doesn|isn|aren|wasn|weren|hasn|haven|wouldn|couldn|shouldn|won|can|didn) t\b", r"\1t", text)



    return text











def _is_strong_user_match(fragment, user_text):



    frag = _normalize_feedback_text(fragment)



    user = _normalize_feedback_text(user_text)



    if not frag or not user:



        return False



    if frag in user or user in frag:



        return True



    ratio = SequenceMatcher(None, frag, user).ratio()



    if ratio >= 0.68:



        return True



    frag_tokens = set(frag.split())



    user_tokens = set(user.split())



    if not frag_tokens or not user_tokens:



        return False



    overlap = len(frag_tokens & user_tokens) / max(1, len(frag_tokens))



    return overlap >= 0.6











def _extract_quoted_candidate(source):



    quoted = re.findall(r'"([^"]{4,140})"', source or "")



    for candidate in quoted:



        snippet = candidate.strip()



        if re.search(r"[A-Za-z]", snippet) and len(snippet.split()) >= 2:



            return snippet



    phrase_patterns = [



        r"\b(i'd like[^.?!]*)",



        r"\b(could i have[^.?!]*)",



        r"\b(i have a reservation[^.?!]*)",



    ]



    for pattern in phrase_patterns:



        match = re.search(pattern, (source or ""), re.IGNORECASE)



        if match:



            snippet = str(match.group(1) or "").strip()



            if len(snippet.split()) >= 2:



                return snippet



    return ""











def _looks_real_grammar_error(fragment):



    text = _normalize_feedback_text(fragment)



    if not text:



        return False



    patterns = [



        r"\bi has\b",



        r"\bi am agree\b",



        r"\bhe have\b",



        r"\bshe have\b",



        r"\bthey is\b",



        r"\bwe is\b",



        r"\byou is\b",



        r"\bi goed\b",



        r"\bi eated\b",



        # Subject-verb disagreements



        r"\bshe don'?t\b",



        r"\bhe don'?t\b",



        r"\bit don'?t\b",



        r"\bshe are\b",



        r"\bhe are\b",



        r"\bi are\b",



        r"\bthey was\b",



        r"\bwe was\b",



        r"\byou was\b",



        r"\bi were\b",



        r"\bhe were\b",



        r"\bshe were\b",



        r"\bit were\b",



        # Common irregular past errors



        r"\bi goed\b",



        r"\bi runned\b",



        r"\bi thinked\b",



        r"\bi buyed\b",



        r"\bi catched\b",



        r"\bi bringed\b",



        r"\bi teached\b",



        r"\bi writed\b",



        r"\bi drived\b",



        r"\bi leaved\b",



        r"\bi falled\b",



        r"\bi feeled\b",



        r"\bi keeped\b",



        r"\bi speaked\b",



        r"\bi telled\b",



        r"\bi understanded\b",



        # Double negatives / wrong auxiliary



        r"\bdon'?t has\b",



        r"\bdoesn'?t have\b.*\bdon'?t\b",



        r"\bhe can speaks\b",



        r"\bshe can speaks\b",



        r"\bcan speaks\b",



        # Tense errors



        r"\bsince\b.*\bi am\b",



        r"\bi am here since\b",



        r"\bhave went\b",



        r"\bhas went\b",



        r"\bhave saw\b",



        r"\bhas saw\b",



        r"\bhave ate\b",



        r"\bhas ate\b",



    ]



    return any(re.search(pattern, text) for pattern in patterns)











def _classify_turn_feedback(user_text, ai_text, practice_mode, must_retry=False, suggested_words=None, structured_correction=None):



    """Classify turn feedback into real error correction vs style suggestion."""



    if not LEARNING_CORRECTION_KIND_ENABLED:



        return None



    if practice_mode != 'learning':



        return {



            "kind": "none",



            "user_text": "",



            "suggested_text": "",



            "reason": "",



            "retry_required": False



        }







    student = str(user_text or '').strip()







    # Priority: use structured correction field from JSON if available



    if structured_correction and isinstance(structured_correction, dict):



        wrong = str(structured_correction.get("wrong", "")).strip()



        right = str(structured_correction.get("right", "")).strip()



        explanation = str(structured_correction.get("explanation_pt", "")).strip()



        # Clean up quotes and trailing punctuation from correction



        right = right.strip("'\"")



        # If 'right' is a fragment (too short or has '...' or '/'), try to build



        # a complete suggested sentence from the student's text with the correction applied



        if right and ('...' in right or len(right.split()) <= 4) and student:



            # Fragment like "I went... I bought" - just keep as-is but clean up



            right = right.replace('...', ', ').strip(', ')



        if right:



            # Determine if this is a real error or style suggestion



            is_style = any(marker in explanation.lower() for marker in [



                "opcional", "dica opcional", "mais educado", "mais natural",



                "mais polido", "opcional:", "style", "upgrade"



            ])



            if is_style and not must_retry:



                return {



                    "kind": "style_upgrade",



                    "user_text": student,



                    "suggested_text": right,



                    "reason": explanation or "Sugestao opcional de naturalidade/polidez.",



                    "retry_required": False



                }



            else:



                return {



                    "kind": "error_correction",



                    "user_text": student,



                    "suggested_text": right,



                    "reason": explanation or "Correcao de erro gramatical/estrutura para esta resposta.",



                    "retry_required": True



                }







    source = str(ai_text or '').strip()



    student = str(user_text or '').strip()



    suggested_words = suggested_words if isinstance(suggested_words, list) else []



    if not source or not student:



        return {



            "kind": "none",



            "user_text": student,



            "suggested_text": student,



            "reason": "Sua frase esta correta para este contexto.",



            "retry_required": False



        }







    style_markers = [



        "more natural",



        "more polite",



        "slightly more polite",



        "optional upgrade",



        "sounds more natural",



        "sounds more professional",



        "forma mais natural",



        "mais educado",



        "mais natural",



        "upgrade opcional",



        "instead of just saying",



    ]



    has_style_marker = any(marker in source.lower() for marker in style_markers)







    patterns = [



        r'Instead of\s*[\"“]?([^\"”]+?)[\"”]?\s*,?\s*say\s*:?\s*[\"“]?([^\"”]+?)[\"”]?(?:[.?!]|$)',



        r'Em vez de\s*\[EN\](.*?)\[/EN\]\s*,?\s*diga\s*:?\s*\[EN\](.*?)\[/EN\](?:[.?!]|$)',



        r'Em vez de\s*[\"“]?([^\"”]+?)[\"”]?\s*,?\s*diga\s*:?\s*[\"“]?([^\"”]+?)[\"”]?(?:[.?!]|$)',



    ]







    wrong_part = ""



    corrected = ""



    for pattern in patterns:



        match = re.search(pattern, source, re.IGNORECASE)



        if match:



            wrong_part = str(match.group(1) or '').strip().strip('\'"“”')



            corrected = str(match.group(2) or '').strip().strip('\'"“”')



            corrected = corrected.split(" - ")[0].split(" (")[0].strip().strip("'\"")



            break







    has_explicit_correction = bool(wrong_part and corrected)



    strong_match = _is_strong_user_match(wrong_part, student) if wrong_part else False







    if has_explicit_correction and strong_match:



        if _looks_real_grammar_error(wrong_part) or (must_retry and not has_style_marker):



            return {



                "kind": "error_correction",



                "user_text": student,



                "suggested_text": corrected,



                "reason": "Correcao de erro gramatical/estrutura para esta resposta.",



                "retry_required": True



            }



        return {



            "kind": "style_upgrade",



            "user_text": student,



            "suggested_text": corrected,



            "reason": "Sugestao opcional de naturalidade/polidez.",



            "retry_required": False



        }







    # Fallback: if the AI flagged must_retry with suggested_words but didn't use



    # the exact "Instead of X, say Y" pattern, check the student's original text



    # for known grammar errors directly.



    if must_retry and suggested_words and not has_style_marker:



        if _looks_real_grammar_error(student):



            return {



                "kind": "error_correction",



                "user_text": student,



                "suggested_text": corrected if corrected else ", ".join(suggested_words),



                "reason": "Correcao de erro gramatical/estrutura para esta resposta.",



                "retry_required": True



            }







    # Optional style suggestion without treating it as error.



    if has_style_marker:



        candidate = _extract_quoted_candidate(source)



        if candidate:



            return {



                "kind": "style_upgrade",



                "user_text": student,



                "suggested_text": candidate,



                "reason": "Sugestao opcional de naturalidade/polidez.",



                "retry_required": False



            }







    # Last-resort fallback: the AI returned must_retry=False and empty suggested_words,



    # but the student's text contains an obvious grammar error that our pattern detector



    # can catch. This ensures errors are never silently ignored.



    if _looks_real_grammar_error(student):



        return {



            "kind": "error_correction",



            "user_text": student,



            "suggested_text": student,



            "reason": "Correcao de erro gramatical/estrutura para esta resposta.",



            "retry_required": True



        }







    return {



        "kind": "none",



        "user_text": student,



        "suggested_text": student,



        "reason": "Sua frase esta correta para este contexto.",



        "retry_required": False



    }











FOLLOW_UP_QUESTION_LOOKUP = {



    'coffee_shop': {



        'en': [



            "Would you like that hot or iced?",



            "What size would you like?",



            "Would you like any milk or sugar?"



        ],



        'pt': [



            "Você prefere quente ou gelado?",



            "Qual tamanho você gostaria?",



            "Quer leite ou acucar?"



        ],



    },



    'restaurant': {



        'en': [



            "Would you like to start with a drink?",



            "What would you like to order?",



            "Would you like fries or salad with that?"



        ],



        'pt': [



            "Quer começar com uma bebida?",



            "O que você gostaria de pedir?",



            "Prefere batata frita ou salada?"



        ],



    },



    'airport': {



        'en': [



            "Where are you flying today?",



            "Do you have a bag to check?",



            "Would you like a window or aisle seat?"



        ],



        'pt': [



            "Para onde você vai hoje?",



            "Você tem bagagem para despachar?",



            "Prefere janela ou corredor?"



        ],



    },



    'hotel': {



        'en': [



            "Can I have your name, please?",



            "How many nights will you stay?",



            "Would you like help with your bags?"



        ],



        'pt': [



            "Qual e o seu nome, por favor?",



            "Quantas noites vai ficar?",



            "Quer ajuda com as malas?"



        ],



    },



    'supermarket': {



        'en': [



            "Did you find everything you needed?",



            "Would you like a bag?",



            "Do you have a loyalty card?"



        ],



        'pt': [



            "Encontrou tudo o que precisava?",



            "Quer sacola?",



            "Você tem cartao de fidelidade?"



        ],



    },



    'doctor': {



        'en': [



            "How long have you felt this?",



            "Do you have a fever?",



            "Are you taking any medicine?"



        ],



        'pt': [



            "Ha quanto tempo você sente isso?",



            "Você esta com febre?",



            "Você esta tomando algum remedio?"



        ],



    },



    'bank': {



        'en': [



            "How can I help you today?",



            "Do you want to deposit or withdraw?",



            "Do you have your ID with you?"



        ],



        'pt': [



            "Como posso ajudar hoje?",



            "Você quer depositar ou sacar?",



            "Você esta com seu documento?"



        ],



    },



    'pharmacy': {



        'en': [



            "What symptoms do you have?",



            "Do you want tablets or syrup?",



            "Are you allergic to any medicine?"



        ],



        'pt': [



            "Quais sintomas você tem?",



            "Prefere comprimidos ou xarope?",



            "Você tem alergia a algum remedio?"



        ],



    },



    'gym': {



        'en': [



            "What kind of workout do you want today?",



            "Do you prefer cardio or weights?",



            "How often do you train?"



        ],



        'pt': [



            "Que tipo de treino você quer hoje?",



            "Você prefere cardio ou pesos?",



            "Com que frequencia você treina?"



        ],



    },



    'job_interview': {



        'en': [



            "Why do you want this job?",



            "What are your strengths?",



            "Can you tell me about your experience?"



        ],



        'pt': [



            "Por que você quer esta vaga?",



            "Quais sao seus pontos fortes?",



            "Pode falar da sua experiencia?"



        ],



    },



    'tech_support': {



        'en': [



            "What exactly is not working?",



            "When did the problem start?",



            "Have you tried restarting it?"



        ],



        'pt': [



            "O que exatamente nao esta funcionando?",



            "Quando o problema comecou?",



            "Você ja tentou reiniciar?"



        ],



    },



    'hair_salon': {



        'en': [



            "What style are you looking for?",



            "How much do you want to cut?",



            "Do you want to wash and dry?"



        ],



        'pt': [



            "Que estilo você quer?",



            "Quanto você quer cortar?",



            "Quer lavar e secar?"



        ],



    },



    'clothing_store': {



        'en': [



            "What size do you need?",



            "Would you like to try it on?",



            "What color do you prefer?"



        ],



        'pt': [



            "Qual tamanho você precisa?",



            "Quer experimentar?",



            "Qual cor você prefere?"



        ],



    },



    'train_station': {



        'en': [



            "Where are you going?",



            "What time do you want to leave?",



            "One-way or return?"



        ],



        'pt': [



            "Para onde você vai?",



            "Que horas você quer sair?",



            "So ida ou ida e volta?"



        ],



    },



    'bus_stop': {



        'en': [



            "Where are you going?",



            "Do you want a one-way ticket?",



            "What time do you need to leave?"



        ],



        'pt': [



            "Para onde você vai?",



            "Quer passagem so de ida?",



            "Que horas você precisa sair?"



        ],



    },



    'renting_car': {



        'en': [



            "What kind of car do you need?",



            "How many days will you rent it?",



            "Do you want insurance?"



        ],



        'pt': [



            "Que tipo de carro você precisa?",



            "Por quantos dias vai alugar?",



            "Quer seguro?"



        ],



    },



    'pizza_delivery': {



        'en': [



            "What would you like to order?",



            "What size would you like?",



            "Delivery or pickup?"



        ],



        'pt': [



            "O que você gostaria de pedir?",



            "Qual tamanho você quer?",



            "Entrega ou retirada?"



        ],



    },



    'bakery': {



        'en': [



            "What would you like today?",



            "How many would you like?",



            "Would you like anything else?"



        ],



        'pt': [



            "O que você gostaria hoje?",



            "Quantos você quer?",



            "Quer mais alguma coisa?"



        ],



    },



    'library': {



        'en': [



            "What are you looking for?",



            "Do you need a specific book?",



            "Do you have a library card?"



        ],



        'pt': [



            "O que você esta procurando?",



            "Você precisa de um livro especifico?",



            "Você tem cartao da biblioteca?"



        ],



    },



    'cinema': {



        'en': [



            "Which movie would you like?",



            "What time do you want?",



            "Would you like popcorn?"



        ],



        'pt': [



            "Qual filme você quer?",



            "Que horario você prefere?",



            "Quer pipoca?"



        ],



    },



    'lost_found': {



        'en': [



            "What did you lose?",



            "Where did you last see it?",



            "What does it look like?"



        ],



        'pt': [



            "O que você perdeu?",



            "Onde você viu pela ultima vez?",



            "Como era o objeto?"



        ],



    },



    'free_conversation': {



        'en': [



            "What happened next?",



            "Why is that important to you?",



            "Can you tell me more about that?"



        ],



        'pt': [



            "O que aconteceu depois?",



            "Por que isso e importante para você?",



            "Pode me contar mais sobre isso?"



        ],



    }



}







QUESTION_SLOT_HINTS = [



    ('temperature', [r'\bhot or iced\b', r'\bquente ou gelado\b']),



    ('size', [r'\bwhat size\b', r'\bsize do you need\b', r'\bqual tamanho\b']),



    ('milk_sugar', [r'\bmilk or sugar\b', r'\bleite ou acucar\b']),



    ('pickup_delivery', [r'\bdelivery or pickup\b', r'\bentrega ou retirada\b']),



    ('ticket_direction', [r'\bone-way or return\b', r'\bso ida\b']),



    ('destination', [r'\bwhere are you (going|flying)\b', r'\bpara onde\b']),



    ('time', [r'\bwhat time\b', r'\bque horas\b']),



    ('name', [r'\byour name\b', r'\bseu nome\b']),



    ('nights', [r'\bhow many nights\b', r'\bquantas noites\b']),



    ('bags', [r'\bhelp with your bags\b', r'\bhelp with your luggage\b', r'\bajuda com as malas\b', r'\bmalas\b']),



    ('color', [r'\bwhat color\b', r'\bqual cor\b']),



    ('order', [r'\bwhat would you like to order\b', r'\bo que você gostaria de pedir\b']),



    ('symptoms', [r'\bwhat symptoms\b', r'\bquais sintomas\b']),



]







SLOT_ANSWER_PATTERNS = {



    'size': re.compile(r'\b(small|medium|large|extra[- ]?large|grande|medio|pequeno|pequena)\b', re.IGNORECASE),



    'temperature': re.compile(r'\b(hot|iced|cold|quente|gelado|gelada)\b', re.IGNORECASE),



    'milk_sugar': re.compile(r'\b(milk|sugar|with sugar|without sugar|no sugar|leite|acucar|sem acucar|com acucar)\b', re.IGNORECASE),



    'pickup_delivery': re.compile(r'\b(delivery|pickup|takeout|to go|entrega|retirada)\b', re.IGNORECASE),



    'ticket_direction': re.compile(r'\b(one-way|return|round trip|so ida|ida e volta)\b', re.IGNORECASE),



    'name': re.compile(r'\b(my name is|this is)\b', re.IGNORECASE),



    'color': re.compile(r'\b(red|blue|black|white|green|yellow|pink|color|cor)\b', re.IGNORECASE),



    'symptoms': re.compile(r'\b(fever|pain|cough|headache|symptom|febre|dor|tosse|dor de cabeca|sintoma)\b', re.IGNORECASE),



    'nights': re.compile(r'\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+nights?\b|\bstay for\b', re.IGNORECASE),



    'bags': re.compile(



        r'\b('



        r'no\b.*\bbags?\b|'



        r'no luggage|'



        r"don'?t need help with (my )?(bags|luggage)|"



        r'do not need help with (my )?(bags|luggage)|'



        r'sem mala|sem malas|sem bagagem'



        r')\b',



        re.IGNORECASE



    ),



    'order': re.compile(



        r"\b("



        r"i(?:'d| would)? like|"



        r"i want|"



        r"i(?:'ll| will)? have|"



        r"can i (?:get|have)|"



        r"pepperoni|margherita|pizza|latte|cappuccino|espresso|coffee|tea|"



        r"quero|gostaria|pedir"



        r")\b",



        re.IGNORECASE



    ),



}











NEUTRAL_FOLLOW_UP_LOOKUP = {



    'coffee_shop': [



        ("Would you like anything else with your order?", "Quer mais alguma coisa no pedido?"),



        ("Would you like to finish your order now?", "Quer finalizar seu pedido agora?"),



        ("Would you like to pay now?", "Quer pagar agora?"),



        ("Would you like your receipt?", "Quer seu comprovante?"),



        ("Would you like this to go or for here?", "Você quer para viagem ou para consumir aqui?"),



        ("Would you like to confirm your final order?", "Quer confirmar seu pedido final?"),



        ("Would you like me to repeat your order details?", "Quer que eu repita os detalhes do pedido?"),



        ("Would you like to close the order now?", "Quer encerrar o pedido agora?"),



    ],



    'pizza_delivery': [



        ("Would you like to add anything else to your order?", "Quer adicionar mais alguma coisa ao pedido?"),



        ("Would you like to confirm the order now?", "Quer confirmar o pedido agora?"),



        ("Would you like an estimated pickup time?", "Quer um tempo estimado para retirada?"),



        ("Would you like me to repeat the order details?", "Quer que eu repita os detalhes do pedido?"),



        ("Would you like to close this order now?", "Quer fechar esse pedido agora?"),



        ("Would you like to confirm your pickup name?", "Quer confirmar o nome para retirada?"),



        ("Would you like to check the total price now?", "Quer verificar o valor total agora?"),



        ("Would you like to receive the pickup instructions?", "Quer receber as instrucoes de retirada?"),



    ],



    'restaurant': [



        ("Would you like anything else today?", "Quer mais alguma coisa hoje?"),



        ("Would you like to finish your order now?", "Quer finalizar seu pedido agora?"),



        ("Would you like the bill now?", "Quer a conta agora?"),



    ],



    'bakery': [



        ("Would you like anything else from the bakery today?", "Quer mais alguma coisa da padaria hoje?"),



        ("Would you like to finish your order now?", "Quer finalizar seu pedido agora?"),



        ("Would you like me to pack it to go?", "Quer que eu embale para viagem?"),



    ],



    'hotel': [



        ("Do you need anything else before we finish check-in?", "Precisa de algo mais antes de finalizarmos o check-in?"),



        ("Would you like me to confirm your check-in details?", "Quer que eu confirme os detalhes do seu check-in?"),



        ("Would you like information about breakfast hours?", "Quer informacoes sobre o horario do cafe da manha?"),



        ("Would you like directions to your room?", "Quer orientacoes para chegar ao seu quarto?"),



    ],



}











def _normalize_for_match(text):



    if not text:



        return ''



    lowered = str(text).lower()



    normalized = unicodedata.normalize('NFD', lowered)



    return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')











def _normalize_question_text(text):



    normalized = _normalize_for_match(text)



    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)



    return re.sub(r'\s+', ' ', normalized).strip()











def _extract_questions_from_text(text):



    if not text:



        return []



    # Capture only the question sentence chunk, not the full preceding paragraph.



    matches = re.findall(r'[^.?!]*\?', str(text))



    questions = []



    for candidate in matches:



        q = candidate.strip()



        if len(q.split()) >= 2:



            questions.append(q)



    return questions











def _infer_slot_from_question(question_text):



    normalized = _normalize_for_match(question_text)



    for slot_name, patterns in QUESTION_SLOT_HINTS:



        for pattern in patterns:



            if re.search(pattern, normalized):



                return slot_name



    return None











def _detect_answered_slots_in_text(text):



    normalized = _normalize_for_match(text)



    answered = set()



    for slot_name, pattern in SLOT_ANSWER_PATTERNS.items():



        if pattern.search(normalized):



            answered.add(slot_name)



    return answered











def _build_question_memory_snapshot(context_key, recent_turns, current_user_text=''):



    snapshot = {



        'answered_slots': set(),



        'recent_questions': [],



        'recent_question_slots': []



    }



    if isinstance(recent_turns, list):



        memory_turns_window = max(60, HISTORY_MAX_MESSAGES * 4)



        for turn in recent_turns[-memory_turns_window:]:



            if not isinstance(turn, dict):



                continue



            if turn.get('context') and turn.get('context') != context_key:



                continue







            user_line = turn.get('user', '')



            ai_line = turn.get('ai', '')







            snapshot['answered_slots'].update(_detect_answered_slots_in_text(user_line))







            for question in _extract_questions_from_text(ai_line):



                normalized = _normalize_question_text(question)



                if normalized:



                    snapshot['recent_questions'].append(normalized)



                inferred_slot = _infer_slot_from_question(question)



                if inferred_slot:



                    snapshot['recent_question_slots'].append(inferred_slot)







    snapshot['answered_slots'].update(_detect_answered_slots_in_text(current_user_text))



    recent_window = max(12, HISTORY_MAX_MESSAGES * 2)



    snapshot['recent_questions'] = snapshot['recent_questions'][-recent_window:]



    snapshot['recent_question_slots'] = snapshot['recent_question_slots'][-recent_window:]



    return snapshot











def _build_contextual_conversation_history(recent_turns, context_key, practice_mode, max_messages):



    """Build prompt history using only turns from the same context (and mode when available)."""



    if not isinstance(recent_turns, list) or max_messages <= 0:



        return ""







    # Look back further because conversations may interleave multiple contexts.



    scan_window = max(60, max_messages * 6)



    contextual_turns = []







    for turn in reversed(recent_turns[-scan_window:]):



        if not isinstance(turn, dict):



            continue







        turn_context = str(turn.get('context') or '').strip()



        if turn_context and turn_context != context_key:



            continue







        turn_mode = str(turn.get('mode') or '').strip()



        if turn_mode and turn_mode != practice_mode:



            continue







        user_line = str(turn.get('user') or '').strip()



        ai_line = str(turn.get('ai') or '').strip()



        if not user_line and not ai_line:



            continue







        contextual_turns.append({"user": user_line, "ai": ai_line})



        if len(contextual_turns) >= max_messages:



            break







    if not contextual_turns:



        return ""







    contextual_turns.reverse()



    history_lines = []



    for msg in contextual_turns:



        if msg['user']:



            history_lines.append(f"Student: {msg['user']}")



        if msg['ai']:



            history_lines.append(f"You: {msg['ai']}")







    if not history_lines:



        return ""



    return "\n### CONVERSATION HISTORY (same context):\n" + "\n".join(history_lines) + "\n"











def _neutral_follow_up_pair(context_key, memory_snapshot=None):



    key = (context_key or '').lower()



    memory_snapshot = memory_snapshot or {}



    recent_questions = set(memory_snapshot.get('recent_questions') or [])







    options = NEUTRAL_FOLLOW_UP_LOOKUP.get(key)



    if options:



        for en_question, pt_question in options:



            if _normalize_question_text(en_question) not in recent_questions:



                return en_question, pt_question



        # If all template options were recently used, return a contextual generic fallback



        # instead of repeating the first template.



        if 'pizza' in key:



            return "Do you need anything before we close your order?", "Precisa de algo antes de fecharmos seu pedido?"



        if 'coffee' in key:



            return "Do you need anything else before we finish your coffee order?", "Precisa de mais algo antes de finalizarmos seu pedido de cafe?"



        if 'hotel' in key:



            hotel_fallback = [



                ("Do you need anything else before heading to your room?", "Precisa de mais alguma coisa antes de ir para o quarto?"),



                ("Would you like any final check-in details before we close?", "Quer mais algum detalhe final do check-in antes de encerrarmos?"),



                ("Would you like me to summarize your stay details one last time?", "Quer que eu resuma os detalhes da sua estadia uma ultima vez?"),



            ]



            for en_question, pt_question in hotel_fallback:



                if _normalize_question_text(en_question) not in recent_questions:



                    return en_question, pt_question



            return hotel_fallback[0]



        return "Would you like to finish this order now?", "Quer finalizar este pedido agora?"



    if 'pizza' in key or 'restaurant' in key or 'coffee' in key or 'bakery' in key:



        return "Would you like anything else with that?", "Quer mais alguma coisa?"



    return "What would you like to talk about next?", "Sobre o que você quer falar agora?"











def _sanitize_learning_robotic_phrases(text):



    """Remove any teacher/coaching language that leaked into the AI response."""



    if not text:



        return text



    sanitized = str(text)



    # Remove full teaching sentences that shouldn't appear in natural character responses



    teaching_patterns = [



        r"\blet'?s practice[^.?!]*[.?!]?\s*",



        r"\bcan you try[^.?!]*[.?!]?\s*",



        r"\brepeat after me[^.?!]*[.?!]?\s*",



        r"\bdoes that make sense[^.?!]*[.?!]?\s*",



        r"\btry saying[^.?!]*[.?!]?\s*",



        r"\buseful phrase\s*:\s*[^.?!]*[.?!]?\s*",



        r"\bin english,?\s+we\b[^.?!]*[.?!]?\s*",



        r"\ba (?:useful|polite|natural) (?:phrase|way)[^.?!]*[.?!]?\s*",



        r"\bI will show (?:you )?easy sentences[^.?!]*[.?!]?\s*",



        r"\btoday we(?:'re| are) going to practice[^.?!]*[.?!]?\s*",



        r"\bgood job\b[^.?!]*[.?!]?\s*",



        r"\bwell done\b[^.?!]*[.?!]?\s*",



        r"\bgreat job\b[^.?!]*[.?!]?\s*",



    ]



    for pattern in teaching_patterns:



        sanitized = re.sub(pattern, ' ', sanitized, flags=re.IGNORECASE)



    sanitized = re.sub(r'\s{2,}', ' ', sanitized).strip()



    return sanitized











def _console_safe_preview(value, limit=100):



    """Make log previews safe for non-UTF8 consoles (e.g., cp1252 on Windows)."""



    text = str(value or "")



    if isinstance(limit, int) and limit > 0 and len(text) > limit:



        text = text[:limit]



    encoding = getattr(getattr(sys, 'stdout', None), 'encoding', None) or 'utf-8'



    try:



        text.encode(encoding)



        return text



    except Exception:



        return text.encode(encoding, errors='replace').decode(encoding, errors='replace')











def _simulator_redirect_line(context_key):



    key = (context_key or "").lower()



    if "hotel" in key:



        return "I can help with your check-in right now."



    if "coffee" in key or "restaurant" in key or "bakery" in key or "pizza" in key:



        return "I can help with your order right now."



    if "airport" in key or "station" in key or "bus" in key:



        return "I can help with your check-in and travel details right now."



    if "pharmacy" in key or "doctor" in key or "clinic" in key:



        return "I can help with your health needs right now."



    return "I can help with this service right now."











def _sanitize_simulator_meta_text(text, context_key):



    """Keep simulator in-character when user asks meta/teaching questions."""



    if not text:



        return text



    cleaned = str(text)



    redirect = _simulator_redirect_line(context_key)



    replacements = [



        (r"\b(i am|i'm)\s+here\s+to\s+assist[^.?!]*\.", redirect),



        (r"\b(i am|i'm)\s+(just\s+)?(the\s+)?receptionist[^.?!]*\.", redirect),



        (r"\b(i am|i'm)\s+(just\s+)?a\s+barista[^.?!]*\.", redirect),



        (r"\b(i am|i'm)\s+a\s+pharmacist[^.?!]*\.", redirect),



        (r"\b(i am|i'm)\s+not\s+a\s+teacher[^.?!]*\.", redirect),



        (r"\byour\s+grammar\s+is[^.?!]*\.", redirect),



        (r"\byour\s+english\s+is[^.?!]*\.", redirect),



        (r"\b(i can|i'll)\s+(teach|explain)[^.?!]*\.", redirect),



        (r"\bnot\s+for\s+lessons?\b", ""),



        (r"\bnot\s+a\s+teacher\b", ""),



        (r"\bnot\s+a\s+tutor\b", ""),



    ]



    for pattern, replacement in replacements:



        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)







    # Remove any remaining meta-teaching sentence fragments.



    meta_marker = re.compile(



        r"\b(teacher|lesson|tutor|grammar|coach|teach|learning mode|learn english)\b",



        re.IGNORECASE



    )



    if meta_marker.search(cleaned):



        kept = []



        for sentence in re.split(r'(?<=[.?!])\s+', cleaned):



            if sentence and not meta_marker.search(sentence):



                kept.append(sentence.strip())



        cleaned = f"{redirect} {' '.join(kept)}".strip() if kept else redirect







    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()



    cleaned = re.sub(r'\s+([,.!?])', r'\1', cleaned)



    return cleaned











def _strip_learning_staff_side_lines(text):



    """Remove staff-side quoted helper lines from Learning replies to avoid role confusion."""



    if not text:



        return text



    source = str(text)



    staff_match = re.search(r"You'll hear from staff\s*:", source, flags=re.IGNORECASE)



    if not staff_match:



        return source







    useful_match = re.search(r"Useful phrase(?: for you)?\s*:", source, flags=re.IGNORECASE)



    if useful_match and useful_match.start() > staff_match.start():



        head = source[:staff_match.start()].strip()



        tail = source[useful_match.start():].strip()



        merged = f"{head} {tail}".strip()



        return re.sub(r'\s{2,}', ' ', merged)







    # If there is no useful phrase after the staff marker, keep only the student-facing part.



    cleaned = source[:staff_match.start()].strip()



    return re.sub(r'\s{2,}', ' ', cleaned)











def _strip_inline_learning_correction(text):



    """Remove explicit correction formulas from AI reply so conversation stays natural.



    Safety net: even though the prompt now tells the AI not to include these,



    this function catches any that leak through."""



    if not text:



        return text



    cleaned = _clean_learning_output_artifacts(text)



    # Patterns that handle quoted text with ? or . inside quotes



    patterns = [



        r"Instead of\s+['\"\u201c][^'\"\u201d]*['\"\u201d]\s*,?\s*say\s*:?\s*['\"\u201c][^'\"\u201d]*['\"\u201d][^.!]*[.!]?\s*",



        r'Instead of\s+\S+[^.!]*?,?\s*say\s*:?\s*[^.!]+[.!]?\s*',



        r'Em vez de\s+[^,]+,?\s*diga\s*:?\s*[^.!]+[.!]?\s*',



        r'Optional upgrade\s*:\s*[^.!]+[.!]?\s*',



        r'To sound more (?:polite|natural|professional)[^.!]*[.!]?\s*',



        r'Useful phrase\s*:\s*[^.!]+[.!]?\s*',



        r'Frase [uú]til\s*:\s*[^.!]+[.!]?\s*',



        r'In English,?\s+we\s+[^.!]+[.!]?\s*',



        r'A (?:useful|polite|natural|professional) (?:phrase|way|expression)[^.!]+[.!]?\s*',



    ]



    for pattern in patterns:



        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)



    # Remove orphaned quoted translations like '... (Portuguese translation).'



    cleaned = re.sub(r"'\s*\([^)]*\)\.?\s*", ' ', cleaned)



    cleaned = re.sub(r'"\s*\(([^)]*)\)', r' (\1)', cleaned)



    cleaned = re.sub(r'\s+[,.!?]', lambda m: m.group(0).strip(), cleaned)



    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()



    cleaned = _clean_learning_output_artifacts(cleaned)



    return cleaned or str(text)











def _looks_farewell(text):



    if not text:



        return False



    raw = str(text).strip()



    if not raw or '?' in raw:



        return False







    normalized = _normalize_for_match(raw)







    explicit_close = re.search(



        r'\b(bye|goodbye|see you|see ya|later|take care|tchau|até logo|falou|encerrar|finalizar|lets finish|let us finish)\b',



        normalized



    )



    if explicit_close:



        return True







    completion_close = re.search(



        r'\b(all good|that is all|thats all|nothing else|no more|done for now|finished)\b',



        normalized



    )



    if completion_close:



        return True







    gratitude_only = re.match(



        r'^(thanks|thank you|thank you very much|obrigado|obrigada|valeu)\.?$',



        normalized



    )



    return bool(gratitude_only)











def _choose_follow_up_question_pair(context_key, memory_snapshot=None):



    key = (context_key or '').lower()



    memory_snapshot = memory_snapshot or {}



    answered_slots = set(memory_snapshot.get('answered_slots') or [])



    recent_questions = set(memory_snapshot.get('recent_questions') or [])



    recent_slots = set((memory_snapshot.get('recent_question_slots') or [])[-3:])







    lookup = FOLLOW_UP_QUESTION_LOOKUP.get(key)



    if lookup:



        en_questions = list(lookup.get('en') or [])



        pt_questions = list(lookup.get('pt') or [])



        if en_questions:



            slot_safe_indexes = []



            for idx, en_question in enumerate(en_questions):



                slot = _infer_slot_from_question(en_question)



                if slot and slot in answered_slots:



                    continue



                slot_safe_indexes.append(idx)







            if not slot_safe_indexes:



                return _neutral_follow_up_pair(key, memory_snapshot)







            candidate_indexes = []



            for idx in slot_safe_indexes:



                en_question = en_questions[idx]



                q_norm = _normalize_question_text(en_question)



                if q_norm in recent_questions:



                    continue



                candidate_indexes.append(idx)







            if not candidate_indexes:



                candidate_indexes = list(slot_safe_indexes)







            selected_idx = candidate_indexes[0]



            for idx in candidate_indexes:



                slot = _infer_slot_from_question(en_questions[idx])



                if not slot or slot not in recent_slots:



                    selected_idx = idx



                    break







            pt_question = pt_questions[selected_idx] if selected_idx < len(pt_questions) else "Pode me contar mais?"



            return en_questions[selected_idx], pt_question







    if 'airport' in key or 'flight' in key:



        return "Where are you flying today?", "Para onde você vai hoje?"



    if 'hotel' in key:



        return "Can I have your name, please?", "Qual e o seu nome, por favor?"



    if 'restaurant' in key or 'pizza' in key or 'bakery' in key:



        return "What would you like to order?", "O que você gostaria de pedir?"



    if 'doctor' in key or 'clinic' in key:



        return "What brings you in today?", "O que te traz aqui hoje?"







    return "Can you tell me a bit more about that?", "Pode me contar um pouco mais sobre isso?"











def _rewrite_repetitive_trailing_question(text, context_key, memory_snapshot=None):



    if not text:



        return text, None



    stripped = str(text).strip()



    if not stripped.endswith('?'):



        return stripped, None







    questions = _extract_questions_from_text(stripped)



    if not questions:



        return stripped, None







    last_question = questions[-1]



    last_normalized = _normalize_question_text(last_question)



    memory_snapshot = memory_snapshot or {}



    recent_questions = set(memory_snapshot.get('recent_questions') or [])



    answered_slots = set(memory_snapshot.get('answered_slots') or [])



    question_slot = _infer_slot_from_question(last_question)







    is_duplicate = last_normalized in recent_questions



    already_answered_slot = bool(question_slot and question_slot in answered_slots)







    if not is_duplicate and not already_answered_slot:



        return stripped, None







    replacement_en, replacement_pt = _choose_follow_up_question_pair(context_key, memory_snapshot)



    if _normalize_question_text(replacement_en) == last_normalized:



        replacement_en, replacement_pt = _neutral_follow_up_pair(context_key, memory_snapshot)







    start_idx = stripped.rfind(last_question)



    prefix = stripped[:start_idx].strip() if start_idx >= 0 else ""



    rewritten = f"{prefix} {replacement_en}".strip() if prefix else replacement_en



    return rewritten, replacement_pt







def get_cached_model_for_context(context_key, system_prompt, mode_key='learning'):



    """Get or create a cached Gemini adapter for a specific context+mode."""



    global cached_models



    



    if not GENAI_AVAILABLE or not GOOGLE_API_KEY or not genai_client:



        return model  # Fallback to basic model



    



    # Include mode + prompt hash so different prompt variants never share the wrong cache entry.



    prompt_hash = hashlib.sha256((system_prompt or '').encode('utf-8')).hexdigest()[:16]



    cache_key = f"{context_key}|{mode_key}|{prompt_hash}"



    if cache_key in cached_models:



        return cached_models[cache_key]



    



    try:



        cached_model = GeminiModelAdapter(



            genai_client,



            GEMINI_MODEL_NAME,



            system_instruction=system_prompt,



            default_generation_config=DEFAULT_GEN_CONFIG,



            fallback_adapter=openai_fallback_adapter



        )
        cached_models[cache_key] = cached_model



        print(f"[CACHE] Created cached model for context: {context_key} ({mode_key})")



        return cached_model



    except Exception as e:



        print(f"[CACHE] Error creating cached model for {context_key} ({mode_key}): {e}")



        return model  # Fallback to basic model







def load_context_data():



    """Reload scenarios/grammar so new topics are available without restart."""



    global SCENARIOS, GRAMMAR_TOPICS, GRAMMAR_TOPIC_IDS, GRAMMAR_TOPIC_TITLES, CONTEXT_PROMPTS, SIMULATOR_PROMPTS, LESSONS_DB



    SCENARIOS = load_json_file(SCENARIOS_PATH)



    GRAMMAR_TOPICS = load_json_file(GRAMMAR_PATH)



    GRAMMAR_TOPIC_IDS = {g.get('id') for g in GRAMMAR_TOPICS}



    GRAMMAR_TOPIC_TITLES = {g.get('id'): g.get('title', g.get('id', '').replace('_', ' ').title()) for g in GRAMMAR_TOPICS}



    CONTEXT_PROMPTS = {s.get('id'): s.get('prompt', '') for s in SCENARIOS}



    CONTEXT_PROMPTS.update({g.get('id'): g.get('prompt', '') for g in GRAMMAR_TOPICS})



    # Load simulator prompts (realistic roleplay mode)



    SIMULATOR_PROMPTS = {s.get('id'): s.get('simulator_prompt', '') for s in SCENARIOS if s.get('simulator_prompt')}



    # Load structured lessons for Learning mode



    lessons_data = load_json_file(LESSONS_PATH)



    LESSONS_DB = lessons_data if isinstance(lessons_data, dict) else {}



    return GRAMMAR_TOPICS







CONTEXT_CHECK_INTERVAL_SEC = max(1, _int_env('CONTEXT_CHECK_INTERVAL_SEC', 5))



_last_context_signature = None



_last_context_check_ts = 0.0







def _context_signature():



    signature_parts = []



    for path in (SCENARIOS_PATH, GRAMMAR_PATH, LESSONS_PATH):



        try:



            stat = os.stat(path)



            signature_parts.append((path, stat.st_mtime_ns, stat.st_size))



        except OSError:



            signature_parts.append((path, None, None))



    return tuple(signature_parts)







def maybe_reload_context_data(force=False):



    """Reload context JSON only when files change (or forced)."""



    global _last_context_signature, _last_context_check_ts



    now = time.time()



    if not force and (now - _last_context_check_ts) < CONTEXT_CHECK_INTERVAL_SEC:



        return False



    _last_context_check_ts = now



    signature = _context_signature()



    if force or signature != _last_context_signature:



        load_context_data()



        _last_context_signature = signature



        return True



    return False







# Initial load



maybe_reload_context_data(force=True)







# Retrieve grammar topics endpoint



@app.route('/api/grammar-topics', methods=['GET'])



def get_grammar_topics():



    maybe_reload_context_data()



    return jsonify(GRAMMAR_TOPICS)







# Merge prompts handled in load_context_data







# Email whitelist configuration



AUTHORIZED_EMAILS_FILE = os.path.join(BASE_DIR, 'authorized_emails.json')



DEFAULT_ADMIN_EMAIL = 'admin@example.com'







def _env_non_empty(name, fallback):



    raw = os.environ.get(name)



    if raw is None:



        return fallback



    value = str(raw).strip()



    return value if value else fallback







ADMIN_EMAIL = _env_non_empty('ADMIN_EMAIL', DEFAULT_ADMIN_EMAIL).lower()



ADMIN_PASSWORD = str(os.environ.get('ADMIN_PASSWORD', '')).strip()



ADMIN_LOGIN_EMAILS = {ADMIN_EMAIL} if ('@' in ADMIN_EMAIL and ADMIN_PASSWORD) else set()



ADMIN_LOGIN_PASSWORDS = {ADMIN_PASSWORD} if ADMIN_PASSWORD else set()



if not ADMIN_LOGIN_EMAILS:



    print("[SECURITY] Admin login disabled: set both ADMIN_EMAIL and ADMIN_PASSWORD env vars.")



MAINTENANCE_MODE = os.environ.get('MAINTENANCE_MODE', 'false').strip().lower() in ('1', 'true', 'yes', 'on')



MAINTENANCE_MESSAGE = "IA de conversa\u00e7\u00e3o indispon\u00edvel no momento. Estar\u00e1 dispon\u00edvel novamente no pr\u00f3ximo s\u00e1bado. Obrigado pela compreens\u00e3o!"







def load_authorized_emails():



    """Load authorized emails from JSON file"""



    try:



        # Check if file exists first



        if not os.path.exists(AUTHORIZED_EMAILS_FILE):



             print(f"[WARNING] Authorized emails file not found at: {AUTHORIZED_EMAILS_FILE}")



             return set(ADMIN_LOGIN_EMAILS)



             



        with open(AUTHORIZED_EMAILS_FILE, 'r', encoding='utf-8-sig') as f:



            content = f.read().strip()



            if not content:



                return set(ADMIN_LOGIN_EMAILS)



            



            data = json.loads(content)



            emails = set()



            for raw_email in data.get('authorized_emails', []):



                normalized = str(raw_email or '').strip().lower()



                if normalized and '@' in normalized:



                    emails.add(normalized)



            # Always include admin emails



            emails.update(ADMIN_LOGIN_EMAILS)



            return emails



    except Exception as e:



        print(f"[ERROR] Error loading authorized emails: {e}")



        # Return set with just admin email as fallback



        return set(ADMIN_LOGIN_EMAILS)







def save_authorized_emails(emails_set):



    """Save authorized emails to JSON file"""



    normalized_emails = set()



    for raw_email in emails_set:



        normalized = str(raw_email or '').strip().lower()



        if normalized and '@' in normalized:



            normalized_emails.add(normalized)



    normalized_emails.update(ADMIN_LOGIN_EMAILS)







    emails_list = sorted(list(normalized_emails))



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



    normalized = str(email or '').strip().lower()



    return normalized in authorized_emails or normalized in ADMIN_LOGIN_EMAILS







def is_admin_credentials(email, password):



    """Check if admin email and password are correct"""



    normalized_email = str(email or '').strip().lower()



    clean_password = str(password or '')



    if not clean_password:



        return False



    return normalized_email in ADMIN_LOGIN_EMAILS and clean_password in ADMIN_LOGIN_PASSWORDS







def _is_admin_token_request():



    """Check whether current request carries a valid admin JWT token."""



    auth_header = request.headers.get('Authorization', '')



    if not auth_header.startswith('Bearer '):



        return False



    token = auth_header.split(' ')[1]



    try:



        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])



        return bool(payload.get('is_admin', False))



    except Exception:



        return False







def _is_admin_login_attempt():



    """Allow admin login during maintenance mode."""



    if request.path != '/api/auth/login' or request.method != 'POST':



        return False



    data = request.get_json(silent=True) or {}



    email = str(data.get('email') or '').strip().lower()



    password = str(data.get('password') or '')



    return is_admin_credentials(email, password)







def _is_bypass_login_attempt():



    """Allow bypass-listed emails to login during maintenance mode."""



    if not TEMP_BYPASS_EMAILS:



        return False



    if request.path != '/api/auth/login' or request.method != 'POST':



        return False



    data = request.get_json(silent=True) or {}



    email = str(data.get('email') or '').strip().lower()



    return _is_bypass_email(email)







def _is_bypass_token_request():



    """Check if current request carries a JWT from a bypass-listed email."""



    if not TEMP_BYPASS_EMAILS:



        return False



    auth_header = request.headers.get('Authorization', '')



    if not auth_header.startswith('Bearer '):



        return False



    token = auth_header.split(' ')[1]



    try:



        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])



        email = str(payload.get('email', '')).strip().lower()



        return _is_bypass_email(email)



    except Exception:



        return False







@app.before_request



def maintenance_gate():



    """Block student API access during maintenance, but allow login and static files."""



    if not MAINTENANCE_MODE:



        return None







    # Always allow health check



    if request.path == '/api/health':



        return None







    # Admin and bypass users get full access



    if _is_admin_token_request() or _is_admin_login_attempt():



        return None



    if _is_bypass_login_attempt() or _is_bypass_token_request():



        return None







    # Allow login for ALL users — they see the maintenance message after login



    if request.path == '/api/auth/login' and request.method == 'POST':



        return None







    # Allow static files (HTML, JS, CSS, images) so the login page loads



    if not request.path.startswith('/api/'):



        return None







    # Block all other API endpoints for non-admin/non-bypass users



    return jsonify({



        "error": "maintenance_mode",



        "message": MAINTENANCE_MESSAGE



    }), 503







# Load authorized emails on startup



authorized_emails = load_authorized_emails()



print(f"[OK] Loaded {len(authorized_emails)} authorized emails")



print(f"[OK] Admin login emails active: {sorted(list(ADMIN_LOGIN_EMAILS))}")







@app.route('/api/auth/login', methods=['POST'])



@limiter.limit("10 per minute")



def login():



    """Authentication endpoint with email whitelist"""



    try:



        if not JWT_AVAILABLE:



            return jsonify({"error": "Auth system not available"}), 503







        data = request.get_json(silent=True)



        if not isinstance(data, dict):



            return jsonify({"error": "Invalid JSON payload"}), 400







        email = str(data.get('email', '')).strip().lower()



        password = str(data.get('password', '')).strip()







        # Validate email format



        if not email or '@' not in email or len(email) > 200:



            return jsonify({"error": "Invalid email format"}), 400







        # Check if this is an admin login attempt (bypasses whitelist).



        is_admin = False



        if email in ADMIN_LOGIN_EMAILS:



            if password:



                if is_admin_credentials(email, password):



                    is_admin = True



                else:



                    record_live_activity("anonymous", email, "/api/auth/login", status="invalid_admin_password", mode="auth")



                    return jsonify({"error": "Invalid admin password"}), 401



            else:



                record_live_activity("anonymous", email, "/api/auth/login", status="missing_admin_password", mode="auth")



                return jsonify({"error": "Admin password required"}), 401



        else:



            # Regular user must be authorized (unless open access is enabled)



            if not OPEN_ACCESS_ENABLED and not is_email_authorized(email):



                print(f"Login failed: Email {email} not in authorized list (size: {len(authorized_emails)})")



                record_live_activity("anonymous", email, "/api/auth/login", status="denied", mode="auth")



                return jsonify({



                    "error": "Email not authorized",



                    "message": "This email is not registered in our system. Please contact support if you believe this is an error."



                }), 403



        



        # Generate user ID and token



        user_id = f"{email}_{int(datetime.now().timestamp())}"



        



        # Get user name from email (first part before @)



        name = email.split('@')[0].title()



        



        token_payload = {



            'user_id': user_id,



            'name': name,



            'email': email,



            'is_admin': is_admin,



            'exp': _utc_now() + timedelta(days=7)



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







        # Regular students enter through the daily methodology complement.
        # This keeps login/status aligned with the 10-minute daily rule even
        # when the first request does not yet include the frontend headers.
        if not is_admin:
            request.is_portal_trial = True
            request.user_email = email

        # Get usage data for this email



        is_bypass = _is_bypass_email(email)



        usage_data = get_user_usage_data(email, force_active=is_bypass or bool(getattr(request, 'is_portal_trial', False)))



        usage_payload = build_usage_payload(email, usage_data=usage_data)



        record_live_activity(user_id, email, "/api/auth/login", status="ok", mode="auth")







        # If maintenance mode is active and user is NOT admin/bypass, flag it



        maintenance_blocked = MAINTENANCE_MODE and not is_admin and not is_bypass







        return jsonify({



            "token": token,



            "user": {



                "user_id": user_id,



                "name": name,



                "email": email,



                "is_admin": is_admin



            },



            "maintenance": {



                "active": maintenance_blocked,



                "message": MAINTENANCE_MESSAGE if maintenance_blocked else None



            },



            "usage": usage_payload



        })



    except Exception as e:



        import traceback



        print(f"LOGIN CRASH: {str(e)}")



        print(traceback.format_exc())



        return jsonify({"error": "Internal server error"}), 500







@app.route('/api/scenarios', methods=['GET'])



def get_scenarios():



    maybe_reload_context_data()



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



    request_started_at = time.perf_counter()



    # Reload topics only if JSON files changed (cheap mtime check)



    maybe_reload_context_data()







    if not GOOGLE_API_KEY or not model:



        record_live_activity(getattr(request, 'user_id', 'unknown'), getattr(request, 'user_email', ''), "/api/chat", status="model_unavailable")



        return jsonify({"error": "AI service not configured"}), 500







    # Check daily usage limit



    user_email = request.user_email



    if not is_usage_exempt_request() and not check_usage_limit(user_email):



        remaining = get_remaining_seconds(user_email)
        is_portal_trial = bool(getattr(request, 'is_portal_trial', False))
        blocked_message = "Você usou os 10 minutos de IA de Conversação liberados para hoje." if is_portal_trial else (f"Practice is available on weekends only (Saturday-Sunday), {weekend_limit_label()} per weekend." if not is_weekend() else f"You've used your {weekend_limit_label()} for this weekend. See you next Saturday!")
        record_live_activity(getattr(request, 'user_id', 'unknown'), user_email, "/api/chat", status="usage_blocked")
        return jsonify({



            "error": "Weekend practice limit reached",



            "message": blocked_message,
            "remaining_seconds": remaining,



            "is_weekend": True if is_portal_trial else is_weekend(),

            "portal_trial": is_portal_trial
        }), 429







    data = request.json or {}



    user_text = data.get('text')



    context_key = data.get('context', 'coffee_shop')



    lesson_lang = data.get('lessonLang', 'en')  # 'en' or 'pt'



    practice_mode = _normalize_practice_mode(data.get('practiceMode', 'learning'))  # 'learning' or 'simulator'



    student_level = (data.get('studentLevel') or '').strip()



    turn_count = data.get('turnCount', 0)



    recent_corrections = data.get('recentCorrections', []) if isinstance(data.get('recentCorrections', []), list) else []



    difficulty = data.get('difficulty', 'intermediate')  # 'beginner', 'intermediate', 'advanced'

    # ===== SECRET "Modo Daniela" profile (interview prep) =====
    # Activated from the frontend (7-tap secret toggle) which sends profile='daniela',
    # or implicitly when the dedicated interview contexts are used. Injects a tailored
    # recruiter+coach persona into the system prompt below (see _resolve_chat_system_prompt).
    profile = (data.get('profile') or '').strip().lower()
    is_daniela_profile = (profile == 'daniela') or (context_key in ('bdr_interview', 'bdr_interview_drills'))







    # Validate input



    is_valid, result = validate_text_input(user_text, max_length=500)



    if not is_valid:



        record_live_activity(getattr(request, 'user_id', 'unknown'), user_email, "/api/chat", status="invalid_input")



        return jsonify({"error": result}), 400







    user_text = result







    # Detect confusion/struggle to slow down the lesson pace



    needs_slowdown = bool(re.search(



        r"(don't understand|do not understand|what does that mean|repeat|say again|slower|more slowly|i don't get it|"



        r"i don't know|not sure|no idea|"



        r"nao entendi|não entendi|nao entendo|não entendo|pode repetir|repete|mais devagar|"



        r"nao sei|não sei|não tenho certeza|nao tenho certeza)",



        user_text,



        re.IGNORECASE



    ))



    is_farewell = _looks_farewell(user_text)



    short_reply = len(user_text.split()) <= 2



    if short_reply and not is_farewell:



        needs_slowdown = True







    # Get conversation history for current context/mode only



    user_id = request.user_id



    conversation_history = ""



    if user_id in user_conversations:



        recent = user_conversations[user_id]



        conversation_history = _build_contextual_conversation_history(



            recent,



            context_key=context_key,



            practice_mode=practice_mode,



            max_messages=HISTORY_MAX_MESSAGES



        )







    slowdown_note = ""



    if needs_slowdown:



        slowdown_note = (



            "\n### STUDENT NEEDS HELP\n"



            "- The student is confused or struggling. Stay on the SAME point this turn.\n"



            "- Simplify, give ONE extra example, then ask them to try again.\n"



            "- Do NOT advance to a new topic in this response.\n"



        )







    # Grammar topics don't support simulator mode - force to learning



    if practice_mode == 'simulator' and context_key in GRAMMAR_TOPIC_IDS:



        practice_mode = 'learning'



        print(f"[CHAT] Grammar topic '{context_key}' forced from simulator to learning mode")







    # Check if this is a grammar/learning topic



    is_grammar_topic = context_key in GRAMMAR_TOPIC_IDS



    is_demonstratives = context_key in ['demonstratives', 'this_that_these_those']







    # Objective and level notes



    objective_text = COMMUNICATIVE_OBJECTIVES.get(context_key)



    if is_grammar_topic:



        topic_title = GRAMMAR_TOPIC_TITLES.get(context_key, context_key.replace('_', ' ').title())



        objective_text = f"Practice {topic_title} in natural conversation."







    # Get System Prompt based on context and practice mode



    system_prompt, active_mode, prompt_source = _resolve_chat_system_prompt(



        context_key=context_key,



        practice_mode=practice_mode,



        is_grammar_topic=is_grammar_topic,



        objective_text=objective_text



    )



    if active_mode == 'simulator':



        if prompt_source == 'fallback_context_prompt':



            print(f"[CHAT] Using SIMULATOR mode for {context_key} (fallback prompt)")



        else:



            print(f"[CHAT] Using SIMULATOR mode for {context_key}")



    else:



        print(f"[CHAT] Using LEARNING mode for {context_key}")



    



    # ===== Inject the secret "Modo Daniela" recruiter+coach persona =====
    # Appended AFTER the base prompt so it takes priority. Because get_cached_model_for_context
    # hashes system_prompt into its cache key, this creates an isolated cache entry and never
    # contaminates the normal job_interview model.
    if is_daniela_profile:
        daniela_persona = (
            "\n\n===== PRIORITY OVERRIDE: BDR INTERVIEW COACH (MODO DANIELA) =====\n"
            "You are now a senior recruiter / hiring manager running an English job interview "
            "for an OUTBOUND SALES role (BDR/SDR), and also Daniela's private interview coach. "
            "This override takes priority over any cafe/shop/service persona above.\n"
            "\nABOUT THE CANDIDATE (Daniela):\n"
            "- 20+ years commercial experience; 5+ years focused on outbound sales, lead generation, "
            "prospecting, and appointment setting (B2B).\n"
            "- Real results to draw out of her: 400+ cold calls/week; consistently 12 qualified "
            "meetings/month; about 1 in 3 decision-maker conversations becomes a meeting; 73% meeting "
            "attendance; 36% meeting-to-opportunity; led and coached a team of 10 SDRs at Yandex.\n"
            "- Tools she already knows: HubSpot, Salesloft, Apollo.io, LinkedIn Sales Navigator. "
            "Methods: SPIN, BANT, Social Selling. English: working proficiency, gets nervous.\n"
            "\nTARGET ROLE she is preparing for: Business Development Representative (Mid-Market and "
            "Commercial) at a SaaS company like PandaDoc. Outbound-first into 200+ FTE accounts; "
            "cold call + email + video; convert inbound MQLs; hit a monthly meeting quota. "
            "Their stack: Salesforce, Gong Engage, Nooks, Chilipiper, ZoomInfo, LinkedIn Sales "
            "Navigator, and AI tools INCLUDING CLAUDE for research and personalization.\n"
            "TOOL BRIDGE (coach her to translate her experience): HubSpot~Salesforce; "
            "Salesloft~Gong Engage; Apollo~ZoomInfo; high-volume calling~Nooks dialer; "
            "appointment setting~Chilipiper; 'I use AI to research and personalize'~Claude.\n"
            "\nHOW TO RUN THE INTERVIEW (your 'en' reply is the interviewer speaking, ENGLISH ONLY):\n"
            "- Have a REAL, free-flowing conversation - NOT a script. React to what she ACTUALLY said, "
            "build on her specific words, and let one answer lead naturally into the next thing you ask. "
            "Sometimes just a short human reaction, sometimes a deeper probe, sometimes a quick bit of "
            "context a real recruiter would share. Kill the robotic 'That sounds good. How do you...?' "
            "template.\n"
            "- YOU lead the interview at all times. NEVER ask the candidate what she wants to talk about, "
            "never offer to change the subject, never act like a generic chat assistant. After any "
            "pleasantry (e.g. she says 'thanks'), reply briefly and IMMEDIATELY continue with the next "
            "interview question. There is always a next question.\n"
            "- Speak natural, professional adult English in full sentences. Do NOT simplify, shorten, or "
            "slow down your English - Daniela is an experienced professional, talk to her like one.\n"
            "- Do not march through a fixed checklist. Follow the thread: circle back, ask 'why', "
            "challenge gently, react to a number she drops - like a human on a Zoom screening.\n"
            "- Over the whole conversation, naturally cover outbound-sales territory (cold-account "
            "strategy, objections, research, personalization, quota stories, why this role, "
            "expectations), and sometimes rephrase the SAME question in completely different words so she "
            "trains her ear.\n"
            "\nVARY YOUR DELIVERY (sound human, not scripted):\n"
            "- Do NOT reuse the same sentence template every turn (avoid always 'That sounds... How do "
            "you...'). Mix short reactions ('Got it.', 'Love that.', 'Makes sense.'), brief "
            "acknowledgements, and occasional warmth, like a real recruiter on a Zoom screening.\n"
            "- Sometimes ask the SAME underlying question rephrased in COMPLETELY different words across "
            "turns, so she trains her ear to recognize the intent behind any phrasing.\n"
            "\nANSWER COACH - fill the JSON 'correction' object on EVERY one of her turns (even great "
            "answers), never leave it null:\n"
            "- 'right' = a STRONGER, more compelling version of HER answer in natural English: tighter, "
            "with a number or concrete result when relevant, and bridging her tools to the target stack. "
            "If her answer is already strong, still give a polished model version she can study and repeat.\n"
            "- 'explanation_pt' = ONE short Portuguese line of CONTENT coaching (did she sell it? add a "
            "metric? bridge a tool? be more concise?), and ALWAYS end that line with the exact text "
            "'(versao mais natural e forte - opcional)' so it reads as a suggestion, not a scolding.\n"
            "- Set 'must_retry' to false. Only set it true if her English was genuinely impossible to "
            "understand.\n"
            '- Example of one turn: {"en":"That is a strong process. How do you decide which accounts to '
            'research first?","pt":"Esse e um processo forte. Como voce decide quais contas pesquisar '
            'primeiro?","suggested_words":[],"must_retry":false,"correction":{"wrong":"<her exact words>",'
            '"right":"My process starts with research: I map the account, find the 2-3 decision-makers, '
            'and use AI to pull a recent trigger before I reach out - which is how I consistently book 12 '
            'qualified meetings a month.","explanation_pt":"Conteudo: otimo processo - cite seu numero (12 '
            'reunioes/mes) pra vender o resultado. (versao mais natural e forte - opcional)"}}\n'
            "===== END MODO DANIELA OVERRIDE =====\n"
        )
        system_prompt = (system_prompt or "") + daniela_persona

    # Get cached model for this context (saves ~90% on system prompt tokens)



    context_model = get_cached_model_for_context(context_key, system_prompt, practice_mode)







    level_note = ""



    if student_level:



        level_note = (



            f"\n### STUDENT LEVEL\n"



            f"- Level: {student_level}. Adjust pace/support for this level, but keep vocabulary easy and everyday.\n"



        )



        if str(student_level).strip().lower() == 'zero':



            level_note += (



                "\n### ZERO BEGINNER RULES\n"



                "- This student is absolute beginner A0. Never expect spontaneous English.\n"



                "- Use English phrases with at most 4 words.\n"



                "- Use only everyday core words: I, you, am, are, is, like, want, need, have, happy, tired, hungry, good, bad, yes, no, please, water, food, home, work, today.\n"



                "- Never ask open questions. Always give 2 or 3 concrete answer options.\n"



                "- Show meaning with the format: EN — PT.\n"



                "- If the student answers in Portuguese, give one tiny English model and let them choose.\n"



            )







    objective_note = ""



    if objective_text:



        objective_note = f"\n### SESSION OBJECTIVE\n- {objective_text}\n"







    review_note = ""



    if practice_mode != 'simulator' and isinstance(turn_count, int) and turn_count and (turn_count % 4 == 0):



        if recent_corrections:



            focus_phrase = recent_corrections[-1]



            review_note = (



                "\n### QUICK REVIEW\n"



                f"- Ask the student to reuse this corrected phrase naturally: \"{focus_phrase}\".\n"



                "- Keep it short (1-2 sentences) and then ask a related follow-up question.\n"



            )







    language_nudge_note = ""



    # Only suppress nudge for PT grammar topics (where Portuguese is expected).



    # For scenario conversations, always nudge even if lessonLang is 'pt'.



    pt_grammar_mode = lesson_lang == 'pt' and is_grammar_topic



    if practice_mode != 'simulator' and not pt_grammar_mode and looks_portuguese(user_text):



        language_nudge_note = (



            "\n### LANGUAGE NUDGE\n"



            "- The student replied in Portuguese. Gently ask them to answer in English.\n"



            "- Give a short starter/model (5-8 words) to help them respond.\n"



        )







    short_reply_note = ""



    if practice_mode != 'simulator' and short_reply and not is_farewell:



        short_reply_note = (



            "\n### SHORT ANSWER\n"



            "- The student answered with very few words.\n"



            "- Ask for a slightly longer answer in a natural way (not as a command).\n"



            "- Give one short starter model they can reuse.\n"



            "- Avoid repeating the same teaching sentence every turn.\n"



        )







    farewell_note = ""



    if practice_mode != 'simulator' and is_farewell:



        farewell_note = (



            "\n### FAREWELL MOMENT\n"



            "- The student is ending the conversation.\n"



            "- Respond warmly in 1 short sentence and close naturally.\n"



            "- Do NOT start a new practice drill.\n"



            "- Do NOT ask a new transactional question.\n"



        )







    interest_note = "\n### INTEREST RULE\n- If the student mentions a personal topic, stay on it for at least 2 turns before changing.\n"



    easy_vocab_note = (



        "\n### GLOBAL LANGUAGE RULE (APPLIES TO ALL LEVELS)\n"



        "- Keep vocabulary easy and everyday whenever possible.\n"



        "- Prefer short, clear sentences.\n"



        "- Avoid rare, academic, or idiomatic words unless necessary.\n"



        "- If a complex word is needed, prefer a simpler synonym.\n"



    )







    common_notes = f"{level_note}{objective_note}{review_note}{language_nudge_note}{short_reply_note}{farewell_note}{interest_note}{easy_vocab_note}"







    # SIMULATOR MODE: REAL LIFE SIMULATOR - NO TEACHING



    SERVICE_SCENARIOS = {'coffee_shop', 'restaurant', 'hotel', 'airport', 'supermarket', 'pharmacy', 'bank', 'post_office', 'train_station', 'bus_stop', 'cinema', 'library', 'gas_station', 'hair_salon', 'clothing_store', 'bakery', 'dental_clinic', 'tech_support', 'pizza_delivery', 'renting_car', 'lost_found', 'gym', 'taxi', 'doctor', 'hospital'}



    is_service = context_key in SERVICE_SCENARIOS







    # Global easy-language instruction for every learner level.



    difficulty_instruction = """LANGUAGE STYLE (ALL LEVELS):



- Always prefer easy, everyday words.



- Keep sentences short and clear.



- Avoid advanced vocabulary, slang, and idioms when possible.



- Be natural and friendly, but simple."""







    if practice_mode == 'simulator':



        # Adapt language based on scenario type



        person_label = "customer" if is_service else "person"



        role_label = "a real service worker (barista, waiter, receptionist, etc)" if is_service else "the character described in your role above"







        if is_service:



            proactive_section = """PROACTIVE SERVICE (CRITICAL):



- NEVER ask generic questions like "Is there anything else I can assist you with?"



- ALWAYS offer 2-3 concrete options relevant to the context



- Guide the conversation by suggesting specific next steps



Examples:



- Hotel: "I can help with check-in, room service, or local recommendations."



- Coffee: "Would you like that hot or iced? Small, medium, or large?"



- Restaurant: "Would you prefer a table by the window, or our quieter section?"



"""



            end_section = "END CONDITION:\nWhen order is complete: Ask about payment \u2192 Confirm method \u2192 Close politely"



            confirmation_section = """CONFIRMATION RULE:



When confirming an order, do NOT turn it into practice.



- CORRECT: "Alright, one large hot coffee."



- WRONG: "I'd like a large hot coffee, please! Can you say that?"



"""



        else:



            proactive_section = """NATURAL CONVERSATION FLOW (CRITICAL):



- NEVER ask generic or off-topic questions



- ALWAYS keep questions relevant to the specific scenario context



- Guide the conversation naturally toward the next logical step



- Stay strictly within the domain of your role



"""



            end_section = "END CONDITION:\nWhen the interaction reaches its natural conclusion, wrap up politely and professionally."



            confirmation_section = ""







        full_prompt = f"""{system_prompt}



{conversation_history}







YOU ARE IN REAL LIFE SIMULATOR MODE.



The {person_label} just said: "{user_text}"







CORE RULE:



You must ALWAYS act like {role_label}.



You must NEVER act like a teacher, tutor, or language teacher.



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



- Ask only questions that your character would naturally ask in this scenario



- Respond naturally to what the {person_label} says



- Offer real options that exist in the scenario



- Handle misunderstandings like a human (ask to repeat or clarify)



- Stay 100% within the domain of your role and scenario







{difficulty_instruction}







COMPLETE SENTENCES (CRITICAL):



- NEVER end a sentence with "or", "and", a comma, or an ellipsis.



- NEVER split options across multiple turns. List ALL options in one complete sentence.







{proactive_section}







CONVERSATION FLOW (MOST CRITICAL RULE):



- Your response MUST ALWAYS end with a question mark (?). NO EXCEPTIONS.



- NEVER end with just a statement or affirmation. NEVER leave the {person_label} with nothing to respond to.



- The question must be RELEVANT to the current context and advance the interaction toward the goal.



- You must LEAD the conversation by asking for the next piece of information needed.







RECAST RULE (VERY IMPORTANT):



If the user says something incorrect in English:



- DO NOT correct explicitly



- DO NOT explain



- Simply respond using the correct, natural version







{confirmation_section}







META QUESTIONS FROM USER:



If the user questions the simulation or asks meta questions:



- Answer briefly (1 sentence)



- Reaffirm the role without mentioning "teacher", "lesson", "tutor", or "grammar"



- Preferred redirect style: "I can help with your <service> right now."



- Immediately return to the scenario







RESPONSE LENGTH (CRITICAL):



- Keep responses short: 1-2 sentences max (under 30 words).



- Structure: brief reaction/confirmation + one question. Like a real person, not an interrogation.







FLOW CONTROL:



- One question at a time



- Never repeat a question already answered



- Never explain what you are doing







{end_section}







Your ONLY goal: Simulate a real interaction so naturally that the user forgets this is an AI.







### RESPONSE FORMAT



Return JSON: {{"en": "your response", "pt": "tradução em português", "feedback": "Quick grammar tip or encouragement about what the student just said (1 sentence max, in Portuguese). Example: 'Ótimo vocabulário!' or 'Dica: use could em vez de can para ser mais educado.' If nothing to correct, just encourage briefly."}}



"""



    elif is_grammar_topic:



        if is_demonstratives and lesson_lang == 'pt':



            full_prompt = f"""{system_prompt}







### MODO PORTUGUES-INGLES (BILINGUAL)



Você e uma professora de inglês humana, proxima e natural. Fale como em uma conversa real.



Quando usar exemplos em inglês, marque com [EN]exemplo em inglês[/EN].







### TEACHER MODE - DEMONSTRATIVOS (INTERMEDIARIO)



REGRAS DURAS:



- Cada mensagem deve terminar com uma tarefa/pergunta aberta que obrigue o aluno a responder.



- Cada mensagem deve ter entre 20 e 60 palavras.



- Estrutura obrigatoria: (A) 1 frase amigavel curta + (B) 1 frase curta de ensino + (C) 1 tarefa/pergunta.



- Depois de cumprimentar, volte ao tema na mesma mensagem.



- Em cada turno, exija que o aluno use pelo menos um de: [EN]this[/EN], [EN]that[/EN], [EN]these[/EN], [EN]those[/EN].



- No maximo 2 exemplos por turno.



- Nao repita a frase inteira do aluno. Se corrigir, use: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]."







### MICRO-ENSINO



[EN]This/These[/EN] = perto (singular/plural)



[EN]That/Those[/EN] = longe (singular/plural)



Tambem pode ser distancia no tempo: [EN]that day[/EN], [EN]those years[/EN].



{common_notes}



{slowdown_note}







### SITUACAO ATUAL



O aluno disse: "{user_text}"







### FORMATO DE SAIDA



Retorne APENAS JSON: {{"pt": "...", "suggested_words": ["word1","word2","word3","word4"], "must_retry": true}}



"""



        elif is_demonstratives and lesson_lang != 'pt':



            full_prompt = f"""{system_prompt}







### TEACHER MODE - DEMONSTRATIVES (INTERMEDIATE)



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



{common_notes}



{slowdown_note}







### CURRENT SITUATION



The student just said: "{user_text}"







### OUTPUT FORMAT



Return ONLY JSON: {{"en": "...", "suggested_words": ["word1","word2","word3","word4"], "must_retry": true}}



"""



        elif lesson_lang == 'pt':



            # PORTUGUESE MODE: Topic-focused bilingual approach



            topic_title = GRAMMAR_TOPIC_TITLES.get(context_key, context_key.replace('_', ' ').title())



            full_prompt = f"""{system_prompt}







### MODO PORTUGUES-INGLES (BILINGUAL)



Você e uma professora de inglês humana, proxima e natural. Fale como em uma conversa real.



Quando usar exemplos em inglês, marque com [EN]exemplo em inglês[/EN].



{conversation_history}



{common_notes}



{slowdown_note}



### SITUACAO ATUAL



O aluno disse: "{user_text}"







### FOCO DO TOPICO: {topic_title} (REGRA MAIS IMPORTANTE)



- Você esta ensinando **{topic_title}**. TODA resposta DEVE incluir um exemplo natural deste ponto gramatical.



- Se o aluno mudar de assunto, reconheca brevemente e redirecione: "Interessante! A proposito..." e volte para {topic_title}.



- Suas perguntas devem fazer o aluno USAR {topic_title} na resposta.



- ERRADO: Conversa generica que ignora o topico gramatical.



- CERTO: Cada resposta modela e prática {topic_title} naturalmente.







### REGRAS CRITICAS



1. Se o aluno fizer uma PERGUNTA, responda PRIMEIRO, depois redirecione para {topic_title}.



2. Seja uma parceira de conversa REAL que naturalmente inclui {topic_title} em toda resposta.



3. So corrija ERROS GRAMATICAIS REAIS (especialmente erros relacionados a {topic_title}).



4. NAO corrija alternativas validas! Ex: [EN]doing great[/EN] e [EN]doing well[/EN] sao AMBOS corretos.



5. Se o inglês do aluno estiver correto, continue a conversa usando exemplos de {topic_title}.







### COMO RESPONDER



- Reaja ao conteudo e mantenha a conversa fluindo EM TORNO DE {topic_title}.



- Se houver ERRO REAL, corrija: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]."



- Responda em PORTUGUES BRASILEIRO. Ingles sempre em [EN]...[/EN].



- 1 a 2 frases curtas.



- **REGRA OBRIGATORIA**: Sua resposta DEVE SEMPRE terminar com uma PERGUNTA que faca o aluno praticar {topic_title}.



- suggested_words: APENAS quando houver ERRO GRAMATICAL REAL; senao [].



- must_retry: true APENAS se suggested_words nao estiver vazio; senao false.



- Retorne JSON: {{"pt": "...", "suggested_words": [], "must_retry": false}}



"""



        else:



            # ENGLISH MODE: Topic-focused immersion approach



            topic_title = GRAMMAR_TOPIC_TITLES.get(context_key, context_key.replace('_', ' ').title())



            full_prompt = f"""{system_prompt}



{conversation_history}



{common_notes}



{slowdown_note}



### CURRENT SITUATION



The student just said: "{user_text}"







### TOPIC FOCUS: {topic_title} (MOST IMPORTANT RULE)



- You are teaching **{topic_title}**. EVERY response MUST include a natural example of this grammar point.



- If the student drifts off topic, acknowledge briefly, then redirect: "That's interesting! By the way..." and bring back {topic_title}.



- Your questions must be designed to make the student USE {topic_title} in their answer.



- WRONG: Generic conversation that ignores the grammar topic.



- RIGHT: Every response naturally models and practices {topic_title}.







### CRITICAL RULES



1. If the student asks you a QUESTION, answer it FIRST, then redirect back to {topic_title}.



2. Be a REAL conversation partner who naturally weaves {topic_title} into every response.



3. Only correct REAL GRAMMAR ERRORS (especially errors related to {topic_title}).



4. Do NOT correct valid alternatives! "doing great" and "doing well" are BOTH correct.



5. If their English is correct, continue the conversation using {topic_title} examples.







### NO TECHNICAL GRAMMAR TERMS (CRITICAL)



- NEVER use grammar terminology like: "first conditional", "zero conditional", "present perfect",



  "past simple", "vowel sound", "subject-verb agreement", "auxiliary verb", "conjugation", etc.



- Instead of explaining rules, just show the correct form naturally.



- WRONG: "That's a good example of a first conditional!"



- RIGHT: "Nice sentence! So, what will you do if it rains?"



- The student is learning by DOING, not by studying theory.







### HOW TO RESPOND



- React to what they said and keep the conversation flowing AROUND {topic_title}.



- If there's a REAL error, correct it briefly: "Instead of <short snippet>, say: <corrected>."



- Speak in English (simple, natural, friendly).



- Keep responses SHORT: max 2 sentences, under 30 words total. Correction + question.



- **MANDATORY RULE**: Your response MUST ALWAYS end with a QUESTION that makes the student practice {topic_title}.



- suggested_words: ONLY when there is a REAL GRAMMAR ERROR; otherwise [].



- must_retry: true ONLY if suggested_words is not empty; else false.



- Return JSON: {{"en": "...", "suggested_words": [], "must_retry": false}}



"""



    else:



        # Standard scenario mode (Learning mode = structured teaching)



        if practice_mode == 'learning':



            # LEARNING MODE: Natural scenario character with structured corrections in JSON



            full_prompt = f"""{system_prompt}



{conversation_history}



{common_notes}



{slowdown_note}



Student just said: "{user_text}"







### YOU ARE THE SCENARIO CHARACTER — NOT A TEACHER



Respond naturally as the character in this scenario (barista, receptionist, waiter, etc).



Your "en" field must sound like a REAL person — never like a teacher or tutor.







### ABSOLUTE PROHIBITIONS (in the "en" field):



- "Instead of X, say Y" or "Em vez de X, diga Y"



- "Useful phrase:" or "Frase útil:"



- "In English, we..." or grammar explanations



- "Try saying..." or "Repeat after me"



- "Good job!" or praise for language skills



- Modeling phrases for the student to say



- Any correction, coaching, or teaching language



- "I will show you..." or "Let me teach you..."







### RECAST RULE (CRITICAL):



If the student makes a grammar error, respond using the correct form naturally — WITHOUT explaining.



Example: Student: "I wants two coffee" → You: "Sure, two coffees coming right up. Would you like those hot or iced?"



Example: Student: "How much costs a cappuccino?" → You: "A cappuccino costs $4.50. Would you like one?"



The recast is IMPLICIT in your response. The EXPLICIT correction goes ONLY in the "correction" field.







### RESPONSE BEHAVIOR:



- Keep responses short: 1-2 sentences, under 30 words



- End most turns with a question that advances the scenario



- Stay 100% in character at all times



- Use beginner-friendly vocabulary (A1/A2)



- One question at a time — never multiple questions



- NEVER repeat a question already answered







### GREETING HANDLING:



If the student greets you ("Hi", "Hello", "Good morning"):



- Respond naturally as the character (1 short line)



- If the student tells you their name, ALWAYS use it in your response (e.g., "Welcome, Mr. Wesley!" not just "Welcome, Mr.")



- Immediately start the scenario with a relevant question



- Example (Hotel): "Good morning, Wesley! Welcome to our hotel. Do you have a reservation?"



- Example (Coffee): "Hi there! What can I get started for you?"







### FIRST MESSAGE:



Your FIRST message must:



1. Greet briefly as the character



2. Immediately ask the first scenario-relevant question



Example (Hotel): "Good morning, welcome! Do you have a reservation, or would you like to book a room?"



After the first message, just keep advancing the scenario naturally.







### HOW TO LEAD:



- Move to the next logical step in the scenario after each exchange



- NEVER stay on the same topic for more than 2 exchanges



- Offer concrete options when relevant (e.g., "small, medium, or large?")







### CORRECTIONS — USE ONLY THE "correction" JSON FIELD



If the student uses WORDS THAT DO NOT EXIST in English (e.g., "chole", "buyed", "goed", "maked"):



- This is ALWAYS an error — set "correction" with what they likely meant



- CRITICAL: "right" MUST be the COMPLETE corrected sentence



- Set "must_retry" to true



- Explain in Portuguese what the correct word/phrase is







If the student has a CLEAR grammar error (wrong verb form, wrong tense, wrong word order):



- Set "correction" field with wrong/right/explanation_pt



- CRITICAL: "right" MUST be the COMPLETE corrected sentence (not just the corrected word or fragment)



- Set "suggested_words" to 3-4 helpful words



- Set "must_retry" to true







If the student's phrasing is understandable but could be more natural/polite:



- Set "correction" field (mark explanation_pt as optional/style upgrade)



- CRITICAL: "right" MUST be the COMPLETE corrected sentence



- Keep "must_retry" as false, "suggested_words" as []







If the student is correct:



- Set "correction" to null



- "suggested_words": [], "must_retry": false







IMPORTANT: ONLY mark as correct if ALL words in the sentence are real English words AND grammar is correct.







### EXAMPLE WITH ERROR (Coffee Shop):



Student: "I wants two coffee"



CORRECT JSON:



{{"en": "Sure, two coffees coming right up! Would you like those hot or iced?", "pt": "Claro, dois cafes saindo! Você quer quente ou gelado?", "suggested_words": ["I", "want", "two", "coffees"], "must_retry": true, "correction": {{"wrong": "I wants two coffee", "right": "I want two coffees, please", "explanation_pt": "Use 'I want' (sem 's') e 'coffees' no plural."}}}}







### EXAMPLE WITHOUT ERROR (Coffee Shop):



Student: "Can I have a medium latte with oat milk?"



CORRECT JSON:



{{"en": "Of course! Would you like anything else with that?", "pt": "Claro! Gostaria de mais alguma coisa?", "suggested_words": [], "must_retry": false, "correction": null}}







### EXAMPLE STYLE UPGRADE (Coffee Shop):



Student: "Give me coffee"



CORRECT JSON:



{{"en": "Sure thing! What size would you like?", "pt": "Pode deixar! Qual tamanho?", "suggested_words": [], "must_retry": false, "correction": {{"wrong": "Give me coffee", "right": "Can I have a coffee, please?", "explanation_pt": "Dica opcional: 'Can I have...' soa mais educado que 'Give me...'."}}}}







### RESPONSE FORMAT



Return ONLY valid JSON:



{{"en": "natural character response", "pt": "tradução em português", "suggested_words": [], "must_retry": false, "correction": null}}



When there IS an error: {{"en": "...", "pt": "...", "suggested_words": ["w1","w2","w3","w4"], "must_retry": true, "correction": {{"wrong": "...", "right": "...", "explanation_pt": "..."}}}}



"""



        else:



            # FREE CONVERSATION MODE: Casual conversation partner



            full_prompt = f"""{system_prompt}







IMPORTANT: You are a friendly English conversation partner.



{conversation_history}



{common_notes}



User just said: "{user_text}"







CRITICAL RULES:



1. If the student asks you a QUESTION, you MUST answer it first before continuing. Never ignore their questions!



2. Be a real conversation partner, NOT a correction machine. If their English is correct, just chat naturally.



3. Only correct REAL GRAMMAR ERRORS (wrong verb tense, subject-verb disagreement, wrong preposition, etc).



4. Do NOT correct valid alternatives! "doing great" and "doing well" are BOTH correct - don't "fix" one to the other.



5. Keep the conversation moving: ask a follow-up in most turns, but a complete direct answer is allowed when appropriate.



6. Avoid generic closers like "What about you?" - ask a specific follow-up related to what the student said.



7. Keep language EASY: use common daily words and short clear sentences.



8. Avoid slang, idioms, and rare words whenever possible.







Response format:



- Respond naturally in English, provide Portuguese translation.



- If correcting a REAL error, use: "Instead of <short snippet>, say: <corrected>."



- Ask thoughtful follow-ups often, but avoid turning every turn into an interrogation.



- suggested_words: ONLY when there is a REAL GRAMMAR ERROR; otherwise [].



- must_retry: true ONLY if suggested_words is not empty; else false.



- Return JSON: {{"en": "...", "pt": "...", "suggested_words": [], "must_retry": false}}







Keep responses to 1-3 short sentences (about 20-45 words total).



"""







    try:



        # Use cached model with just the user-specific prompt (system already cached)



        # For cached models, only send the dynamic part (user text + current situation)



        if context_model != model:



            # Using cached model - send minimal prompt



            if practice_mode == 'simulator':



                # SIMULATOR MODE: REAL LIFE - NO TEACHING



                speaker_label = "Customer" if is_service else "Person"



                sim_role_label = "a REAL service worker" if is_service else "the real scenario character"



                minimal_prompt = f"""{conversation_history}



{speaker_label} just said: "{user_text}"







REAL LIFE SIMULATOR. You are {sim_role_label}. NOT a teacher.



This is NOT a lesson. NOT practice. NOT teaching.







ABSOLUTE PROHIBITIONS (simulation FAILS if you do these):



- "Can you try?" / "Repeat after me" / "Let's practice"



- "How about you?" / "What do you think?" / "Does that make sense?"



- "Good job!" / Any praise for language



- Any request to repeat or practice English







RECAST RULE:



If user says incorrect English -> respond using correct form naturally. NO explanation.



Example: "Can we small?" -> "No problem - a small coffee."







CONFIRMATION RULE:



- CORRECT: "Alright, one large hot coffee."



- WRONG: "Can you say that?"







META QUESTIONS:



Answer briefly -> reaffirm role -> return to scenario.



Do not use words like teacher/lesson/tutor/grammar.



Example: "I can help with your order right now. What else can I get for you?"







FLOW: One question at a time. Never repeat answered questions.







RESPONSE LENGTH: 1-2 sentences max (under 30 words). Brief reaction + one question. Natural, not an interrogation.







PROACTIVE SERVICE:



- NEVER say "Is there anything else I can assist you with?"



- ALWAYS offer 2-3 concrete options (e.g., "I can help with check-in, room service, or local recommendations.")







CONVERSATION FLOW (MOST CRITICAL):



- EVERY response MUST end with a question mark (?). NO EXCEPTIONS.



- NEVER end with just a statement. Always ask a RELEVANT follow-up question.



- WRONG: "I'd be happy to get you checked in." -> RIGHT: "I'd be happy to help with check-in. May I see your ID?"



- Lead the conversation toward the goal with specific, contextual questions.







{difficulty_instruction}







COMPLETE SENTENCES: NEVER end with "or", "and", comma, or "...". Always finish the full list of options.







Return JSON: {{"en": "your response", "pt": "tradução em português", "feedback": "Quick grammar tip or encouragement about what the student just said (1 sentence max, in Portuguese). Example: 'Ótimo vocabulário!' or 'Dica: use could em vez de can para ser mais educado.' If nothing to correct, just encourage briefly."}}"""



            elif is_grammar_topic:



                if is_demonstratives and lesson_lang == 'pt':



                    minimal_prompt = f"""### SITUACAO ATUAL



O aluno disse: "{user_text}"



{common_notes}



{slowdown_note}







Teacher mode (demonstrativos):



- 20-60 palavras.



- Estrutura: 1 frase amigavel + 1 frase de ensino + 1 tarefa/pergunta.



- Exigir uso de [EN]this/that/these/those[/EN] pelo aluno.



- No maximo 2 exemplos.



- Se corrigir, use: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]."



Retorne apenas JSON: {{"pt": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.



"""



                elif is_demonstratives and lesson_lang != 'pt':



                    minimal_prompt = f"""### CURRENT SITUATION



The student just said: "{user_text}"



{common_notes}



{slowdown_note}







Teacher mode (demonstratives):



- 40-110 words.



- Structure: 1 friendly line + 1 teaching line + 1 task/question.



- Require the student to use this/that/these/those.



- Max 2 examples.



- If correcting, use: "Instead of <short snippet>, say: <corrected>."



Return only JSON: {{"en": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.



"""



                elif lesson_lang == 'pt':



                    topic_title = GRAMMAR_TOPIC_TITLES.get(context_key, context_key.replace('_', ' ').title())



                    minimal_prompt = f"""### SITUACAO ATUAL



O aluno disse: "{user_text}"



{common_notes}



{slowdown_note}







FOCO DO TOPICO: {topic_title}



TODA resposta DEVE incluir exemplo natural de {topic_title}. Se o aluno mudar de assunto, redirecione para {topic_title}.



Suas perguntas devem fazer o aluno USAR {topic_title} na resposta.



Use português e marque inglês com [EN]...[/EN]. Evite "aula/licao/exercicio/gramatica".



1-2 frases curtas (max ~16 palavras cada) e termine com uma pergunta sobre {topic_title}.



Se corrigir, use: "Em vez de [EN]trecho curto[/EN], diga: [EN]frase correta[/EN]." (max 4 palavras do aluno).



Nao repita a frase inteira do aluno.



suggested_words: 4 palavras/expressoes curtas quando houver erro ou oportunidade; senao [].



must_retry: true se suggested_words nao estiver vazio; senao false.



Retorne apenas JSON: {{"pt": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.



"""



                else:



                    topic_title = GRAMMAR_TOPIC_TITLES.get(context_key, context_key.replace('_', ' ').title())



                    minimal_prompt = f"""### CURRENT SITUATION



The student just said: "{user_text}"



{common_notes}



{slowdown_note}







TOPIC FOCUS: {topic_title}



EVERY response MUST include a natural example of {topic_title}. If the student drifts off topic, redirect back to {topic_title}.



Your questions must make the student USE {topic_title} in their answer.



Use simple English. Avoid "lesson/grammar/exercise". No grammar terms (conditional, present perfect, etc).



1-2 short sentences (max 30 words total), end with a question about {topic_title}.



If you correct, use: "Instead of <short snippet>, say: <corrected>." (max 4 words from the student).



Do not repeat the full student sentence. Do not explain grammar rules.



suggested_words: 4 short words/phrases when there is a mistake or clear improvement; otherwise [].



must_retry: true if suggested_words is not empty; else false.



Return only JSON: {{"en": "...", "suggested_words": ["...","...","...","..."], "must_retry": true}}.



"""



            else:



                if practice_mode == 'learning':



                    # LEARNING MODE: Natural character with structured corrections in JSON



                    minimal_prompt = f"""{conversation_history}



{common_notes}



{slowdown_note}



Student said: "{user_text}"







You are the SCENARIO CHARACTER (barista, receptionist, waiter, etc) — NOT a teacher.



Respond naturally as this character. Keep responses short (1-2 sentences, max 30 words).







ABSOLUTE PROHIBITIONS in the "en" field:



- "Instead of X, say Y" or grammar explanations



- "Useful phrase:" or teaching language



- "In English, we..." or coaching directives



- Modeling phrases for the student



- "Good job!" or praise for language skills







RECAST RULE: If student has grammar error, respond using the correct form naturally.



Example: Student: "I wants coffee" → You: "Sure, I can get that coffee for you. Hot or iced?"







All corrections go ONLY in the "correction" JSON field.







GRAMMAR ERROR DETECTION (CRITICAL):



- If the student uses WORDS THAT DO NOT EXIST in English (e.g., "chole", "buyed", "goed", "maked"), this is ALWAYS an error



- If the student's sentence has a CLEAR grammar error (wrong verb form, wrong tense), you MUST:



  1. Set "correction" with wrong/right/explanation_pt — "right" MUST be the COMPLETE corrected sentence (NOT just the corrected word)



  2. Set "suggested_words" to 3-4 helpful words



  3. Set "must_retry" to true



- Examples of CLEAR errors: "He have" (has), "She don't" (doesn't), "They was" (were), "I goed" (went), "chole" (not a word)



- ONLY mark as correct if ALL words are real English words AND grammar is correct



- Do NOT flag correct sentences as errors. "I have been here since morning" is CORRECT — do NOT correct it.



- Only set must_retry to true for REAL grammar mistakes, never for style preferences.







Return JSON: {{"en": "natural response as character", "pt": "tradução", "suggested_words": [], "must_retry": false, "correction": null}}



If there IS an error: {{"en": "natural response with recast", "pt": "tradução", "suggested_words": ["w1","w2","w3"], "must_retry": true, "correction": {{"wrong": "I wants a coffee", "right": "I want a coffee, please.", "explanation_pt": "explicação em português"}}}}



For style suggestion (no retry): {{"en": "...", "pt": "...", "suggested_words": [], "must_retry": false, "correction": {{"wrong": "Give me coffee", "right": "Can I have a coffee, please?", "explanation_pt": "dica opcional..."}}}}"""



                else:



                    # FREE CONVERSATION MODE: Casual conversation partner



                    minimal_prompt = f"""{conversation_history}



{common_notes}



User just said: "{user_text}"







CRITICAL RULES:



1. If user asks a QUESTION, answer it first! Never ignore questions.



2. Be a friendly conversation partner with MEMORY of the conversation above.



3. Only correct REAL GRAMMAR ERRORS. Do NOT "fix" valid alternatives.



4. Keep 1-3 short sentences (roughly 20-45 words total).



5. Keep the flow natural: ask follow-up questions often, but direct complete answers are allowed.



6. Avoid generic closers like "What about you?" - ask a specific follow-up related to the user's message.



7. Keep language EASY: use common daily words and short clear sentences.



8. Avoid slang, idioms, and rare words whenever possible.



suggested_words: ONLY for real grammar errors; otherwise [].



must_retry: true ONLY if suggested_words not empty; else false.



Return JSON: {{"en": "...", "pt": "...", "suggested_words": [], "must_retry": false}}."""



            # Mode-aware token limits for lower latency while keeping natural output.



            mode_gen_config = {"max_output_tokens": MAX_OUTPUT_TOKENS_LEARNING} if practice_mode == 'learning' else {"max_output_tokens": MAX_OUTPUT_TOKENS_SIMULATOR}



            response = context_model.generate_content(minimal_prompt, generation_config=mode_gen_config)



        else:



            # Fallback to basic model with full prompt



            mode_gen_config = {"max_output_tokens": MAX_OUTPUT_TOKENS_LEARNING} if practice_mode == 'learning' else {"max_output_tokens": MAX_OUTPUT_TOKENS_SIMULATOR}



            response = model.generate_content(full_prompt, generation_config=mode_gen_config)



        



        user_preview = _console_safe_preview(user_text, 50)



        response_preview = _console_safe_preview(getattr(response, 'text', ''), 100)



        print(f"[CHAT] User: {user_preview}... | Response: {response_preview}...")







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



            # Extract structured correction field (new Learning mode format)



            structured_correction = parsed.get('correction', None)



            if structured_correction and isinstance(structured_correction, dict):



                structured_correction = {



                    "wrong": str(structured_correction.get("wrong", "")).strip(),



                    "right": str(structured_correction.get("right", "")).strip(),



                    "explanation_pt": str(structured_correction.get("explanation_pt", "")).strip(),



                }



                # If correction has no meaningful content, discard it



                if not structured_correction["wrong"] and not structured_correction["right"]:



                    structured_correction = None



            else:



                structured_correction = None







            # Handle response based on lesson language mode



            if lesson_lang == 'pt' and is_grammar_topic:



                # PT mode for grammar topics: Use Portuguese text as primary (contains [EN] tags for English examples)



                ai_text = parsed.get('pt', raw_text)



                ai_trans = ''  # No separate translation needed in PT mode



            else:



                # EN mode: Use English as primary, Portuguese as translation



                ai_text = parsed.get('en', raw_text)



                ai_trans = parsed.get('pt', '')



                feedback = parsed.get('feedback', '') if practice_mode == 'simulator' else ''







            # NOW clean asterisks from the extracted content (but preserve [EN][/EN] tags)



            if ai_text:



                ai_text = ai_text.replace('*', '').replace('_', '').replace('~', '').replace('`', '')



                ai_text = _clean_learning_output_artifacts(ai_text)



            if ai_trans:



                ai_trans = ai_trans.replace('*', '').replace('_', '').replace('~', '').replace('`', '')



                ai_trans = _clean_learning_output_artifacts(ai_trans)







            # Normalize suggested_words



            if isinstance(suggested_words, str):



                suggested_words = [w.strip() for w in suggested_words.split(',') if w.strip()]



            if not isinstance(suggested_words, list):



                suggested_words = []



            suggested_words = [str(w).strip() for w in suggested_words if str(w).strip()]



            suggested_words = suggested_words[:4]







            # Initial retry guardrail: never force retry from style-only output.



            if not suggested_words:



                must_retry = False



            if is_demonstratives and not suggested_words and re.search(r'(Instead of|Em vez de)', ai_text or '', re.IGNORECASE):



                suggested_words = ["this", "that", "these", "those"]



                must_retry = True



                if not retry_prompt:



                    retry_prompt = "Veja 3 formas de responder a pergunta anterior:"







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



                    # Fallback deterministic teacher message - IMMEDIATE (No 2nd model call)



                    # This prevents Vercel timeouts by avoiding a double LLM round-trip.



                    if lesson_lang == 'pt':



                        ai_text = "Legal! Hoje vamos praticar [EN]this/that/these/those[/EN]. Regra rápida: [EN]this/these[/EN] = perto, [EN]that/those[/EN] = longe. Olhe ao seu redor e diga: o que é [EN]this[/EN] perto de você e o que é [EN]that[/EN] mais longe? Responda com duas frases curtas."



                    else:



                        ai_text = "Nice! Today we're practicing this/that/these/those. Quick rule: this/these = near, that/those = far. Look around you and tell me: what is this near you and what is that far from you? Answer with two short sentences."



                    suggested_words = ["this", "that", "these", "those"]



                    must_retry = True



                    retry_prompt = "Veja 3 formas de responder a pergunta anterior:"



                



        except (json.JSONDecodeError, AttributeError):



            # Fallback: regex extraction or raw text



            ai_text = raw_text



            ai_trans = ""



            



            # Try to rescue via regex if JSON parse failed



            try:



                if lesson_lang == 'pt' and is_grammar_topic:



                    # PT mode for grammar topics: look for pt field first



                    rescued_pt = _extract_json_field_value(raw_text, 'pt')



                    if rescued_pt:



                        ai_text = rescued_pt



                else:



                    # EN mode: look for en field, then pt for translation



                    rescued_en = _extract_json_field_value(raw_text, 'en')



                    rescued_pt = _extract_json_field_value(raw_text, 'pt')



                    if rescued_en:



                        ai_text = rescued_en



                    if rescued_pt:



                        ai_trans = rescued_pt



            except:



                pass







            # Clean the fallback text



            if ai_text:



                ai_text = ai_text.replace('*', '').replace('_', '').replace('~', '').replace('`', '')



                # Remove markdown json artifacts if they remain in raw text



                ai_text = ai_text.replace('```json', '').replace('```', '').replace('{', '').replace('}', '')



                ai_text = _clean_learning_output_artifacts(ai_text)



            if ai_trans:



                ai_trans = _clean_learning_output_artifacts(ai_trans)







        if 'suggested_words' not in locals():



            suggested_words = []



            must_retry = False



            retry_prompt = ""







        # Enforce shorter AI responses (avoid long monologues)



        def _word_count(value):



            return len(re.findall(r"[A-Za-z\u00C0-\u00FF0-9']+", value or ""))







        def _trim_sentences(value, max_sentences=2):



            if not value:



                return value



            protected = str(value).strip()



            # Prevent abbreviation dots (Dr., Mr., etc.) from being split as sentence boundaries.



            protected = re.sub(



                r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St)\.',



                lambda m: f"{m.group(1)}<DOT>",



                protected,



                flags=re.IGNORECASE



            )



            parts = re.split(r'(?<=[.!?])\s+', protected)



            parts = [p.replace('<DOT>', '.').strip() for p in parts if p.strip()]



            return ' '.join(parts[:max_sentences]).strip()







        def _trim_words(value, max_words):



            if not value:



                return value



            words = value.split()



            if len(words) <= max_words:



                return value



            return ' '.join(words[:max_words]).rstrip() + '...'







        def _is_single_question_only(value):



            if not value:



                return False



            stripped = str(value).strip()



            if not stripped.endswith('?'):



                return False



            questions = _extract_questions_from_text(stripped)



            if len(questions) != 1:



                return False



            # No obvious previous sentence before the trailing question



            return not re.search(r'[.!]\s+', stripped)







        user_words = _word_count(user_text)



        # Learning mode needs more words for teaching + translation + question



        if practice_mode == 'learning':



            max_words = max(40, int(user_words * 2.5)) if user_words else 40



        else:



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







        recent_turns_for_user = user_conversations.get(user_id, [])



        context_memory_snapshot = _build_question_memory_snapshot(



            context_key,



            recent_turns_for_user,



            current_user_text=user_text



        )







        # CRITICAL: Ensure response ALWAYS ends with a question



        # If AI failed to include a question, append a follow-up question



        def _ensure_ends_with_question_pair(text, context=''):



            """Returns (en_text_with_question, pt_question_appended_or_None)."""



            if not text:



                return text, None



            text = text.strip()



            if text.endswith('?'):



                return text, None







            # Grammar topics: fixed pair



            if is_grammar_topic:



                en_q = "Can you give me one more example about your life?"



                pt_q = "Me de mais um exemplo sobre isso?"



                return f"{text} {en_q}", pt_q







            key = (context or context_key or '').lower()



            en_q, pt_q = _choose_follow_up_question_pair(key, context_memory_snapshot)



            return f"{text} {en_q}", pt_q







        # Strip "Today you will learn" from non-first messages in learning mode



        if practice_mode == 'learning' and conversation_history:



            import re as _re



            ai_text = _re.sub(r'Today you will learn[^.]*\.?\s*', '', ai_text, flags=_re.IGNORECASE).strip()



            ai_text = _re.sub(r'Learning mode:\s*[^.!?]*[.!?]?\s*', '', ai_text, flags=_re.IGNORECASE).strip()



            ai_text = _re.sub(r'I will\s+(coach|show|give|share)\s+(easy\s+|simple\s+)?(lines?|sentences?|phrases?)\s+you\s+can\s+(say|use)[^.!?]*[.!?]?\s*', '', ai_text, flags=_re.IGNORECASE).strip()



            if ai_trans:



                ai_trans = _re.sub(r'Hoje você (vai|irá) aprender[^.]*\.?\s*', '', ai_trans, flags=_re.IGNORECASE).strip()



                ai_trans = _re.sub(r'Modo Learning:\s*[^.!?]*[.!?]?\s*', '', ai_trans, flags=_re.IGNORECASE).strip()



                ai_trans = _re.sub(r'(Eu vou|Vou)\s+(guiar|mostrar|dar)\s+frases?\s+(simples\s+)?que\s+você\s+pode\s+(dizer|usar)[^.!?]*[.!?]?\s*', '', ai_trans, flags=_re.IGNORECASE).strip()







        # Rewrite repeated/answered trailing questions to improve memory and didactics.



        if practice_mode == 'learning':



            ai_text, rewritten_pt = _rewrite_repetitive_trailing_question(



                ai_text,



                context_key,



                context_memory_snapshot



            )



            if ai_trans and rewritten_pt:



                if _is_single_question_only(ai_text):



                    ai_trans = rewritten_pt



                elif not ai_trans.strip().endswith('?'):



                    ai_trans = f"{ai_trans.strip()} {rewritten_pt}"







        # Question cadence:



        # - Simulator: never force questions (natural roleplay flow)



        # - Grammar learning: keep strong practice rhythm (always enforce)



        # - Other learning contexts: enforce every 2 turns or when student needs extra support



        should_enforce_question = False



        if practice_mode == 'learning':



            if is_farewell:



                should_enforce_question = False



            elif is_grammar_topic:



                should_enforce_question = True



            else:



                should_enforce_question = needs_slowdown or (isinstance(turn_count, int) and (turn_count <= 2 or turn_count % 2 == 0))



        if should_enforce_question:



            ai_text, appended_pt = _ensure_ends_with_question_pair(ai_text, context_key)



            if ai_trans and appended_pt:



                if not ai_trans.strip().endswith('?'):



                    ai_trans = f"{ai_trans.strip()} {appended_pt}"







        # Final guard: never end with a repeated or already-answered slot question.



        if practice_mode == 'learning':



            ai_text, rewritten_pt_final = _rewrite_repetitive_trailing_question(



                ai_text,



                context_key,



                context_memory_snapshot



            )



            if ai_trans and rewritten_pt_final:



                if _is_single_question_only(ai_text):



                    ai_trans = rewritten_pt_final



                elif not ai_trans.strip().endswith('?'):



                    ai_trans = f"{ai_trans.strip()} {rewritten_pt_final}"



            ai_text = _sanitize_learning_robotic_phrases(ai_text)



            if not is_grammar_topic:



                ai_text, ai_trans = _repair_learning_phrase_role(ai_text, ai_trans, context_key)



                ai_text = _strip_learning_staff_side_lines(ai_text)



                if ai_trans:



                    ai_trans = _strip_learning_staff_side_lines(ai_trans)



                if ai_text and not is_farewell and not ai_text.strip().endswith('?'):



                    ai_text, appended_pt_after_strip = _ensure_ends_with_question_pair(ai_text, context_key)



                    if ai_trans and appended_pt_after_strip and not ai_trans.strip().endswith('?'):



                        ai_trans = f"{ai_trans.strip()} {appended_pt_after_strip}"



            if is_farewell and ai_text.strip().endswith('?'):



                ai_text = "Thank you, have a great day!"



                if ai_trans:



                    ai_trans = "Obrigado, tenha um otimo dia!"







        if practice_mode == 'simulator':



            ai_text = _sanitize_simulator_meta_text(ai_text, context_key)



            if ai_trans:



                ai_trans = _sanitize_simulator_meta_text(ai_trans, context_key)



            if ai_text and not ai_text.strip().endswith('?'):



                ai_text, appended_pt_sim = _ensure_ends_with_question_pair(ai_text, context_key)



                if ai_trans and appended_pt_sim and not ai_trans.strip().endswith('?'):



                    ai_trans = f"{ai_trans.strip()} {appended_pt_sim}"







        # Keep Learning responses conversational; feedback is shown in structured popup instead.







        turn_feedback = _classify_turn_feedback(



            user_text,



            ai_text,



            practice_mode,



            must_retry=must_retry,



            suggested_words=suggested_words,



            structured_correction=locals().get('structured_correction', None)



        )







        if practice_mode == 'learning':



            ai_text = _strip_inline_learning_correction(ai_text)



            if ai_trans:



                ai_trans = _strip_inline_learning_correction(ai_trans)



            ai_text = _clean_learning_output_artifacts(ai_text)



            if ai_trans:



                ai_trans = _clean_learning_output_artifacts(ai_trans)







        # Global safety rule: retry only for real error correction.



        if practice_mode == 'learning' and turn_feedback and turn_feedback.get("kind") != "error_correction":



            must_retry = False



            retry_prompt = ""



            if not is_demonstratives:



                suggested_words = []







        if practice_mode == 'learning' and turn_feedback and turn_feedback.get("kind") == "error_correction":



            must_retry = True



            if not retry_prompt:



                retry_prompt = "Veja 3 formas de responder a pergunta anterior:"







        # Modo Daniela: a real interview should FLOW. Never hard-block with the retry overlay;
        # show every correction as a gentle, non-blocking coaching card (style_upgrade) instead.
        if is_daniela_profile and practice_mode == 'learning':
            must_retry = False
            retry_prompt = ""
            suggested_words = []
            if turn_feedback and turn_feedback.get("kind") == "error_correction":
                turn_feedback["kind"] = "style_upgrade"
                turn_feedback["retry_required"] = False

        # Store conversation for the user



        user_id = request.user_id



        if user_id not in user_conversations:



            user_conversations[user_id] = []







        user_conversations[user_id].append({



            "timestamp": datetime.now().isoformat(),



            "user": user_text,



            "ai": ai_text,



            "context": context_key,



            "mode": practice_mode



        })



        elapsed_ms = (time.perf_counter() - request_started_at) * 1000.0



        record_live_activity(



            user_id,



            user_email,



            "/api/chat",



            status="ok",



            context=context_key,



            mode=practice_mode,



            response_ms=elapsed_ms,



            extra={



                "must_retry": bool(must_retry),



                "suggested_words_count": len(suggested_words) if isinstance(suggested_words, list) else 0



            }



        )



        turn_correction = None



        if turn_feedback and turn_feedback.get("kind") == "error_correction":



            turn_correction = {



                "frase_aluno": turn_feedback.get("user_text", ""),



                "frase_natural": turn_feedback.get("suggested_text", ""),



                "explicacao": turn_feedback.get("reason", "")



            }







        return jsonify({



            "text": ai_text,



            "translation": ai_trans,



            "lessonLang": lesson_lang,



            "suggested_words": suggested_words,



            "retry_prompt": retry_prompt,



            "must_retry": must_retry,



            "feedback": locals().get('feedback', ''),



            "turn_correction": turn_correction,



            "turn_feedback": turn_feedback or {



                "kind": "none",



                "user_text": "",



                "suggested_text": "",



                "reason": "",



                "retry_required": False



            },



            "learning_correction_kind_enabled": LEARNING_CORRECTION_KIND_ENABLED



        })



    except Exception as e:



        import traceback



        print(f"[CHAT] Error: {e}")



        print(f"[CHAT] Traceback: {traceback.format_exc()}")



        elapsed_ms = (time.perf_counter() - request_started_at) * 1000.0
        error_text = str(e)
        error_lower = error_text.lower()
        is_transient_model_error = _is_transient_model_error(error_lower)

        if is_transient_model_error:
            record_live_activity(
                getattr(request, 'user_id', 'unknown'),
                getattr(request, 'user_email', ''),
                "/api/chat",
                status="model_transient_fallback",
                context=locals().get('context_key', ''),
                mode=locals().get('practice_mode', ''),
                response_ms=elapsed_ms
            )
            fallback_text = (
                "I'm having a short connection delay. Let's keep practicing: "
                "tell me one simple thing you did today."
            )
            fallback_translation = (
                "Estou com uma pequena demora de conexão. Vamos continuar praticando: "
                "me diga uma coisa simples que você fez hoje."
            )
            return jsonify({
                "text": fallback_text,
                "translation": fallback_translation,
                "lessonLang": locals().get('lesson_lang', 'en'),
                "suggested_words": ["I went", "I studied", "I worked"],
                "retry_prompt": "",
                "must_retry": False,
                "feedback": "",
                "turn_correction": None,
                "turn_feedback": {
                    "kind": "none",
                    "user_text": "",
                    "suggested_text": "",
                    "reason": "",
                    "retry_required": False
                },
                "learning_correction_kind_enabled": LEARNING_CORRECTION_KIND_ENABLED,
                "model_fallback": "transient_provider_unavailable"
            }), 200



        record_live_activity(



            getattr(request, 'user_id', 'unknown'),



            getattr(request, 'user_email', ''),



            "/api/chat",



            status="error",



            context=locals().get('context_key', ''),



            mode=locals().get('practice_mode', ''),



            response_ms=elapsed_ms



        )



        return jsonify({"error": f"Failed to generate response: {str(e)}"}), 500











def _sse_event(event_name, payload):
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """SSE-compatible chat endpoint.

    The active model path is non-streaming, so this endpoint delegates to
    /api/chat and returns a final SSE event. This keeps the frontend contract
    intact without causing a 405 followed by a duplicate model call.
    """
    response = app.make_response(chat())

    if response.status_code != 200:
        return response

    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return response

    return app.response_class(
        _sse_event("final", payload),
        status=200,
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route('/api/free-conversation', methods=['POST'])



@limiter.limit("30 per minute")



@require_auth



def free_conversation_action():



    request_started_at = time.perf_counter()



    if not GOOGLE_API_KEY or not model:



        record_live_activity(getattr(request, 'user_id', 'unknown'), getattr(request, 'user_email', ''), "/api/free-conversation", status="model_unavailable")



        return jsonify({"error": "AI service not configured"}), 500







    # Check daily usage limit



    user_email = request.user_email



    if not is_usage_exempt_request() and not check_usage_limit(user_email):



        remaining = get_remaining_seconds(user_email)



        is_portal_trial = bool(getattr(request, 'is_portal_trial', False))
        blocked_message = "Você usou os 10 minutos de IA de Conversação liberados para hoje." if is_portal_trial else (f"Practice is available on weekends only (Saturday-Sunday), {weekend_limit_label()} per weekend." if not is_weekend() else f"You've used your {weekend_limit_label()} for this weekend. See you next Saturday!")

        record_live_activity(getattr(request, 'user_id', 'unknown'), user_email, "/api/free-conversation", status="usage_blocked", mode="guided")
        return jsonify({



            "error": "Weekend practice limit reached",



            "message": blocked_message,
            "remaining_seconds": remaining,



            "is_weekend": True if is_portal_trial else is_weekend(),

            "portal_trial": is_portal_trial
        }), 429







    data = request.json or {}



    action = data.get('action', '').strip()



    main_question = data.get('main_question', '')



    student_answer = data.get('student_answer') or data.get('main_answer', '')



    followup_question = data.get('followup_question', '')



    followup_answer = data.get('followup_answer', '')



    student_question = data.get('student_question', '')



    previous_transition = data.get('previous_transition', '')



    previous_transitions = data.get('previous_transitions', [])



    mission_title = data.get('mission_title', '')



    mission_objective = data.get('mission_objective', '')



    mission_steps = data.get('mission_steps', [])



    mission_answers = data.get('mission_answers', [])



    if isinstance(previous_transitions, list):



        previous_transitions = [str(item).strip() for item in previous_transitions if str(item).strip()][:12]



    else:



        previous_transitions = []



    if previous_transition and previous_transition not in previous_transitions:



        previous_transitions.append(previous_transition)







    def compact_text(value):



        return re.sub(r'\s+', ' ', str(value or '')).strip()







    def trim_words(value, max_words):



        text = compact_text(value)



        if not text:



            return text



        words = text.split()



        if len(words) <= max_words:



            return text



        return ' '.join(words[:max_words])







    def ensure_question(value, fallback="What do you want to share next?"):



        text = compact_text(value) or fallback



        text = text.rstrip('.! ')



        if not text.endswith('?'):



            text = f"{text}?"



        return text







    def ensure_statement(value, fallback="Good answer."):



        text = compact_text(value) or fallback



        text = text.replace('?', '.').strip()



        if not text.endswith('.'):



            text = f"{text.rstrip('.! ')}."



        return text







    def normalize_transition(value):



        return re.sub(r'[^a-z0-9\s]', '', str(value or '').lower()).strip()







    forbidden_transition_snippets = [



        "what else is on your mind",



        "what would you like to talk about next",



        "do you want to talk about something else",



        "what do you want to talk about now",



        "do you have any additional questions",



        "that was interesting"



    ]



    transition_fallbacks = [



        "What do you want to share next?",



        "Want to continue with one more idea?",



        "What is one more point for this?",



        "Do you want a new simple question?",



        "What can we explore now?"



    ]



    easy_question_styles = [



        "Use a simple WHAT question.",



        "Use a simple WHEN question.",



        "Use a simple WHERE question.",



        "Use a simple WHO question.",



        "Use a simple HOW question."



    ]



    simple_style_hint = random.choice(easy_question_styles)







    if not action:



        record_live_activity(getattr(request, 'user_id', 'unknown'), user_email, "/api/free-conversation", status="invalid_action", mode="guided")



        return jsonify({"error": "No action provided"}), 400







    system_prompt = (



        "You are a friendly English conversation partner for speaking practice. "



        "Do NOT correct grammar or comment on mistakes. "



        "Be natural, warm, and helpful. "



        "Use easy, everyday vocabulary whenever possible. "



        "Prefer short common words over formal or advanced words. "



        "Keep sentences short and clear. "



        "Respond ONLY in English. Do not include translations or Portuguese. "



        "Return only the requested content in plain English."



    )







    context_model = get_cached_model_for_context('free_conversation_guided', system_prompt, 'guided')



    active_model = context_model if context_model else model







    if action == 'followup':



        prompt = f"""{system_prompt}







Task: Create ONE short follow-up question in English based on the student's answer.



- Use 1 sentence.



- Max 10 words.



- Do not correct grammar.



- Use English only; no translations or other languages.



- Keep language EASY (A1/A2 words).



- Use short common words. Avoid abstract words and idioms.



- Style hint: {simple_style_hint}



- Output ONLY the question text.







Main question: "{main_question}"



Student answer: "{student_answer}"



"""



    elif action == 'opinion':



        prompt = f"""{system_prompt}







Task: React to what the student said with a genuine, brief comment.



- 1-2 sentences ONLY. Maximum 20 words.



- Share a real thought, a mild agreement, or a small personal touch - NOT empty praise.



- AVOID generic cheerleading like "That sounds amazing!" or "That must be so rewarding!".



- Do NOT start with "In my opinion" or "I completely agree".



- Reference ONE specific detail from the student's words.



- Do not correct grammar.



- Use English only.



- Keep language EASY (A1/A2 words).



- Use simple everyday words. Avoid slang, idioms, and rare words.



- Prefer words with 8 letters or less.



- Do NOT end with a question.



- Output ONLY the response text - no labels, no thinking, no extra words.







Main question: "{main_question}"



Student answer: "{student_answer}"



Follow-up question: "{followup_question}"



Follow-up answer: "{followup_answer}"



"""



    elif action == 'answer':



        prompt = f"""{system_prompt}







Task: Answer the student's question directly in English.



- 2-3 sentences. Maximum 30 words.



- Start with the answer right away - do NOT open with compliments like "That sounds great!" or "That's impressive!".



- Be conversational, like a friend answering a question.



- Do NOT mention being an AI or reference "chatting" or "conversations".



- Do not correct grammar.



- Use English only.



- Keep language EASY (A1/A2 words).



- Use simple everyday words. Avoid slang, idioms, and rare words.



- Prefer words with 8 letters or less.



- Do NOT end with a question.



- Output ONLY the response text - no labels, no thinking, no extra words.







Student question: "{student_question}"



Main question context: "{main_question}"



Student answer context: "{student_answer}"



"""



    elif action == 'react_intro':



        react_styles = [



            "Reply casually, like 'I am good, thanks!'",



            "Reply upbeat, like 'I am doing well today!'",



            "Reply relaxed, like 'I am fine, thank you!'",



            "Reply cheerfully, like 'I am okay, thanks!'",



            "Reply warmly, like 'I am doing fine today!'"



        ]



        react_style = random.choice(react_styles)



        prompt = f"""{system_prompt}







Task: The student just responded to your "How are you?" greeting. Reply briefly and warmly.



- 1 short sentence, max 10 words.



- If they asked how you are, answer naturally.



- Style hint: {react_style}



- Keep language EASY (A1/A2 words) with very common words.



- Avoid slang, idioms, and rare words.



- NEVER use the word "wonderful" or "great". Use fresh, varied words.



- Do NOT suggest a topic or ask another question.



- Output ONLY the response text - no labels, no thinking, no extra words.







Student said: "{student_answer}"



"""



    elif action == 'introduce_topic':



        prompt = f"""{system_prompt}







Task: Start a conversation about the topic below. Ask ONE open-ended question.



- 1 sentence ONLY. Maximum 10 words.



- Jump straight into a question; no filler.



- Sound like a curious friend, not an interviewer.



- Keep language EASY (A1/A2 words).



- Use short everyday words only.



- Style hint: {simple_style_hint}



- Output ONLY the question text.







Topic: "{main_question}"



"""



    elif action == 'transition':



        transition_styles = [



            "Ask if they want to keep going",



            "Ask what they want to talk about now",



            "Invite one more simple point",



            "Offer a new easy angle",



            "Ask for one short extra idea"



        ]



        trans_style = random.choice(transition_styles)



        previous_transitions_text = '\n'.join([f'- {item}' for item in previous_transitions]) if previous_transitions else ''



        prompt = f"""{system_prompt}







Task: Create a short, natural bridge question.



- 1 sentence, max 8 words.



- Keep language EASY (A1/A2 words).



- Use short common words.



- Approach: {trans_style}



- This is a TRANSITION, not a follow-up about the same detail.



- NEVER say "Do you have any additional questions" or "That was interesting".



- NEVER use the words "conversation", "topic", or "discuss".



- NEVER say these lines: "What would you like to talk about next?" and "What else is on your mind?"{f'''



- Do NOT repeat or closely copy these recent transitions:



{previous_transitions_text}''' if previous_transitions_text else ''}



- Output ONLY the question.







Topic discussed: "{main_question}"



"""



    elif action == 'mission_feedback':



        mission_steps = mission_steps if isinstance(mission_steps, list) else []



        mission_answers = mission_answers if isinstance(mission_answers, list) else []



        mission_pairs = []



        for idx, question in enumerate(mission_steps[:3]):



            answer = mission_answers[idx] if idx < len(mission_answers) else ''



            mission_pairs.append(f"Step {idx + 1} question: {str(question)} | Student answer: {str(answer)}")



        mission_pairs_text = "\n".join(mission_pairs) if mission_pairs else "No mission step details provided."







        prompt = f"""{system_prompt}







Task: The student finished an Easy Mission. Write short final feedback in English.



- Exactly 2 short sentences.



- Sentence 1 must start with: "Strong point:"



- Sentence 2 must start with: "Next step:"



- Keep language EASY (A1/A2 words) with very common vocabulary.



- Keep the whole feedback under 28 words.



- Be specific to the student's answers.



- Do NOT use grammar terms.



- Output ONLY the 2-sentence feedback text.







Mission title: "{mission_title}"



Mission objective: "{mission_objective}"



Mission details:



{mission_pairs_text}



"""



    else:



        record_live_activity(getattr(request, 'user_id', 'unknown'), user_email, "/api/free-conversation", status="invalid_action", mode="guided")



        return jsonify({"error": "Invalid action"}), 400







    try:



        response = active_model.generate_content(



            prompt,



            generation_config={"max_output_tokens": MAX_OUTPUT_TOKENS_GUIDED}



        )



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







        # Strip stray model thinking labels (e.g. "thoughts\nActual response")



        if '\n' in cleaned:



            lines = cleaned.split('\n')



            # If first line looks like a label (short, no punctuation), skip it



            if len(lines[0]) < 20 and not any(c in lines[0] for c in '.?!,'):



                cleaned = '\n'.join(lines[1:]).strip()







        # Enforce formatting rules



        if action == 'react_intro':



            cleaned = ensure_statement(trim_words(cleaned, 10), "I am fine, thanks.")



        elif action in ('followup', 'introduce_topic'):



            cleaned = ensure_question(trim_words(cleaned, 10))



        elif action == 'transition':



            cleaned = ensure_question(trim_words(cleaned, 8))



            normalized = normalize_transition(cleaned)



            recent_norms = [normalize_transition(item) for item in previous_transitions if item]



            forbidden_hit = any(normalize_transition(snippet) in normalized for snippet in forbidden_transition_snippets)



            repeated_hit = any(



                normalized == prev or normalized in prev or prev in normalized



                for prev in recent_norms if prev



            )



            if forbidden_hit or repeated_hit:



                fresh_fallbacks = [



                    option for option in transition_fallbacks



                    if normalize_transition(option) not in recent_norms



                ]



                chosen = random.choice(fresh_fallbacks or transition_fallbacks)



                cleaned = ensure_question(chosen)



        elif action == 'opinion':



            cleaned = ensure_statement(trim_words(cleaned, 20), "Nice point.")



        elif action == 'answer':



            cleaned = ensure_statement(trim_words(cleaned, 30), "You can start with one simple step.")



        elif action == 'mission_feedback':



            compact = re.sub(r'\s+', ' ', cleaned).strip()



            strong_sentence = ''



            next_sentence = ''







            if compact:



                parts = re.split(r'next step:', compact, maxsplit=1, flags=re.IGNORECASE)



                if len(parts) == 2:



                    strong_candidate = parts[0].strip().rstrip('.!?')



                    next_candidate = parts[1].strip().rstrip('.!?')



                    if strong_candidate:



                        if strong_candidate.lower().startswith('strong point:'):



                            strong_sentence = "Strong point: " + strong_candidate.split(':', 1)[1].strip()



                        else:



                            strong_sentence = f"Strong point: {strong_candidate}"



                    if next_candidate:



                        next_sentence = f"Next step: {next_candidate}"







            if not strong_sentence or not next_sentence:



                strong_sentence = "Strong point: your answers were clear"



                next_sentence = "Next step: add one more detail next time"







            cleaned = f"{strong_sentence}. {next_sentence}."



            feedback_words = cleaned.split()



            if len(feedback_words) > 28:



                cleaned = "Strong point: your answers were clear. Next step: add one more detail next time."



        elapsed_ms = (time.perf_counter() - request_started_at) * 1000.0



        record_live_activity(



            getattr(request, 'user_id', 'unknown'),



            user_email,



            "/api/free-conversation",



            status="ok",



            context="free_conversation",



            mode=f"guided:{action}",



            response_ms=elapsed_ms



        )



        return jsonify({"text": cleaned})



    except Exception as e:



        print(f"FREE CONVERSATION ERROR: {str(e)}")



        elapsed_ms = (time.perf_counter() - request_started_at) * 1000.0



        record_live_activity(



            getattr(request, 'user_id', 'unknown'),



            user_email,



            "/api/free-conversation",



            status="error",



            context="free_conversation",



            mode=f"guided:{action}",



            response_ms=elapsed_ms



        )



        # F41: a transient model error must not hard-fail the turn and soft-lock the
        # conversation (freeState is already advanced, so a 500 leaves the student
        # talking into a dead handler). Return a graceful 200 with a recovery line so
        # the flow continues naturally and the student is simply asked to repeat.
        transient_message = "Sorry, I lost my train of thought for a second. Could you say that again?"
        return jsonify({"text": transient_message, "transient": True}), 200















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



    exclude_list = data.get('exclude', [])  # Suggestions already shown to user







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



        prompt = f"""Você gera RESPOSTAS VALIDAS para um aluno de inglês.







Topico sendo praticado: {context_info}



A IA disse: "{ai_last_message}"







Gere 4 respostas curtas (max 10 palavras cada) que o aluno pode dizer em INGLES.



- As respostas DEVEM fazer sentido para a fala da IA



- Use vocabulário fácil e do dia a dia (nivel A1/A2)



- Use frases curtas e claras



- Evite girias, idioms e palavras raras



- NAO extraia palavras da pergunta como nomes proprios (ex: "Do you have...?" → "Do" NAO e um nome, e uma palavra da pergunta)



- Se o aluno ja disse o nome dele na conversa, use-o nas sugestoes (ex: "Wesley" em vez de nomes genericos)



- Formato: JSON com array "suggestions", cada item com "en" e "pt"







Exemplo se a IA disse "My day was busy. How is your day?":



{{"suggestions": [



  {{"en": "My day is good, thanks.", "pt": "Meu dia esta bom, obrigado."}},



  {{"en": "It was busy for me too.", "pt": "Tambem foi corrido para mim."}},



  {{"en": "I am fine. And you?", "pt": "Estou bem. E você?"}},



  {{"en": "Can you tell me more?", "pt": "Pode me contar mais?"}}



]}}







CRITICO: Retorne APENAS JSON valido.



"""



        # Add exclusion note if there are suggestions already shown



        if exclude_list and isinstance(exclude_list, list) and len(exclude_list) > 0:



            exclude_items = ', '.join([f'"{s}"' for s in exclude_list[:5]])



            prompt += f"""



MUITO IMPORTANTE: Estas respostas JA FORAM mostradas ao aluno: {exclude_items}.



Você DEVE gerar respostas COMPLETAMENTE DIFERENTES. Use estruturas diferentes, vocabulário diferente, e abordagens criativas. NAO repita nenhuma das respostas acima.



"""



    else:



        prompt = f"""You are generating VALID RESPONSE OPTIONS for an English learner.







Topic being practiced: {context_info}



The AI just said: "{ai_last_message}"







Generate 4 short response options (max 10 words each) the student could say in ENGLISH.



- Responses MUST make sense as replies to the AI's message



- Use appropriate structures from the topic when possible



- Keep vocabulary EASY and everyday (A1/A2 words)



- Keep sentences short and clear



- Avoid slang, idioms, and rare words



- Be natural and conversational



- Do NOT extract words from the question as proper names (e.g., "Do you have...?" → "Do" is NOT a name, it is a question word)



- If the student already provided their name, use it in suggestions instead of generic names



- Format: JSON with "suggestions" array, each item has "en" (English) and "pt" (Portuguese translation)







Example if AI said "My day was busy. How is your day?":



{{"suggestions": [



  {{"en": "My day is good, thanks.", "pt": "Meu dia esta bom, obrigado."}},



  {{"en": "It was busy for me too.", "pt": "Tambem foi corrido para mim."}},



  {{"en": "I am fine. And you?", "pt": "Estou bem. E você?"}},



  {{"en": "Can you tell me more?", "pt": "Pode me contar mais?"}}



]}}







CRITICAL: Responses MUST be valid answers to the AI's statement/question. Return ONLY the JSON.



"""



        # Add exclusion note if there are suggestions already shown



        if exclude_list and isinstance(exclude_list, list) and len(exclude_list) > 0:



            exclude_items = ', '.join([f'"{s}"' for s in exclude_list[:5]])



            prompt += f"""



VERY IMPORTANT: These responses have ALREADY been shown to the student: {exclude_items}.



You MUST generate COMPLETELY DIFFERENT alternatives. Use different sentence structures, different vocabulary, and creative approaches. Do NOT repeat any of the above.



"""







    try:



        response = model.generate_content(



            prompt,



            generation_config={"max_output_tokens": MAX_OUTPUT_TOKENS_SUGGESTIONS}



        )



        raw_text = response.text.strip() if response and response.text else ""







        # Clean markdown and try robust JSON extraction.



        cleaned = raw_text.replace('```json', '').replace('```', '').strip()



        result = None







        try:



            result = json.loads(cleaned)



        except Exception:



            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)



            if json_match:



                try:



                    result = json.loads(json_match.group(0))



                except Exception:



                    result = None







        normalized = []



        if isinstance(result, dict):



            raw_suggestions = result.get('suggestions', [])



            if isinstance(raw_suggestions, list):



                for item in raw_suggestions:



                    if isinstance(item, dict):



                        en_text = str(item.get('en', '')).strip()



                        pt_text = str(item.get('pt', '')).strip()



                    else:



                        en_text = str(item).strip()



                        pt_text = ""



                    if en_text:



                        normalized.append({"en": en_text[:120], "pt": pt_text[:160]})



        elif isinstance(result, list):



            for item in result:



                if isinstance(item, dict):



                    en_text = str(item.get('en', '')).strip()



                    pt_text = str(item.get('pt', '')).strip()



                    if en_text:



                        normalized.append({"en": en_text[:120], "pt": pt_text[:160]})







        # Fallback: recover plain-text bullet lines from model output.



        if not normalized and cleaned:



            candidate_lines = []



            for line in cleaned.splitlines():



                compact = re.sub(r'^[\s\-\*\d\.\)\(]+', '', line).strip()



                if not compact:



                    continue



                if any(token in compact for token in ['{', '}', '[', ']', ':', '"']):



                    continue



                if len(re.findall(r'[A-Za-z]', compact)) < 4:



                    continue



                if len(compact.split()) <= 14:



                    candidate_lines.append(compact)



            for text in candidate_lines[:4]:



                normalized.append({"en": text[:120], "pt": ""})







        # Ensure 4 suggestions for better UI consistency.



        import random



        fallback_pool = [



            {"en": "I understand.", "pt": "Eu entendi."},



            {"en": "I agree.", "pt": "Eu concordo."},



            {"en": "That is true for me too.", "pt": "Isso e verdade para mim tambem."},



            {"en": "Can you say that again?", "pt": "Pode falar isso de novo?"},



            {"en": "Can you give one example?", "pt": "Pode dar um exemplo?"},



            {"en": "That happened to me too.", "pt": "Isso aconteceu comigo tambem."},



            {"en": "I like that idea.", "pt": "Eu gostei dessa ideia."},



            {"en": "I am not sure. Can you explain?", "pt": "Nao tenho certeza. Pode explicar?"},



            {"en": "Good point.", "pt": "Bom ponto."},



            {"en": "I think so too.", "pt": "Eu tambem acho."}



        ]



        random.shuffle(fallback_pool)



        existing = {item.get("en", "").strip().lower() for item in normalized}



        for item in fallback_pool:



            if len(normalized) >= 4:



                break



            key = item["en"].strip().lower()



            if key not in existing:



                normalized.append(item)



                existing.add(key)







        if normalized:



            return jsonify({"suggestions": normalized[:4]})







        raise ValueError("No valid suggestions parsed from model response")



    except Exception as e:



        print(f"[SUGGESTIONS] Error: {e}")



        # Fallback to generic but contextual suggestions



        import random



        generic_pool = [



            {"en": "That is interesting.", "pt": "Isso e interessante."},



            {"en": "I agree with you.", "pt": "Eu concordo com você."},



            {"en": "Tell me more.", "pt": "Me conte mais."},



            {"en": "I think so too.", "pt": "Eu tambem acho."},



            {"en": "Can you give one example?", "pt": "Você pode dar um exemplo?"},



            {"en": "I understand your point.", "pt": "Eu entendi seu ponto."},



            {"en": "That is a good way.", "pt": "Essa e uma boa forma."},



            {"en": "Can you explain a bit more?", "pt": "Pode explicar um pouco mais?"}



        ]



        fallback_choices = random.sample(generic_pool, 4)



        return jsonify({



            "suggestions": fallback_choices



        })











# Structured lesson phrase memory to avoid immediate repetition.



_lesson_variant_memory = {}











def _pick_lesson_variant(memory_key, variants):



    """Pick a variant while avoiding immediate repetition for the same memory key."""



    if not isinstance(variants, list) or not variants:



        return None







    key = str(memory_key or "default")



    last_idx = _lesson_variant_memory.get(key)



    candidate_idxs = list(range(len(variants)))



    if len(candidate_idxs) > 1 and isinstance(last_idx, int) and 0 <= last_idx < len(variants):



        candidate_idxs = [idx for idx in candidate_idxs if idx != last_idx]



        if not candidate_idxs:



            candidate_idxs = list(range(len(variants)))







    chosen_idx = random.choice(candidate_idxs)



    _lesson_variant_memory[key] = chosen_idx







    # Keep memory bounded.



    if len(_lesson_variant_memory) > 4000:



        for stale_key in list(_lesson_variant_memory.keys())[:1000]:



            _lesson_variant_memory.pop(stale_key, None)







    return variants[chosen_idx]











def diversify_lesson_welcome(context, lesson_title, text_en, text_pt, user_key=""):



    base_en = (text_en or "").strip()



    base_pt = (text_pt or "").strip()



    title = (lesson_title or context.replace('_', ' ').title()).strip()



    memory_prefix = f"{(user_key or 'anon').lower()}::{context}::welcome"







    if not base_en:



        base_en = f"Welcome! Today we will practice {title}."



    if not base_pt:



        base_pt = f"Bem-vindo! Hoje vamos praticar {title}."







    opener_pool = [



        ("Great to see you back.", "Que bom te ver de volta."),



        ("Nice, let's keep it practical today.", "Ótimo, hoje vamos manter bem pratico."),



        ("Awesome, we'll do this in short clear steps.", "Perfeito, vamos fazer isso em passos curtos e claros."),



        ("Ready? Let's build confidence one phrase at a time.", "Pronto? Vamos ganhar confianca uma frase por vez."),



    ]



    focus_pool = [



        ("Focus for this round: clarity first, speed second.", "Foco desta rodada: clareza primeiro, velocidade depois."),



        ("Goal for today: speak naturally, even with simple words.", "Meta de hoje: falar com naturalidade, mesmo com palavras simples."),



        ("Small challenge: try one full sentence without reading.", "Desafio rapido: tente uma frase completa sem ler."),



        ("Keep your answer simple and complete in every step.", "Mantenha sua resposta simples e completa em cada etapa."),



    ]



    context_focus = {



        "coffee_shop": ("Goal: complete one full order naturally.", "Meta: fechar um pedido completo com naturalidade."),



        "restaurant": ("Goal: order food and drink with confidence.", "Meta: pedir comida e bebida com confianca."),



        "hotel": ("Goal: handle check-in and one extra request.", "Meta: fazer check-in e um pedido extra."),



        "airport": ("Goal: answer check-in questions clearly.", "Meta: responder perguntas de check-in com clareza."),



        "doctor": ("Goal: describe one symptom and when it started.", "Meta: descrever um sintoma e quando comecou."),



    }







    opener = _pick_lesson_variant(f"{memory_prefix}::opener", opener_pool)



    focus = context_focus.get(context) or _pick_lesson_variant(f"{memory_prefix}::focus", focus_pool)







    if opener:



        open_en, open_pt = opener



        base_en = f"{open_en} {base_en}".strip()



        base_pt = f"{open_pt} {base_pt}".strip()







    if focus:



        focus_en, focus_pt = focus



        if focus_en.lower() not in base_en.lower():



            base_en = f"{base_en} {focus_en}".strip()



        if focus_pt.lower() not in base_pt.lower():



            base_pt = f"{base_pt} {focus_pt}".strip()







    return base_en, base_pt











def diversify_lesson_instruction(context, layer_title, text_en, text_pt, layer_index=0, user_key=""):



    base_en = (text_en or "").strip() or "Choose one option to practice."



    base_pt = (text_pt or "").strip() or "Escolha uma opcao para praticar."



    step_num = int(layer_index) + 1



    memory_key = f"{(user_key or 'anon').lower()}::{context}::instruction::{step_num}"







    lead_pool = [



        (f"Step {step_num}: pick one phrase you can say out loud.", f"Etapa {step_num}: escolha uma frase que você consegue falar em voz alta."),



        (f"Round {step_num}: choose one option and own it.", f"Rodada {step_num}: escolha uma opcao e domine essa frase."),



        (f"Stage {step_num}: focus on one clear sentence.", f"Fase {step_num}: foque em uma frase clara."),



    ]



    lead = _pick_lesson_variant(memory_key, lead_pool)



    if lead:



        lead_en, lead_pt = lead



        if lead_en.lower() not in base_en.lower():



            base_en = f"{lead_en} {base_en}".strip()



        if lead_pt.lower() not in base_pt.lower():



            base_pt = f"{lead_pt} {base_pt}".strip()







    return base_en, base_pt











def diversify_lesson_practice_prompt(context, text_en, text_pt, user_key=""):



    base_en = (text_en or "").strip() or "Now try using this phrase!"



    base_pt = (text_pt or "").strip() or "Agora tente usar essa frase!"



    memory_key = f"{(user_key or 'anon').lower()}::{context}::practice"







    coach_pool = [



        ("Use one clear sentence and keep it natural.", "Use uma frase clara e mantenha natural."),



        ("Answer with a short full sentence.", "Responda com uma frase curta e completa."),



        ("Keep the idea simple and speak with confidence.", "Mantenha a ideia simples e fale com confianca."),



        ("Use your own words and continue the conversation.", "Use suas palavras e continue a conversa."),



    ]



    coach = _pick_lesson_variant(memory_key, coach_pool)



    if coach:



        coach_en, coach_pt = coach



        if coach_en.lower() not in base_en.lower():



            base_en = f"{base_en} {coach_en}".strip()



        if coach_pt.lower() not in base_pt.lower():



            base_pt = f"{base_pt} {coach_pt}".strip()







    return base_en, base_pt











# Structured lesson feedback variation to avoid repetitive retries.



def diversify_lesson_feedback(feedback_kind, text_en, text_pt, target_phrase=''):



    import random







    base_en = (text_en or '').strip()



    base_pt = (text_pt or '').strip()



    hint = ' '.join((target_phrase or '').split()[:7]).strip()







    if feedback_kind == 'redirect':



        generic_markers = (



            "let's try again",



            "use the phrase from the reference card",



        )



        redirect_pool = [



            ("Let's reset and choose one full phrase from the card.", "Vamos reiniciar e escolher uma frase completa do cartao."),



            ("Good focus. Choose one phrase from the card and continue.", "Bom foco. Escolha uma frase do cartao e continue."),



            ("Stay with the card for this step. Use one full option clearly.", "Fique no cartao nesta etapa. Use uma opcao completa com clareza."),



            ("Almost there. Pick one option from the card and move on.", "Quase la. Escolha uma opcao do cartao e siga em frente."),



        ]







        if not base_en or any(marker in base_en.lower() for marker in generic_markers):



            picked_en, picked_pt = random.choice(redirect_pool)



            if hint and random.random() < 0.35:



                picked_en = f'{picked_en} Try: "{hint}".'



                picked_pt = f'{picked_pt} Tente: "{hint}".'



            return picked_en, picked_pt







    if feedback_kind == 'retry':



        retry_pool = [



            ("Good attempt. Keep the same idea in one clear sentence.", "Boa tentativa. Mantenha a mesma ideia em uma frase clara."),



            ("You're close. Keep it simple and use the target phrase clearly.", "Você esta perto. Mantenha simples e use a frase-alvo com clareza."),



            ("Nice effort. Keep this structure and continue with one cleaner sentence.", "Bom esforco. Mantenha essa estrutura e continue com uma frase mais limpa."),



            ("Almost right. Keep the key words and continue with confidence.", "Quase certo. Mantenha as palavras-chave e continue com confianca."),



        ]



        if not base_en or base_en.lower().startswith("good try"):



            return random.choice(retry_pool)







    return base_en, base_pt











def diversify_lesson_conclusion(context, lesson_title, text_en, text_pt):



    import random







    base_en = (text_en or '').strip()



    base_pt = (text_pt or '').strip()



    title = (lesson_title or context.replace('_', ' ').title()).strip()







    close_variants = [



        ("Nice work from start to finish.", "Bom trabalho do inicio ao fim."),



        ("Great job. You spoke clearly today.", "Ótimo trabalho. Você falou com clareza hoje."),



        ("Good session. You are getting more confident.", "Boa sessao. Você esta ficando mais confiante."),



        ("Strong progress. Keep this rhythm.", "Ótimo progresso. Continue nesse ritmo."),



    ]







    context_next_step = {



        "coffee_shop": ("Next time: can you order a drink and one extra?", "Proxima vez: você consegue pedir uma bebida e um extra?"),



        "restaurant": ("Next time: can you order food, drink, and dessert?", "Proxima vez: você consegue pedir comida, bebida e sobremesa?"),



        "airport": ("Next time: can you ask about bag and gate?", "Proxima vez: você consegue perguntar sobre bagagem e portao?"),



        "hotel": ("Next time: can you check in and ask for Wi-Fi?", "Proxima vez: você consegue fazer check-in e pedir o Wi-Fi?"),



        "job_interview": ("Next time: can you answer 'Tell me about yourself' in 2 lines?", "Proxima vez: você consegue responder 'Fale sobre você' em 2 frases?"),



        "doctor": ("Next time: can you explain one symptom and when it started?", "Proxima vez: você consegue explicar um sintoma e quando comecou?"),



        "bank": ("Next time: can you ask to deposit and check your balance?", "Proxima vez: você consegue pedir deposito e checar saldo?"),



        "pharmacy": ("Next time: can you ask what medicine to take?", "Proxima vez: você consegue perguntar qual remedio tomar?"),



        "tech_support": ("Next time: can you explain the problem in 2 simple steps?", "Proxima vez: você consegue explicar o problema em 2 passos simples?"),



        "free_conversation": ("Next time: can you give one personal example in your answer?", "Proxima vez: você consegue dar um exemplo pessoal na resposta?"),



    }



    fallback_next_step = (



        "Next time: can you answer with one more detail?",



        "Proxima vez: você consegue responder com um detalhe a mais?"



    )







    if not base_en:



        base_en = f"Great work. You completed the {title} practice."



    if not base_pt:



        base_pt = f"Ótimo trabalho. Você concluiu a prática de {title}."







    extra_en, extra_pt = random.choice(close_variants)



    if extra_en.lower() not in base_en.lower():



        base_en = f"{base_en} {extra_en}"



    if extra_pt.lower() not in base_pt.lower():



        base_pt = f"{base_pt} {extra_pt}"







    next_en, next_pt = context_next_step.get(context, fallback_next_step)



    if random.random() < 0.75:



        base_en = f"{base_en} {next_en}"



        base_pt = f"{base_pt} {next_pt}"







    return base_en.strip(), base_pt.strip()







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



    selected_phrase_payload = data.get('selected_phrase')



    user_text = data.get('text', '')



    user_key = str(getattr(request, "user_email", "") or getattr(request, "user_id", "") or "anon").strip().lower()







    # Check if lesson exists for this context



    lesson_data = LESSONS_DB.get(context)



    if not lesson_data:



        return jsonify({"error": f"No structured lesson found for '{context}'"}), 404







    layers = lesson_data.get('layers', [])



    total_layers = len(layers)







    # ACTION: START - Show welcome message



    if action == 'start':



        welcome = lesson_data.get('welcome', {})



        lesson_title = lesson_data.get('title', context)



        welcome_en, welcome_pt = diversify_lesson_welcome(



            context=context,



            lesson_title=lesson_title,



            text_en=welcome.get('en', 'Welcome to the lesson!'),



            text_pt=welcome.get('pt', 'Bem-vindo a aula!'),



            user_key=user_key,



        )



        resp = {



            "type": "welcome",



            "text": welcome_en,



            "translation": welcome_pt,



            "lesson_title": lesson_title,



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



            lesson_title = lesson_data.get('title', context)



            text_en = conclusion.get('en', 'Congratulations! You completed the lesson!')



            text_pt = conclusion.get('pt', 'Parabens! Você completou a aula!')



            text_en, text_pt = diversify_lesson_conclusion(context, lesson_title, text_en, text_pt)



            return jsonify({



                "type": "conclusion",



                "text": text_en,



                "translation": text_pt,



                "layer": current_layer,



                "total_layers": total_layers,



                "next_action": "finished"



            })







        layer = layers[current_layer]



        instruction = layer.get('instruction', {})



        options = layer.get('options', [])



        instruction_en, instruction_pt = diversify_lesson_instruction(



            context=context,



            layer_title=layer.get('title', f'Layer {current_layer + 1}'),



            text_en=instruction.get('en', 'Choose an option:'),



            text_pt=instruction.get('pt', 'Escolha uma opcao:'),



            layer_index=current_layer,



            user_key=user_key,



        )







        return jsonify({



            "type": "options",



            "text": instruction_en,



            "translation": instruction_pt,



            "layer_title": layer.get('title', f'Layer {current_layer + 1}'),



            "options": options,



            "interaction": layer.get('interaction', 'repeat'),



            "auto_accept": bool(layer.get('auto_accept', False)),



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



        practice_en, practice_pt = diversify_lesson_practice_prompt(



            context=context,



            text_en=practice_prompt.get('en', 'Now try using this phrase!'),



            text_pt=practice_prompt.get('pt', 'Agora tente usar essa frase!'),



            user_key=user_key,



        )







        # Get the selected phrase



        selected_phrase = None



        skip_to_layer = None



        if isinstance(selected_phrase_payload, dict):



            # Frontend can send the full selected phrase to preserve shuffled option order.



            selected_phrase = {



                "en": selected_phrase_payload.get('en', ''),



                "pt": selected_phrase_payload.get('pt', ''),



                "slots": selected_phrase_payload.get('slots', {}),



                "skip_to_layer": selected_phrase_payload.get('skip_to_layer')



            }



            if selected_phrase.get("skip_to_layer") is not None:



                skip_to_layer = selected_phrase.get("skip_to_layer")







        # Fallback: resolve by option index when provided.



        if selected_phrase is None and selected_option is not None and 0 <= selected_option < len(options):



            selected_phrase = options[selected_option]



            # Check if this option has skip_to_layer (for branching)



            if isinstance(selected_phrase, dict):



                skip_to_layer = selected_phrase.get('skip_to_layer')







        response_data = {



            "type": "practice",



            "text": practice_en,



            "translation": practice_pt,



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



    # Uses pre-defined feedback templates from lessons_db.json so all áudio



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



        auto_accepted = bool(data.get('auto_accepted'))



        front_match_accepted = bool(data.get('front_match_accepted'))



        feedback_templates = layer.get('feedback', {})







        # Robust evaluation with Unicode normalization and fuzzy matching



        def normalize_for_eval(t):



            t = t.lower().strip()



            # Normalize curly/smart quotes and apóstrophes to ASCII



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







        if auto_accepted or front_match_accepted or contains_target or overlap >= min_overlap or char_similarity >= 0.6:



            # SUCCESS - student used the phrase correctly



            fb = feedback_templates.get('success', {})



            ready_for_next = True



            feedback_kind = 'success'



        elif overlap > 0 or char_similarity >= 0.3 or len(user_words) >= 2:



            # RETRY - attempted but needs improvement



            fb = feedback_templates.get('retry', {})



            ready_for_next = False



            feedback_kind = 'retry'



        else:



            # REDIRECT - completely off topic (single word, dot, unrelated)



            fb = feedback_templates.get('redirect', {})



            ready_for_next = False



            feedback_kind = 'redirect'







        # Fallback text if feedback templates not defined in lessons_db.json



        text_en = fb.get('en', "Good try! Let's continue.")



        text_pt = fb.get('pt', 'Boa tentativa! Vamos continuar.')



        text_en, text_pt = diversify_lesson_feedback(feedback_kind, text_en, text_pt, target_phrase)







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





REGRAS DE QUALIDADE:


- Use SOMENTE frases da transcrição (não invente falas).


- Se houver erros, inclua pelo menos 3 correções importantes.


- Se houver poucos erros, use "Correta, mas Pouco Natural" para sugerir formas mais naturais.


- Dicas devem ser acionáveis e ligadas a erros reais observados.





Retorne APENAS um JSON válido seguindo EXATAMENTE este formato:


{{


  "titulo": "Ótimo treino de estruturas básicas!",


  "emoji": "📗",


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


  "frase_prática": "How would you politely ask someone to open the window?",


  "erros_recorrentes": ["erro recorrente 1", "erro recorrente 2"],


  "plano_estudo": ["pratique X por 10 min", "repita Y com exemplos", "grave 3 frases usando Z"],


  "nota_geral": 75,


  "resumo_gramatical": ["Estruturas de pedido educado", "Uso de would/could"]


}}





REGRAS:


- Máximo 3 correções (foque nas mais importantes)


- Analise TODAS as falas do aluno em "analise_frases" (não apenas erros)


- "naturalidade": 0-100 (90-100=perfeita, 60-89=boa, 40-59=compreensível mas não natural, 0-39=erro grave)


- Pelo menos 3 elogios sobre estruturas que usou bem


- Dicas devem sugerir estruturas específicas para estudar


- "erros_recorrentes": 2-4 padrões observados com base nas falas do aluno


- "plano_estudo": 3 ações claras e curtas para a próxima semana (baseadas nos erros)


- Tom sempre positivo e motivador


- "nota_geral": número de 0 a 100 representando a performance geral (60% naturalidade média das frases + 20% frases corretas + 20% variedade de vocabulário)


- "resumo_gramatical": lista de 2-4 pontos gramaticais ou de vocabulário cobertos na conversa (ex: "Estruturas de pedido educado", "Uso de would/could")


- SEM texto fora do JSON


"""


    else:


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





REGRAS DE QUALIDADE:


- Use SOMENTE frases da transcrição (não invente falas).


- Se houver erros, inclua pelo menos 3 correções importantes.


- Se houver poucos erros, use "Correta, mas Pouco Natural" para sugerir formas mais naturais.


- Dicas devem ser acionáveis e ligadas a erros reais observados.


- Evite elogios genéricos: cite evidências concretas do que o aluno fez bem.





Gere um relatório em português e retorne APENAS um JSON válido seguindo EXATAMENTE este formato:


{{


  "titulo": "Frase MUITO MOTIVADORA e positiva sobre o progresso (ex: 'Você está indo muito bem!', 'Ótimo progresso!')",


  "emoji": "emoji positivo (🎉, ✨, 🌟, 👏, 👍)",


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


  "frase_prática": "próxima frase em inglês para o aluno treinar neste contexto",


  "erros_recorrentes": ["erro recorrente 1", "erro recorrente 2"],


  "plano_estudo": ["pratique X por 10 min", "repita Y com exemplos", "grave 3 frases usando Z"],


  "nota_geral": 75,


  "resumo_gramatical": ["ponto gramatical coberto 1", "ponto de vocabulário coberto 2"]


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


- "erros_recorrentes": 2-4 padrões observados com base nas falas do aluno


- "plano_estudo": 3 ações claras e curtas para a próxima semana (baseadas nos erros)


- Se o aluno estiver muito bem, elogie ainda mais!


- "nota_geral": número de 0 a 100 representando a performance geral do aluno (60% naturalidade média das frases + 20% quantidade de frases corretas + 20% variedade de vocabulário)


- "resumo_gramatical": lista de 2-4 pontos gramaticais ou de vocabulário cobertos na conversa (ex: "Simple Past", "Phrasal verbs com 'get'", "Vocabulário de restaurante")


- SEM texto fora do JSON


"""


    try:



        response = model.generate_content(



            prompt,



            generation_config={"max_output_tokens": MAX_OUTPUT_TOKENS_REPORT}



        )



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



    """DEPRECATED: PDF generation now handled client-side via html2pdf.js.



    Kept as fallback for older clients. Will be removed in a future version."""



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



        if report_data.get('frase_prática'):



            pdf.setFont("Helvetica-Bold", 12)



            pdf.drawString(50, y_position, "Next phrase to practice:")



            y_position -= 20



            pdf.setFont("Helvetica-Oblique", 10)



            pdf.drawString(70, y_position, report_data.get('frase_prática', ''))







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



    """Generate cache path for áudio based on text content and parameters"""



    # Create unique hash from text + parameters



    cache_key = f"{text}_{speed}_{lesson_lang}_{voice_name}"



    hash_obj = hashlib.md5(cache_key.encode('utf-8'))



    filename = hash_obj.hexdigest() + '.mp3'



    



    # Use common phrases dir for short, simple texts



    if len(text) < 50 and not '[EN]' in text:



        return os.path.join(COMMON_PHRASES_DIR, filename)



    else:



        return os.path.join(DYNAMIC_CACHE_DIR, filename)







def save_audio_to_cache(áudio_content, cache_path):



    """Save áudio content to cache file"""



    try:



        with open(cache_path, 'wb') as f:



            f.write(áudio_content)



        return True



    except Exception as e:



        print(f"[CACHE] Error saving áudio to cache: {e}")



        return False







def get_audio_from_cache(cache_path):



    """Retrieve áudio from cache if exists"""



    try:



        if os.path.exists(cache_path):



            with open(cache_path, 'rb') as f:



                return f.read()



        return None



    except Exception as e:



        print(f"[CACHE] Error reading áudio from cache: {e}")



        return None











def _dashscope_headers():



    return {



        "Authorization": f"Bearer {QWEN_API_KEY}",



        "Content-Type": "application/json",



        "X-DashScope-Async": "disable",



    }











def _strip_bilingual_tags(text):



    return re.sub(r"\[/?EN\]", " ", str(text or ""), flags=re.IGNORECASE)











def _extract_qwen_audio_url(payload):



    try:



        output = payload.get("output") if isinstance(payload, dict) else None



        audio = None
        if isinstance(output, dict):
            audio = output.get("audio") or output.get("áudio")



        if isinstance(audio, dict):



            url = str(audio.get("url") or "").strip()



            if url.startswith("http"):



                return url



    except Exception:



        pass



    return ""











def _extract_qwen_audio_b64(payload):



    try:



        output = payload.get("output") if isinstance(payload, dict) else None



        audio = None
        if isinstance(output, dict):
            audio = output.get("audio") or output.get("áudio")



        if isinstance(audio, dict):



            for key in ("data", "audioContent", "audio_content", "áudioContent", "áudio_content"):



                value = audio.get(key)



                if isinstance(value, str) and len(value) > 64:



                    return value



    except Exception:



        pass



    return ""











def _normalize_qwen_prefix(raw_prefix):



    prefix = str(raw_prefix or "").strip()



    if not prefix:



        prefix = "clone16"



    prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", prefix).strip("_")



    if not prefix:



        prefix = "clone16"



    return prefix[:32]











def _normalize_qwen_preferred_name(raw_name):



    """preferred_name must be <=16 chars, letters/digits/underscore."""



    value = str(raw_name or "").strip().lower()



    value = re.sub(r"[^a-z0-9_]+", "_", value)



    value = re.sub(r"_+", "_", value).strip("_")



    if not value:



        value = "clone16voice"



    return value[:16]











def _normalize_qwen_voice_name(value):



    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())











def _is_legacy_voice_hint(value):



    """Detect frontend voice aliases that should not override Qwen clone voices."""



    raw = str(value or "").strip().lower()



    if not raw:



        return False







    legacy_aliases = {



        "lesson",



        "achernar",



        "female1",



        "female2",



        "male1",



        "male2",



        "serena",



        "ryan",



        "dylan",



        "emma",



        "alloy",



        "echo",



        "fable",



        "onyx",



        "nova",



        "shimmer",



    }



    if raw in legacy_aliases:



        return True







    # Google-style voice ids should not override Qwen clone selection.



    return ("chirp" in raw) or raw.startswith("en-us-") or raw.startswith("pt-br-")











def _find_qwen_voice_by_hint(hint):



    """Find an existing custom Qwen voice by exact/fuzzy name matching."""



    candidate = str(hint or "").strip()



    if not candidate:



        return ""



    voices = _list_qwen_custom_voices()



    if not voices:



        return ""







    # Exact match first.



    for item in voices:



        if not isinstance(item, dict):



            continue



        name = str(item.get("voice") or "").strip()



        if name and name.lower() == candidate.lower():



            return name







    candidate_norm = _normalize_qwen_voice_name(candidate)



    if not candidate_norm:



        return ""







    # Fuzzy containment.



    for item in voices:



        if not isinstance(item, dict):



            continue



        name = str(item.get("voice") or "").strip()



        if not name:



            continue



        name_norm = _normalize_qwen_voice_name(name)



        if candidate_norm in name_norm or name_norm in candidate_norm:



            return name







    # Special handling: "clone 16" style labels.



    clone_match = re.search(r"clone\D*0*(\d+)", candidate.lower())



    if clone_match:



        token = f"clone{int(clone_match.group(1))}"



        for item in voices:



            if not isinstance(item, dict):



                continue



            name = str(item.get("voice") or "").strip()



            if not name:



                continue



            if token in _normalize_qwen_voice_name(name):



                return name







    return ""











def _guess_audio_mime(path):



    ext = os.path.splitext(str(path or "").lower())[1]



    if ext == ".wav":



        return "áudio/wav"



    if ext == ".mp3":



        return "áudio/mpeg"



    if ext in (".m4a", ".mp4"):



        return "áudio/mp4"



    if ext == ".aac":



        return "áudio/aac"



    return "áudio/wav"











def _load_qwen_voice_cache():



    try:



        if os.path.exists(QWEN_VOICE_CACHE_FILE):



            with open(QWEN_VOICE_CACHE_FILE, "r", encoding="utf-8") as f:



                data = json.load(f)



                if isinstance(data, dict):



                    return data



    except Exception as e:



        print(f"[QWEN/VOICE] Failed to load cache: {e}")



    return {}











def _save_qwen_voice_cache(data):



    try:



        with open(QWEN_VOICE_CACHE_FILE, "w", encoding="utf-8") as f:



            json.dump(data, f, ensure_ascii=False, indent=2)



    except Exception as e:



        print(f"[QWEN/VOICE] Failed to save cache: {e}")











def _list_qwen_custom_voices():



    if not QWEN_API_KEY or not REQUESTS_AVAILABLE:



        return []



    payload = {



        "model": "qwen-voice-enrollment",



        "input": {



            "action": "list",



            "page_index": 0,



            "page_size": 100,



        },



    }



    try:



        response = requests.post(



            QWEN_VOICE_ENROLLMENT_ENDPOINT,



            headers=_dashscope_headers(),



            json=payload,



            timeout=QWEN_TTS_TIMEOUT_SEC,



        )



        if response.status_code != 200:



            return []



        data = response.json()



        output = data.get("output") if isinstance(data, dict) else {}



        voices = []



        if isinstance(output, dict):



            voices = output.get("voices") or output.get("voice_list") or []



        return voices if isinstance(voices, list) else []



    except Exception:



        return []











def _resolve_qwen_reference_audio_path():



    config_path = os.path.join(BASE_DIR, "voice_references", "config.json")



    if not os.path.exists(config_path):



        return None, "Voice reference config not found at voice_references/config.json"



    try:



        with open(config_path, "r", encoding="utf-8") as f:



            config = json.load(f)



    except Exception as e:



        return None, f"Invalid voice reference config: {e}"







    ref_audio = str(config.get("ref_audio") or "").strip()



    if not ref_audio:



        return None, "voice_references/config.json missing 'ref_audio'"







    candidates = [ref_audio]



    if not os.path.isabs(ref_audio):



        candidates.append(os.path.join(BASE_DIR, ref_audio))



        candidates.append(os.path.join(BASE_DIR, "voice_references", ref_audio))







    for candidate in candidates:



        path = os.path.abspath(candidate)



        if os.path.exists(path):



            return path, ""



    return None, f"Reference audio not found: {ref_audio}"











def _create_qwen_custom_voice(prefix, target_model):



    if not QWEN_API_KEY:



        return "", "QWEN_API_KEY/DASHSCOPE_API_KEY not configured"



    if not REQUESTS_AVAILABLE:



        return "", "requests dependency not available"







    ref_audio_path, ref_audio_err = _resolve_qwen_reference_audio_path()



    if ref_audio_err:



        return "", ref_audio_err



    if not ref_audio_path:



        return "", "Reference audio path resolution failed"







    try:



        with open(ref_audio_path, "rb") as f:



            binary_audio = f.read()



    except Exception as e:



        return "", f"Failed reading reference áudio: {e}"







    if len(binary_audio) > 2_000_000:



        return "", "Reference audio must be <= 2MB for DashScope voice enrollment"







    audio_b64 = base64.b64encode(binary_audio).decode("utf-8")



    mime = _guess_audio_mime(ref_audio_path)



    data_uri = f"data:{mime};base64,{audio_b64}"







    normalized_prefix = _normalize_qwen_prefix(prefix)



    preferred_name = _normalize_qwen_preferred_name(normalized_prefix)



    payload = {



        "model": "qwen-voice-enrollment",



        "input": {



            "action": "create",



            "target_model": target_model,



            "preferred_name": preferred_name,



            "áudio": {



                "data": data_uri



            },



        },



    }







    try:



        response = requests.post(



            QWEN_VOICE_ENROLLMENT_ENDPOINT,



            headers=_dashscope_headers(),



            json=payload,



            timeout=QWEN_TTS_TIMEOUT_SEC,



        )



    except Exception as e:



        return "", f"Voice enrollment request failed: {e}"







    if response.status_code != 200:



        details = ""



        try:



            details = response.text[:500]



        except Exception:



            pass



        return "", f"Voice enrollment failed ({response.status_code}): {details}"







    try:



        data = response.json()



    except Exception as e:



        return "", f"Invalid enrollment response JSON: {e}"







    output = data.get("output") if isinstance(data, dict) else {}



    voice_name = str(output.get("voice") or "").strip() if isinstance(output, dict) else ""



    if not voice_name:



        return "", "Voice enrollment did not return 'output.voice'"



    return voice_name, ""











def _ensure_qwen_clone_voice(prefix, target_model, force_create=False):



    normalized_prefix = _normalize_qwen_prefix(prefix)



    target_model = str(target_model or QWEN_TTS_CLONE_MODEL).strip() or QWEN_TTS_CLONE_MODEL



    cache = _load_qwen_voice_cache()



    cache_voice = str(cache.get("voice") or "").strip()



    cache_prefix = str(cache.get("prefix") or "").strip()



    cache_model = str(cache.get("target_model") or "").strip()







    if not force_create and cache_voice and cache_prefix == normalized_prefix and cache_model == target_model:



        return cache_voice, ""







    if not force_create:



        voices = _list_qwen_custom_voices()



        for item in voices:



            if not isinstance(item, dict):



                continue



            name = str(item.get("voice") or "").strip()



            if name and name.startswith(normalized_prefix):



                _save_qwen_voice_cache({



                    "voice": name,



                    "prefix": normalized_prefix,



                    "target_model": target_model,



                    "updated_at": _utc_now().isoformat() + "Z",



                })



                return name, ""







    created_voice, err = _create_qwen_custom_voice(normalized_prefix, target_model)



    if err:



        return "", err







    _save_qwen_voice_cache({



        "voice": created_voice,



        "prefix": normalized_prefix,



        "target_model": target_model,



        "updated_at": _utc_now().isoformat() + "Z",



    })



    return created_voice, ""











def _synthesize_qwen_online(text, lesson_lang="en", speed=1.0, voice_name="", model_name=""):



    if not QWEN_API_KEY:



        return None, "QWEN_API_KEY/DASHSCOPE_API_KEY not configured"



    if not REQUESTS_AVAILABLE:



        return None, "requests dependency not available"







    normalized_text = clean_text_for_tts(_strip_bilingual_tags(text))



    if not normalized_text:



        return None, "Empty text after cleanup"







    selected_voice = str(voice_name or QWEN_TTS_CLONE_VOICE or QWEN_TTS_VOICE).strip()



    selected_model = str(model_name or (QWEN_TTS_CLONE_MODEL if voice_name or QWEN_TTS_CLONE_VOICE else QWEN_TTS_MODEL)).strip()



    if not selected_model:



        selected_model = QWEN_TTS_MODEL



    if not selected_voice:



        return None, "No Qwen voice configured"







    payload = {



        "model": selected_model,



        "input": {



            "text": normalized_text,



            "voice": selected_voice,



        },



    }







    normalized_lang = str(lesson_lang or "").strip().lower()



    if normalized_lang == "pt":



        payload["input"]["language_type"] = "Portuguese"



    elif normalized_lang == "en":



        payload["input"]["language_type"] = "English"







    # Qwen TTS HTTP API uses text/voice/language_type in `input`.



    # Keep speed handling as a no-op until an official non-streaming rate parameter is exposed.



    _ = speed







    try:



        response = requests.post(



            QWEN_TTS_ENDPOINT,



            headers=_dashscope_headers(),



            json=payload,



            timeout=QWEN_TTS_TIMEOUT_SEC,



        )



    except Exception as e:



        return None, f"Qwen TTS request failed: {e}"







    if response.status_code != 200:



        details = ""



        try:



            details = response.text[:500]



        except Exception:



            pass



        return None, f"Qwen TTS failed ({response.status_code}): {details}"







    try:



        data = response.json()



    except Exception as e:



        return None, f"Qwen TTS invalid JSON response: {e}"







    audio_url = _extract_qwen_audio_url(data)



    if audio_url:



        try:



            áudio_resp = requests.get(audio_url, timeout=QWEN_TTS_TIMEOUT_SEC)



            if áudio_resp.status_code == 200 and len(áudio_resp.content) > 100:



                return áudio_resp.content, ""



            return None, f"Qwen áudio URL fetch failed ({áudio_resp.status_code})"



        except Exception as e:



            return None, f"Qwen áudio URL fetch error: {e}"







    audio_b64 = _extract_qwen_audio_b64(data)



    if audio_b64:



        try:



            áudio_bytes = base64.b64decode(audio_b64)



            if len(áudio_bytes) > 100:



                return áudio_bytes, ""



        except Exception as e:



            return None, f"Qwen áudio base64 decode error: {e}"







    return None, "Qwen TTS response missing áudio URL/data"











# Lesson áudio cache directory (pre-generated áudio for structured lessons)



LESSON_AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'audio_cache', 'lessons')







def get_lesson_audio_cache(text):



    """Check if pre-generated lesson áudio exists for this text.







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











@app.route('/api/tts', methods=['POST'])



@limiter.limit("50 per minute")



@require_auth



def tts_endpoint():



    """Text-to-Speech endpoint with Qwen online first, then local Qwen, then Google fallback."""



    try:



        data = request.get_json(silent=True) or {}



        if not isinstance(data, dict):



            return jsonify({"error": "Invalid JSON payload"}), 400







        text = data.get('text')



        speed = data.get('speed', 1.0)  # Default to normal speed



        lesson_lang = str(data.get('lessonLang', 'en') or 'en').strip().lower()



        requested_voice = str(data.get('voice') or "").strip()



        requested_model = str(data.get('model') or "").strip()



        if _is_legacy_voice_hint(requested_voice):



            # Legacy UI aliases (lesson/achernar/etc.) should not override clone voice.



            requested_voice = ""







        # Single Google fallback voice for all interactions (Achernar)



        voice_config = {



            'en': 'en-US-Chirp3-HD-Achernar',



            'pt': 'pt-BR-Chirp3-HD-Achernar',



            'gender': 'FEMALE',



            'name': 'Achernar'



        }







        # Validate input



        is_valid, result = validate_text_input(text, max_length=500)



        if not is_valid:



            return jsonify({"error": result}), 400



        text = result



        if not text:



            return jsonify({"error": "No text provided"}), 400







        # Check lesson áudio cache first (pre-generated áudio for structured lessons)



        lesson_cache_path, lesson_cache_filename = get_lesson_audio_cache(text)



        if lesson_cache_path:



            print(f"[LESSON CACHE] HIT - serving pre-generated áudio: {lesson_cache_filename}")



            if os.environ.get('VERCEL'):



                from flask import redirect



                return redirect(f"/audio_cache/lessons/{lesson_cache_filename}?v=4", code=302)



            return send_file(



                lesson_cache_path,



                mimetype="audio/mp3",



                as_attachment=False,



                download_name="tts.mp3"



            )







        # Check if text contains [EN]...[/EN] tags (bilingual mode)



        has_bilingual_tags = '[EN]' in text and '[/EN]' in text



        print(f"[TTS] lessonLang: {lesson_lang}, has_bilingual_tags: {has_bilingual_tags}")



        print(f"[TTS] Text preview: {text[:100]}...")







        # Portuguese always uses natural 1.0x speed



        pt_speed = 1.0



        if has_bilingual_tags:



            google_voice_name = "bilingual_v2"



            effective_speed = pt_speed



        elif lesson_lang == 'pt':



            google_voice_name = voice_config['pt']



            effective_speed = pt_speed



        else:



            google_voice_name = voice_config['en']



            effective_speed = speed







        clone_prefix = str(data.get('voicePrefix') or QWEN_TTS_CLONE_PREFIX or "clone16").strip() or "clone16"



        selected_qwen_voice = requested_voice or QWEN_TTS_CLONE_VOICE or QWEN_TTS_VOICE



        selected_qwen_model = requested_model or (QWEN_TTS_CLONE_MODEL if (requested_voice or QWEN_TTS_CLONE_VOICE) else QWEN_TTS_MODEL)







        # Resolve/prepare Clone16 voice when VC model is selected.



        if QWEN_API_KEY and selected_qwen_model == QWEN_TTS_CLONE_MODEL:



            matched_voice = _find_qwen_voice_by_hint(selected_qwen_voice) if selected_qwen_voice else ""



            if matched_voice:



                selected_qwen_voice = matched_voice



            else:



                ensured_voice, ensured_err = _ensure_qwen_clone_voice(



                    prefix=clone_prefix,



                    target_model=selected_qwen_model,



                    force_create=False,



                )



                if ensured_voice:



                    selected_qwen_voice = ensured_voice



                elif ensured_err:



                    print(f"[QWEN/VOICE] Could not prepare clone voice. prefix={clone_prefix} err={ensured_err}")







        cache_voice_name = google_voice_name



        if QWEN_API_KEY:



            cache_voice_name = f"qwen_online::{selected_qwen_model}::{selected_qwen_voice}"







        # Check cache first



        cache_path = get_audio_cache_path(text, effective_speed, lesson_lang, cache_voice_name)



        cached_audio = get_audio_from_cache(cache_path)



        if cached_audio:



            print(f"[CACHE] Audio cache HIT")



            return send_file(



                io.BytesIO(cached_audio),



                mimetype="audio/mp3",



                as_attachment=False,



                download_name="tts.mp3"



            )



        print(f"[CACHE] Audio cache MISS - generating new áudio")







        # --- PRIMARY: QWEN ONLINE (DashScope) ---



        if QWEN_API_KEY:



            qwen_audio, qwen_err = _synthesize_qwen_online(



                text=text,



                lesson_lang=lesson_lang,



                speed=effective_speed,



                voice_name=selected_qwen_voice,



                model_name=selected_qwen_model,



            )



            if qwen_audio:



                save_audio_to_cache(qwen_audio, cache_path)



                print(f"[QWEN/ONLINE] Success! {len(qwen_audio)} bytes, voice={selected_qwen_voice}, model={selected_qwen_model}")



                return send_file(



                    io.BytesIO(qwen_audio),



                    mimetype="audio/mp3",



                    as_attachment=False,



                    download_name="tts.mp3"



                )



            print(f"[QWEN/ONLINE] Failed, falling back. Reason: {qwen_err}")







        # --- SECONDARY: LOCAL QWEN SERVER ---



        qwen_tts_url = os.environ.get("QWEN_TTS_URL", "").strip()



        is_vercel = os.environ.get('VERCEL') == '1'



        if qwen_tts_url and not is_vercel:



            try:



                qwen_voice = selected_qwen_voice or QWEN_TTS_CLONE_VOICE or QWEN_TTS_VOICE or 'serena'



                clean_text = clean_text_for_tts(text)



                qwen_response = requests.post(



                    f"{qwen_tts_url}/v1/áudio/speech",



                    json={



                        "model": "tts-1",



                        "input": clean_text,



                        "voice": qwen_voice,



                        "response_format": "mp3",



                        "speed": effective_speed



                    },



                    timeout=3



                )



                if qwen_response.status_code == 200 and len(qwen_response.content) > 100:



                    audio_data = qwen_response.content



                    save_audio_to_cache(audio_data, cache_path)



                    print(f"[QWEN/LOCAL] Success! {len(audio_data)} bytes, voice={qwen_voice}")



                    return send_file(



                        io.BytesIO(audio_data),



                        mimetype="audio/mp3",



                        as_attachment=False,



                        download_name="tts.mp3"



                    )



                print(f"[QWEN/LOCAL] Failed: status={qwen_response.status_code}, falling back to Google")



            except Exception as e:



                print(f"[QWEN/LOCAL] Error: {e}, falling back to Google")







        # --- FINAL FALLBACK: GOOGLE CLOUD TTS ---



        google_api_keys = []
        for candidate_key in (GOOGLE_API_KEY, os.environ.get("GOOGLE_API_KEY_2", "").strip()):
            if candidate_key and candidate_key not in google_api_keys:
                google_api_keys.append(candidate_key)

        if not google_api_keys:



            return jsonify({



                "error": "TTS service not configured",



                "message": "Configure QWEN_API_KEY (or DASHSCOPE_API_KEY) for Qwen online, or GOOGLE_API_KEY/GOOGLE_API_KEY_2 for Google fallback."



            }), 503







        if has_bilingual_tags:



            ssml_text = convert_to_bilingual_ssml(text)



            payload = {



                "input": {"ssml": ssml_text},



                "voice": {



                    "languageCode": "pt-BR",



                    "name": voice_config['pt'],



                    "ssmlGender": voice_config['gender']



                },



                "audioConfig": {



                    "audioEncoding": "MP3",



                    "speakingRate": pt_speed



                }



            }



            google_voice_name = voice_config['pt']



        elif lesson_lang == 'pt':



            payload = {



                "input": {"text": clean_text_for_tts(text)},



                "voice": {



                    "languageCode": "pt-BR",



                    "name": voice_config['pt'],



                    "ssmlGender": voice_config['gender']



                },



                "audioConfig": {



                    "audioEncoding": "MP3",



                    "speakingRate": pt_speed



                }



            }



            google_voice_name = voice_config['pt']



        else:



            payload = {



                "input": {"text": clean_text_for_tts(text)},



                "voice": {



                    "languageCode": "en-US",



                    "name": voice_config['en'],



                    "ssmlGender": voice_config['gender']



                },



                "audioConfig": {



                    "audioEncoding": "MP3",



                    "speakingRate": speed



                }



            }



            google_voice_name = voice_config['en']







        print(f"[TTS] Using Google fallback voice: {google_voice_name}")

        response_data = None
        last_google_status = None
        last_google_error = ""
        for key_index, google_api_key in enumerate(google_api_keys, start=1):
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={google_api_key}"
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                response_data = response.json()
                if key_index > 1:
                    print(f"[TTS] GOOGLE fallback recovered with key #{key_index}")
                break

            error_msg = response.text[:500] if response.text else "Unknown error"
            last_google_status = response.status_code
            last_google_error = error_msg
            print(f"[TTS] GOOGLE TTS API ERROR key=#{key_index} status={response.status_code} voice={google_voice_name} msg={error_msg}")

        if response_data is None:
            return jsonify({
                "error": "Text-to-speech service error",
                "status_code": last_google_status,
                "voice": google_voice_name,
                "details": last_google_error
            }), 503



        áudio_content = response_data.get('audioContent') or response_data.get('áudioContent')



        if not áudio_content:



            return jsonify({"error": "No áudio content received from Google TTS API"}), 503







        audio_data = base64.b64decode(áudio_content)



        save_audio_to_cache(audio_data, cache_path)



        return send_file(



            io.BytesIO(audio_data),



            mimetype="audio/mp3",



            as_attachment=False,



            download_name="tts.mp3"



        )



    except Exception as e:



        print(f"TTS Error: {e}")



        return jsonify({"error": "Failed to generate speech"}), 500











@app.route('/api/tts/clone', methods=['POST'])



@limiter.limit("10 per minute")



@require_auth



def tts_clone():



    """Voice cloning TTS with Qwen online (DashScope), with local fallback."""



    try:



        data = request.get_json(silent=True) or {}



        if not isinstance(data, dict):



            return jsonify({"error": "Invalid JSON payload"}), 400







        text = data.get('text', '')



        speed = data.get('speed', 0.85)



        lesson_lang = str(data.get('lessonLang', 'en') or 'en').strip().lower()



        requested_voice = str(data.get('voice') or "").strip()



        requested_model = str(data.get('model') or "").strip() or QWEN_TTS_CLONE_MODEL



        voice_prefix = str(data.get('voicePrefix') or QWEN_TTS_CLONE_PREFIX or "clone16").strip()



        force_create_raw = data.get('forceCreate', False)



        force_create = bool(force_create_raw) if isinstance(force_create_raw, bool) else str(force_create_raw).strip().lower() in ('1', 'true', 'yes', 'on')







        is_valid, result = validate_text_input(text, max_length=500)



        if not is_valid:



            return jsonify({"error": result}), 400



        text = result







        if QWEN_API_KEY:



            # Prefer explicit Clone16 label, then fuzzy search existing cloud voices, then create/reuse by prefix.



            requested_or_default = requested_voice or QWEN_TTS_CLONE_VOICE



            active_voice = _find_qwen_voice_by_hint(requested_or_default) if requested_or_default else ""



            if not active_voice and requested_or_default:



                # Use configured voice name directly when list/fuzzy lookup is unavailable.



                active_voice = requested_or_default







            if not active_voice:



                active_voice, ensure_err = _ensure_qwen_clone_voice(



                    prefix=voice_prefix,



                    target_model=requested_model,



                    force_create=force_create,



                )



                if ensure_err:



                    return jsonify({"error": "Failed to prepare cloned voice", "details": ensure_err}), 503







            audio_data, synth_err = _synthesize_qwen_online(



                text=text,



                lesson_lang=lesson_lang,



                speed=speed,



                voice_name=active_voice,



                model_name=requested_model,



            )



            if not audio_data and requested_or_default and active_voice == requested_or_default:



                # If direct voice name failed, try provisioning/retrieving by prefix once.



                fallback_voice, ensure_err = _ensure_qwen_clone_voice(



                    prefix=voice_prefix,



                    target_model=requested_model,



                    force_create=force_create,



                )



                if fallback_voice:



                    active_voice = fallback_voice



                    audio_data, synth_err = _synthesize_qwen_online(



                        text=text,



                        lesson_lang=lesson_lang,



                        speed=speed,



                        voice_name=active_voice,



                        model_name=requested_model,



                    )



                elif ensure_err:



                    synth_err = f"{synth_err}; voice-ensure: {ensure_err}" if synth_err else ensure_err







            if not audio_data:



                return jsonify({"error": "Qwen clone synthesis failed", "details": synth_err}), 503







            return send_file(



                io.BytesIO(audio_data),



                mimetype="audio/mp3",



                as_attachment=False,



                download_name="tts_clone.mp3"



            )







        # Legacy fallback: local GPU clone server



        qwen_tts_url = os.environ.get("QWEN_TTS_URL", "").strip()



        is_vercel = os.environ.get('VERCEL') == '1'



        if not qwen_tts_url or is_vercel:



            return jsonify({



                "error": "Voice cloning service not configured",



                "message": "Set QWEN_API_KEY/DASHSCOPE_API_KEY for online cloning, or QWEN_TTS_URL for local clone server."



            }), 503







        config_path = os.path.join(os.path.dirname(__file__), '..', 'voice_references', 'config.json')



        if not os.path.exists(config_path):



            return jsonify({"error": "Voice reference config not found. Run scripts/download_voice_reference.py first."}), 500







        with open(config_path, 'r', encoding='utf-8') as f:



            voice_config = json.load(f)







        ref_audio_path = os.path.join(os.path.dirname(__file__), '..', voice_config['ref_audio'])



        if not os.path.exists(ref_audio_path):



            return jsonify({"error": f"Reference audio not found: {voice_config['ref_audio']}. Run scripts/download_voice_reference.py first."}), 500







        if 'PLACEHOLDER' in voice_config.get('ref_text', 'PLACEHOLDER'):



            return jsonify({"error": "Voice reference transcription not set. Edit voice_references/config.json and add the transcription."}), 500







        with open(ref_audio_path, 'rb') as f:



            ref_audio_b64 = base64.b64encode(f.read()).decode('utf-8')







        try:



            response = requests.post(



                f"{qwen_tts_url}/v1/áudio/speech/clone",



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



                return send_file(



                    io.BytesIO(response.content),



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



        return jsonify({"error": "Failed to generate cloned speech"}), 500











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



    usage_payload = build_usage_payload(user_email, usage_data=usage_data)



    usage_payload["date"] = usage_data['date']



    return jsonify(usage_payload)







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



        



        if is_usage_exempt_request():



            usage_payload = build_usage_payload(user_email)



            usage_payload["success"] = True



            return jsonify(usage_payload)







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



@app.route('/api/admin/live-metrics', methods=['GET'])



@require_admin



def get_admin_live_metrics():



    """Real-time operational view for admin dashboard."""



    now = _utc_now()



    _trim_live_metrics(now)







    try:



        window_minutes = int(request.args.get('window_minutes', 10))



    except ValueError:



        window_minutes = 10



    window_minutes = max(5, min(window_minutes, 60))







    active_cutoff = now - timedelta(minutes=window_minutes)



    cutoff_5m = now - timedelta(minutes=5)



    cutoff_60m = now - timedelta(minutes=60)







    events = list(live_activity_events)



    events_5m = [e for e in events if e["timestamp"] >= cutoff_5m]



    events_60m = [e for e in events if e["timestamp"] >= cutoff_60m]



    practice_events_5m = [e for e in events_5m if e.get("endpoint") in ("/api/chat", "/api/free-conversation")]



    practice_events_60m = [e for e in events_60m if e.get("endpoint") in ("/api/chat", "/api/free-conversation")]







    response_times_5m = [e.get("response_ms") for e in practice_events_5m if isinstance(e.get("response_ms"), (int, float))]



    avg_response_ms_5m = round(sum(response_times_5m) / len(response_times_5m), 2) if response_times_5m else 0.0







    errors_5m = [e for e in practice_events_5m if e.get("status") != "ok"]



    error_rate_5m = round((len(errors_5m) / len(practice_events_5m)) * 100, 2) if practice_events_5m else 0.0







    chat_events_5m = [e for e in events_5m if e.get("endpoint") == "/api/chat" and e.get("status") == "ok"]



    must_retry_count_5m = sum(1 for e in chat_events_5m if e.get("must_retry"))



    must_retry_rate_5m = round((must_retry_count_5m / len(chat_events_5m)) * 100, 2) if chat_events_5m else 0.0







    mode_breakdown = Counter((e.get("mode") or "unknown") for e in practice_events_60m if e.get("status") == "ok")



    context_breakdown = Counter((e.get("context") or "unknown") for e in practice_events_60m if e.get("status") == "ok")







    active_users = []



    for user_id, info in live_user_activity.items():



        last_seen = info.get("last_seen")



        if not last_seen or last_seen < active_cutoff:



            continue



        user_events = [e for e in practice_events_60m if e.get("user_id") == user_id and e.get("status") == "ok"]



        user_response_times = [e.get("response_ms") for e in user_events if isinstance(e.get("response_ms"), (int, float))]



        active_users.append({



            "user_id": user_id,



            "email": info.get("email", ""),



            "last_seen": last_seen.isoformat() + "Z",



            "last_context": info.get("last_context", ""),



            "last_mode": info.get("last_mode", ""),



            "messages": int(info.get("messages", 0)),



            "last_status": info.get("last_status", ""),



            "last_response_ms": info.get("last_response_ms", None),



            "avg_response_ms_60m": round(sum(user_response_times) / len(user_response_times), 2) if user_response_times else None



        })







    active_users.sort(key=lambda item: item["last_seen"], reverse=True)



    top_contexts = [{"context": name, "count": count} for name, count in context_breakdown.most_common(6)]







    # Build last-60-minute time series (1-minute buckets) for dashboard charts.



    minute_base = now.replace(second=0, microsecond=0)



    minute_slots = [minute_base - timedelta(minutes=59 - idx) for idx in range(60)]



    minute_index = {slot: idx for idx, slot in enumerate(minute_slots)}



    series_messages = [0 for _ in minute_slots]



    series_latency_sum = [0.0 for _ in minute_slots]



    series_latency_count = [0 for _ in minute_slots]



    series_errors = [0 for _ in minute_slots]







    for event in practice_events_60m:



        ts = event.get("timestamp")



        if not ts:



            continue



        slot = ts.replace(second=0, microsecond=0)



        idx = minute_index.get(slot)



        if idx is None:



            continue



        series_messages[idx] += 1



        if event.get("status") != "ok":



            series_errors[idx] += 1



        response_ms = event.get("response_ms")



        if isinstance(response_ms, (int, float)):



            series_latency_sum[idx] += float(response_ms)



            series_latency_count[idx] += 1







    chart_messages = []



    chart_latency = []



    chart_error_rate = []



    for idx, slot in enumerate(minute_slots):



        label = slot.strftime('%H:%M')



        latency_value = (series_latency_sum[idx] / series_latency_count[idx]) if series_latency_count[idx] else 0.0



        error_value = (series_errors[idx] / series_messages[idx] * 100.0) if series_messages[idx] else 0.0



        chart_messages.append({"t": label, "value": series_messages[idx]})



        chart_latency.append({"t": label, "value": round(latency_value, 2)})



        chart_error_rate.append({"t": label, "value": round(error_value, 2)})







    return jsonify({



        "generated_at": now.isoformat() + "Z",



        "window_minutes": window_minutes,



        "active_users_count": len(active_users),



        "messages_last_5m": len(practice_events_5m),



        "messages_last_60m": len(practice_events_60m),



        "avg_response_ms_5m": avg_response_ms_5m,



        "error_rate_5m": error_rate_5m,



        "must_retry_rate_5m": must_retry_rate_5m,



        "mode_breakdown_60m": dict(mode_breakdown),



        "top_contexts_60m": top_contexts,



        "active_users": active_users[:20],



        "charts_60m": {



            "messages_per_minute": chart_messages,



            "latency_ms_per_minute": chart_latency,



            "error_rate_per_minute": chart_error_rate



        }



    })







@app.route('/api/admin/weekly-report', methods=['GET'])



@require_admin



def get_admin_weekly_report():



    """Weekly didactic and retention summary for admin dashboard."""



    try:



        weeks = int(request.args.get('weeks', 8))



    except ValueError:



        weeks = 8



    _flush_weekly_activity_store(force=True)



    report = build_weekly_didactic_report(weeks)



    return jsonify(report)







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



    """Transcribe áudio using Google Speech-to-Text, Deepgram Nova-2, or Groq Whisper"""



    if not (GOOGLE_API_KEY or DEEPGRAM_API_KEY or GROQ_API_KEY):



        return jsonify({"error": "Transcription service not configured"}), 503



    



    if not REQUESTS_AVAILABLE:



        return jsonify({"error": "Transcription service not available - missing dependencies"}), 503



    



    # Check daily usage limit



    user_email = request.user_email



    if not is_usage_exempt_request() and not check_usage_limit(user_email):



        remaining = get_remaining_seconds(user_email)
        is_portal_trial = bool(getattr(request, 'is_portal_trial', False))
        blocked_message = "Você usou os 10 minutos de IA de Conversação liberados para hoje." if is_portal_trial else (f"Practice is available on weekends only (Saturday-Sunday), {weekend_limit_label()} per weekend." if not is_weekend() else f"You've used your {weekend_limit_label()} for this weekend. See you next Saturday!")



        return jsonify({



            "error": "Weekend practice limit reached",



            "message": blocked_message,
            "remaining_seconds": remaining,



            "is_weekend": True if is_portal_trial else is_weekend(),

            "portal_trial": is_portal_trial
        }), 429



    



    # Get audio file from request. The frontend sends "audio"; accented keys
    # are kept as fallbacks for older clients.

    audio_file = request.files.get('audio')

    if not audio_file:

        return jsonify({"error": "No audio file provided"}), 400

    raw_language_hint = (request.form.get('language') or 'en').strip().lower()
    if raw_language_hint in ('en', 'en-us', 'en_us', 'english'):
        language_hint = 'en'
    elif raw_language_hint in ('pt', 'pt-br', 'pt_br', 'portuguese', 'português'):
        language_hint = 'pt'
    else:
        # Conversation practice is primarily English; avoid accidental pt-BR STT.
        language_hint = 'en'



    audio_mime = request.form.get('mime_type', '')  # actual MIME from browser







    if audio_file.filename == '':



        return jsonify({"error": "Empty audio file"}), 400







    try:



        # Read áudio data



        audio_data = audio_file.read()







        if len(audio_data) == 0:



            return jsonify({"error": "Audio file is empty"}), 400







        # --- DETECT REAL AUDIO FORMAT ---



        # Browser sends actual mimeType; also sniff magic bytes as fallback



        is_webm = True  # default assumption



        if audio_mime:



            is_webm = 'webm' in audio_mime.lower()



        elif len(audio_data) >= 4:



            # WebM/Matroska starts with 0x1A45DFA3



            is_webm = audio_data[:4] == b'\x1a\x45\xdf\xa3'







        audio_format_label = "webm/opus" if is_webm else "mp4/aac"



        print(f"[Transcription] Received audio: {len(audio_data)} bytes, hint: {language_hint}, format: {audio_format_label}, mime: {audio_mime or 'not sent'}")







        # Minimum confidence to accept Google Speech result before trying fallbacks



        GOOGLE_STT_MIN_CONFIDENCE = 0.78







        # --- INTELLIGENT ROUTING ---



        # Priority: Groq Whisper for English practice, then provider fallbacks.



        # If Google returns low confidence, try Deepgram/Groq for a better result







        transcript = None



        confidence = 0.0



        provider = "none"



        google_low_confidence = False  # track if Google returned low-quality result
        fallback_transcript = None
        fallback_confidence = 0.0
        fallback_provider = "none"

        prefer_groq_for_english = bool(GROQ_API_KEY and language_hint == 'en')

        if prefer_groq_for_english:
            print("[Transcription] English practice: using Groq Whisper before Google/Deepgram.")







        # 1. Try GOOGLE SPEECH-TO-TEXT with Service Account (only for WebM/Opus)



        google_sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()



        if not prefer_groq_for_english and SPEECH_AVAILABLE and google_sa_json and is_webm:



            try:



                sa_info = json.loads(google_sa_json)



                credentials = service_account.Credentials.from_service_account_info(sa_info)



                client = speech.SpeechClient(credentials=credentials)







                lang_code = 'en-US' if language_hint == 'en' else 'pt-BR'



                # Do not add pt-BR as an English alternative; it caused desktop
                # recordings with Brazilian accents to be accepted in the wrong language.
                alt_languages = [] if language_hint == 'en' else ['en-US']







                config = speech.RecognitionConfig(



                    encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,



                    sample_rate_hertz=48000,



                    language_code=lang_code,



                    alternative_language_codes=alt_languages,



                    enable_automatic_punctuation=True,



                    model="latest_long"



                )







                google_audio = speech.RecognitionAudio(content=audio_data)



                response = client.recognize(config=config, audio=google_audio)







                if response.results:



                    result = response.results[0]



                    if result.alternatives:



                        g_transcript = result.alternatives[0].transcript



                        g_confidence = result.alternatives[0].confidence



                        if g_transcript and g_confidence >= GOOGLE_STT_MIN_CONFIDENCE:



                            transcript = g_transcript



                            confidence = g_confidence



                            provider = "google-speech-sa"



                            print(f"[Google STT SA] Accepted: '{transcript[:60]}...', Conf: {confidence:.2f}")



                        elif g_transcript:



                            # Low confidence — save as fallback but try other providers

                            google_low_confidence = True
                            fallback_transcript = g_transcript
                            fallback_confidence = g_confidence
                            fallback_provider = "google-speech-sa-lowconf"

                            print(f"[Google STT SA] Low confidence ({g_confidence:.2f}): '{g_transcript[:60]}...' — trying other providers")



                        else:



                            print("[Google STT SA] Empty transcript")



                else:



                    print("[Google STT SA] No results in response")







            except Exception as e:



                print(f"[Google STT SA] Exception: {e}")



        elif not prefer_groq_for_english and SPEECH_AVAILABLE and google_sa_json and not is_webm:



            print(f"[Google STT SA] Skipped — áudio is {audio_format_label}, not WebM/Opus")







        # 2. Try DEEPGRAM (smart format detection)



        prefer_groq_for_mixed = (language_hint != 'en')



        should_use_deepgram = not transcript and DEEPGRAM_API_KEY and not prefer_groq_for_english and (not prefer_groq_for_mixed or not GROQ_API_KEY)







        if should_use_deepgram:



            try:



                # Send the actual content type so Deepgram decodes correctly



                dg_content_type = 'audio/webm' if is_webm else 'audio/mp4'



                headers = {



                    'Authorization': f'Token {DEEPGRAM_API_KEY}',



                    'Content-Type': dg_content_type



                }







                if language_hint == 'en':



                    dg_url = "https://api.deepgram.com/v1/listen?model=nova-2-general&smart_format=true&punctuate=true&language=en-US"



                else:



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



                        dg_transcript = alternatives['transcript']



                        dg_confidence = alternatives['confidence']



                        if dg_transcript:



                            transcript = dg_transcript



                            confidence = dg_confidence



                            provider = "deepgram-nova-2"



                            print(f"[Deepgram] Success: '{transcript[:60]}...', Conf: {confidence:.2f}")



                        else:



                            print("[Deepgram] Returned empty transcript")



                    except (KeyError, IndexError):



                        print("[Deepgram] Error parsing response")



                else:



                    print(f"[Deepgram] Request failed: {response.status_code}")







            except Exception as e:



                print(f"[Deepgram] Exception: {e}")







        # 3. Try GROQ WHISPER (handles any áudio format natively)



        # 3. Try GROQ WHISPER (handles any audio format natively)
        if not transcript and GROQ_API_KEY:
            print("[Transcription] Falling back to Groq Whisper...")
            try:
                groq_filename = 'audio.webm' if is_webm else 'audio.mp4'
                groq_mime = 'audio/webm' if is_webm else 'audio/mp4'
                files = {'file': (groq_filename, audio_data, groq_mime)}

                if language_hint == 'en' or not language_hint:
                    whisper_prompt = "Transcribe the user's speech exactly as spoken in English."
                else:
                    whisper_prompt = "Transcreva a fala do usuario exatamente."

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

                headers = {'Authorization': f'Bearer {GROQ_API_KEY}'}

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
                    print(f"[Groq] Success: '{transcript[:60]}...'")
                else:
                    print(f"[Groq] Error {response.status_code}: {response.text}")

            except Exception as e_groq:
                print(f"[Groq] Exception: {e_groq}")

        # 3b. Fallback: se Groq foi preferido para ingles mas falhou, tentar Deepgram e Google
        if not transcript and prefer_groq_for_english:
            print("[Transcription] Groq failed for English — trying Deepgram/Google as fallback")
            if DEEPGRAM_API_KEY:
                try:
                    dg_content_type = 'audio/webm' if is_webm else 'audio/mp4'
                    dg_headers = {'Authorization': f'Token {DEEPGRAM_API_KEY}', 'Content-Type': dg_content_type}
                    dg_url = "https://api.deepgram.com/v1/listen?model=nova-2-general&smart_format=true&punctuate=true&language=en-US"
                    dg_resp = requests.post(dg_url, data=audio_data, headers=dg_headers, timeout=10)
                    if dg_resp.status_code == 200:
                        dg_result = dg_resp.json()
                        dg_alt = dg_result['results']['channels'][0]['alternatives'][0]
                        if dg_alt.get('transcript'):
                            transcript = dg_alt['transcript']
                            confidence = dg_alt.get('confidence', 0.9)
                            provider = "deepgram-nova-2-fallback"
                            print(f"[Deepgram Fallback] Success: '{transcript[:60]}...'")
                except Exception as e_dg:
                    print(f"[Deepgram Fallback] Exception: {e_dg}")

            if not transcript and SPEECH_AVAILABLE and google_sa_json and is_webm:
                try:
                    sa_info = json.loads(google_sa_json)
                    credentials = service_account.Credentials.from_service_account_info(sa_info)
                    g_client = speech.SpeechClient(credentials=credentials)
                    g_config = speech.RecognitionConfig(
                        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                        sample_rate_hertz=48000,
                        language_code='en-US',
                        enable_automatic_punctuation=True,
                        model="latest_long"
                    )
                    g_resp = g_client.recognize(config=g_config, audio=speech.RecognitionAudio(content=audio_data))
                    if g_resp.results and g_resp.results[0].alternatives:
                        g_t = g_resp.results[0].alternatives[0].transcript
                        g_c = g_resp.results[0].alternatives[0].confidence
                        if g_t:
                            transcript = g_t
                            confidence = g_c
                            provider = "google-speech-sa-fallback"
                            print(f"[Google Fallback] Success: '{transcript[:60]}...'")
                except Exception as e_gfb:
                    print(f"[Google Fallback] Exception: {e_gfb}")


        # --- FINAL CHECK ---



        if not transcript:
            if fallback_transcript:
                transcript = fallback_transcript
                confidence = fallback_confidence
                provider = fallback_provider
                print(f"[Transcription] Using low-confidence fallback: '{transcript[:60]}...'")
            else:
                return jsonify({"error": "No speech detected"}), 400







        return jsonify({



            "text": transcript,



            "confidence": confidence,



            "provider": provider



        })



            



    except Exception as e:



        print(f"Transcription Error: {e}")



        return jsonify({"error": str(e)}), 500












@app.errorhandler(429)
def rate_limit_exceeded(e):
    """Return a retry-friendly JSON response for rate-limited requests."""
    msg = str(getattr(e, 'description', e))
    # Check if this is a usage-limit 429 (already handled by the route logic)
    # For flask-limiter's own 429, return a retry hint
    return jsonify({
        "error": "Muitas solicitações. Aguarde alguns segundos e tente novamente.",
        "retry": True,
        "message": "Aguarde alguns segundos e tente novamente.",
        "rate_limit": True
    }), 429


@app.route('/health', methods=['GET'])



@app.route('/api/health', methods=['GET'])



def health_check():



    """Health check endpoint"""



    return jsonify({



        "status": "ok",



        "timestamp": datetime.now().isoformat(),



        "google_api_configured": bool(GOOGLE_API_KEY),



        "qwen_api_configured": bool(QWEN_API_KEY),



        "qwen_tts_model": QWEN_TTS_MODEL,



        "qwen_tts_clone_model": QWEN_TTS_CLONE_MODEL,



        "groq_api_configured": bool(GROQ_API_KEY),



        "deepgram_api_configured": bool(DEEPGRAM_API_KEY),



        "transcription_available": bool(GOOGLE_API_KEY or DEEPGRAM_API_KEY or GROQ_API_KEY),



        "transcription_providers": [name for name, enabled in {
            "google": bool(GOOGLE_API_KEY),
            "deepgram": bool(DEEPGRAM_API_KEY),
            "groq": bool(GROQ_API_KEY),
        }.items() if enabled],



        "genai_available": GENAI_AVAILABLE,



        "genai_provider": GENAI_PROVIDER,



        "genai_model": GEMINI_MODEL_NAME,



        "genai_thinking_budget": GEMINI_THINKING_BUDGET,



        "requests_available": REQUESTS_AVAILABLE



    })







@app.route('/api/debug_imports', methods=['GET'])



@require_admin



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



        "google-genai": {



            "available": globals().get('GENAI_AVAILABLE'),



            "provider": globals().get('GENAI_PROVIDER'),



            "model": globals().get('GEMINI_MODEL_NAME'),



            "thinking_budget": globals().get('GEMINI_THINKING_BUDGET'),



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







# ═══ FEEDBACK SYSTEM ════════════════════════════════════════════════════



# In-memory feedback store (persisted to JSON file)



FEEDBACK_FILE = os.path.join(CACHE_ROOT, 'feedbacks.json')







def _load_feedbacks():



    """Load feedbacks from JSON file."""



    try:



        if os.path.exists(FEEDBACK_FILE):



            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:



                return json.load(f)



    except Exception as e:



        print(f"[Feedback] Error loading feedbacks: {e}")



    return []







def _save_feedbacks(feedbacks):



    """Save feedbacks to JSON file."""



    try:



        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:



            json.dump(feedbacks, f, ensure_ascii=False, indent=2)



    except Exception as e:



        print(f"[Feedback] Error saving feedbacks: {e}")







@app.route('/api/feedback', methods=['POST'])



def submit_feedback():



    """Submit user feedback (public)."""



    try:



        data = request.get_json()



        if not data:



            return jsonify({"error": "No data provided"}), 400







        feedback_entry = {



            "id": str(int(time.time() * 1000)),



            "timestamp": data.get("timestamp", datetime.now().isoformat()),



            "email": data.get("email", "anonymous"),



            "name": data.get("name", ""),



            "rating": data.get("rating", 0),



            "category": data.get("category", ""),



            "message": data.get("message", ""),



            "language": data.get("language", "pt"),



            "read": False



        }







        feedbacks = _load_feedbacks()



        feedbacks.append(feedback_entry)



        _save_feedbacks(feedbacks)







        return jsonify({"success": True, "id": feedback_entry["id"]}), 201



    except Exception as e:



        print(f"[Feedback] Error submitting: {e}")



        return jsonify({"error": "Failed to save feedback"}), 500







@app.route('/api/admin/feedbacks', methods=['GET'])



@require_admin



def get_feedbacks():



    """Get all feedbacks (public with link)."""



    try:



        feedbacks = _load_feedbacks()



        feedbacks.reverse()  # Newest first



        return jsonify({"feedbacks": feedbacks, "total": len(feedbacks)})



    except Exception as e:



        return jsonify({"error": str(e)}), 500







@app.route('/api/admin/feedbacks/<feedback_id>/read', methods=['PATCH'])



@require_admin



def mark_feedback_read(feedback_id):



    """Mark a feedback as read."""



    try:



        feedbacks = _load_feedbacks()



        for fb in feedbacks:



            if fb.get("id") == feedback_id:



                fb["read"] = True



                _save_feedbacks(feedbacks)



                return jsonify({"success": True})



        return jsonify({"error": "Feedback not found"}), 404



    except Exception as e:



        return jsonify({"error": str(e)}), 500







@app.route('/api/admin/feedbacks/stats', methods=['GET'])



@require_admin



def get_feedback_stats():



    """Get feedback statistics (public with link)."""



    try:



        feedbacks = _load_feedbacks()



        total = len(feedbacks)



        unread = sum(1 for fb in feedbacks if not fb.get("read", False))



        avg_rating = sum(fb.get("rating", 0) for fb in feedbacks) / total if total > 0 else 0







        # Category breakdown



        categories = {}



        for fb in feedbacks:



            cat = fb.get("category", "other")



            categories[cat] = categories.get(cat, 0) + 1







        # Rating distribution



        ratings = {str(i): 0 for i in range(1, 6)}



        for fb in feedbacks:



            r = str(fb.get("rating", 0))



            if r in ratings:



                ratings[r] += 1







        return jsonify({



            "total": total,



            "unread": unread,



            "avg_rating": round(avg_rating, 1),



            "categories": categories,



            "ratings": ratings



        })



    except Exception as e:



        return jsonify({"error": str(e)}), 500







# ═══ END FEEDBACK SYSTEM ════════════════════════════════════════════════







@app.route('/<path:path>')



def serve_static(path):



    try:



        def _normalize_static_path(value):



            if not value:



                return ""



            value = value.replace('\\', '/').lstrip('/')



            normalized = os.path.normpath(value).replace('\\', '/')



            if normalized.startswith('../') or normalized.startswith('..\\') or normalized.startswith('/'):



                return ""



            return normalized







        def _is_safe_static_path(value):



            if not value or value.startswith('.'):



                return False



            blocked = {



                '.env', '.env.example', '.gitignore', '.vercelignore',



                'authorized_emails.json', 'lessons_db.json', 'grammar_topics.json', 'scenarios_db.json',



                'requirements.txt', 'requirements_backup.txt', 'server.log', 'api_crash_log.txt'



            }



            if os.path.basename(value) in blocked:



                return False







            root_exts = {'.html', '.css', '.js', '.ico', '.png', '.jpg', '.jpeg', '.svg', '.webp'}



            media_exts = {'.mp3', '.wav'}



            json_exts = {'.json'}



            ext = os.path.splitext(value)[1].lower()







            if '/' not in value:



                return ext in root_exts







            if value.startswith('assets/áudio/'):



                return ext in media_exts



            if value.startswith('audio_cache/lessons/'):



                return ext in media_exts



            if value.startswith('free_conversation/'):



                return ext in json_exts







            return False







        safe_path = _normalize_static_path(path)



        if not _is_safe_static_path(safe_path):



            return jsonify({"error": "File not found"}), 404







        response = send_from_directory(BASE_DIR, safe_path)



        # No cache for HTML files to ensure fresh content



        if safe_path.endswith('.html'):



            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'



            response.headers['Pragma'] = 'no-cache'



            response.headers['Expires'] = '0'



        return response



    except FileNotFoundError:



        return jsonify({"error": "File not found"}), 404







if __name__ == '__main__':



    # PORT 4344



    app.run(debug=False, port=4344)



































