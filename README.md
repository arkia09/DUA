# Department of Unnecessary Affairs

A Django app where you hand a fictional, deadpan government office a problem and get real help back. A local
open-weight model (`gemma4:e4b`, served by [Ollama](https://ollama.com)) does the thinking. Nothing you type leaves
your machine.

The rule behind every office: **the help is serious and the jokes are separate.** Plans, drafts, summaries and
comparisons are plain and useful. The humour lives in clearly labelled notices, excuses and stamps.

There is also a **demo mode** that needs no model, so the app can be hosted as a public demo. See
[Demo mode](#demo-mode).

## The five offices

| Office | You give it | You get back |
|---|---|---|
| **Morning Docket Office** (`/briefing/`) | A pile of notes, to-dos, messages or a chat export (paste, `.txt`, `.md` or text-based `.pdf`) | Today's top three, what can safely wait, what is coming up, each item with a quote from your own words that the server has checked |
| **Bureau of Pending Affairs** (`/pending/`) | A messy list of things to do | A ranked plan: a verdict per task (do now, schedule, delegate, defer, deny), a next step, the minimum effort to be done, and procrastination permits for tasks you may skip. Tick tasks off, carry the unfinished ones into a new plan, or download the plan as Markdown or an `.ics` to-do list |
| **Office of Correspondence Avoidance** (`/correspondence/`) | Rough notes about a message you need to send, plus a tone. Optionally, the message you received (reply mode; notes become optional) | A ready-to-send draft, two alternatives, `[placeholders]` for facts you did not give, a list of the questions the received message asks (each with its own words, marked answered or still needing your input), and an internal memo |
| **Commission for Unnecessarily Complicated Documents** (`/documents/`) | Pasted text, or a `.txt`, `.md` or text-based `.pdf` file | A plain-language summary, key points, and the deadlines, actions and requirements the document states, each with a quote you can check. Also what is unclear or missing, and a complexity rating |
| **Tribunal for Minor Inconveniences** (`/tribunal/`) | A small dilemma and what you care about | A comparison of 2 to 5 options with pros and cons, a recommendation tied to your stated preferences, and a mock judgment you may appeal |

There are also a few things in the building that are not on the directory. Good luck.

## Requirements

- Python 3.12 or newer (Django 6.1 needs it)
- [Ollama](https://ollama.com/download), running locally (not needed for demo mode)
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

The first request after Ollama has been idle is slow, because the model has to load into memory (about 15 seconds on
the machine this was built on). Later requests are quicker.

## Demo mode

Set `DEMO_MODE=true` and the app runs with no Ollama and no model. Each office has "Try" buttons with sample inputs.
Clicking one and submitting returns a pre-written result, shown exactly like a live one: the same page, the same
permalink, the same exports.

```bash
DEMO_MODE=true python manage.py runserver
```

What demo mode does and does not do:

- **Only the samples work.** The text has to match one of the Try buttons (case, spacing and punctuation are ignored).
  Anything else gets a clear message and no case is created.
- **The results are checked like live ones.** The pre-written output goes through the same validators as model
  output, so the quote checks and verdict guards still run. A test fails if any sample would lose a claim.
- **Switched off in demo mode:** file uploads, the tone selector (each sample has one draft) and "carry unfinished
  tasks into a new plan" (a new plan would need a model).
- **Still on:** ticking tasks, Markdown and `.ics` export, permalinks, shredding, the hidden pages, and the fixed
  kind reply for self-harm language in the Tribunal.
- **A banner** on every page says it is a demo.

The samples live in `cases/demo_data/`, one JSON file per office, stored as the raw JSON a model would return. The
first set was written by hand. To replace them with real output from your local model:

```bash
python manage.py record_demo                  # all offices
python manage.py record_demo pending --tries 5
```

It runs every Try button through Ollama and keeps an answer only if it passes the validators with nothing dropped. An
office's file is replaced only if all of its samples succeed. If you change the example inputs in
`cases/departments.py`, run it again (the tests fail until the data matches the buttons).

### Hosting the demo

Any host that runs Python works. The settings below are the ones that matter:

```bash
# Build
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

# Start
gunicorn dua.wsgi
```

| Variable | Value |
|---|---|
| `DEMO_MODE` | `true` |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | a long random string |
| `DJANGO_ALLOWED_HOSTS` | your host name, e.g. `dua-demo.onrender.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | your public origin, e.g. `https://dua-demo.onrender.com` |
| `DJANGO_BEHIND_PROXY` | `true` on hosts that terminate HTTPS for you (most of them), unless you set the origin above |

Set at least one of the last two. On hosts that terminate HTTPS for you, submits fail with a 403 without them
(checked by simulating such a proxy). `DJANGO_BEHIND_PROXY` trusts the `X-Forwarded-Proto` header from any sender,
so use it only when the app is reachable through the proxy alone. Static files are served by WhiteNoise.

Notes: each visitor only sees the cases they filed themselves, and all cases are deleted whenever the server starts
(see [Case data](#case-data)). Run a single worker, which is gunicorn's default: the wipe happens once per server
process, so extra workers would each wipe again as they start.

## Configuration

Settings are read from **environment variables**. Django does not read `.env` files by itself, so either export them
in your shell or load `.env.example` with a tool of your choice. Every variable is optional.

| Variable | Default | What it does |
|---|---|---|
| `DEMO_MODE` | `false` | Answer sample inputs from pre-written results, no model |
| `WIPE_ON_START` | `true` | Delete all cases when the server starts. Set to `false` to keep them between restarts |
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
| `DJANGO_DEBUG` | `true` | Development mode. Set to `false` before deploying |
| `DJANGO_SECRET_KEY` | (dev key) | Required when `DJANGO_DEBUG` is `false`; the app refuses to start without it |
| `DJANGO_ALLOWED_HOSTS` | (empty) | Comma-separated host names, needed when `DJANGO_DEBUG` is `false` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | (empty) | Comma-separated public origins, e.g. `https://example.com`. Needed behind an HTTPS proxy |
| `DJANGO_BEHIND_PROXY` | `false` | Trust the proxy's `X-Forwarded-Proto` header |

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

## Case data

- **Each visitor only sees their own cases.** A case belongs to the browser session that filed it. Listing, opening,
  exporting, ticking, retrying and shredding all check that. Someone else's case number just gives a 404.
- **Cases are deleted when the server starts.** Strictly, on the first request after it starts, so nothing carries
  over a restart. This is on by default. `WIPE_ON_START=false` keeps them in `db.sqlite3` instead (each visitor still
  only sees their own, and clearing your cookies loses access to yours).
- `python manage.py wipe_cases` deletes everything immediately and restarts the case numbers at 2048.
- Cases filed by the `briefing` command line tool have no owner, so they never show up in the browser.
- Stopping the server does not delete anything by itself. The data is removed at the next start, so the file
  `db.sqlite3` still holds the old cases until then. Delete it if that matters.

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

The suite (244 tests) mocks Ollama, so it needs no model and runs in a couple of seconds. It proves what the code does
with whatever a model returns, including hostile or malformed output. It cannot prove how the real model behaves, so
also try each office by hand on your machine after changing a prompt.

| File | Covers |
|---|---|
| `test_core.py` | Ollama client, Pending and Correspondence validators, API basics |
| `test_offices.py` | Documents and Tribunal offices, uploads, validators, prompt safety |
| `test_features.py` | Reply mode, plan progress, carry-over, exports, the Morning Docket, PDF uploads |
| `test_site.py` | Hidden pages, 404, CSRF, environment configuration |
| `test_demo.py` | Demo mode, sample data, `record_demo` |
| `test_privacy.py` | Per-visitor cases, the wipe on start, the session cookie on failed requests |

## Morning docket from the command line

```bash
python manage.py briefing notes.txt chat-export.md      # prints today's docket as Markdown
cat overnight.txt | python manage.py briefing --out today.md
```

Schedule it with cron or Task Scheduler to have the docket waiting each morning. This needs the real model, so it
does not work in demo mode.

## Troubleshooting

| You see | Cause and fix |
|---|---|
| "The local AI service (Ollama) is not reachable" | Ollama is not running. Start the desktop app or run `ollama serve`, and check `OLLAMA_BASE_URL` |
| "The configured AI model is not installed" | Run `ollama pull gemma4:e4b` (or whatever `OLLAMA_MODEL` names) |
| "The AI officer took too long" | The first request loads the model, so try again. If it keeps happening, make sure `OLLAMA_THINK` is `false`, shorten the input, or raise `OLLAMA_READ_TIMEOUT` |
| "returned an unusable response" | The model produced output that failed validation. Use **Send back for review** (documents must be resubmitted, because they are not kept) |
| A long document is summarised badly or cut short | Raise `OLLAMA_NUM_CTX` and `MAX_DOCUMENT_CHARS` together; larger contexts use more memory |
| The server log shows `Case XX-NNNN failed: ...` | That line names the technical reason. Your text is never written to the log |
| "This is a demo with no AI model behind it" | `DEMO_MODE` is on and the input is not one of the samples. Use a Try button |
| Every submit fails with 403 on a hosted site | Set `DJANGO_CSRF_TRUSTED_ORIGINS` to your public `https://` origin, or `DJANGO_BEHIND_PROXY=true` |
| Page loads but has no styling on a hosted site | Run `python manage.py collectstatic --noinput` as part of the build |

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
  ollama.py              The only code that talks to Ollama
  demo.py                Demo mode: finds the pre-written answer for a sample input
  middleware.py          Wipe on first request, session cookie on 5xx responses
  wipe.py                Deletes all cases (used by the middleware and the wipe_cases command)
  demo_data/             The pre-written answers, one JSON file per office
  context.py             Template variable (DEMO_MODE) for every page
  management/commands/   briefing (docket without a browser), record_demo (regenerate demo data), wipe_cases
  static/cases/          app.js (offices), fun.js (the rest), style.css
  templates/cases/       Pages
  test_*.py              Tests
```

## Known limitations

- This is a single-user app. Run locally it uses Django's development server, which is not hardened for the public
  internet. For anything shared, set the `DJANGO_*` variables above and serve it with gunicorn (see Hosting the demo).
- There are no accounts. Cases are separated by browser session, which is privacy between casual visitors, not a
  security boundary. Anyone with your session cookie is you. Also, a live, model-backed copy on the public internet
  would let strangers use your machine's model, so keep that one private.
- PDFs must contain selectable text. Scanned PDFs (images) are not supported; there is no OCR.
- The `.ics` export has no due dates: deadlines are your own words ("Friday") and are never turned into guessed dates,
  so they appear in each task's description.
- English works best. The documents reading-ease score is tuned for English.
