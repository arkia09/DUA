"""Regenerate the demo data from the real model.

    python manage.py record_demo                 # all five offices
    python manage.py record_demo pending tribunal --tries 5

Runs every example button of each office through Ollama, keeps only output that passes the normal validators with
nothing dropped, and rewrites cases/demo_data/<office>.json. An office's file is replaced only if all of its examples
succeed. Needs Ollama running, and DEMO_MODE off.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ... import demo
from ...departments import DEPARTMENTS, VALIDATORS, build_user_prompt, clean_options
from ...ollama import OllamaError, ask
from ...validators_common import InvalidModelOutput


def nothing_dropped(result):
    """True if the validator removed no claims from the model's answer."""
    body = next(v for k, v in result.items() if k != "notice")
    return all(not v for k, v in body.items() if k.startswith("dropped"))


class Command(BaseCommand):
    help = "Regenerate cases/demo_data/ by running every example input through the local model."

    def add_arguments(self, parser):
        parser.add_argument("offices", nargs="*", help="Offices to record (default: all).")
        parser.add_argument("--tries", type=int, default=3, help="Attempts per example before giving up (default 3).")

    def handle(self, *args, offices, tries, **options):
        if settings.DEMO_MODE:
            raise CommandError("Turn DEMO_MODE off first: recording needs the real model.")
        offices = offices or list(demo.DEPARTMENTS)
        unknown = [o for o in offices if o not in demo.DEPARTMENTS]
        if unknown:
            raise CommandError(f"Unknown office: {', '.join(unknown)}. Choose from {', '.join(demo.DEPARTMENTS)}.")

        for department in offices:
            entries = []
            for text, opts in demo.example_inputs(department):
                options_clean, error = clean_options(department, opts)
                if error:
                    raise CommandError(f"{department}: {error}")
                entries.append(self.record_one(department, text, opts, options_clean, tries))
            path = demo.DATA_DIR / f"{department}.json"
            path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            self.stdout.write(f"{department}: wrote {len(entries)} samples to {path.name}")
        demo.samples.cache_clear()

    def record_one(self, department, text, opts, options, tries):
        system, schema = DEPARTMENTS[department]
        prompt = build_user_prompt(text, options, department)
        label = f"{department}: {text[:40]!r}"
        for attempt in range(1, tries + 1):
            try:
                raw = ask(system, prompt, schema)
                result = VALIDATORS[department](raw, text, options)
                if not nothing_dropped(result):
                    raise InvalidModelOutput("some claims were dropped")
            except (OllamaError, InvalidModelOutput) as e:
                self.stderr.write(f"{label} attempt {attempt}/{tries} failed: {e}")
                continue
            entry = {"text": text}
            entry.update({k: v for k, v in opts.items() if v})
            entry["raw"] = raw
            return entry
        raise CommandError(f"{label}: no usable answer after {tries} tries. Nothing was written for {department}.")
