# ScholarIQ

ScholarIQ analyses a student's marksheets, works out which subjects and topics
need attention, and tutors them with explanations, worked problems and practice
questions from a curated local knowledge base, with diagnostic quizzes that
update topic evidence and a study plan whose ordering it explains.

**It does not use AI models.** No OpenAI, Anthropic, Gemini, Hugging Face,
embedding APIs or local LLMs. Analysis and answers come from deterministic
algorithms, classical information retrieval (BM25), rule-based language
processing and hand-reviewed content. The only learned component is the
Tesseract OCR engine, which runs locally to read scanned marksheets. See
[docs/COMPLIANCE.md](docs/COMPLIANCE.md) for how this is enforced.

## Status

| Milestone | State |
| --- | --- |
| 1. Foundation: skeleton, schema, config, health, Docker, compliance tests | **Done** |
| 2. Marksheet ingestion and review | **Done** |
| 3. Analytics, topic evidence, dashboard | **Done** |
| 4. Knowledge base and BM25 retrieval | **Done** |
| 5. Question answering (AI-free tutor) | **Done** |
| 6. Diagnostics and study plans | **Done** |
| 7. Hardening | Not started |

What works today:

* A local student profile (consent required, signed HttpOnly cookie).
* Marksheet import from digital PDF, scanned PDF, PNG/JPEG (local Tesseract OCR),
  XLSX, CSV and TXT, with per-field confidence and warnings.
* A review screen where every value can be corrected, rows added or excluded,
  and grades mapped to a chosen or custom grading scale. Nothing is saved until
  the student confirms.
* Confirmed results by semester and exam, with repeat attempts tracked.
* Deleting an upload (with its results) and deleting all of a student's data.
* A dashboard with overall, credit-weighted and GPA figures (each says how many
  results it counts, or why it is unavailable), latest score per subject, a
  semester trend, data gaps and the calculation rules.
* A versioned curriculum (`content/curriculum/`, 6 subjects and 40 topics) with
  subject matching by code, name, alias and close spelling. Subjects outside the
  curriculum can be moved onto a curriculum subject or given topics by hand.
* Topic classification (Strong, Developing, Needs attention, Insufficient
  evidence) from topic-level evidence only. A subject mark counts as one weak
  observation; at least five topic-level observations are needed. Students can
  add topic test results and self-assessments, and remove what they entered.
* A Computer Science knowledge base (`content/knowledge/`): 151 concepts,
  201 explanations and worked examples, 242 practice questions and 205
  prerequisite and related-concept links across all 40 topics, each citing
  textbooks or RFCs for further reading. None of it has been reviewed by a
  person yet, and the app labels it that way everywhere.
* Knowledge Base pages with coverage per topic, concept pages, and search that
  shows its whole score: BM25 contribution per word plus a bonus when the query
  names a concept. Retrieval quality is measured in
  [docs/eval/retrieval.md](docs/eval/retrieval.md).
* An AI-free tutor. It recognises definition, explanation, comparison,
  procedure, worked-problem, reasoning, prerequisite, practice, "what should I
  study" and follow-up questions, tolerates shorthand ("diff b/w") and
  misspellings ("semafore"), and asks which meaning was intended when a name is
  ambiguous. Answers are assembled from the knowledge base and say which entry
  each section came from; comparison tables show "Not recorded" rather than
  filling gaps. Local solvers work out arithmetic, percentages, linear and
  quadratic equations, recurrences (master theorem), truth tables, graph
  traversals and SELECT queries on a built-in practice database, showing each
  step. Python code is analysed for running time without being run. Questions
  it cannot answer are declined with the closest concepts it does cover.
  Teaching depth follows the student's topic classification (or the depth they
  ask for) and never changes the facts. Quality is measured on 60 gold
  questions in [docs/eval/answers.md](docs/eval/answers.md).
* Diagnostic quizzes on every topic (Practice). A quiz has up to five stored
  questions mixing understanding and application, chooses questions the
  student has seen least, and shuffles answer options with a fixed per-quiz
  seed. After submission each answer is explained, the result is stored as
  topic evidence, and the page shows the topic's classification before and
  after with the reasons. Quizzes can be retaken; past quizzes stay viewable.
* A study plan built with a published formula (`plan-formula/1`): need from
  the classification, curriculum importance, goals the student picks, how many
  planned topics build on it, recent quiz results and study time. Prerequisite
  topics always come first. Each position shows its formula terms. Students
  can mark a topic as studied or skip it; that is progress, not evidence, and
  never changes a classification.

Sections without a backend yet say so; none show sample data. The roadmap and design are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start with Docker

```bash
cp .env.example .env
docker compose up --build
```

Open http://localhost:3000. The API is at http://localhost:8000 (OpenAPI docs at
`/docs`). Migrations run automatically when the API container starts.

## Local development

Requirements: Python 3.11+, Node.js 22, PostgreSQL 16 (or use SQLite), and
optionally the `tesseract` binary.

```bash
make setup                         # venv, backend deps, frontend deps
cp .env.example backend/.env       # adjust SCHOLARIQ_DATABASE_URL
make migrate
make api                           # http://localhost:8000
make web                           # http://localhost:3000 (in another terminal)
```

Single-user offline mode with SQLite:

```bash
export SCHOLARIQ_DEPLOYMENT_MODE=offline
export SCHOLARIQ_DATABASE_URL=sqlite:///./var/scholariq.db
make migrate api
```

The frontend finds the API through `SCHOLARIQ_API_URL` (default
`http://localhost:8000`).

## Tests and checks

```bash
make test         # backend pytest + frontend vitest
make lint         # ruff, mypy, tsc, eslint
make compliance   # no-external-AI scan, prints violations
```

Backend tests run against SQLite by default. Set
`SCHOLARIQ_TEST_POSTGRES_URL` to also run the migration round-trip on
PostgreSQL. All backend tests run with outbound network access blocked.

## Configuration

All settings are environment variables prefixed `SCHOLARIQ_`; see
[.env.example](.env.example). Invalid combinations fail at startup, for example
offline mode with a PostgreSQL URL, or production with the default secret key.

If any AI-provider credential (the list is in `compliance/policy.py`) is set in the
environment the API refuses to start. ScholarIQ never uses them; unset them, or
set `SCHOLARIQ_STRICT_AI_ENV_CHECK=false` to start with a warning (readiness
will still report the check as failed).

## Health endpoints

* `GET /api/health/live` returns 200 when the process is up.
* `GET /api/health/ready` checks the database and schema revision, upload
  storage, knowledge content, OCR availability (optional) and AI compliance.
  Returns 503 if a required check fails.
* `GET /api/system/info` lists which capabilities are available or planned.

## How marksheet import works

1. **Validate**: size limit, file type from content signature (the extension
   must agree), PDF/image/XLSX integrity, decompression-bomb and macro checks.
2. **Extract**: digital PDFs via pdfplumber (words with positions and ruled
   tables); PDFs with no text layer are rendered and OCR'd; images are OCR'd
   with Tesseract after grayscale/contrast/upscale preprocessing; XLSX values
   via openpyxl; CSV with delimiter sniffing; text split on tabs, runs of
   spaces or pipes.
3. **Interpret**: pluggable layout parsers. The header-table parser matches
   column headers against a synonym dictionary (with edit-distance tolerance)
   and aligns cells by column position; the line parser reads rows without a
   recognisable header by value order. The parser whose output has the best
   count x confidence wins.
4. **Score**: each field carries reading confidence (1.0 for digital text,
   Tesseract word confidence for OCR) multiplied by interpretation confidence
   (exact header match, fuzzy match, positional guess, OCR digit correction).
   These are heuristic scores for highlighting, not probabilities. Fields under
   0.8 are highlighted for review.
5. **Review and confirm**: the student corrects values and chooses how grades
   are read. Only then are assessments and results written; the extracted text
   is discarded.

Rules it follows: a missing mark is stored as missing, never zero; absent and
withheld are statuses, not marks; maximum marks are never assumed; grades are
not converted without a confirmed scale (and a scale that lacks a grade is
refused); theory and practical columns become separate components; repeat
sittings become new attempts.

## Knowledge-base content and review

Content is YAML under `content/knowledge/<subject>/<topic>.yaml`, validated on
load (unknown references, duplicate slugs, prerequisite cycles and malformed
questions are errors) and synced into the database by
`python -m scholariq.curriculum.sync`, which also runs on container start.
Removed entries are retired, not deleted.

Each concept carries a review block. To sign one off after checking it:

```bash
cd backend
python -m scholariq.knowledge.review                  # list concepts and status
python -m scholariq.knowledge.review db.3nf --by "Your Name"   # prints a review block
```

Paste the printed block into the concept. It includes a hash of the concept's
content, so any later edit returns the concept to "not yet reviewed" until it
is checked again.

`SCHOLARIQ_ALLOW_UNREVIEWED_CONTENT` (default `true`) decides whether search,
the tutor and quizzes may use unreviewed concepts. When `true`, every answer
built from one is labelled "not yet reviewed by a person". Set it to `false`
to use reviewed content only.

To re-measure search and the tutor after changing content, ranking or the
answer rules:

```bash
cd backend && python -m scholariq.knowledge.evaluate --out ../docs/eval/retrieval.md
cd backend && python -m scholariq.answering.evaluate --out ../docs/eval/answers.md
```

## Tutor conversations and privacy

Each question and its structured answer are stored with the student's profile
so the conversation can be reopened and follow-ups ("explain step 2 again")
work. Nothing about a question is written to the logs. A conversation is
deleted `SCHOLARIQ_CONVERSATION_RETENTION_DAYS` (default 30) after its last
message; `0` keeps conversations until the student deletes them. Students can
delete one conversation from the tutor page, or everything with Delete my data.
Answers to "test my understanding" questions are marked but not recorded, so
they never change a topic classification.

## Known limitations

* Every quiz question is multiple choice, and most topics have five to eight
  questions, so after one or two retakes questions repeat (in a new order).
  The answer keys are seed content no person has reviewed yet.
* Topic prerequisites are derived from concept "requires" links in the
  knowledge base. The plan formula's weights are teaching conventions (defaults
  in `backend/scholariq/analytics/policy.py`, overridable in an optional
  `content/policy.yaml`), not fitted to outcomes.
* The tutor answers only from the knowledge base and its solvers. It is not a
  general problem solver: it handles the problem families listed above, Python
  code only, and running-time templates for common loop and recursion shapes
  (anything else is reported as "not matched"). Its question grammar and
  thresholds were tuned on questions written by the same author as the content,
  so real students' phrasing will expose gaps; the held-out evaluation set is
  small (24 questions).
* No knowledge-base entry has been reviewed by a person yet. The seed content
  was written for ScholarIQ from standard textbook material.
* Knowledge-base search is lexical. It handles names, aliases, British and
  American spellings and word endings, but not misspellings (the tutor corrects
  spelling before searching), and some queries about unrelated
  subjects still return loosely related concepts (2 of 6 in the evaluation).
* Custom subjects are shared rows. A student cannot change the topics of a custom
  subject that another profile also uses.
* Profiles have no password. A profile is tied to the browser that created it,
  so use a trusted device and do not expose the app publicly yet.
* Extraction runs during the upload request. Large scanned PDFs (up to 20
  pages) can take several seconds; a background job queue is not needed yet.
* Two layout parsers ship today. Unusual layouts fall back to the line parser
  and need more correction on the review screen.
* OCR quality depends on the scan. Handwritten marks are not supported.
* The upload rate limit is per process; multi-worker deployments need a
  shared limiter.
