"""Server-side validation of model output. Prompting alone is not trusted."""
import re

URGENCIES = ("low", "medium", "high", "critical")
VERDICTS = ("do_now", "schedule", "defer", "delegate", "deny")
MAX_QUESTIONS = 3
MAX_TASKS = 30
MAX_TEXT = 500
MAX_NOTICE = 1200


class InvalidModelOutput(Exception):
    pass


def _text(value, field, limit=MAX_TEXT, required=True):
    if not isinstance(value, str):
        if required:
            raise InvalidModelOutput(f"{field} is not a string")
        return ""
    value = value.strip()
    if required and not value:
        raise InvalidModelOutput(f"{field} is empty")
    return value[:limit]


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def validate_pending(raw, statement):
    """Return {"plan": {...useful...}, "notice": {...humour...}} or raise InvalidModelOutput."""
    if not isinstance(raw, dict):
        raise InvalidModelOutput("not an object")
    raw_tasks = raw.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise InvalidModelOutput("no tasks")

    source = _norm(statement)
    tasks, remarks = [], []
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
        remarks.append(_text(t.get("status_remark"), "status_remark", required=False))

    # Dependencies should refer to listed tasks; drop dangling references.
    titles = {_norm(t["title"]) for t in tasks}
    for t in tasks:
        t["depends_on"] = [d for d in t["depends_on"] if _norm(d) in titles]

    questions = raw.get("clarifying_questions")
    questions = [q.strip()[:MAX_TEXT] for q in questions if isinstance(q, str) and q.strip()][:MAX_QUESTIONS] \
        if isinstance(questions, list) else []

    # Never hand back a plan that excuses the applicant from everything.
    if all(t["verdict"] in ("defer", "deny") for t in tasks):
        tasks[0]["verdict"] = "schedule"

    action = _text(raw.get("smallest_next_action"), "smallest_next_action")

    return {
        "plan": {
            "tasks": tasks,
            "clarifying_questions": questions,
            "smallest_next_action": action,
        },
        "notice": {
            "official_notice": _text(raw.get("official_notice"), "official_notice", MAX_NOTICE, required=False),
            "task_remarks": remarks,
        },
    }
