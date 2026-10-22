# Security review

Reviewed for Milestone 7 (2026-10-22). This covers what ScholarIQ protects, how,
what was changed in the review, and what is still a risk. It is a review by the
people who built the app, not an independent audit.

## What is being protected

* Students' marksheets (uploaded files) and the results extracted from them.
* Topic evidence, quiz answers, study plans and tutor conversations.
* Each student's account: the profile cookie and, if set, an email and password.

The main threats considered: another user reading or changing a student's data;
someone on a shared computer using a profile that was left signed in; password
guessing; cross-site requests made from another web page; malicious uploads;
and data leaving the machine (to AI services or anywhere else).

## Controls

### Accounts and sessions

* A profile is identified by an HttpOnly, SameSite=Lax cookie holding
  `student id . session version . HMAC-SHA256`, signed with
  `SCHOLARIQ_SECRET_KEY`. Production refuses to start with the default key, and
  the cookie is marked Secure in production.
* A student can add an email and password in Settings. Passwords are hashed with
  scrypt (N=2^14, r=8, p=1, 16-byte random salt) from the Python standard
  library, need at least 10 characters, and are compared in constant time.
  Signing in with an unknown email runs the same hash against a dummy value, so
  timing and the error message ("Email or password is not correct.") do not tell
  which emails exist.
* Changing the password, or "Sign out everywhere", increases the profile's
  session version, which invalidates every cookie issued before. Plain "Sign
  out" clears only this browser's cookie, and is offered only once a password
  exists (otherwise signing out would lose the profile).
* Sign-in attempts are limited to 10 per email per 15 minutes and 200 in total
  per 15 minutes per process; further attempts get HTTP 429.

### Access to data

* Every query for student data is scoped to the signed-in student; another
  student's ids return 404, never 403, so ids cannot be probed.
* Deleting a profile cascades to every student-owned row and removes uploaded
  files from disk. The end-to-end tests check this through the UI.
* Uploads are stored outside any served directory under random names with mode
  0600, checked by file signature (not by extension), limited to
  `SCHOLARIQ_MAX_UPLOAD_BYTES` (10 MB default) and 20 PDF pages, and deleted
  after `SCHOLARIQ_UPLOAD_RETENTION_DAYS`. Spreadsheet formulas are never
  evaluated and macro workbooks are refused.
* The practice SQL solver runs in an in-memory SQLite database with an
  authorizer that allows only reading its own tables. Student code is parsed
  with `ast`, never executed.

### Requests from other sites

* The browser talks only to the Next.js server, which forwards `/api/*` to the
  API. The forwarder refuses state-changing requests (anything but GET/HEAD)
  whose `Origin` host differs from the request host, or that the browser marks
  `Sec-Fetch-Site: cross-site`. This is in addition to SameSite=Lax.
* Pages are sent with a Content Security Policy: scripts, styles, connections
  and forms only from the same origin, no plugins (`object-src 'none'`), and
  `frame-ancestors 'none'` against clickjacking. Inline scripts are allowed
  because Next.js needs them for hydration; there is no user-supplied HTML
  anywhere in the app (React escapes all text). Also sent: `X-Frame-Options:
  DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and a
  `Permissions-Policy` that turns off camera, microphone, geolocation and
  payment APIs.
* API responses carry `Cache-Control: no-store` so shared caches never keep
  personal data. The interactive API docs (`/docs`, `/openapi.json`) are off in
  production.

### Data leaving the machine

* There are no outbound calls in the application. The compliance scanner (run in
  CI) fails the build on AI SDK imports, AI provider hosts, model files and AI
  dependencies, and the API refuses to start if AI credentials are set (see
  [COMPLIANCE.md](COMPLIANCE.md)).
* The end-to-end suite starts the API and the web server with guards that refuse
  and record every connection to a non-loopback address, and blocks the
  browser's requests to other hosts. The run fails if anything was attempted.
* Request bodies, files and question text are not logged.

## Changes made in this review

* Added password sign-in, sign-out, "sign out everywhere" and session versions
  (before this, a profile could not be signed out or used from a second browser).
* Added the sign-in rate limits and the unknown-email timing protection.
* Added the cross-site request check in the forwarder, the Content Security
  Policy and the other response headers, and turned off API docs in production.
* Forwarded every `Set-Cookie` header from the API (previously only the first
  would have survived, which matters once sign-in sets and clears cookies).

## Dependency audit (2026-10-22)

* Python: `pip-audit` over the 59 installed backend packages reported no known
  vulnerabilities.
* JavaScript: `npm audit --omit=dev` reports 0 vulnerabilities in what ships.
  `npm audit` including development tools reports 5 high-severity advisories,
  all in the ESLint toolchain (`braces`, `micromatch`, `fast-glob` via
  `eslint-config-next`). They affect only linting on a developer's machine and
  are not in the built app; the fix requires a major ESLint config upgrade,
  which is left for a dependency update.

Re-run with `npm audit` in `frontend/` and `pip-audit` against the backend
environment before each release.

## Residual risks

* **No HTTPS of its own.** Run ScholarIQ behind a reverse proxy that terminates
  TLS (and sets `SCHOLARIQ_ENVIRONMENT=production` so cookies are Secure)
  before exposing it beyond one machine or a trusted network.
* **Profiles without a password** are only as safe as the browser holding the
  cookie. Anyone with that browser can use the profile. The UI says so and
  offers a password.
* **No email verification or password reset.** The email is only a sign-in
  name; nothing is ever sent to it. A forgotten password cannot be recovered;
  the profile is still usable from the browser that has the cookie.
* **Rate limits are per process.** With several API workers each keeps its own
  counts, so the effective limit is multiplied by the number of workers.
* **`'unsafe-inline'` scripts** in the CSP weaken it as a defence against
  script injection. There is no known injection point; moving to nonces needs
  per-request rendering of every page.
* **Uploaded files are parsed by third-party libraries** (pdfplumber, PDFium,
  Pillow, openpyxl, Tesseract). They run in the API process without an extra
  sandbox; keep them updated.
* **Seed content has not been reviewed by a person.** A wrong answer key would
  mark a correct student answer as wrong and lower their topic evidence. Every
  such question is labelled "not yet reviewed by a person", and
  `SCHOLARIQ_ALLOW_UNREVIEWED_CONTENT=false` restricts the app to reviewed
  content.
