"""Demo mode: answer the built-in sample inputs without a model.

Each file in demo_data/ holds pre-written model output for one office, stored exactly as a model would return it
(the raw JSON that ask() produces). In demo mode that output goes through the same validators as a live answer, so
quote checks, verdict guards and computed statistics all still run.

A sample is matched on the input text (case, spacing and punctuation are ignored), plus the pasted message for
Correspondence and the preferences for the Tribunal. Tone is not part of the match: the demo has one draft per
sample. Anything else raises DemoMiss.

The files can be regenerated with a real model: `python manage.py record_demo`.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

from .ollama import OllamaError
from .validators_common import words

DATA_DIR = Path(__file__).resolve().parent / "demo_data"
DEPARTMENTS = ("briefing", "pending", "correspondence", "documents", "tribunal")


class DemoMiss(OllamaError):
    code = "demo_sample_only"
    user_message = ("This is a demo with no AI model behind it, so it only answers the sample inputs. "
                    "Click one of the \"Try\" buttons to load one.")


def key(department, text, options=None):
    """Matching key for an input. Only the fields that change the answer are included."""
    options = options or {}
    extra = ""
    if department == "correspondence":
        extra = words(options.get("incoming") or "")
    elif department == "tribunal":
        extra = words(options.get("preferences") or "")
    return department, words(text), extra


@lru_cache(maxsize=1)
def samples():
    """{key: raw model output} for every sample on disk."""
    found = {}
    for department in DEPARTMENTS:
        path = DATA_DIR / f"{department}.json"
        if not path.exists():
            continue
        for entry in json.loads(path.read_text(encoding="utf-8")):
            options = {"incoming": entry.get("incoming", ""), "preferences": entry.get("preferences", "")}
            found[key(department, entry["text"], options)] = entry["raw"]
    return found


def has_sample(department, text, options=None):
    return key(department, text, options) in samples()


def answer(department, text, options=None):
    """The pre-written model output for this input, or DemoMiss."""
    raw = samples().get(key(department, text, options))
    if raw is None:
        raise DemoMiss("no sample for this input")
    return copy.deepcopy(raw)


def example_inputs(department):
    """(text, options) for every example button of an office, in page order. Used to record and to check the data."""
    from .departments import PAGES
    out = []
    for ex in PAGES[department].get("examples", []):
        if isinstance(ex, str):
            out.append((ex, {}))
        else:
            options = {k: v for k, v in ex.items() if k in ("incoming", "preferences")}
            out.append((ex["text"], options))
    return out
