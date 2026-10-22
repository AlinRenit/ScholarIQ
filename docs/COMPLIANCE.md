# No-external-AI compliance

ScholarIQ's academic intelligence (marksheet interpretation, analytics, topic
classification, retrieval, question understanding, answers, quizzes and study
plans) is implemented with deterministic algorithms and a curated local
knowledge base. It does not call, embed, download or fall back to any language
model or AI service.

## How this is enforced

| Check | Where | When |
| --- | --- | --- |
| Declared Python dependencies against a denylist | `scanner.scan_python_manifests` | CI, `make compliance` |
| Every installed Python distribution (catches transitive deps) | `scanner.scan_installed_distributions` | CI |
| AST scan of all Python imports, including `importlib.import_module("...")` | `scanner.scan_python_imports` | CI |
| Intelligence packages import no network modules (`socket`, `httpx`, `requests`, `urllib.request`, ...) | same | CI |
| npm `package.json` and every package in `package-lock.json` | `scanner.scan_npm` | CI |
| Source, config and Docker files contain no inference hostnames or AI credential variables | `scanner.scan_text` | CI |
| `.env.example` contains no secrets | `test_env_example_has_no_secrets` | CI |
| The API refuses to start when AI credentials are set | `compliance.runtime.enforce_environment` | every start |
| Readiness reports any AI configuration as a failed check | `/api/health/ready` | runtime |
| Every backend test runs with outbound network blocked | `tests/conftest.py::_offline` | every test |

The policy itself (package names, import roots, hostnames, environment
variables, network modules) lives in `backend/scholariq/compliance/policy.py`.
The scanner has its own tests that plant known-bad files and assert each rule
fires, so a broken scanner cannot pass silently.

### Limits of these checks

A denylist catches known providers. It cannot prove that no AI exists anywhere:
a new provider or a hand-written HTTP call to an unknown endpoint from outside
the intelligence packages would need code review to catch. The network-import
rule for intelligence packages is the stronger guarantee, because it does not
depend on knowing provider names.

Some developer tools set provider variables in the shell. The test suite clears
every listed variable to simulate a clean install, and dedicated tests set them
on purpose to prove the refusal works.

## Dependency audit

Later milestones append rows here as they add packages.

| Dependency | Kind | Network at runtime | Uses ML models | Verdict |
| --- | --- | --- | --- | --- |
| fastapi, starlette | web framework | serves requests only | no | allowed |
| uvicorn | ASGI server | serves requests only | no | allowed |
| pydantic, pydantic-settings | validation | no | no | allowed |
| sqlalchemy, alembic | ORM, migrations | database only | no | allowed |
| psycopg | PostgreSQL driver | database only | no | allowed |
| pytest, httpx (dev) | testing | test client only | no | allowed |
| ruff, mypy (dev) | static analysis | no | no | allowed |
| next, react, react-dom | frontend | serves pages, proxies to own API | no | allowed |
| tailwindcss, @tailwindcss/postcss (dev) | CSS build | no | no | allowed |
| typescript, eslint, eslint-config-next (dev) | static analysis | no | no | allowed |
| vitest, @testing-library/*, jsdom (dev) | testing | no | no | allowed |
| Tesseract (binary, Docker image) | OCR | no | local LSTM character recogniser | allowed (explicitly permitted; see ARCHITECTURE.md) |
| pytesseract (M2) | subprocess wrapper around the local `tesseract` binary | no | no (calls Tesseract) | allowed |
| pdfplumber, pdfminer.six (M2) | PDF words, positions and ruled tables | no | no | allowed |
| pypdfium2 (M2) | PDF integrity check and page rendering for OCR (PDFium) | no | no | allowed |
| Pillow (M2) | image validation and OCR preprocessing | no | no | allowed |
| openpyxl (M2) | XLSX values (formulas are not evaluated; macro workbooks rejected) | no | no | allowed |
| rapidfuzz (M2) | edit-distance matching of header names | no | no | allowed |
| python-multipart (M2) | multipart upload parsing | no | no | allowed |
| reportlab (M2, dev only) | generates the PDF test fixtures | no | no | allowed |
| server-only (M2, frontend) | build-time guard for server modules | no | no | allowed |
| PyYAML (M3) | reads curriculum and policy files (`safe_load` only) | no | no | allowed |
| recharts (M3, frontend) | SVG charts on the dashboard | no | no | allowed |
| prettier (M3, frontend dev) | code formatting | no | no | allowed |

Next.js telemetry is disabled in the Docker images (`NEXT_TELEMETRY_DISABLED=1`).
Set the same variable, or run `npx next telemetry disable`, for local development.

## Offline operation

After installation and content setup, nothing in the intelligence pipeline needs
the internet. Milestone 7 adds an end-to-end test that runs the full stack on a
Docker network with no external route.
