# Department of Unnecessary Affairs

A Django web app where you hand a fictional, deadpan government office a problem and get real help back, delivered
with unnecessary ceremony. All of the thinking is done by a **local open-weight model** (`gemma4:e4b`, served by
[Ollama](https://ollama.com)). Nothing you type leaves your machine.

The rule behind every office: **the help is serious and the jokes are separate.** Plans, drafts, summaries and
comparisons are plain and useful; the humour lives in clearly labelled notices, excuses and stamps.

## The five offices

| Office | You give it | You get back |
|---|---|---|
| **Morning Docket Office** (`/briefing/`) | A pile of notes, to-dos, messages or a chat export (paste, `.txt`, `.md` or text-based `.pdf`) | Today's top three, what can safely wait, what is coming up, each item with a quote from your own words that the server has checked |
| **Bureau of Pending Affairs** (`/pending/`) | A messy list of things to do | A ranked plan: a verdict per task (do now, schedule, delegate, defer, deny), a next step, the minimum effort to be done, and procrastination permits for tasks you may skip. Tick tasks off, carry the unfinished ones into a new plan, or download the plan as Markdown or an `.ics` to-do list |
| **Office of Correspondence Avoidance** (`/correspondence/`) | Rough notes about a message you need to send, plus a tone. Optionally, the message you received (reply mode; notes become optional) | A ready-to-send draft, two alternatives, `[placeholders]` for facts you did not give, a list of the questions the received message asks (each with its own words, marked answered or still needing your input), and an internal memorandum |
| **Commission for Unnecessarily Complicated Documents** (`/documents/`) | Pasted text, or a `.txt`, `.md` or text-based `.pdf` file | A plain-language summary, key points, and the deadlines, actions and requirements the document actually states, each with a quote you can check; plus what is unclear or missing and a complexity rating |
| **Tribunal for Minor Inconveniences** (`/tribunal/`) | A small dilemma and what you care about | A comparison of 2 to 5 options with pros and cons, a recommendation tied to your stated preferences, and a mock judgment you may appeal |

There are also a few things in the building that are not on the directory. Good luck.

## Requirements

- Python 3.12 or newer (required by Django 6.1)
- [Ollama](https://ollama.com/download), running locally
- Enough memory to run `gemma4:e4b` (see the model's page in the Ollama library)

## Setup

```bash
# 1. Get the model (one time; it is a large download)
ollama pull gemma4:e4b

# 2. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Create the database
python manage.py migrate

# 4. Run it (Ollama must be running too; the desktop app starts it, or run `ollama serve`)
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

The first request after Ollama has been idle is slow, because the model has to load into memory (roughly 15 seconds
on the machine this was built on). Later requests are quicker.

## Configuration

Settings are read from **environment variables**. Django does not read `.env` files by itself, so either export them
in your shell or load `.env.example` with a tool of your choice. Every variable is optional.

| Variable | Default | What it does |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama is listening |
| `OLLAMA_MODEL` | `gemma4:e4b` | Which model to use. Only `gemma4:e4b` has been tested; another model must support Ollama's structured (JSON schema) output |
| `OLLAMA_CONNECT_TIMEOUT` | `5` | Seconds to wait for Ollama to accept a connection |
| `OLLAMA_READ_TIMEOUT` | `180` | Seconds to wait for an answer |
| `OLLAMA_THINK` | `false` | Turn the model's "thinking" mode on. Off is much faster and avoids timeouts |
| `OLLAMA_NUM_CTX` | `8192` | Context window requested from Ollama. Raise together with `MAX_DOCUMENT_CHARS` |
| `MAX_STATEMENT_CHARS` | `6000` | Longest statement for the three non-document offices |
| `MAX_DOCUMENT_CHARS` | `12000` | Longest document |
| `MAX_UPLOAD_BYTES` | `60000` | Largest uploaded `.txt` / `.md` file |
| `MAX_PDF_BYTES` | `2000000` | Largest uploaded PDF |
| `MAX_PDF_PAGES` | `40` | Most pages read from a PDF |
| `DJANGO_DEBUG` | `true` | Development mode. Set to `false` before sharing the app |
| `DJANGO_SECRET_KEY` | (dev key) | Required when `DJANGO_DEBUG` is `false`; the app refuses to start without it |
| `DJANGO_ALLOWED_HOSTS` | (empty) | Comma-separated host names, needed when `DJANGO_DEBUG` is `false` |

Example (PowerShell): `$env:OLLAMA_MODEL = "gemma4:e4b"; python manage.py runserver`

## How it keeps the model honest

A small local model will sometimes be wrong, so the server never trusts its output. Every answer is checked in code
before it is stored or shown:

- **Deadlines** the model reports must be the applicant's own words. Invented ones are dropped.
- **Verdicts** are overridden: a task with a stated deadline or high urgency can never be marked "defer" or "deny".
- **Document claims** (deadlines, actions, requirements) must each carry a quote copied from the document. The server
  checks the quote really appears in the text and removes any claim that fails, then tells you how many were removed.
- **Tribunal** recommendations must be one of the listed options, every option needs at least one pro and one con,
  and the preferences it says it relied on must really be in what you wrote.
- **Reading statistics** for documents are computed from the text, never taken from the model.
- **Serious topics** (health, law, money, safety) switch the Tribunal's jokes off and say it is the wrong venue.
  Language about self-harm never reaches the model at all and gets a fixed, kind message instead.
- Everything you type is passed to the model inside tags as data, and typed-in closing tags are neutralised, so text
  such as "ignore your instructions" has no special power.

The model can still misjudge things the code cannot check, such as whether a summary is fair. Read the quoted source
before relying on a document summary. Nothing here is legal, medical or financial advice.

## Privacy

- The model runs on your machine through Ollama. No cloud service is called.
- Cases are stored in a local SQLite file (`db.sqlite3`). Keep it out of version control (the `.gitignore` already does).
- **Documents are not kept.** The full text is read in memory. Only a 200-character preview, the word count and the
  result (including the short quotes that back each claim) are stored.
- Every case page has a **Shred this case** button that deletes the case permanently.
- Uploads are limited to `.txt`, `.md` and `.pdf`. Text files are decoded strictly as UTF-8. PDFs are parsed in memory
  with `pypdf`, text only: encrypted PDFs, scans (no selectable text), oversized and damaged files are refused. Nothing
  is written to disk or executed.
- The Morning Docket Office works like the Documents office: your notes are read in memory and only a 200-character
  preview and the docket are stored.
- The visitor "staff record" (offices visited, things found) lives only in the visitor's own browser storage.

## Running the tests

```bash
python manage.py test
```

The suite (211 tests) mocks Ollama, so it needs no model and runs in a couple of seconds. It proves what the code does
with whatever a model returns, including hostile or malformed output. It cannot prove how the real model behaves, so
also try each office by hand on your machine after changing a prompt.

## Morning docket from the command line

```bash
python manage.py briefing notes.txt chat-export.md      # prints today's docket as Markdown
cat overnight.txt | python manage.py briefing --out today.md
```

Schedule it with cron or Task Scheduler to have the docket waiting each morning.

## Troubleshooting

| You see | Cause and fix |
|---|---|
| "The local AI service (Ollama) is not reachable" | Ollama is not running. Start the desktop app or run `ollama serve`, and check `OLLAMA_BASE_URL` |
| "The configured AI model is not installed" | Run `ollama pull gemma4:e4b` (or whatever `OLLAMA_MODEL` names) |
| "The AI officer took too long" | The first request loads the model, so try again. If it keeps happening, make sure `OLLAMA_THINK` is `false`, shorten the input, or raise `OLLAMA_READ_TIMEOUT` |
| "returned an unusable response" | The model produced output that failed validation. Use **Send back for review** (documents must be resubmitted, because they are not kept) |
| A long document is summarised badly or cut short | Raise `OLLAMA_NUM_CTX` and `MAX_DOCUMENT_CHARS` together; larger contexts use more memory |
| The server log shows `Case XX-NNNN failed: ...` | That line names the technical reason. Your text is never written to the log |

## Project layout

```
dua/                     Django project (settings, root URLs)
cases/
  models.py              Case: department, status, statement, options, result
  views.py               Pages, JSON API, upload handling, shred
  departments.py         Office registry, prompt building, page copy
  offices/               One file per office: prompt, output schema, validator
  validation.py          Pending and Correspondence validators
  validators_common.py   Shared checks (text limits, quote-in-source, tag neutralising)
  exports.py             Markdown and .ics exports of finished cases
  pdf_text.py            PDF text extraction (pypdf, strict limits)
  management/commands/   `briefing`: the docket without a browser
  ollama.py              The only code that talks to Ollama
  static/cases/          app.js (offices), fun.js (the rest), style.css
  templates/cases/       Pages
  test_*.py, tests.py    Tests
```

## Known limitations

- This is a local, single-user app run with Django's development server. It is not hardened for the public internet.
  If you share it beyond your own machine, set the three `DJANGO_*` variables and put it behind a proper web server
  that also serves the static files.
- PDFs must contain selectable text. Scanned PDFs (images) are not supported; there is no OCR.
- The `.ics` export has no due dates: deadlines are your own words ("Friday") and are never turned into guessed dates, so they appear in each task's description.
- English works best. The documents reading-ease score is tuned for English.
- Authentication, accounts and per-user separation of cases do not exist: anyone who can reach the server can see
  every case.
