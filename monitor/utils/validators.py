"""
Validators for API responses and content
"""
import re
import time
from typing import Dict, List, Any, Tuple


class ValidationResult:
    """Result of a validation check"""

    def __init__(self, passed: bool, message: str = "", details: Dict[str, Any] = None):
        self.passed = passed
        self.message = message
        self.details = details or {}

    def __bool__(self):
        return self.passed

    def __repr__(self):
        return f"ValidationResult(passed={self.passed}, message='{self.message}')"


class Validators:
    """Collection of validation methods"""

    # Robotic phrases that should not appear in simulator mode
    ROBOTIC_PHRASES = [
        'can you try',
        'please repeat',
        'could you say that again',
        'i didn\'t catch that',
        'can you rephrase',
        'let me help you',
        'that\'s correct',
        'good job',
        'well done'
    ]

    # Grammar jargon that should not appear
    GRAMMAR_JARGON = [
        'past simple',
        'present perfect',
        'conditional',
        'auxiliary verb',
        'fill in the blank',
        'choose the correct',
        'complete the sentence'
    ]

    @staticmethod
    def validate_encoding(text: str) -> ValidationResult:
        """Detect double-encoded UTF-8 or corrupted characters"""
        if not text:
            return ValidationResult(True)

        # Patterns indicating double-encoded UTF-8
        mojibake_patterns = [
            'Ã£',  # ã encoded twice
            'Ã©',  # é encoded twice
            'Ã§',  # ç encoded twice
            'Ã¡',  # á encoded twice
            'Ã³',  # ó encoded twice
            'Ãº',  # ú encoded twice
            'Ã­',  # í encoded twice
        ]

        found_issues = []
        for pattern in mojibake_patterns:
            if pattern in text:
                found_issues.append(pattern)

        if found_issues:
            return ValidationResult(
                False,
                f"Double-encoded UTF-8 detected: {', '.join(found_issues)}",
                {"patterns": found_issues, "text_sample": text[:100]}
            )

        return ValidationResult(True, "Encoding OK")

    @staticmethod
    def validate_json_schema(data: Dict[str, Any], required_fields: List[str]) -> ValidationResult:
        """Validate JSON response has required fields"""
        if not isinstance(data, dict):
            return ValidationResult(False, f"Expected dict, got {type(data).__name__}")

        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return ValidationResult(
                False,
                f"Missing required fields: {', '.join(missing_fields)}",
                {"missing": missing_fields, "present": list(data.keys())}
            )

        return ValidationResult(True, "Schema valid")

    @staticmethod
    def validate_behavioral(text: str, mode: str, context: str = "") -> ValidationResult:
        """Detect behavioral issues (robotic phrases, drift, etc.)"""
        if not text:
            return ValidationResult(False, "Empty response")

        text_lower = text.lower()
        issues = []

        # Check for robotic phrases in simulator mode
        if mode == 'simulator':
            for phrase in Validators.ROBOTIC_PHRASES:
                if phrase in text_lower:
                    issues.append(f"Robotic phrase: '{phrase}'")

        # Check for grammar jargon (should never appear)
        for jargon in Validators.GRAMMAR_JARGON:
            if jargon in text_lower:
                issues.append(f"Grammar jargon: '{jargon}'")

        # Check if response is too long
        word_count = len(text.split())
        if mode == 'simulator' and word_count > 40:
            issues.append(f"Too long for simulator mode: {word_count} words (max 40)")
        elif mode == 'learning' and word_count > 100:
            issues.append(f"Too long for learning mode: {word_count} words (max 100)")

        # Check if response ends with question (should in most cases)
        if mode == 'simulator' and not text.rstrip().endswith('?'):
            # This is a warning, not a hard fail
            pass

        if issues:
            return ValidationResult(
                False,
                f"Behavioral issues: {'; '.join(issues)}",
                {"issues": issues, "text": text}
            )

        return ValidationResult(True, "Behavior OK")

    @staticmethod
    def validate_performance(response_time_ms: int, threshold_warning: int = 3000,
                            threshold_critical: int = 5000) -> ValidationResult:
        """Validate response time performance"""
        if response_time_ms < threshold_warning:
            return ValidationResult(True, f"Performance good: {response_time_ms}ms")
        elif response_time_ms < threshold_critical:
            return ValidationResult(
                True,
                f"Performance warning: {response_time_ms}ms (>= {threshold_warning}ms)",
                {"level": "warning", "response_time_ms": response_time_ms}
            )
        else:
            return ValidationResult(
                False,
                f"Performance critical: {response_time_ms}ms (>= {threshold_critical}ms)",
                {"level": "critical", "response_time_ms": response_time_ms}
            )

    @staticmethod
    def validate_translation(en_text: str, pt_text: str) -> ValidationResult:
        """Validate that PT translation is present and different from EN"""
        if not pt_text or not pt_text.strip():
            return ValidationResult(False, "Missing Portuguese translation")

        if en_text.strip() == pt_text.strip():
            return ValidationResult(False, "PT translation identical to EN text")

        # Basic check: PT text should have some PT-specific characters
        pt_char_codes = {227, 245, 231, 225, 233, 237, 243, 250, 226, 234, 244}
        has_pt_chars = any(ord(char) in pt_char_codes for char in pt_text.lower())

        if not has_pt_chars and len(pt_text.split()) > 3:
            # Only warn if text is substantial (>3 words)
            return ValidationResult(
                True,  # Not a hard fail
                "PT text doesn't contain typical Portuguese characters (warning)",
                {"level": "warning"}
            )

        return ValidationResult(True, "Translation OK")

    @staticmethod
    def validate_audio_file(audio_data: bytes, min_size: int = 1000) -> ValidationResult:
        """Validate audio file is not empty and has reasonable size"""
        if not audio_data:
            return ValidationResult(False, "Audio data is empty")

        size = len(audio_data)
        if size < min_size:
            return ValidationResult(
                False,
                f"Audio file too small: {size} bytes (min {min_size})",
                {"size": size, "min_size": min_size}
            )

        # Check for common audio file headers
        headers = {
            b'RIFF': 'WAV',
            b'ID3': 'MP3',
            b'\xff\xfb': 'MP3',
            b'\xff\xf3': 'MP3',
            b'\xff\xf2': 'MP3'
        }

        file_type = None
        for header, ftype in headers.items():
            if audio_data.startswith(header):
                file_type = ftype
                break

        if not file_type:
            return ValidationResult(
                False,
                "Unknown audio format (no valid header)",
                {"first_bytes": audio_data[:10].hex()}
            )

        return ValidationResult(True, f"Audio valid ({file_type}, {size} bytes)")

    @staticmethod
    def validate_corrections_present(response_data: Dict[str, Any], has_errors: bool) -> ValidationResult:
        """Validate that corrections are provided when errors exist"""
        if not has_errors:
            # No errors, no corrections expected
            return ValidationResult(True)

        # Check for correction indicators
        correction_fields = ['corrections', 'feedback', 'must_retry']

        has_correction_info = any(field in response_data for field in correction_fields)

        if not has_correction_info:
            return ValidationResult(
                False,
                "Expected corrections but none provided",
                {"has_errors": has_errors, "response_fields": list(response_data.keys())}
            )

        # If must_retry is False when errors exist, that's suspicious
        if 'must_retry' in response_data and not response_data['must_retry'] and has_errors:
            return ValidationResult(
                False,
                "must_retry=false but errors exist",
                {"must_retry": False, "has_errors": True}
            )

        return ValidationResult(True, "Corrections present")


def validate_response(response, expected_status: int = 200, required_fields: List[str] = None,
                     mode: str = None, has_errors: bool = False) -> Tuple[bool, List[ValidationResult]]:
    """
    Comprehensive response validation
    Returns: (all_passed, list_of_results)
    """
    validators = Validators()
    results = []

    # Status code
    if response.status_code != expected_status:
        results.append(ValidationResult(
            False,
            f"Status code {response.status_code} != {expected_status}"
        ))
        return False, results

    results.append(ValidationResult(True, f"Status code OK ({expected_status})"))

    # JSON parsing
    try:
        data = response.json()
    except Exception as e:
        results.append(ValidationResult(False, f"JSON parse error: {e}"))
        return False, results

    results.append(ValidationResult(True, "JSON valid"))

    # Schema validation
    if required_fields:
        schema_result = validators.validate_json_schema(data, required_fields)
        results.append(schema_result)
        if not schema_result:
            return False, results

    # Encoding validation (for text fields)
    text_fields = ['en', 'pt', 'text', 'message', 'response']
    for field in text_fields:
        if field in data and isinstance(data[field], str):
            encoding_result = validators.validate_encoding(data[field])
            results.append(encoding_result)
            if not encoding_result:
                return False, results

    # Translation validation
    if 'en' in data and 'pt' in data:
        translation_result = validators.validate_translation(data['en'], data['pt'])
        results.append(translation_result)

    # Behavioral validation
    if mode and 'en' in data:
        behavioral_result = validators.validate_behavioral(data['en'], mode)
        results.append(behavioral_result)
        if not behavioral_result:
            return False, results

    # Corrections validation
    if has_errors:
        corrections_result = validators.validate_corrections_present(data, has_errors)
        results.append(corrections_result)

    all_passed = all(r.passed for r in results)
    return all_passed, results
