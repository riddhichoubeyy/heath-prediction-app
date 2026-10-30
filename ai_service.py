"""Client for the external AI API (Google Gemini Developer API, REST).

Only the three blood test values are sent. No name, email or date of birth
ever leaves the application.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash"
TIMEOUT_SECONDS = 30
MAX_OUTPUT_TOKENS = 1024
# Gemini 3.x models "think" before answering and thinking tokens count towards
# the output limit. A low level keeps the short remark from being cut off.
THINKING_LEVEL = "low"


class AIServiceError(Exception):
    """Raised for any failure to obtain a usable assessment. Message is user-friendly."""


def _build_prompt(glucose, haemoglobin, cholesterol):
    return (
        "You are assisting a software demo that summarises blood test values. "
        "Give an informational risk assessment only, not a diagnosis.\n"
        f"Glucose: {glucose} mg/dL\n"
        f"Haemoglobin: {haemoglobin} g/dL\n"
        f"Cholesterol: {cholesterol} mg/dL\n\n"
        "Reply in 2 to 3 short plain-English sentences for a non-technical reader. "
        "Say whether each value looks low, typical or high compared with common reference "
        "ranges, and state an overall risk level (Low, Moderate or High). "
        "Do not name specific diseases as confirmed. End with: "
        "'Informational only - not a medical diagnosis.'"
    )


def _api_error_detail(response):
    """Short message from Google's error JSON, if there is one (never contains the key)."""
    try:
        return str(response.json()["error"]["message"])[:200]
    except (ValueError, KeyError, TypeError):
        return ""


def _extract_text(data):
    """Pull the assessment text out of a generateContent response body."""
    candidates = data.get("candidates")
    if not candidates:
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        if block_reason:
            raise AIServiceError(f"The AI service blocked this request (reason: {block_reason}).")
        raise AIServiceError("The AI service returned an unexpected response. Please try again.")

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason and finish_reason != "STOP":
        raise AIServiceError(
            f"The AI service did not finish the assessment (reason: {finish_reason}). Please try again."
        )

    parts = candidate["content"]["parts"]
    text = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
    if not text:
        raise AIServiceError("The AI service returned an empty assessment. Please try again.")
    return text


def generate_remarks(glucose, haemoglobin, cholesterol):
    """Return a short assessment string, or raise AIServiceError."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AIServiceError(
            "GEMINI_API_KEY is not set. Add it to your .env file (see .env.example) and restart the app."
        )

    model = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(glucose, haemoglobin, cholesterol)}]}],
        "generationConfig": {
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "thinkingConfig": {"thinkingLevel": THINKING_LEVEL},
        },
    }

    try:
        # The key goes in a header rather than the URL so it never appears in logs.
        response = requests.post(
            API_URL.format(model=model),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        raise AIServiceError("The AI service timed out. Please try again.")
    except requests.exceptions.RequestException as exc:
        raise AIServiceError(
            f"Could not reach the AI service ({exc.__class__.__name__}). Check your internet connection."
        )

    status = response.status_code
    if status in (400, 401, 403):
        raise AIServiceError(
            "The AI service rejected the request. Check that GEMINI_API_KEY is valid. "
            + _api_error_detail(response)
        )
    if status == 404:
        raise AIServiceError(
            f"The AI model '{model}' was not found. Check the GEMINI_MODEL setting. "
            + _api_error_detail(response)
        )
    if status == 429:
        raise AIServiceError("AI service rate limit reached. Wait a moment and try again.")
    if status >= 500:
        raise AIServiceError(f"The AI service is temporarily unavailable (HTTP {status}). Please try again.")
    if status != 200:
        raise AIServiceError(f"The AI service returned an error (HTTP {status}). Please try again.")

    try:
        data = response.json()
    except ValueError:
        raise AIServiceError("The AI service returned an unexpected response. Please try again.")

    try:
        return _extract_text(data)
    except (AttributeError, KeyError, IndexError, TypeError):
        raise AIServiceError("The AI service returned an unexpected response. Please try again.")
