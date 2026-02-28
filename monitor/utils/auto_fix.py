"""
Auto-fix mechanisms for common issues
"""
import os
import time
import requests
from typing import Dict, Any, Optional, List
from pathlib import Path


class FixResult:
    """Result of an auto-fix attempt"""

    def __init__(self, success: bool, message: str, details: Dict[str, Any] = None):
        self.success = success
        self.message = message
        self.details = details or {}

    def __bool__(self):
        return self.success

    def __repr__(self):
        return f"FixResult(success={self.success}, message='{self.message}')"


class AutoFix:
    """Auto-fixing mechanisms for common problems"""

    def __init__(self, api_client=None, logger=None, config=None):
        self.api_client = api_client
        self.logger = logger
        self.config = config or {}
        self.failure_history = {}  # Track failures for GitHub issue creation

    def _log(self, level, msg, **kwargs):
        """Internal logging helper"""
        if self.logger:
            getattr(self.logger, level)(msg, **kwargs)

    @staticmethod
    def fix_encoding(text: str) -> FixResult:
        """Fix double-encoded UTF-8"""
        if not text:
            return FixResult(True, "Text is empty, nothing to fix")

        original = text

        try:
            # Try to fix double-encoded UTF-8 (Windows cp1252 → UTF-8 issue)
            fixed = text.encode('cp1252').decode('utf-8')

            if fixed != original:
                return FixResult(
                    True,
                    "Fixed double-encoded UTF-8",
                    {"original": original[:50], "fixed": fixed[:50]}
                )
            else:
                return FixResult(True, "No encoding issues detected")

        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            # Try another approach: replace mojibake patterns directly
            mojibake_map = {
                'Ã£': 'ã',
                'Ã©': 'é',
                'Ã§': 'ç',
                'Ã¡': 'á',
                'Ã³': 'ó',
                'Ãº': 'ú',
                'Ã­': 'í',
                'Ã ': 'à',
                'Ã´': 'ô',
                'Ãª': 'ê',
            }

            fixed = text
            for wrong, right in mojibake_map.items():
                fixed = fixed.replace(wrong, right)

            if fixed != original:
                return FixResult(
                    True,
                    "Fixed UTF-8 via pattern replacement",
                    {"replacements": len([k for k in mojibake_map.keys() if k in text])}
                )

            return FixResult(
                False,
                f"Could not fix encoding: {str(e)}",
                {"error": str(e)}
            )

    def clear_cache(self, cache_type: str = "audio") -> FixResult:
        """Clear API cache"""
        if not self.api_client:
            return FixResult(False, "No API client available")

        try:
            # Attempt to call cache clear endpoint if it exists
            endpoint = f"/api/admin/clear-cache?type={cache_type}"
            response = self.api_client.get(endpoint, retry_count=1)

            if response.status_code == 200:
                self._log('info', f"Cleared {cache_type} cache successfully")
                return FixResult(
                    True,
                    f"Cleared {cache_type} cache",
                    {"endpoint": endpoint, "status": response.status_code}
                )
            else:
                return FixResult(
                    False,
                    f"Cache clear failed: {response.status_code}",
                    {"status_code": response.status_code, "response": response.text[:200]}
                )

        except Exception as e:
            self._log('error', f"Cache clear error: {e}")
            return FixResult(False, f"Cache clear error: {str(e)}")

    def retry_with_fallback(self, func, providers: List[str], *args, **kwargs) -> FixResult:
        """Retry a function with fallback providers"""
        last_error = None

        for provider in providers:
            try:
                self._log('info', f"Trying provider: {provider}")
                kwargs['provider'] = provider
                result = func(*args, **kwargs)

                if result:
                    return FixResult(
                        True,
                        f"Success with provider: {provider}",
                        {"provider": provider, "result": result}
                    )

            except Exception as e:
                last_error = e
                self._log('warning', f"Provider {provider} failed: {e}")
                continue

        return FixResult(
            False,
            f"All providers failed. Last error: {last_error}",
            {"providers_tried": providers}
        )

    def track_failure(self, test_id: str, environment: str, error: str):
        """Track failure for potential GitHub issue creation"""
        key = f"{environment}:{test_id}"

        if key not in self.failure_history:
            self.failure_history[key] = {
                "count": 0,
                "first_seen": time.time(),
                "last_seen": None,
                "errors": []
            }

        self.failure_history[key]["count"] += 1
        self.failure_history[key]["last_seen"] = time.time()
        self.failure_history[key]["errors"].append({
            "timestamp": time.time(),
            "error": error
        })

        # Keep only last 10 errors
        if len(self.failure_history[key]["errors"]) > 10:
            self.failure_history[key]["errors"] = self.failure_history[key]["errors"][-10:]

    def should_create_issue(self, test_id: str, environment: str) -> bool:
        """Check if we should create a GitHub issue for this failure"""
        key = f"{environment}:{test_id}"
        threshold = self.config.get('consecutive_failures_for_issue', 3)

        if key in self.failure_history:
            return self.failure_history[key]["count"] >= threshold

        return False

    def create_github_issue(self, test_id: str, environment: str, error: str) -> FixResult:
        """Create a GitHub issue for persistent failure"""
        if not self.config.get('github_issues', {}).get('enabled', False):
            return FixResult(False, "GitHub issue creation is disabled")

        try:
            github_token = os.getenv(self.config['github_issues'].get('token_env', 'GITHUB_TOKEN'))
            if not github_token:
                return FixResult(False, "No GitHub token found")

            repo = self.config['github_issues'].get('repo')
            if not repo:
                return FixResult(False, "No GitHub repo configured")

            key = f"{environment}:{test_id}"
            failure_info = self.failure_history.get(key, {})

            title = f"[Monitor] {test_id} failing on {environment}"
            body = f"""## Automated Issue from Monitoring System

**Test ID:** `{test_id}`
**Environment:** `{environment}`
**Failure Count:** {failure_info.get('count', 0)}
**First Seen:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(failure_info.get('first_seen', 0)))}
**Last Seen:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(failure_info.get('last_seen', 0)))}

### Latest Error
```
{error}
```

### Recent Errors
"""

            for err in failure_info.get('errors', [])[-5:]:
                body += f"\n- {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(err['timestamp']))}: `{err['error'][:100]}`"

            body += "\n\n---\n*This issue was automatically created by the monitoring system.*"

            # Create issue via GitHub API
            url = f"https://api.github.com/repos/{repo}/issues"
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            payload = {
                "title": title,
                "body": body,
                "labels": self.config['github_issues'].get('labels', [])
            }

            response = requests.post(url, json=payload, headers=headers, timeout=10)

            if response.status_code == 201:
                issue_url = response.json().get('html_url')
                self._log('info', f"Created GitHub issue: {issue_url}")
                return FixResult(
                    True,
                    f"Created GitHub issue",
                    {"issue_url": issue_url}
                )
            else:
                return FixResult(
                    False,
                    f"Failed to create issue: {response.status_code}",
                    {"response": response.text[:200]}
                )

        except Exception as e:
            self._log('error', f"GitHub issue creation error: {e}")
            return FixResult(False, f"GitHub issue creation error: {str(e)}")

    def attempt_fix(self, test_id: str, environment: str, error_type: str,
                    error_details: Dict[str, Any]) -> FixResult:
        """Attempt to fix an error based on its type"""
        self.track_failure(test_id, environment, str(error_details))

        if not self.config.get('enabled', True):
            return FixResult(False, "Auto-fix is disabled")

        self._log('info', f"Attempting auto-fix for {test_id}: {error_type}")

        # Route to appropriate fix based on error type
        if error_type == "encoding":
            if 'text' in error_details:
                return self.fix_encoding(error_details['text'])

        elif error_type == "audio_cache":
            return self.clear_cache("audio")

        elif error_type == "api_timeout":
            # For timeouts, we don't fix - just log and potentially create issue
            if self.should_create_issue(test_id, environment):
                return self.create_github_issue(test_id, environment, str(error_details))

        elif error_type == "behavioral":
            # Behavioral issues require code fixes, just create issue
            if self.should_create_issue(test_id, environment):
                return self.create_github_issue(test_id, environment, str(error_details))

        return FixResult(
            False,
            f"No auto-fix available for error type: {error_type}",
            {"error_type": error_type}
        )
