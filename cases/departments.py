from django.conf import settings

from .offices import briefing, documents, tribunal
from .offices.correspondence import (
    CORRESPONDENCE_SCHEMA, CORRESPONDENCE_SYSTEM, DEFAULT_TONE, MAX_INCOMING_CHARS, TONES,
)
from .offices.pending import PENDING_SCHEMA, PENDING_SYSTEM
from .validation import validate_correspondence, validate_pending
from .validators_common import neutralize_tag

DEPARTMENTS = {
    "pending": (PENDING_SYSTEM, PENDING_SCHEMA),
    "correspondence": (CORRESPONDENCE_SYSTEM, CORRESPONDENCE_SCHEMA),
    "documents": (documents.DOCUMENTS_SYSTEM, documents.DOCUMENTS_SCHEMA),
    "tribunal": (tribunal.TRIBUNAL_SYSTEM, tribunal.TRIBUNAL_SCHEMA),
    "briefing": (briefing.BRIEFING_SYSTEM, briefing.BRIEFING_SCHEMA),
}

# Per-department validators: (raw model dict, source text, options) -> normalized result.
# Raise validation.InvalidModelOutput on unusable output.
VALIDATORS = {
    "pending": lambda raw, source, options: validate_pending(raw, source),
    "correspondence": validate_correspondence,
    "documents": documents.validate,
    "tribunal": tribunal.validate,
    "briefing": briefing.validate,
}

# Optional checks that run BEFORE the model. Return a finished result to skip the model, or None to carry on.
PRECHECKS = {
    "tribunal": tribunal.precheck,
}

# Departments that deliberately do not keep the applicant's full text (see views.file_case).
PRIVATE_DEPARTMENTS = {"documents", "briefing"}
# Departments whose main text may be as long as a document (notes and chat exports are long too).
LONG_TEXT_DEPARTMENTS = {"documents", "briefing"}
# Departments that accept an uploaded file.
UPLOAD_DEPARTMENTS = {"documents", "briefing"}
PREVIEW_CHARS = 200


def char_limit(department):
    """Maximum characters of the main text for a department."""
    return settings.MAX_DOCUMENT_CHARS if department in LONG_TEXT_DEPARTMENTS else settings.MAX_STATEMENT_CHARS


def clean_options(department, options):
    """Validate user-supplied options for a department. Returns (clean_options, error_or_None)."""
    if options is None:
        options = {}
    if not isinstance(options, dict):
        return {}, "Options must be an object"
    if department == "correspondence":
        tone = options.get("tone", DEFAULT_TONE)
        if tone not in TONES:
            return {}, "Unknown tone"
        incoming = options.get("incoming", "")
        if incoming is None:
            incoming = ""
        if not isinstance(incoming, str):
            return {}, "The message you received must be text"
        incoming = incoming.strip()
        if len(incoming) > MAX_INCOMING_CHARS:
            return {}, f"The message you received is too long (maximum {MAX_INCOMING_CHARS} characters)"
        clean = {"tone": tone}
        if incoming:
            clean["incoming"] = incoming
        return clean, None
    if department == "tribunal":
        preferences = options.get("preferences", "")
        if preferences is None:
            preferences = ""
        if not isinstance(preferences, str):
            return {}, "Preferences must be text"
        preferences = preferences.strip()
        if len(preferences) > tribunal.MAX_PREFERENCES_CHARS:
            return {}, f"Preferences are too long (maximum {tribunal.MAX_PREFERENCES_CHARS} characters)"
        return {"preferences": preferences}, None
    return {}, None


def build_user_prompt(statement: str, options=None, department="pending") -> str:
    """Wrap every piece of user text in tags (the system prompts call them DATA). A closing tag typed inside the
    text is defused so that the text cannot step outside its wrapper."""
    options = options or {}
    if department == "documents":
        return f"<document>\n{neutralize_tag(statement, 'document')}\n</document>"
    if department == "briefing":
        return f"<material>\n{neutralize_tag(statement, 'material')}\n</material>"
    if department == "tribunal":
        prefs = neutralize_tag(options.get("preferences", ""), "preferences")
        return (f"<dilemma>\n{neutralize_tag(statement, 'dilemma')}\n</dilemma>\n"
                f"<preferences>\n{prefs}\n</preferences>")
    prompt = f"<statement>\n{neutralize_tag(statement, 'statement')}\n</statement>"
    if department == "correspondence" and options.get("incoming"):
        prompt += f"\n<incoming_message>\n{neutralize_tag(options['incoming'], 'incoming_message')}\n</incoming_message>"
    tone = options.get("tone")
    if tone in TONES:
        prompt += f"\n<tone>{tone}: {TONES[tone]}</tone>"
    return prompt


# Deterministic jokes live here, not in the model
RECEIVED = "Your request has been received. We regret to inform you that we were not expecting it."
MODEL_FAILED = "Our AI officer is currently attending a mandatory meeting about meeting efficiency."


# ---- Site directory and per-page copy (single source of truth for the home page and department pages) ----
DIRECTORY = [
    {
        "slug": "briefing", "code": "MD", "name": "Morning Docket Office", "open": True,
        "purpose": "Reads your overnight pile of notes, to-dos, messages or chat export, so that you start the day "
                   "knowing the few things that actually matter.",
        "gives": "Today's top three (each with a quote you can check), what can safely wait, what is coming up, and a "
                 "Notice of Daily Obligations nobody asked for.",
        "cta": "Collect today's docket",
    },
    {
        "slug": "pending", "code": "BA", "name": "Bureau of Pending Affairs", "open": True,
        "purpose": "Turns your panicked brain dump into a ranked plan, and officially excuses the tasks that "
                   "do not deserve your time.",
        "gives": "Priorities, next steps, the minimum effort to be done, and permits to ignore the rest.",
        "cta": "Enter the Bureau",
    },
    {
        "slug": "correspondence", "code": "OC", "name": "Office of Correspondence Avoidance", "open": True,
        "purpose": "Drafts the email, follow-up or polite refusal you have been avoiding, in the tone of your choice. "
                   "Paste the message you received and it drafts the reply, too.",
        "gives": "A ready-to-send message, two alternative versions, a check of which questions in the message you "
                 "received are still unanswered, and an internal memorandum nobody asked for.",
        "cta": "Visit the Office",
    },
    {
        "slug": "documents", "code": "CD", "name": "Commission for Unnecessarily Complicated Documents", "open": True,
        "purpose": "Reads the long, frightening document so that you do not have to. Paste it in, or hand over a "
                   ".txt, .md or text-based .pdf file.",
        "gives": "A plain-language summary, the deadlines and requirements the document actually states (each with "
                 "a quote you can check), what is unclear, and an official complexity rating.",
        "cta": "Submit a document",
        "closed_note": "Closed for renovation. Staff are reading the terms and conditions of their own closure.",
    },
    {
        "slug": "tribunal", "code": "TM", "name": "Tribunal for Minor Inconveniences", "open": True,
        "purpose": "Decides small everyday dilemmas on your behalf, with a verdict you are not permitted to argue with.",
        "gives": "A comparison of options, a reasoned ruling based on what you care about, and a fictional appeals "
                 "procedure.",
        "cta": "Approach the bench",
        "closed_note": "Adjourned until further notice. The judge is deliberating over lunch.",
    },
]

PAGES = {
    "briefing": {
        "prompt": "Paste the pile: notes, to-do lists, messages, a chat export, anything from overnight:",
        "placeholder": "e.g. Dentist Tuesday 3pm. Priya asked if I can review her slides by Thursday. Landlord says the "
                       "rent is due on the 1st. Should probably clear my inbox. Mum's birthday on Saturday, no gift yet.",
        "button": "Collect today's docket",
        "tone": False,
        "upload": True,
        "privacy": "Your notes are read in memory and are not saved. Only a short preview and the docket (including the "
                   "short quotes that back each item) are kept, and you can shred the case at any time.",
        "examples": [
            "Dentist Tuesday 3pm. Priya asked if I can review her slides by Thursday. Landlord says the rent is due on "
            "the 1st. Should probably clear my inbox at some point. Mum's birthday is on Saturday and I have no gift. "
            "Maybe repaint the shelf. Gym membership renewal email, no idea when it expires.",
            "Standup moved to 10am. Need to send the invoice to Daniel before end of day Friday. Someone in the group "
            "chat wants to plan a trip in March, nothing decided. Water bill arrived, due in two weeks. Learn to "
            "juggle. Call the bank about the card they blocked, it is declined everywhere.",
        ],
    },
    "pending": {
        "prompt": "Describe everything you have yet to do, in any order or state of panic:",
        "placeholder": "e.g. 3 assignments due Friday, need to reply to an email, and my room needs cleaning before my parents visit on Sunday",
        "button": "File declaration",
        "tone": False,
        "examples": [
            "Assignment due Friday, reply to Priya's email, reorganise my bookmarks, water the plant, maybe learn guitar someday",
            "Pay the electricity bill by the 25th, book a dentist appointment, clear 400 unread newsletters, call grandma",
        ],
    },
    "correspondence": {
        "prompt": "Who must you write to, and what do you need to say? (Rough notes are fine.)",
        "placeholder": "e.g. Tell my landlord the heater has been broken for two weeks and I would like it fixed this week",
        "button": "Request a memorandum",
        "tone": True,
        "incoming": {
            "label": "Replying to something? Paste the message you received (optional):",
            "placeholder": "e.g. Hi, can you come to the planning meeting on Thursday? Also, did you get the budget file?",
            "max": MAX_INCOMING_CHARS,
            "notes_label": "Your notes on how to reply (optional when you have pasted a message):",
        },
        "examples": [
            "Politely tell my manager I cannot take on the extra project this month because I am already at capacity",
            "Follow up with a recruiter who has not replied in a week, without sounding desperate",
            {"text": "Yes to Thursday but I can only stay an hour. I have not seen the budget file.",
             "incoming": "Hi, can you come to the planning meeting on Thursday at 2? Also, did you get the budget "
                         "file I sent last week? And who is covering the front desk while we are in there?"},
        ],
    },
    "documents": {
        "prompt": "Paste the document you would rather not read:",
        "placeholder": "Paste the terms, letter, policy or contract text here, or upload a .txt, .md or .pdf file.",
        "button": "Submit for review",
        "tone": False,
        "upload": True,
        "privacy": "Your full document is read in memory and is not saved. Only a short preview and the results "
                   "(including the short quotes that back each claim) are kept, and you can shred the case at any time.",
        "examples": [
            "Notice of Fee Adjustment. Pursuant to Section 4(b) of the Residents' Agreement, the monthly service fee shall "
            "increase by 8% with effect from 1 March. Residents who wish to contest the adjustment must submit a written "
            "objection to the Estates Office no later than 14 February. Objections received after that date will not be "
            "considered. Payment of the adjusted fee is required regardless of any pending objection. The Estates Office "
            "may waive the adjustment in exceptional circumstances, as determined at its sole discretion.",
            "By continuing to use the Service you agree to these Terms. We may change the Terms at any time by posting "
            "an update, and your continued use means you accept the changes. You must be at least 16 years old to "
            "create an account. You must keep your password confidential. We may suspend your account if we believe, "
            "acting reasonably, that you have breached these Terms. Refunds for annual plans are available within 30 "
            "days of purchase. Unused credits expire after a period determined by us.",
        ],
    },
    "tribunal": {
        "prompt": "What is the dilemma? (Small ones only. Pizza, not problems.)",
        "placeholder": "e.g. Should I order pizza or sushi tonight?",
        "button": "Request a ruling",
        "tone": False,
        "preferences": {
            "label": "What matters to you here? (Optional, but the Tribunal cannot read minds.)",
            "placeholder": "e.g. I want something cheap and quick, and I do not want to wash dishes",
            "max": tribunal.MAX_PREFERENCES_CHARS,
        },
        "examples": [
            {"text": "Should I order pizza or sushi tonight?",
             "preferences": "cheap, quick, and I do not want to wash dishes"},
            {"text": "Do I reply to this group chat now or tomorrow morning?",
             "preferences": "I am tired and the topic is not urgent"},
            {"text": "Should I take the bus or walk to the library?",
             "preferences": ""},
        ],
    },
}


def get_department(slug):
    return next((d for d in DIRECTORY if d["slug"] == slug), None)
