"""Plain-file exports of a finished case: Markdown for every office, plus an iCalendar to-do list for Pending plans.

Only data already stored on the case is used (never the model, never the original text of private offices).
"""
from datetime import datetime, timezone

FOOTER = ("_Exported from the Department of Unnecessary Affairs. AI-generated: check it before relying on it. "
          "Valid in no jurisdiction._")
VERDICT_LABELS = {"do_now": "do now", "schedule": "schedule", "delegate": "delegate", "defer": "deferred",
                  "deny": "denied"}
EXCUSED = ("defer", "deny")


class NotExportable(Exception):
    pass


def _bullets(items):
    return [f"- {x}" for x in items]


def _pending(case):
    plan = case.result["plan"]
    done = set(case.done_tasks or [])
    lines = [f"# Action plan: case {case.number}", ""]
    lines += [f"**Start here (under 5 minutes):** {plan['smallest_next_action']}", ""]

    def task(i, t):
        box = "x" if i in done else " "
        out = [f"- [{box}] **{t['title']}** ({t['urgency']}; {VERDICT_LABELS.get(t['verdict'], t['verdict'])})",
               f"  - Next step: {t['next_step']}"]
        if t.get("deadline"):
            out.append(f"  - Deadline (as you stated): {t['deadline']}")
        out += [f"  - Minimum effort to be done: {t['minimum_effort']}", f"  - Why it ranks here: {t['reason']}"]
        if t.get("depends_on"):
            out.append(f"  - Do these first: {'; '.join(t['depends_on'])}")
        return out

    active = [(i, t) for i, t in enumerate(plan["tasks"]) if t["verdict"] not in EXCUSED]
    excused = [(i, t) for i, t in enumerate(plan["tasks"]) if t["verdict"] in EXCUSED]
    lines += ["## To do", ""]
    for i, t in active:
        lines += task(i, t)
    if excused:
        lines += ["", "## Officially excused (you may skip these)", ""]
        for i, t in excused:
            lines += task(i, t)
    if plan.get("clarifying_questions"):
        lines += ["", "## Questions that would sharpen this plan", ""] + _bullets(plan["clarifying_questions"])
    return lines


def _correspondence(case):
    d = case.result["draft"]
    lines = [f"# Message draft: case {case.number}", ""]
    if (case.options or {}).get("tone"):
        lines += [f"Tone: {case.options['tone']}", ""]
    if d.get("subject"):
        lines += [f"**Subject:** {d['subject']}", ""]
    lines += [d["body"], ""]
    if d.get("placeholders"):
        lines += ["**Fill in before sending:** " + " ".join(d["placeholders"]), ""]
    iq = d.get("incoming_questions") or []
    if iq:
        lines += ["## Questions in the message you received", ""]
        for q in iq:
            mark = "answered in the draft" if q["answered"] else "STILL NEEDS YOUR INPUT"
            lines.append(f"- {q['question']} ({mark}). Their words: \"{q['quote']}\"")
        lines.append("")
    for a in d.get("alternatives") or []:
        lines += [f"## Alternative: {a['label']}", "", a["body"], ""]
    if d.get("clarifying_questions"):
        lines += ["## Questions that would improve this message", ""] + _bullets(d["clarifying_questions"])
    return lines


def _documents(case):
    r = case.result["review"]
    lines = [f"# Document review: case {case.number}", "", "## In plain language", "", r["summary"], ""]
    if r.get("key_points"):
        lines += ["## Key points", ""] + _bullets(r["key_points"]) + [""]
    if r.get("deadlines"):
        lines += ["## Deadlines stated in the document", ""]
        lines += [f"- **{d['when']}**: {d['what']}  \n  Source: \"{d['source_quote']}\"" for d in r["deadlines"]] + [""]
    if r.get("action_items"):
        lines += ["## What you are asked to do", ""]
        lines += [f"- [ ] {a['item']}  \n  Source: \"{a['source_quote']}\"" for a in r["action_items"]] + [""]
    if r.get("requirements"):
        lines += ["## Requirements and conditions", ""]
        lines += [f"- {a['item']}  \n  Source: \"{a['source_quote']}\"" for a in r["requirements"]] + [""]
    if r.get("unclear_or_missing"):
        lines += ["## Unclear, ambiguous or missing", ""] + _bullets(r["unclear_or_missing"])
    return lines


def _tribunal(case):
    r = case.result["ruling"]
    if r.get("crisis"):
        raise NotExportable("This case is not exportable.")
    lines = [f"# Ruling: case {case.number}", "", f"**Recommended:** {r['recommended_option']}", "", r["reasoning"], ""]
    for o in r["options"]:
        lines += [f"## {o['name']}", "", "Pros:"] + _bullets(o["pros"]) + ["", "Cons:"] + _bullets(o["cons"]) + [""]
    return lines


def _briefing(case):
    d = case.result["docket"]
    lines = [f"# Today's docket: case {case.number}", ""]
    if d.get("one_liner"):
        lines += [d["one_liner"], ""]
    lines += ["## Today", ""]
    for t in d["top"]:
        lines += [f"- [ ] **{t['title']}**" + (f" (deadline: {t['deadline']})" if t.get("deadline") else ""),
                  f"  - Why: {t['why']}", f"  - Next step: {t['next_step']}", f"  - Your words: \"{t['quote']}\""]
    if d.get("heads_up"):
        lines += ["", "## Coming up", ""]
        lines += [f"- **{h['title']}**" + (f" ({h['when']})" if h.get("when") else "") + f"  \n  Your words: \"{h['quote']}\""
                  for h in d["heads_up"]]
    if d.get("can_wait"):
        lines += ["", "## Can wait", ""]
        lines += [f"- **{c['title']}**: {c['why']}" for c in d["can_wait"]]
    if d.get("clarifying_questions"):
        lines += ["", "## Questions that would sharpen this docket", ""] + _bullets(d["clarifying_questions"])
    return lines


_RENDERERS = {"pending": _pending, "correspondence": _correspondence, "documents": _documents,
              "tribunal": _tribunal, "briefing": _briefing}
_RESULT_KEYS = {"pending": "plan", "correspondence": "draft", "documents": "review", "tribunal": "ruling",
                "briefing": "docket"}


def _check(case):
    if case.status != "resolved" or not isinstance(case.result, dict) or \
            _RESULT_KEYS.get(case.department) not in case.result:
        raise NotExportable("Only finished cases can be exported.")


def to_markdown(case):
    _check(case)
    return "\n".join(_RENDERERS[case.department](case) + ["", "---", FOOTER, ""])


# ---------------------------------------------------------------- iCalendar (to-do list)

def _ics_escape(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n"))


def _fold(line):
    """RFC 5545: lines are at most 75 octets; continuation lines start with one space. Never split a UTF-8 character."""
    out, current, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 75:
            out.append(current)
            current, size = " " + ch, 1 + n
        else:
            current += ch
            size += n
    out.append(current)
    return "\r\n".join(out)


def to_ics(case, now=None):
    """A VTODO per task (denied tasks left out). Deadlines are the applicant's own words ("Friday"), which cannot be
    turned into dates without guessing, so they go in the description and no due date is set."""
    _check(case)
    if case.department != "pending":
        raise NotExportable("Only action plans can be exported as a to-do list.")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    done = set(case.done_tasks or [])
    priority = {"critical": 1, "high": 3, "medium": 5, "low": 9}
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Department of Unnecessary Affairs//EN", "CALSCALE:GREGORIAN"]
    for i, t in enumerate(case.result["plan"]["tasks"]):
        if t["verdict"] == "deny":
            continue
        desc = [f"Next step: {t['next_step']}", f"Minimum effort: {t['minimum_effort']}"]
        if t.get("deadline"):
            desc.insert(0, f"Deadline (as you stated): {t['deadline']}")
        lines += ["BEGIN:VTODO", f"UID:{case.number}-{i + 1}@unnecessary-affairs", f"DTSTAMP:{stamp}",
                  f"SUMMARY:{_ics_escape(t['title'])}", f"DESCRIPTION:{_ics_escape(chr(10).join(desc))}",
                  f"PRIORITY:{priority[t['urgency']]}",
                  "STATUS:COMPLETED" if i in done else "STATUS:NEEDS-ACTION", "END:VTODO"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
