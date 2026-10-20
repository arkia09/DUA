"""Single gateway to the local Ollama server. All model I/O goes through ask()."""
import json

import requests
from django.conf import settings


class OllamaError(Exception):
    """Base error. `code` is machine-readable; `user_message` is safe to show end users."""

    code = "generation_failed"
    user_message = "The AI officer could not complete the review. Please try again."


class OllamaUnavailable(OllamaError):
    code = "unavailable"
    user_message = "The local AI service (Ollama) is not reachable. Make sure Ollama is running."


class OllamaModelMissing(OllamaError):
    code = "model_missing"
    user_message = "The configured AI model is not installed in Ollama."


class OllamaTimeout(OllamaError):
    code = "timeout"
    user_message = "The AI officer took too long to respond. Please try again, or shorten the request."


class OllamaInvalidResponse(OllamaError):
    code = "invalid_response"
    user_message = "The AI officer returned a response we could not understand. Please try again."


def ask(system: str, user: str, schema: dict) -> dict:
    """Send one chat turn constrained to `schema`; return the parsed JSON object."""
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": schema,
        "stream": False,
        "think": settings.OLLAMA_THINK,
        "options": {"temperature": 0.6},
    }
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    timeout = (settings.OLLAMA_CONNECT_TIMEOUT, settings.OLLAMA_READ_TIMEOUT)
    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.ConnectionError as e:  # ConnectTimeout is a subclass of both; unavailable wins
        raise OllamaUnavailable(type(e).__name__) from e
    except requests.Timeout as e:
        raise OllamaTimeout(type(e).__name__) from e
    except requests.RequestException as e:
        raise OllamaError(type(e).__name__) from e

    if r.status_code == 404:
        raise OllamaModelMissing(f"HTTP 404 for model {settings.OLLAMA_MODEL}")
    if not r.ok:
        raise OllamaError(f"HTTP {r.status_code}")

    try:
        content = r.json()["message"]["content"]
        parsed = json.loads(content)
    except (ValueError, KeyError, TypeError) as e:
        raise OllamaInvalidResponse(type(e).__name__) from e
    if not isinstance(parsed, dict):
        raise OllamaInvalidResponse("not a JSON object")
    return parsed
