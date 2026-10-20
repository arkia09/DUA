import json
import logging
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .departments import DEPARTMENTS, MODEL_FAILED, RECEIVED, VALIDATORS, build_user_prompt
from .models import Case
from .ollama import OllamaError, ask
from .validation import InvalidModelOutput

logger = logging.getLogger(__name__)

# Machine-readable Ollama failure code -> HTTP status
ERROR_STATUS = {"unavailable": 503, "model_missing": 503, "timeout": 504, "invalid_response": 502}


def serialize(case):
    return {
        "number": case.number,
        "department": case.department,
        "status": case.status,
        "statement": case.statement,
        "result": case.result,
        "created_at": case.created_at.isoformat(),
    }


def index(request):
    return render(request, "cases/index.html", {"max_chars": settings.MAX_STATEMENT_CHARS})


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

    case = Case.objects.create(department=department, statement=statement)
    system, schema = DEPARTMENTS[department]

    try:
        case.status = "under_review"
        raw = ask(system, build_user_prompt(statement), schema)
        case.result = VALIDATORS[department](raw, statement)
        case.status = "resolved"
        case.save()
    except (OllamaError, InvalidModelOutput) as e:
        case.status = "failed"
        case.save()
        # Technical reason only (never the user's statement) so failures are diagnosable.
        logger.warning("Case %s failed: %s: %s", case.number, type(e).__name__, e)
        if isinstance(e, OllamaError):
            code, message = e.code, e.user_message
        else:
            code, message = "invalid_response", "The AI officer returned an unusable response. Please try again."
        return JsonResponse(
            {"notice": MODEL_FAILED, "error": message, "error_code": code, "case": serialize(case)},
            status=ERROR_STATUS.get(code, 500 if code == "generation_failed" else 502),
        )

    return JsonResponse({"notice": RECEIVED, "case": serialize(case)}, status=201)


@require_GET
def list_cases(request):
    return JsonResponse({"cases": [serialize(c) for c in Case.objects.order_by("-created_at")]})
