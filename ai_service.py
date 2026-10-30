
"""Gemini AI service using Google's Interactions API."""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

DEFAULT_MODEL = "gemini-3.1-flash-lite"
TIMEOUT_SECONDS = 60
MAX_RETRIES = 3


class AIServiceError(Exception):
    """Raised when the AI service cannot provide an assessment."""


def _build_prompt(glucose, haemoglobin, cholesterol):
    return (
        "You are assisting a software demo that summarises blood test values. "
        "Provide informational remarks only, not a diagnosis or medical diagnosis."
        f"Glucose: {glucose} mg/dL\n"
        f"Haemoglobin: {haemoglobin} g/dL\n"
        f"Cholesterol: {cholesterol} mg/dL\n\n"
        "Write 2 to 3 short sentences in plain English. "
        "Briefly describe whether each value appears low, typical or high "
        "compared with common reference ranges. Give an overall risk level "
        "(Low, Moderate or High). Do not claim that the person has a disease. "
        "End with: Informational only - not a medical diagnosis."
    )


def _extract_text(data):
    """Extract generated text from the Interactions API response."""

    if data.get("status") != "completed":
        raise AIServiceError(
            "The AI assessment did not complete. Please try again."
        )

    results = []

    for step in data.get("steps", []):
        if step.get("type") == "model_output":
            for item in step.get("content", []):
                if item.get("type") == "text":
                    results.append(item.get("text", ""))

    result = "\n".join(results).strip()

    if not result:
        raise AIServiceError(
            "The AI service returned an empty assessment."
        )

    return result


def generate_remarks(glucose, haemoglobin, cholesterol):
    """Generate informational remarks from blood test values."""

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        raise AIServiceError(
            "GEMINI_API_KEY is missing. Add it to your .env file."
        )

    model = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL

    payload = {
        "model": model,
        "input": _build_prompt(
            glucose, haemoglobin, cholesterol
        ),
        "store": False
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                API_URL,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=TIMEOUT_SECONDS
            )

            if response.status_code in (429, 502, 503, 504):
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue

            break

        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES - 1:
                raise AIServiceError(
                    "The AI service timed out. Please try again later."
                )

            time.sleep(2 ** (attempt + 1))

        except requests.exceptions.RequestException as exc:
            raise AIServiceError(
                "Could not connect to the AI service. "
                "Check your internet connection."
            ) from exc

    try:
        data = response.json()
    except ValueError:
        raise AIServiceError(
            "The AI service returned an unexpected response."
        )

    if response.status_code != 200:
        error_message = data.get("error", {}).get(
            "message", "Unknown API error"
        )

        raise AIServiceError(
            f"Gemini API error (HTTP {response.status_code}): "
            f"{error_message[:200]}"
        )

    try:
        return _extract_text(data)
    except (AttributeError, KeyError, IndexError, TypeError):
        raise AIServiceError(
            "The AI service returned an unexpected response."
        )
