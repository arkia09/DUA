import json
import logging
import os
import re

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .departments import (
    DEPARTMENTS, DIRECTORY, MODEL_FAILED, PAGES, PRECHECKS, PREVIEW_CHARS, PRIVATE_DEPARTMENTS, RECEIVED, TONES,
    VALIDATORS, build_user_prompt, char_limit, clean_options, get_department,
)
from .models import Case
from .offices.documents import MIN_DOCUMENT_WORDS
from .ollama import OllamaError, ask
from .validation import InvalidModelOutput

logger = logging.getLogger(__name__)

# Machine-readable Ollama failure code -> HTTP status
ERROR_STATUS = {"unavailable": 503, "model_missing": 503, "timeout": 504, "invalid_response": 502}
HISTORY_LIMIT = 50

ALLOWED_UPLOAD_EXTENSIONS = (".txt", ".md")
# Everything below a space except tab and newline, plus DEL: a text file has none of these.
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MULTIPART_OVERHEAD = 8192


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


# ---------------------------------------------------------------- HTML pages

def home(request):
    return render(request, "cases/home.html", {"directory": DIRECTORY})


@ensure_csrf_cookie
def department_page(request, slug):
    department = get_department(slug)
    if department is None:
        raise Http404("No such department")
    page = PAGES.get(slug)
    context = {"department": department, "directory": DIRECTORY}
    if department["open"] and page:
        max_chars = char_limit(slug)
        context.update(page=page, tones=list(TONES), max_chars=max_chars, upload_kb=settings.MAX_UPLOAD_BYTES // 1000,
                       config={"department": slug, "maxChars": max_chars,
                               "maxUploadBytes": settings.MAX_UPLOAD_BYTES, **page})
    return render(request, "cases/department.html", context)


def files_page(request):
    return render(request, "cases/files.html", {"directory": DIRECTORY})


@ensure_csrf_cookie
def file_page(request, number):
    case = Case.objects.filter(number=number).first()
    if case is None:
        raise Http404("No such case")
    return render(request, "cases/case.html", {"number": case.number, "directory": DIRECTORY})


# ---------------------------------------------------------------- JSON API

def review(case, source=None):
    """Run the AI review for a case. Returns a JsonResponse; the case ends resolved or failed.

    `source` is the text the model reads. It defaults to the stored statement, but private departments pass the
    full text separately because they keep only a preview in the database.
    """
    source = case.statement if source is None else source
    system, schema = DEPARTMENTS[case.department]
    case.transition("under_review")
    try:
        precheck = PRECHECKS.get(case.department)
        result = precheck(source, case.options) if precheck else None
        if result is None:
            raw = ask(system, build_user_prompt(source, case.options, case.department), schema)
            result = VALIDATORS[case.department](raw, source, case.options)
        case.result = result
        case.transition("resolved")
    except (OllamaError, InvalidModelOutput) as e:
        # Technical reason only (never the user's text) so failures are diagnosable.
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


def text_problem(department, text):
    """Error message if the main text is unusable for this department, else None."""
    if not text:
        return "Statement is empty"
    limit = char_limit(department)
    if len(text) > limit:
        what = "Document" if department == "documents" else "Statement"
        return f"{what} is too long (maximum {limit} characters)"
    if department == "documents" and len(text.split()) < MIN_DOCUMENT_WORDS:
        return f"Document is too short to review (minimum {MIN_DOCUMENT_WORDS} words)"
    return None


def preview_of(text):
    flat = " ".join(text.split())
    return flat[:PREVIEW_CHARS] + ("…" if len(flat) > PREVIEW_CHARS else "")


def file_case(department, text, options, source_meta=None):
    """Create a case and review it. Private departments store a preview, never the full text."""
    if department in PRIVATE_DEPARTMENTS:
        meta = {"chars": len(text), "words": len(text.split()), **(source_meta or {})}
        case = Case.objects.create(department=department, statement=preview_of(text), options={**options, **meta})
        return review(case, source=text)
    case = Case.objects.create(department=department, statement=text, options=options)
    return review(case)


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
    problem = text_problem(department, statement)
    if problem:
        return JsonResponse({"error": problem}, status=400)
    options, error = clean_options(department, data.get("options"))
    if error:
        return JsonResponse({"error": error}, status=400)

    return file_case(department, statement, options, {"source": "paste"} if department == "documents" else None)


def read_upload(request):
    """Validate an uploaded .txt/.md file. Returns (text, safe_filename, None) or (None, None, (message, status)).

    The file is only ever held in memory, decoded strictly as UTF-8 text and handed to the model as data. It is
    never written to disk by this code and never executed.
    """
    limit = settings.MAX_UPLOAD_BYTES
    # Refuse oversized bodies before Django parses (and possibly spools) them.
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > limit + MULTIPART_OVERHEAD:
        return None, None, (f"File is too large (maximum {limit // 1000} KB)", 413)

    files = request.FILES.getlist("file")
    if len(files) != 1 or len(request.FILES) != 1:
        return None, None, ("Upload exactly one file in the 'file' field", 400)
    upload = files[0]

    name = os.path.basename((upload.name or "").replace("\\", "/"))
    if os.path.splitext(name)[1].lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        return None, None, ("Only .txt and .md files are accepted (PDF and other formats are not supported yet)", 400)
    safe_name = re.sub(r"[^\w.\- ]", "_", name)[:80]

    if upload.size > limit:
        return None, None, (f"File is too large (maximum {limit // 1000} KB)", 413)
    data = upload.read(limit + 1)
    if len(data) > limit:
        return None, None, (f"File is too large (maximum {limit // 1000} KB)", 413)

    if data.lstrip()[:5] == b"%PDF-":
        return None, None, ("That is a PDF with a renamed extension. PDFs are not supported yet; paste the text "
                            "or upload a .txt or .md file", 400)
    try:
        text = data.decode("utf-8-sig")      # strict: invalid UTF-8 raises instead of being silently repaired
    except UnicodeDecodeError:
        return None, None, ("The file is not valid UTF-8 text", 400)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if CONTROL_CHARS.search(text):
        return None, None, ("The file does not look like plain text (it contains binary or control characters)", 400)
    return text.strip(), safe_name, None


@require_POST          # not csrf_exempt: the page sends the CSRF token with the upload
def upload_request(request):
    text, filename, problem = read_upload(request)
    if problem:
        return JsonResponse({"error": problem[0]}, status=problem[1])
    error = text_problem("documents", text)
    if error:
        return JsonResponse({"error": error.replace("Statement", "File")}, status=400)
    return file_case("documents", text, {}, {"source": "upload", "filename": filename})


@csrf_exempt
@require_POST
def retry_case(request, number):
    """Re-run the review for a failed case (failed -> under_review -> resolved/failed)."""
    case = Case.objects.filter(number=number).first()
    if case is None:
        return JsonResponse({"error": "Case not found"}, status=404)
    if case.status != "failed":
        return JsonResponse({"error": "Only failed cases can be sent back for review"}, status=409)
    if case.department in PRIVATE_DEPARTMENTS:
        return JsonResponse(
            {"error": "This office does not keep your document, so it cannot be reviewed again. "
                      "Please submit it again."}, status=409)
    return review(case)


@require_POST          # not csrf_exempt: this one deletes data
def shred_case(request, number):
    """Permanently delete a case (record, options and result)."""
    case = Case.objects.filter(number=number).first()
    if case is None:
        return JsonResponse({"error": "Case not found"}, status=404)
    case.delete()
    return JsonResponse({"shredded": number})


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
