import json
import logging
import os
import re

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import exports
from .departments import (
    DEPARTMENTS, DIRECTORY, MODEL_FAILED, PAGES, PRECHECKS, PREVIEW_CHARS, PRIVATE_DEPARTMENTS, RECEIVED, TONES,
    UPLOAD_DEPARTMENTS, VALIDATORS, build_user_prompt, char_limit, clean_options, get_department,
)
from .models import Case
from .offices.documents import MIN_DOCUMENT_WORDS
from .ollama import OllamaError, ask
from .pdf_text import PdfProblem, extract_text
from .validation import InvalidModelOutput

logger = logging.getLogger(__name__)

# Machine-readable Ollama failure code -> HTTP status
ERROR_STATUS = {"unavailable": 503, "model_missing": 503, "timeout": 504, "invalid_response": 502}
HISTORY_LIMIT = 50
REPLY_WITHOUT_NOTES = "(No notes given. Write a suitable, honest reply to the incoming message.)"

ALLOWED_UPLOAD_EXTENSIONS = (".txt", ".md", ".pdf")
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
        "done_tasks": case.done_tasks or [],
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
        return not_found(request)
    page = PAGES.get(slug)
    context = {"department": department, "directory": DIRECTORY}
    if department["open"] and page:
        max_chars = char_limit(slug)
        context.update(page=page, tones=list(TONES), max_chars=max_chars, upload_kb=settings.MAX_UPLOAD_BYTES // 1000,
                       pdf_mb=settings.MAX_PDF_BYTES // 1_000_000,
                       config={"department": slug, "maxChars": max_chars,
                               "maxUploadBytes": settings.MAX_UPLOAD_BYTES,
                               "maxPdfBytes": settings.MAX_PDF_BYTES, **page})
    return render(request, "cases/department.html", context)


def not_found(request, exception=None):
    """Themed 404 page. Also used directly by the page views so it shows in DEBUG mode too."""
    return render(request, "cases/404.html", {"directory": DIRECTORY}, status=404)


def break_room(request):
    return render(request, "cases/break_room.html", {"directory": DIRECTORY})


def complaints(request):
    return render(request, "cases/complaints.html", {"directory": DIRECTORY})


ROBOTS = """User-agent: *
Disallow: /admin/
Disallow: /api/
# The following room is not a security measure. It is a courtesy to a tired colleague.
Disallow: /break-room/
# Nobody is hiding in the break room. He is merely resting his eyes.
"""


def robots_txt(request):
    return HttpResponse(ROBOTS, content_type="text/plain; charset=utf-8")


def files_page(request):
    return render(request, "cases/files.html", {"directory": DIRECTORY})


@ensure_csrf_cookie
def file_page(request, number):
    case = Case.objects.filter(number=number).first()
    if case is None:
        return not_found(request)
    return render(request, "cases/case.html", {"number": case.number, "directory": DIRECTORY})


# ---------------------------------------------------------------- JSON API

def execute_review(case, source=None):
    """Run the AI review for a case. The case ends resolved or failed.

    Returns None on success, or (error_code, user_message) on failure. `source` is the text the model reads. It
    defaults to the stored statement, but private departments pass the full text separately because they keep only a
    preview in the database.
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
            return e.code, e.user_message
        return "invalid_response", "The AI officer returned an unusable response. Please try again."
    return None


def review(case, source=None):
    """execute_review() as an HTTP response: 201 with the case, or an error status with the failed case."""
    failure = execute_review(case, source)
    if failure:
        code, message = failure
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
        what = {"documents": "Document", "briefing": "Notes"}.get(department, "Statement")
        return f"{what} is too long (maximum {limit} characters)"
    if department == "documents" and len(text.split()) < MIN_DOCUMENT_WORDS:
        return f"Document is too short to review (minimum {MIN_DOCUMENT_WORDS} words)"
    return None


def preview_of(text):
    flat = " ".join(text.split())
    return flat[:PREVIEW_CHARS] + ("…" if len(flat) > PREVIEW_CHARS else "")


def create_case(department, text, options, source_meta=None):
    """Create a case. Returns (case, source): private departments store a preview, never the full text."""
    if department in PRIVATE_DEPARTMENTS:
        meta = {"chars": len(text), "words": len(text.split()), **(source_meta or {})}
        case = Case.objects.create(department=department, statement=preview_of(text), options={**options, **meta})
        return case, text
    return Case.objects.create(department=department, statement=text, options=options), None


def file_case(department, text, options, source_meta=None):
    """Create a case and review it."""
    case, source = create_case(department, text, options, source_meta)
    return review(case, source=source)


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
    options, error = clean_options(department, data.get("options"))
    if error:
        return JsonResponse({"error": error}, status=400)
    if department == "correspondence" and options.get("incoming") and not statement:
        statement = REPLY_WITHOUT_NOTES     # replying with no notes: the model drafts a sensible reply
    problem = text_problem(department, statement)
    if problem:
        return JsonResponse({"error": problem}, status=400)

    return file_case(department, statement, options,
                     {"source": "paste"} if department in PRIVATE_DEPARTMENTS else None)


def size_label(n):
    return f"{n // 1_000_000} MB" if n >= 1_000_000 else f"{max(n // 1000, 1)} KB"


def upload_too_large(request):
    """Refuse oversized bodies from the declared length alone, before Django parses (and possibly spools) them."""
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    limit = max(settings.MAX_UPLOAD_BYTES, settings.MAX_PDF_BYTES) + MULTIPART_OVERHEAD
    return declared > limit


def read_upload(request):
    """Validate an uploaded .txt/.md/.pdf file.

    Returns (text, safe_filename, pages, None) or (None, None, None, (message, status)). `pages` is None for text files.
    The file is only ever held in memory. Text files are decoded strictly as UTF-8; PDFs go through pypdf, which
    extracts text only (nothing in a PDF is executed or rendered). Nothing is written to disk.
    """
    text_limit, pdf_limit = settings.MAX_UPLOAD_BYTES, settings.MAX_PDF_BYTES
    files = request.FILES.getlist("file")
    if len(files) != 1 or len(request.FILES) != 1:
        return None, None, None, ("Upload exactly one file in the 'file' field", 400)
    upload = files[0]

    name = os.path.basename((upload.name or "").replace("\\", "/"))
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return None, None, None, ("Only .txt, .md and .pdf files are accepted", 400)
    safe_name = re.sub(r"[^\w.\- ]", "_", name)[:80]

    limit = pdf_limit if ext == ".pdf" else text_limit
    too_large = (f"File is too large (maximum {size_label(pdf_limit)} for a PDF)" if ext == ".pdf"
                 else f"File is too large (maximum {text_limit // 1000} KB)", 413)
    if upload.size > limit:
        return None, None, None, too_large
    data = upload.read(limit + 1)
    if len(data) > limit:
        return None, None, None, too_large

    is_pdf = data.lstrip()[:5] == b"%PDF-"
    if ext == ".pdf":
        if not is_pdf:
            return None, None, None, ("That file is named .pdf but is not a PDF", 400)
        try:
            text, pages = extract_text(data)
        except PdfProblem as e:
            return None, None, None, (str(e), 400)
        return text, safe_name, pages, None

    if is_pdf:
        return None, None, None, ("That is a PDF with the wrong extension. Rename it to .pdf and upload it again", 400)
    try:
        text = data.decode("utf-8-sig")      # strict: invalid UTF-8 raises instead of being silently repaired
    except UnicodeDecodeError:
        return None, None, None, ("The file is not valid UTF-8 text", 400)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if CONTROL_CHARS.search(text):
        return None, None, None, ("The file does not look like plain text (it contains binary or control characters)", 400)
    return text.strip(), safe_name, None, None


@require_POST
def upload_request(request):
    if upload_too_large(request):      # must come first: reading request.POST would parse the body
        return JsonResponse({"error": f"File is too large (maximum {size_label(settings.MAX_PDF_BYTES)} for a PDF)"},
                            status=413)
    department = request.POST.get("department", "documents")
    if department not in UPLOAD_DEPARTMENTS:
        return JsonResponse({"error": "This office does not accept uploads"}, status=400)
    text, filename, pages, problem = read_upload(request)
    if problem:
        return JsonResponse({"error": problem[0]}, status=problem[1])
    error = text_problem(department, text)
    if error:
        return JsonResponse({"error": error.replace("Statement", "File")}, status=400)
    meta = {"source": "upload", "filename": filename}
    if pages:
        meta["pages"] = pages
    return file_case(department, text, {}, meta)


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


@require_POST
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


# ---------------------------------------------------------------- plan progress, carry-over, export

def _pending_plan_case(number):
    """(case, None) for a finished Pending plan, else (None, JsonResponse error)."""
    case = Case.objects.filter(number=number).first()
    if case is None:
        return None, JsonResponse({"error": "Case not found"}, status=404)
    if case.department != "pending" or case.status != "resolved" or not isinstance(case.result, dict) \
            or "plan" not in case.result:
        return None, JsonResponse({"error": "Only finished action plans have tasks to tick off"}, status=409)
    return case, None


@require_POST
def set_task_done(request, number, index):
    """Tick (or untick) one task of a Pending plan. Body: {"done": true|false}."""
    case, error = _pending_plan_case(number)
    if error:
        return error
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict) or not isinstance(data.get("done"), bool):
        return JsonResponse({"error": "Send {\"done\": true} or {\"done\": false}"}, status=400)
    if not 0 <= index < len(case.result["plan"]["tasks"]):
        return JsonResponse({"error": "No such task"}, status=404)
    done = set(case.done_tasks or [])
    done.add(index) if data["done"] else done.discard(index)
    case.done_tasks = sorted(done)
    case.save(update_fields=["done_tasks"])
    return JsonResponse({"case": serialize(case)})


def carry_over_statement(case):
    """A fresh brain dump built from the tasks still open, most important first. The applicant's own deadline words
    are kept so that the next plan can quote them. Denied tasks are left behind on purpose."""
    done = set(case.done_tasks or [])
    lines, size, limit = [], 0, settings.MAX_STATEMENT_CHARS
    for i, t in enumerate(case.result["plan"]["tasks"]):
        if i in done or t["verdict"] == "deny":
            continue
        line = "- " + t["title"] + (f" (deadline: {t['deadline']})" if t.get("deadline") else "")
        if size + len(line) + 1 > limit:
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines)


@require_POST
def carry_over(request, number):
    """File a new Pending case from the tasks that are not done yet."""
    case, error = _pending_plan_case(number)
    if error:
        return error
    statement = carry_over_statement(case)
    if not statement:
        return JsonResponse({"error": "Nothing to carry over: every task is done or denied"}, status=400)
    return file_case("pending", statement, {"carried_from": case.number})


EXPORT_TYPES = {"md": ("text/markdown; charset=utf-8", exports.to_markdown),
                "ics": ("text/calendar; charset=utf-8", exports.to_ics)}


@require_GET
def export_case(request, number, fmt):
    """Download a finished case as a Markdown file (every office) or an iCalendar to-do list (Pending plans)."""
    case = Case.objects.filter(number=number).first()
    if case is None:
        return JsonResponse({"error": "Case not found"}, status=404)
    if fmt not in EXPORT_TYPES:
        return JsonResponse({"error": "Unknown export format"}, status=404)
    content_type, build = EXPORT_TYPES[fmt]
    try:
        body = build(case)
    except exports.NotExportable as e:
        return JsonResponse({"error": str(e)}, status=409)
    response = HttpResponse(body, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{case.number}.{fmt}"'
    return response
