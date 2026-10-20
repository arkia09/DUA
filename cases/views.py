import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .departments import (
    DEPARTMENTS, MODEL_FAILED, RECEIVED, TONES, VALIDATORS, build_user_prompt, clean_options,
)
from .models import Case
from .ollama import OllamaError, ask
from .validation import InvalidModelOutput

logger = logging.getLogger(__name__)

# Machine-readable Ollama failure code -> HTTP status
ERROR_STATUS = {"unavailable": 503, "model_missing": 503, "timeout": 504, "invalid_response": 502}
HISTORY_LIMIT = 50


def serialize(case):
    return {
        "number": case.number,
        "department": case.department,
        "status": case.status,
        "statement": case.statement,
        "options": case.options,
        "result": case.result,
        "created_at": case.created_at.isoformat(),
    }


def index(request):
    return render(request, "cases/index.html", {"max_chars": settings.MAX_STATEMENT_CHARS, "tones": list(TONES)})


def review(case):
    """Run the AI review for a case. Returns a JsonResponse; the case ends resolved or failed."""
    system, schema = DEPARTMENTS[case.department]
    case.transition("under_review")
    try:
        raw = ask(system, build_user_prompt(case.statement, case.options), schema)
        case.result = VALIDATORS[case.department](raw, case.statement)
        case.transition("resolved")
    except (OllamaError, InvalidModelOutput) as e:
        # Technical reason only (never the user's statement) so failures are diagnosable.
        logger.warning("Case %s failed: %s: %s", case.number, type(e).__name__, e)
        case.transition("failed")
        if isinstance(e, OllamaError):
            code, message = e.code, e.user_message
        else:
            code, message = "invalid_response", "The AI officer returned an unusable response. Please try again."
        return JsonResponse(
            {"notice": MODEL_FAILED, "error": message, "error_code": code, "case": serialize(case)},
            status=ERROR_STATUS.get(code, 500 if code == "generation_failed" else 502),
        )
    return JsonResponse({"notice": RECEIVED, "case": serialize(case)}, status=201)


@csrf_exempt  # fine for local dev, revisit if you add a separate frontend origin
@require_POST
def file_request(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    department = data.get("department")
    statement = data.get("statement")
    statement = statement.strip() if isinstance(statement, str) else ""

    if department not in DEPARTMENTS:
        return JsonResponse({"error": "Unknown department"}, status=400)
    if not statement:
        return JsonResponse({"error": "Statement is empty"}, status=400)
    if len(statement) > settings.MAX_STATEMENT_CHARS:
        return JsonResponse(
            {"error": f"Statement is too long (maximum {settings.MAX_STATEMENT_CHARS} characters)"}, status=400
        )
    options, error = clean_options(department, data.get("options"))
    if error:
        return JsonResponse({"error": error}, status=400)

    case = Case.objects.create(department=department, statement=statement, options=options)
    return review(case)


@csrf_exempt
@require_POST
def retry_case(request, number):
    """Re-run the review for a failed case (failed -> under_review -> resolved/failed)."""
    case = Case.objects.filter(number=number).first()
    if case is None:
        return JsonResponse({"error": "Case not found"}, status=404)
    if case.status != "failed":
        return JsonResponse({"error": "Only failed cases can be sent back for review"}, status=409)
    return review(case)


@require_GET
def case_detail(request, number):
    case = Case.objects.filter(number=number).first()
    if case is None:
        return JsonResponse({"error": "Case not found"}, status=404)
    return JsonResponse({"case": serialize(case)})


@require_GET
def list_cases(request):
    cases = Case.objects.order_by("-created_at")[:HISTORY_LIMIT]
    return JsonResponse({"cases": [serialize(c) for c in cases]})
