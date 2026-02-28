"""
Test Suite: API Endpoints Health Check.
"""

import time
from typing import Dict, Any, List

from ..utils.fixtures import ENDPOINT_TEST_DATA


class EndpointTestResult:
    """Result of an endpoint test."""

    def __init__(
        self,
        endpoint: str,
        passed: bool,
        duration_ms: int,
        status_code: int = None,
        error: str = None,
        details: Dict = None,
    ):
        self.endpoint = endpoint
        self.passed = passed
        self.duration_ms = duration_ms
        self.status_code = status_code
        self.error = error
        self.details = details or {}

    def to_dict(self):
        return {
            "endpoint": self.endpoint,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "status_code": self.status_code,
            "error": self.error,
            "details": self.details,
        }


class EndpointTestSuite:
    """Suite for testing API endpoint health."""

    POLICY_429_HINTS = (
        "weekend practice limit reached",
        "practice is available on weekends only",
        "see you next saturday",
    )

    def __init__(self, api_client, logger, validators, auto_fix, config):
        self.api_client = api_client
        self.logger = logger
        self.validators = validators
        self.auto_fix = auto_fix
        self.config = config
        self.results: List[EndpointTestResult] = []

    def _is_known_policy_429(self, response, endpoint_config: Dict[str, Any]) -> bool:
        """Allow 429 as known behavior for weekday usage blocks on selected endpoints."""
        if response.status_code != 429:
            return False
        if not endpoint_config.get("known_policy_429", False):
            return False
        text = (response.text or "").lower()
        return any(hint in text for hint in self.POLICY_429_HINTS)

    def _status_matches(self, actual_status: int, expected_status) -> bool:
        if isinstance(expected_status, list):
            return actual_status in expected_status
        return actual_status == expected_status

    def _validate_array_payload(
        self,
        data: Any,
        required_item_fields: List[str],
    ) -> Any:
        if not isinstance(data, list):
            return False, f"Expected array payload, got {type(data).__name__}", {}
        if not data:
            return True, "Array returned empty", {"item_count": 0}
        if required_item_fields and isinstance(data[0], dict):
            missing = [field for field in required_item_fields if field not in data[0]]
            if missing:
                return (
                    False,
                    f"Array item missing fields: {', '.join(missing)}",
                    {"missing": missing, "sample_item_keys": list(data[0].keys())},
                )
        return True, "Array schema valid", {"item_count": len(data)}

    def _test_endpoint(self, endpoint: str, endpoint_config: Dict[str, Any]) -> EndpointTestResult:
        method = endpoint_config.get("method", "GET")
        expected_status = endpoint_config.get("expected_status", 200)
        required_fields = endpoint_config.get("required_fields", [])
        required_any_fields = endpoint_config.get("required_any_fields", [])
        required_item_fields = endpoint_config.get("required_item_fields", [])
        payload = endpoint_config.get("payload")
        request_timeout = endpoint_config.get("timeout")
        expected_type = endpoint_config.get("expected_type", "object")
        expected_binary = endpoint_config.get("expected_binary", False)
        content_type_prefix = (endpoint_config.get("content_type_prefix") or "").lower()

        self.logger.info(f"Testing {method} {endpoint}")
        start_time = time.time()

        try:
            if method == "GET":
                response = self.api_client.get(endpoint, retry_count=1, timeout=request_timeout)
            elif method == "POST":
                response = self.api_client.post(endpoint, json=payload, retry_count=1, timeout=request_timeout)
            else:
                return EndpointTestResult(endpoint, False, 0, error=f"Unsupported method: {method}")

            duration_ms = int((time.time() - start_time) * 1000)

            if self._is_known_policy_429(response, endpoint_config):
                return EndpointTestResult(
                    endpoint,
                    True,
                    duration_ms,
                    status_code=response.status_code,
                    details={
                        "known_state": "weekday_policy_block",
                        "response_text": response.text[:200],
                    },
                )

            if not self._status_matches(response.status_code, expected_status):
                return EndpointTestResult(
                    endpoint,
                    False,
                    duration_ms,
                    status_code=response.status_code,
                    error=f"Expected {expected_status}, got {response.status_code}",
                    details={"response_text": response.text[:300]},
                )

            if expected_binary:
                content_type = (response.headers.get("Content-Type") or "").lower()
                if content_type_prefix and not content_type.startswith(content_type_prefix):
                    return EndpointTestResult(
                        endpoint,
                        False,
                        duration_ms,
                        status_code=response.status_code,
                        error=f"Unexpected content-type: {content_type}",
                        details={"expected_prefix": content_type_prefix},
                    )
                audio_result = self.validators.validate_audio_file(response.content, min_size=300)
                if not audio_result:
                    return EndpointTestResult(
                        endpoint,
                        False,
                        duration_ms,
                        status_code=response.status_code,
                        error=audio_result.message,
                        details=audio_result.details,
                    )
                return EndpointTestResult(
                    endpoint,
                    True,
                    duration_ms,
                    status_code=response.status_code,
                    details={"content_type": content_type, "response_size": len(response.content)},
                )

            try:
                data = response.json()
            except Exception as exc:
                return EndpointTestResult(
                    endpoint,
                    False,
                    duration_ms,
                    status_code=response.status_code,
                    error=f"JSON parse error: {exc}",
                )

            if expected_type == "array":
                ok, msg, details = self._validate_array_payload(data, required_item_fields)
                if not ok:
                    return EndpointTestResult(
                        endpoint,
                        False,
                        duration_ms,
                        status_code=response.status_code,
                        error=msg,
                        details=details,
                    )
            else:
                if required_fields:
                    schema_result = self.validators.validate_json_schema(data, required_fields)
                    if not schema_result:
                        return EndpointTestResult(
                            endpoint,
                            False,
                            duration_ms,
                            status_code=response.status_code,
                            error=schema_result.message,
                            details=schema_result.details,
                        )
                if required_any_fields:
                    has_any_group = any(
                        all(field in data for field in group) for group in required_any_fields
                    )
                    if not has_any_group:
                        return EndpointTestResult(
                            endpoint,
                            False,
                            duration_ms,
                            status_code=response.status_code,
                            error=f"Missing required field groups: {required_any_fields}",
                            details={"present": list(data.keys()) if isinstance(data, dict) else []},
                        )

                for field in ("en", "pt", "text", "message", "translation"):
                    if isinstance(data, dict) and field in data and isinstance(data[field], str):
                        encoding_result = self.validators.validate_encoding(data[field])
                        if not encoding_result:
                            return EndpointTestResult(
                                endpoint,
                                False,
                                duration_ms,
                                status_code=response.status_code,
                                error=f"Encoding issue in '{field}': {encoding_result.message}",
                                details=encoding_result.details,
                            )

            perf_result = self.validators.validate_performance(
                duration_ms,
                self.config.get("response_time_warning_ms", 3000),
                self.config.get("response_time_critical_ms", 5000),
            )
            if not perf_result:
                self.logger.warning(f"Performance issue on {endpoint}: {perf_result.message}")

            return EndpointTestResult(
                endpoint,
                True,
                duration_ms,
                status_code=response.status_code,
                details={"response_size": len(response.text)},
            )
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            return EndpointTestResult(endpoint, False, duration_ms, error=f"Exception: {exc}")

    def run(self) -> Dict[str, Any]:
        """Run all endpoint tests."""
        self.logger.info("Starting endpoint test suite")
        start_time = time.time()

        self.results = []
        for endpoint, endpoint_config in ENDPOINT_TEST_DATA.items():
            result = self._test_endpoint(endpoint, endpoint_config)
            self.results.append(result)
            self.logger.test_result(
                run_id="",
                environment=self.api_client.base_url,
                test_suite="endpoints",
                test_case=endpoint,
                status="PASS" if result.passed else "FAIL",
                duration_ms=result.duration_ms,
                details=result.details,
                error=result.error,
            )

        duration = time.time() - start_time
        passed_count = sum(1 for result in self.results if result.passed)
        total_count = len(self.results)

        summary = {
            "suite": "endpoints",
            "duration_seconds": duration,
            "total_tests": total_count,
            "passed": passed_count,
            "failed": total_count - passed_count,
            "pass_rate": (passed_count / total_count * 100) if total_count > 0 else 0,
            "results": [result.to_dict() for result in self.results],
        }

        self.logger.info(f"Endpoint suite completed: {passed_count}/{total_count} passed")
        return summary
