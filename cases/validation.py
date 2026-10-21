"""Server-side validation of model output. Prompting alone is not trusted."""
import re

from .validators_common import InvalidModelOutput, text as _text  # noqa: F401  (re-exported for callers)

URGENCIES = ("low", "medium", "high", "critical")
VERDICTS = ("do_now", "schedule", "defer", "delegate", "deny")
MAX_QUESTIONS = 3
EXCUSED = ("defer", "deny")
# Used only when the model forgets a permit clause for an excused task.
FALLBACK_PERMIT_CLAUSES = (
    "you mention it again",
    "the sloth officer finishes his current blink",
    "the next full moon, or a tuesday, whichever is less convenient",
    "someone asks you about it in a confident tone",
)
MAX_TASKS = 30
MAX_TEXT = 500
MAX_NOTICE = 1200


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def summary_line(counts):
    """Smug one-liner computed purely from the verdict counts (no model involved)."""
    total = sum(counts.values())
    excused = counts["defer"] + counts["deny"]
    noun = "task" if total == 1 else "tasks"
    if excused == 0:
        return f"Of {total} {noun}, none are officially excused. The Bureau shares your disappointment."
    verb = "is" if excused == 1 else "are"
    return f"Of {total} {noun}, {excused} {verb} officially excused. You're welcome."


def validate_pending(raw, statement):
    """Return {"plan": {...useful...}, "notice": {...humour...}} or raise InvalidModelOutput."""
    if not isinstance(raw, dict):
        raise InvalidModelOutput("not an object")
    raw_tasks = raw.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise InvalidModelOutput("no tasks")

    source = _norm(statement)
    tasks, remarks, clauses = [], [], []
    for i, t in enumerate(raw_tasks[:MAX_TASKS]):
        if not isinstance(t, dict):
            raise InvalidModelOutput(f"task {i} is not an object")
        urgency = _text(t.get("urgency"), "urgency", 20).lower()
        if urgency not in URGENCIES:
            raise InvalidModelOutput(f"bad urgency {urgency!r}")

        verdict = _text(t.get("verdict"), "verdict", 20).lower()
        if verdict not in VERDICTS:
            raise InvalidModelOutput(f"bad verdict {verdict!r}")

        deadline = t.get("deadline")
        deadline = _text(deadline, "deadline", 100, required=False) if isinstance(deadline, str) else ""
        # Deadlines must be the applicant's own words; anything not found in the statement is dropped.
        if not deadline or _norm(deadline) not in source:
            deadline = None

        # Safety guard: never let the model excuse someone from a deadline or a high-stakes task.
        if verdict in ("defer", "deny") and (deadline or urgency in ("high", "critical")):
            verdict = "do_now" if urgency == "critical" else "schedule"

        deps = t.get("depends_on")
        deps = [_text(d, "dependency", 200) for d in deps if isinstance(d, str) and d.strip()] if isinstance(deps, list) else []

        tasks.append({
            "title": _text(t.get("title"), "title", 200),
            "urgency": urgency,
            "verdict": verdict,
            "reason": _text(t.get("reason"), "reason"),
            "deadline": deadline,
            "depends_on": deps,
            "next_step": _text(t.get("next_step"), "next_step"),
            "minimum_effort": _text(t.get("minimum_effort"), "minimum_effort"),
        })
        remarks.append(_text(t.get("excuse"), "excuse", required=False))
        clauses.append(_text(t.get("permit_clause"), "permit_clause", 160, required=False))

    # Dependencies should refer to listed tasks; drop dangling references.
    titles = {_norm(t["title"]) for t in tasks}
    for t in tasks:
        t["depends_on"] = [d for d in t["depends_on"] if _norm(d) in titles]

    questions = raw.get("clarifying_questions")
    questions = [q.strip()[:MAX_TEXT] for q in questions if isinstance(q, str) and q.strip()][:MAX_QUESTIONS] \
        if isinstance(questions, list) else []

    # Never hand back a plan that excuses the applicant from everything.
    if all(t["verdict"] in EXCUSED for t in tasks):
        tasks[0]["verdict"] = "schedule"

    # Permit clauses exist only for excused tasks (verdicts may have been changed by the guards above).
    permits = []
    for i, (t, clause) in enumerate(zip(tasks, clauses)):
        if t["verdict"] in EXCUSED:
            permits.append(clause or FALLBACK_PERMIT_CLAUSES[i % len(FALLBACK_PERMIT_CLAUSES)])
        else:
            permits.append("")

    counts = {v: sum(1 for t in tasks if t["verdict"] == v) for v in VERDICTS}

    action = _text(raw.get("smallest_next_action"), "smallest_next_action")

    return {
        "plan": {
            "tasks": tasks,
            "counts": counts,
            "clarifying_questions": questions,
            "smallest_next_action": action,
        },
        "notice": {
            "official_notice": _text(raw.get("official_notice"), "official_notice", MAX_NOTICE, required=False),
            "task_excuses": remarks,
            "task_permits": permits,
            "summary_line": summary_line(counts),
        },
    }


MAX_BODY = 4000
MAX_ALTERNATIVES = 2
PLACEHOLDER = re.compile(r"\[[^\[\]\n]{1,40}\]")


def _placeholders(*texts):
    seen = []
    for t in texts:
        for m in PLACEHOLDER.findall(t):
            if m not in seen:
                seen.append(m)
    return seen


def validate_correspondence(raw, statement):
    """Return {"draft": {...useful...}, "notice": {...humour...}} or raise InvalidModelOutput."""
    if not isinstance(raw, dict):
        raise InvalidModelOutput("not an object")

    body = _text(raw.get("body"), "body", MAX_BODY)
    subject = _text(raw.get("subject"), "subject", 200, required=False)

    alternatives = []
    alts = raw.get("alternatives")
    if isinstance(alts, list):
        for a in alts:
            if not isinstance(a, dict):
                continue
            ab = a.get("body")
            if isinstance(ab, str) and ab.strip():
                alternatives.append({
                    "label": _text(a.get("label"), "label", 60, required=False) or "Alternative",
                    "body": ab.strip()[:MAX_BODY],
                })
            if len(alternatives) == MAX_ALTERNATIVES:
                break

    questions = raw.get("clarifying_questions")
    questions = [q.strip()[:MAX_TEXT] for q in questions if isinstance(q, str) and q.strip()][:MAX_QUESTIONS] \
        if isinstance(questions, list) else []

    return {
        "draft": {
            "subject": subject,
            "body": body,
            "alternatives": alternatives,
            # computed here, not trusted from the model: details the applicant must still fill in
            "placeholders": _placeholders(subject, body, *[a["body"] for a in alternatives]),
            "clarifying_questions": questions,
        },
        "notice": {
            "official_memo": _text(raw.get("official_memo"), "official_memo", MAX_NOTICE, required=False),
        },
    }
