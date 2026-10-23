"""Make today's docket from the command line, no browser needed:

    python manage.py briefing notes.txt chat-export.md
    cat overnight.txt | python manage.py briefing --out today.md

Reads .txt, .md and text-based .pdf files (or standard input), asks the local model, prints the docket as Markdown.
Like the website, it keeps only a short preview of the text, never the full text.
"""
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ... import exports
from ...pdf_text import PdfProblem, extract_text
from ...views import create_case, execute_review, text_problem


def read_path(path):
    try:
        if path.lower().endswith(".pdf"):
            with open(path, "rb") as fh:
                return extract_text(fh.read(settings.MAX_PDF_BYTES + 1))[0]
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read(settings.MAX_DOCUMENT_CHARS * 4)
    except OSError as e:
        raise CommandError(f"Cannot read {path}: {e.strerror}") from e
    except UnicodeDecodeError as e:
        raise CommandError(f"{path} is not valid UTF-8 text") from e
    except PdfProblem as e:
        raise CommandError(f"{path}: {e}") from e


class Command(BaseCommand):
    help = "Turn notes, messages or a chat export into today's docket (Markdown)."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*", help="Files to read (.txt, .md, .pdf). Omit to read standard input.")
        parser.add_argument("--out", help="Write the Markdown to this file instead of printing it.")

    def handle(self, *args, paths, out=None, **options):
        parts = [f"[{p}]\n{read_path(p)}" if len(paths) > 1 else read_path(p) for p in paths] if paths \
            else [sys.stdin.read()]
        text = "\n\n".join(parts).strip()
        problem = text_problem("briefing", text)
        if problem:
            raise CommandError(problem)
        case, source = create_case("briefing", text, {}, {"source": "command"})
        failure = execute_review(case, source)
        if failure:
            raise CommandError(f"{failure[1]} (case {case.number} is marked failed)")
        markdown = exports.to_markdown(case)
        if out:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(markdown)
            self.stdout.write(f"Docket for case {case.number} written to {out}")
        else:
            self.stdout.write(markdown)
