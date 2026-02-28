"""
API Client for making requests to the application.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import time

import jwt as pyjwt
import requests


class APIClient:
    """Client for interacting with the IA de Conversacao API."""

    def __init__(
        self,
        base_url: str,
        email: str,
        password: Optional[str] = None,
        timeout: int = 30,
        logger=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = (password or "").strip()
        self.default_timeout = timeout
        self.logger = logger
        self.token = None
        self.token_expires_at = None
        self.session = requests.Session()
        # Keep default headers generic so multipart requests can set their own content type.
        self.session.headers.update({"Accept": "*/*"})

    def _log(self, level, msg, **kwargs):
        """Internal logging helper."""
        if self.logger:
            getattr(self.logger, level)(msg, **kwargs)

    def _is_token_expired(self) -> bool:
        """Check if JWT token is expired."""
        if not self.token or not self.token_expires_at:
            return True
        return datetime.now(timezone.utc) >= self.token_expires_at

    def login(self) -> bool:
        """Authenticate with the API, with fallback for non-admin password flows."""
        try:
            url = f"{self.base_url}/api/auth/login"
            self._log("info", f"Authenticating with {url}")

            def _attempt(include_password: bool) -> requests.Response:
                payload = {"email": self.email}
                if include_password and self.password:
                    payload["password"] = self.password
                return self.session.post(url, json=payload, timeout=self.default_timeout)

            include_password = bool(self.password)
            response = _attempt(include_password=include_password)

            # Some deployments return 401 when a password is sent for a regular user.
            if (
                response.status_code == 401
                and include_password
                and "invalid admin password" in response.text.lower()
            ):
                self._log("warning", "Invalid admin password response, retrying login without password")
                response = _attempt(include_password=False)

            if response.status_code != 200:
                self._log(
                    "error",
                    f"Authentication failed: {response.status_code} - {response.text}",
                )
                return False

            data = response.json()
            self.token = data.get("token")
            if not self.token:
                self._log("error", "No token in response")
                return False

            try:
                decoded = pyjwt.decode(self.token, options={"verify_signature": False})
                exp_timestamp = decoded.get("exp")
                if exp_timestamp:
                    self.token_expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
                else:
                    self.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=6)
            except Exception as exc:
                self._log("warning", f"Could not decode token: {exc}")
                self.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=6)

            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            self._log("info", "Authentication successful")
            return True
        except Exception as exc:
            self._log("error", f"Authentication error: {exc}")
            return False

    def _ensure_authenticated(self):
        """Ensure we have a valid token."""
        if self._is_token_expired():
            self._log("info", "Token expired, re-authenticating")
            if not self.login():
                raise Exception("Failed to authenticate")

    def _request(
        self,
        method: str,
        endpoint: str,
        timeout: Optional[int] = None,
        retry_count: int = 3,
        **kwargs,
    ) -> requests.Response:
        """Make an authenticated request with retry logic."""
        self._ensure_authenticated()

        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.default_timeout

        last_exception = None
        for attempt in range(retry_count):
            try:
                response = self.session.request(method, url, timeout=timeout, **kwargs)
                return response
            except requests.exceptions.Timeout as exc:
                last_exception = exc
                self._log("warning", f"Request timeout (attempt {attempt + 1}/{retry_count}): {url}")
                if attempt < retry_count - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                self._log("warning", f"Request error (attempt {attempt + 1}/{retry_count}): {exc}")
                if attempt < retry_count - 1:
                    time.sleep(2 ** attempt)

        raise last_exception

    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """Make a GET request."""
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> requests.Response:
        """Make a POST request."""
        return self._request("POST", endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs) -> requests.Response:
        """Make a PUT request."""
        return self._request("PUT", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint, **kwargs)

    def health_check(self) -> Dict[str, Any]:
        """Check API health."""
        response = self.get("/api/health", retry_count=1)
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
        }

    def get_scenarios(self) -> Dict[str, Any]:
        """Get available scenarios."""
        response = self.get("/api/scenarios")
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
        }

    def get_grammar_topics(self) -> Dict[str, Any]:
        """Get available grammar topics."""
        response = self.get("/api/grammar-topics")
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
        }

    def chat(
        self,
        message: str,
        conversation_history: list,
        scenario: str,
        practice_mode: str = "learning",
        lesson_lang: str = "en",
        user_level: str = "intermediate",
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a chat message using the current API contract."""
        payload = {
            "text": message,
            "context": scenario,
            "practiceMode": practice_mode,
            "lessonLang": lesson_lang,
            "studentLevel": user_level,
            **kwargs,
        }
        response = self.post("/api/chat", json=payload, timeout=30)
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
            "text": response.text,
        }

    def generate_report(self, conversation_history: list, scenario: str) -> Dict[str, Any]:
        """Generate conversation report using the current API contract."""
        payload = {
            "conversation": conversation_history,
            "context": scenario,
        }
        response = self.post("/api/report", json=payload, timeout=30)
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
            "text": response.text,
        }

    def tts(self, text: str, speed: float = 1.0, lesson_lang: str = "en") -> Dict[str, Any]:
        """Text-to-speech endpoint; expects binary audio on success."""
        payload = {
            "text": text,
            "speed": speed,
            "lessonLang": lesson_lang,
        }
        response = self.post("/api/tts", json=payload, timeout=15)
        content_type = (response.headers.get("Content-Type") or "").lower()
        is_audio = response.status_code == 200 and "audio/" in content_type
        return {
            "status_code": response.status_code,
            "is_audio": is_audio,
            "content_type": content_type,
            "audio_size": len(response.content or b""),
            "data": response.json() if response.status_code == 200 and not is_audio else None,
            "text": response.text if not is_audio else None,
        }

    def transcribe(self, audio_data: bytes, filename: str = "test.wav") -> Dict[str, Any]:
        """Transcribe audio."""
        files = {"audio": (filename, audio_data, "audio/wav")}
        response = self.post("/api/transcribe", files=files, timeout=20)
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
            "text": response.text,
        }
