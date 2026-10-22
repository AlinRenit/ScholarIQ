# ScholarIQ

ScholarIQ analyses a student's marksheets, works out which subjects and topics
need attention, and (in later milestones) tutors them with explanations and
quizzes from a curated local knowledge base.

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
| 2. Marksheet ingestion and review | Not started |
| 3. Analytics, topic evidence, dashboard | Not started |
| 4. Knowledge base and BM25 retrieval | Not started |
| 5. Question answering | Not started |
| 6. Diagnostics and study plans | Not started |
| 7. Hardening | Not started |

What works today: the API, health and readiness checks, configuration
validation, the full database schema and migration, and a frontend shell with
the eight product sections. Sections without a backend yet say so; none show
sample data. The roadmap and design are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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

## Known limitations (Milestone 1)

* No marksheet import, analytics, knowledge base or tutor yet.
* No authentication yet; do not expose the app publicly.
* Tesseract is installed in the API image but nothing uses it until Milestone 2.
