# Classarit

The flow of knowledge. A FastAPI app for independent teachers and institutes to manage
teams, students, classes, sports events, attendance and makeup lessons.

## Guide

- [Local and IntelliJ setup](#run-locally)
- [Google login setup](#google-login-setup)
- [Current login flow](#current-login-flow)
- [Features and limitations](#features)
- [Architecture and data ownership](#architecture-and-data-ownership)
- [Render deployment](#deploy-on-render)
- [Environment variables](#environment-variables)
- [Authentication database DDL](#authentication-database-ddl)
- [Future login methods](#future-login-methods)
- [Workspace and teaching data flow](#workspace-and-teaching-data-flow)
- [UI walkthrough and API reference](#ui-walkthrough-and-api-reference)
- [Progressive implementation plan](#progressive-implementation-plan)
- [Tests](#tests)

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --reload
```

Open <http://127.0.0.1:8000>. The landing page is public; `/login` offers Google,
and `/dashboard` requires a valid session. There is no demo bypass. On a fresh
installation, configure `.env`, initialize [authentication DDL](#authentication-database-ddl),
then run `python setup/apply_migration.py 001_workspaces_and_teaching.sql` before
opening the signed-in dashboard. Existing configured databases with the journaled
migration skip safely.

In IntelliJ, select `.venv/bin/python` as the project interpreter and run the root
`run.py` file. Leave parameters blank for debugging, or use `--reload` for local
reloads. The working directory can be the project root; asset/database paths are
resolved from the source files. Enable the JetBrains Mermaid plugin to render
this README's diagrams in Markdown preview.

## Google login setup

1. Copy [.env.example](.env.example) to `.env` only if you do not already have one.
   Fill in Google and PostgreSQL settings. `.env` is private and ignored by Git.
2. In Google Cloud, configure an OAuth **Web application**, consent screen and any
   test users required while the application is in testing mode. Register the exact
   redirect URI: `http://127.0.0.1:8000/auth/google/callback` for local development.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. The callback is built from the
   current request origin plus `/auth/google/callback`; no redirect environment variable
   is used. Stay on the same hostname throughout login. The signing key is generated
   and saved automatically unless an optional `SESSION_SECRET_KEY` is supplied.
4. Initialize a fresh PostgreSQL authentication schema with `setup/auth_schema.sql`.
   If you already installed the earlier five-table design, run only
   `setup/auth_sessions.sql` to add revocable sessions. No destructive migration runs
   automatically on application startup.
5. Start the app, choose **Log in → Continue with Google**, complete Google approval,
   and return to your dashboard. If the popup is blocked, use **Continue in this tab**.

A first successful Google login creates its account automatically. The separate
Signup button only shows a coming-soon toast; no password signup or OTP is enabled.
An existing email belonging to another identity requires a future linking flow and
is not automatically merged in this release.

## Current login flow

```mermaid
flowchart TD
    Home[Public landing page] --> Choice{Choose action}
    Choice -->|Sign up| Toast[Show coming-soon toast]
    Choice -->|Log in| Login[Separate login page]
    Login --> Click[Continue with Google]
    Click --> Popup{Popup allowed?}
    Popup -->|Yes| Google[Google authorization window]
    Popup -->|No| Tab[Offer login in the same tab]
    Tab --> Google
    Google --> Callback[Callback validates state, signature, issuer, audience, expiry and nonce]
    Callback -->|Invalid or cancelled| Error[Show retry message]
    Callback -->|Valid| Identity{Google subject already linked?}
    Identity -->|Yes| Active{Account ACTIVE?}
    Identity -->|No| Email{Email already belongs to an account?}
    Email -->|Yes| LinkLater[Explain account linking is coming soon]
    Email -->|No| Create[Create user, email and Google identity atomically]
    Create --> Active
    Active -->|No| Deny[Deny login]
    Active -->|Yes| Session[Create hashed server session and rotate cookie state]
    Session --> Notify[Notify parent or detect session by polling]
    Notify --> Dashboard[Redirect to private dashboard]
    Dashboard --> Workspace{Has active workspace?}
    Workspace -->|No| Onboard[Create individual or institute workspace]
    Workspace -->|Yes| Switch[Open remembered workspace]
    Onboard --> Request[Check session, membership, role and assignment on each request]
    Switch --> Request
    Request --> Logout[Logout revokes server session and clears cookie]
    Logout --> Home
```

The popup sends only a completion notification, never credentials or tokens. The
parent checks the message origin/source and confirms `/auth/me` before navigating.
Polling handles providers that disconnect the popup's opener. Cancelled or failed
login displays a retry option. OAuth tokens are not persisted.

## Features

### Workspace dashboard

- Google login opens workspace onboarding for a new account. Choose an individual
  practice or institute; the creator receives Owner and Teacher roles.
- Create multiple workspaces, switch between them, and remember the last selection.
- Overview cards show students, programs, upcoming sessions and unexpired open credits.
- The existing navy/blue style continues in a responsive dashboard with real forms.

### Team and teaching setup

- Invite teachers, coaches, admins and operators with an expiring shareable link.
  Acceptance requires the invited verified Google email. Revoke invitations and
  manage member roles/status; the final active owner cannot be removed.
- Create academic, arts, sports or other activities inline when creating a program.
- Create group or one-to-one courses and one-off events. Assign default teachers,
  duration, capacity, level and online/in-person/hybrid delivery details.
- Add venues, addresses, directions and rooms/courts/pitches.
- Add/edit students and their primary guardian contact; enroll students in courses
  or book them directly into event sessions. End enrollment to release future seats.

### Scheduling, attendance and makeup classes

- Schedule occurrences from program defaults. Active eligible enrollments populate
  the roster; enrolling later also populates already-scheduled future sessions.
- Reschedule future sessions, cancel with an explanation, join online meetings,
  open venue directions, mark attendance and complete finished sessions.
- Reject teacher, student and venue/space overlaps and full classes/sessions.
- Cancellation can grant credits to the original roster in one transaction.
  Staff can grant individual absence credits or approved policy exceptions.
- Book a compatible replacement, release/rebook it, and fulfill the credit when
  attendance is Present or Late. Replacement cancellation preserves the original credit.
- Teacher-only members see their assigned teaching records and relevant students;
  management actions remain restricted by backend role checks.

### Previous dashboard

`/legacy/dashboard` preserves the previous account-scoped SQLite dashboard, payment
records, materials and upload APIs. Its placeholder dialogs are unchanged. Those
records are **not** shared with the new PostgreSQL workspace dashboard. No legacy
records are automatically assigned or copied into a new business.

### Current MVP limitations

- Signup still shows the coming-soon notice. Password/OTP, Apple/Facebook and account
  linking remain future work, as requested.
- Invitations are shareable links; the app does not send email invitations yet.
- Schedule is an occurrence list, not a drag-and-drop calendar. Recurrence generation
  and bulk editing are not implemented. Schedule each occurrence explicitly.
- Program teacher edits change defaults for new sessions; existing session assignments
  remain historical snapshots. UI scheduling inherits defaults; the API also accepts
  per-session teacher, delivery and capacity overrides.
- Workspace closure, class/venue deletion, student self-service and attendance
  correction after a settled makeup require later workflows.
- Students have optional primary guardian entry/edit in the UI; multiple-guardian
  management is reserved by the schema. Clearing a guardian name does not delete history.
- A nonzero absence notice requirement needs staff review. Owner/Admin can grant an
  `OTHER` exception with a note. No-show/Excused replacement attendance leaves the
  credit open for another future session; no automatic financial penalty is applied.
- Billing/materials migration, reminders, audit logs, database RLS, pagination and
  branch administration remain future phases. Makeup fee inclusion is metadata,
  not payment collection. Workspace writes currently serialize per workspace.


## Architecture and data ownership

| Module | Responsibility |
| --- | --- |
| `run.py` | Local/Render Uvicorn startup; Render host, port and proxy handling |
| `app/main.py` | Application composition, middleware, lifecycle and protected file serving |
| `app/routes/public.py` | Public landing and health routes |
| `app/auth/routes.py` | Login page, Google start/callback, login status and logout |
| `app/auth/settings.py` | OAuth configuration and cookie policy |
| `app/auth/database.py` | Lazy PostgreSQL connection from DB variables |
| `app/auth/repository.py` | Google identity resolution, users and revocable sessions |
| `app/auth/dependencies.py` | Session/status checks and CSRF validation |
| `app/routes/dashboard.py` | Workspace selection, onboarding and invitation pages |
| `app/workspaces/routes/` | Typed HTTP endpoints for organizations, catalog and sessions |
| `app/workspaces/schemas.py` | Validated request payloads |
| `app/workspaces/access.py` | Active membership, roles, assignments and workspace write lock |
| `app/workspaces/db.py` | Transaction boundary and parameterized SQL helpers |
| `app/workspaces/services/organizations.py` | Workspace creation, invitations and member roles |
| `app/workspaces/services/catalog.py` | Activities, venues, programs, students and enrollment |
| `app/workspaces/services/scheduling.py` | Timezones, overlap checks, rosters and attendance |
| `app/workspaces/services/makeups.py` | Policy, credits, booking, cancellation and release |
| `app/workspaces/services/queries.py` | Permission-filtered dashboard projection |
| `app/static/workspaces/` | Separate API, forms, actions, rendering and startup JS modules |
| `setup/apply_migration.py` | Atomic versioned migration with checksum journal |
| `app/routes/legacy_dashboard.py`, `app/routes/teaching.py` | Previous SQLite dashboard and APIs |
| `app/services/ownership.py` | Map authenticated UUIDs to private teacher workspaces |
| `app/services/serializers.py` | API response serialization |
| `app/models.py`, `app/database.py` | Existing SQLAlchemy teaching data in SQLite |
| `app/config.py` | Load `.env`; select local/persistent data paths |
| `app/templates/`, `app/static/` | Separate landing/login/callback/dashboard UI, CSS and JavaScript |

Authentication and the new workspace teaching model use PostgreSQL in `classarit`.
All business relationships are qualified by `workspace_id`. Authorization checks an
active account, active membership, role and relevant teacher assignment. Mutations
lock the workspace row before checking capacity/conflicts and commit all changes
atomically. Composite foreign keys prevent cross-workspace relationships even if a
caller supplies another workspace's UUID. The selector itself grants no permission.

SQLite and local uploads remain only for the previous dashboard. Its
`teachers.auth_user_id` mapping and ownership checks continue to protect old records.
The local preflight found unassigned demo teaching records and no owned student
records to migrate. They were preserved. A Render disk may contain different legacy
data: inventory that separately before any future billing/materials migration.
Startup still initializes legacy SQLite storage, but never runs the new PostgreSQL DDL.

```mermaid
flowchart LR
    UI[Workspace template and JS modules] --> Routes[Typed FastAPI routes]
    Routes --> Auth[Session and CSRF checks]
    Auth --> Access[Membership and role checks]
    Access --> Lock[Workspace transaction lock]
    Lock --> Services[Focused domain services]
    Services --> SQL[Parameterized SQL store]
    SQL --> PG[(PostgreSQL classarit)]
    Legacy[Previous dashboard] --> Ownership[Account ownership checks]
    Ownership --> SQLite[(Legacy SQLite and uploads)]
```

Session cookies are HttpOnly and SameSite=Lax, with Secure enabled for HTTPS/Render.
The browser holds an opaque session token inside a signed cookie; PostgreSQL stores
only its SHA-256 hash and expiry (12 hours). Every protected request rechecks ACTIVE
status. Logout deletes the server session, so replaying an old cookie cannot log in.
Teaching API mutations require `X-CSRF-Token` from the dashboard's `csrf-token` meta
field. Logout uses a hidden form token. Protected responses have `Cache-Control: no-store`.

## Deploy on Render

Push changes to the connected branch, then create a Blueprint from `render.yaml`
or configure an existing service with:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Root directory | Blank (repository root) |
| Build | `python -m pip install -r requirements.txt` |
| Start | `python run.py` |
| Python version | `PYTHON_VERSION=3.13.5` |
| Health path | `/health` |
| Data directory | `CLASSARIT_DATA_DIR=/var/data` |
| Persistent disk | `/var/data`, 1 GB, paid instance |

Set Google and DB credentials in Render's Environment settings. Register
`https://YOUR-SERVICE.onrender.com/auth/google/callback` in Google Cloud and use that
HTTPS callback in Google Cloud. No callback or session-secret environment variable
is required. The request host and trusted proxy scheme determine the callback.
Proxy headers are trusted by the launcher only when `RENDER=true`; do not set
that flag locally. PostgreSQL must be initialized before login can succeed.

Apply the authentication schema on a fresh database, then apply the workspace
migration before releasing this dashboard:

```bash
python setup/apply_migration.py 001_workspaces_and_teaching.sql
```

Run against the intended DB credentials from `.env` locally or Render Environment.
The configured project database was migrated on 2026-09-10. If Render uses that same
database, do not manually rerun the SQL: the runner safely verifies/skips its journaled
version. A different Render database needs its own initialization. No DDL runs on startup.

The Blueprint uses paid persistent storage for legacy SQLite, uploads and the generated
session signing key. PostgreSQL accounts, workspaces and teaching records persist
separately. With a disposable disk and `CLASSARIT_DATA_DIR=/tmp/classarit`, legacy
records/uploads and the generated signing key are lost on restart; users must sign
in again. PostgreSQL workspace records remain intact. See [Render persistent disks](https://render.com/docs/disks).

## Environment variables

`python-dotenv` loads `.env` without overriding actual environment variables. No
credential belongs in `.env.example`, source files or the README.

| Variables | Purpose |
| --- | --- |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth credentials |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL credentials; distinct from the SQLite teaching database |
| `DB_SCHEMA` | Authentication schema, default `classarit` |
| `DB_SSLMODE` | PostgreSQL TLS policy; use `require` or the provider's stricter recommendation for hosted databases |
| `SESSION_SECRET_KEY` | Optional shared signing key (minimum 32 characters when supplied); otherwise generated automatically |
| `CLASSARIT_DATA_DIR` | SQLite/uploads directory; defaults to the project root |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | Reserved for future OTP sending; not used yet |
| `OTP_HMAC_SECRET` | Reserved for future OTP hashing; separate from the session secret |

Resend uses an API key, not a client ID. No email is sent by this release.
Missing Google settings leave the landing page available with login disabled.
A database/provider failure shows a generic login error without exposing secrets.


### Automatic callback and session signing

The app uses `request.url_for("google_callback")`, so the browser's origin determines
its callback:

- Local: `http://127.0.0.1:8000/auth/google/callback`.
- Remote: `https://myremote.example.com/auth/google/callback`.
- Opening via `localhost` instead of `127.0.0.1` produces a `localhost` callback;
  register that exact URL too if you use it.

Render's trusted proxy headers tell Uvicorn the original HTTPS scheme. The launcher
already enables this on Render; other hosting platforms must configure their own
trusted proxy correctly. Non-local HTTP login is refused. Google still requires an
exact match in its authorized redirect list and otherwise returns
`redirect_uri_mismatch`. Old `GOOGLE_REDIRECT_URI` environment values are ignored.
See [FastAPI proxy handling](https://fastapi.tiangolo.com/advanced/behind-a-proxy/).

The session signing key prevents modification of the cookie containing OAuth state,
CSRF data and the opaque session token. It is not a Google credential. When
`SESSION_SECRET_KEY` is absent, a random key is saved with private permissions at
`CLASSARIT_DATA_DIR/.session_secret` (project root by default). Concurrent processes
sharing that directory reuse the same key. It is ignored by Git and never served.
The Render persistent disk preserves it across restarts and deploys. On ephemeral
storage, replacing the filesystem changes the key and users must sign in again.
For multiple replicas on separate disks, set the same optional `SESSION_SECRET_KEY`
on every replica. Removing or changing any active key also invalidates old cookies.
HTTPS requests receive Secure cookies; localhost HTTP remains supported.

## Authentication database DDL

[setup/auth_schema.sql](setup/auth_schema.sql) is the canonical **fresh-install** DDL
for PostgreSQL 14+. It creates the `classarit` schema and all six tables:

| Table | Purpose |
| --- | --- |
| `app_users` | Shared profile, optional future username, currency, status, timestamps |
| `user_emails` | Unique contact emails, verification date and primary-email flag |
| `auth_identities` | Unique provider/subject identities linked to users |
| `auth_sessions` | Hashed, expiring, revocable sessions (implemented) |
| `password_credentials` | Reserved for password login |
| `auth_challenges` | Reserved for email verification, password setup/reset and linking |

`citext` is installed before tables. If already installed in `public` or another
schema, the script reuses its type/operators through a transaction-local search path;
it never relocates a shared extension. Application tables and trigger functions
remain in `classarit`. `classarit.set_updated_at()` is created before its triggers.
PostgreSQL 14+ includes `gen_random_uuid()`. The installation role needs privileges
for creating schemas/tables/functions and, if absent, the extension.

The script fails if `classarit.app_users` already exists. Do not drop an existing
account database to apply it. For the previous five-table schema use the additive
[auth_sessions.sql](setup/auth_sessions.sql). Legacy Authoryn's single-table schema
requires a separate data migration preserving UUIDs and business foreign keys.

```bash
# Supply the connection string securely through your shell environment.
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f setup/auth_schema.sql
# Existing five-table installation only:
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f setup/auth_sessions.sql
```

For a non-default `DB_SCHEMA`, adapt the SQL schema qualifiers before applying it.
The checked-in installation scripts target `classarit`.

<details>
<summary>Complete fresh-install authentication DDL</summary>

```sql
-- PostgreSQL 14+; fresh installation only, not an existing app_users migration.
-- Execute with psql -v ON_ERROR_STOP=1 -f setup/auth_schema.sql.
BEGIN;
CREATE SCHEMA IF NOT EXISTS classarit;
CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA classarit;
-- Reuse an existing shared citext installation without relocating it.
DO $$
DECLARE extension_schema text;
BEGIN
    SELECT n.nspname INTO extension_schema FROM pg_extension e
    JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='citext';
    PERFORM set_config('search_path', format('classarit,%I,pg_catalog', extension_schema), true);
END;
$$;

-- Fail before changes if a legacy account table already exists.
DO $$
BEGIN
    IF to_regclass('classarit.app_users') IS NOT NULL THEN
        RAISE EXCEPTION 'app_users already exists; use a reviewed data migration, not this fresh-install DDL';
    END IF;
END;
$$;

-- Created before the triggers that depend on it.
CREATE OR REPLACE FUNCTION classarit.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TABLE classarit.app_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username citext UNIQUE,
    full_name text,
    avatar_url text,
    base_currency varchar(3) NOT NULL DEFAULT 'USD'
        CHECK (base_currency ~ '^[A-Z]{3}$'),
    status varchar(30) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ACTIVE', 'BLOCKED', 'INACTIVE')),
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (username IS NULL OR username::text ~ '^[A-Za-z0-9_]{3,50}$')
);

CREATE TABLE classarit.user_emails (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    email citext NOT NULL UNIQUE,
    verified_at timestamptz,
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (email::text = btrim(email::text) AND length(email::text) > 0)
);
CREATE INDEX idx_user_emails_user ON classarit.user_emails(app_user_id);
CREATE UNIQUE INDEX uq_user_primary_email ON classarit.user_emails(app_user_id)
    WHERE is_primary;

CREATE TABLE classarit.auth_identities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('GOOGLE', 'APPLE', 'FACEBOOK')),
    provider_subject text NOT NULL CHECK (length(btrim(provider_subject)) > 0),
    provider_email citext,
    provider_email_verified boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_provider_subject UNIQUE (provider, provider_subject)
);
CREATE INDEX idx_auth_identities_user ON classarit.auth_identities(app_user_id);

CREATE TABLE classarit.password_credentials (
    app_user_id uuid PRIMARY KEY REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    password_hash text NOT NULL CHECK (length(btrim(password_hash)) > 0),
    password_changed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.auth_challenges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    target_email citext NOT NULL,
    purpose text NOT NULL CHECK (purpose IN
        ('EMAIL_VERIFY', 'PASSWORD_SETUP', 'PASSWORD_RESET', 'LINK_IDENTITY')),
    -- Keyed HMAC of a random code/token, challenge ID, purpose and target.
    -- The HMAC key belongs in server secrets, never in this database.
    secret_digest text NOT NULL CHECK (length(btrim(secret_digest)) > 0),
    -- Bind linking proof to the provider identity validated by the backend.
    pending_provider text CHECK (pending_provider IN ('GOOGLE', 'APPLE', 'FACEBOOK')),
    pending_subject text,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 5,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at),
    CHECK (attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts),
    CHECK (
        (purpose = 'LINK_IDENTITY' AND pending_provider IS NOT NULL
         AND pending_subject IS NOT NULL AND length(btrim(pending_subject)) > 0)
        OR (purpose <> 'LINK_IDENTITY' AND pending_provider IS NULL AND pending_subject IS NULL)
    )
);
CREATE INDEX idx_auth_challenges_user ON classarit.auth_challenges(app_user_id);
CREATE INDEX idx_auth_challenges_expiry ON classarit.auth_challenges(expires_at)
    WHERE consumed_at IS NULL;

CREATE TRIGGER trg_app_users_updated_at BEFORE UPDATE ON classarit.app_users
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
CREATE TRIGGER trg_user_emails_updated_at BEFORE UPDATE ON classarit.user_emails
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
CREATE TRIGGER trg_auth_identities_updated_at BEFORE UPDATE ON classarit.auth_identities
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
CREATE TRIGGER trg_password_credentials_updated_at BEFORE UPDATE ON classarit.password_credentials
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
CREATE TABLE IF NOT EXISTS classarit.auth_sessions (
    token_hash text PRIMARY KEY,
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON classarit.auth_sessions(app_user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON classarit.auth_sessions(expires_at);
COMMIT;
```

</details>

### Optional destructive teardown

[setup/auth_teardown.sql](setup/auth_teardown.sql) removes the six authentication
tables and their rows, indexes and triggers. It preserves the schema, shared function
and extension. It uses a transaction and RESTRICT, so dependencies from business
tables stop the operation rather than cascading into unrelated data. Review and
back up the target database before running it. It is never run by the application.

## Future login methods

Signup currently shows only a toast. Password signup/setup/reset, Resend OTP,
Apple/Facebook and multi-provider linking remain future work. The database supports
their identities; routes and proof flows still need implementation.

The longer-term experience is one user account with several login methods. Never
silently attach a provider or password because its email matches an existing account.
Automatic linking needs sufficient provider proof and a verified existing account;
otherwise require an inline ownership challenge. A Google-first user needs verified
password setup before password login can work. Apple relay addresses may require
explicit linking from an authenticated account. Google's `email_verified` alone is
not sufficient ownership proof for every third-party email. See
[Google identity claims](https://developers.google.com/identity/gsi/web/reference/html-reference).

Before enabling those methods: use Argon2id hashes; bind OTP HMACs to purpose, account,
email and pending identity; enforce issuance/attempt limits; atomically consume proofs;
never return OTPs in API responses; preserve BLOCKED/INACTIVE status; and prevent an
unverified password signup from leaving an attacker-chosen password on a later social
account. These are application rules, not guarantees provided by DDL alone.

<details>
<summary>Future multi-method login flow (not implemented)</summary>

```mermaid
flowchart TD
    Start[Open login or signup] --> Method{Choose login method}
    Method -->|Email or username and password| Password{Password credential exists?}
    Password -->|Yes| CheckPassword[Verify password hash]
    CheckPassword -->|Invalid| Reject[Generic error or retry]
    CheckPassword -->|Valid| Verified{Account email verified?}
    Password -->|No| Setup[Offer signup or password setup with email proof]
    Setup --> Proof[Send expiring code to account email]
    Proof --> Consume[Rate limit and atomically verify and consume challenge]
    Consume -->|Invalid or expired| Reject
    Consume -->|Valid| Save[Set password or verify email in the same transaction]
    Save --> Gate
    Verified -->|No| Proof
    Verified -->|Yes| Gate
    Method -->|Google, Apple or Facebook| Provider[Authenticate with provider]
    Provider --> Validate[Validate provider response, state and identity claims]
    Validate -->|Invalid| Reject
    Validate -->|Valid| Known{Provider identity already linked?}
    Known -->|Yes| Gate
    Known -->|No| Match{Account with matching email?}
    Match -->|No| New[Create account and provider identity atomically]
    New --> Gate
    Match -->|Yes| Safe{Existing email verified and provider ownership proof sufficient?}
    Safe -->|Yes| Link[Link identity atomically without moving existing identities]
    Safe -->|No| LinkProof[Inline proof of existing account ownership]
    LinkProof -->|Fails| Reject
    LinkProof -->|Passes| Link
    Link --> Gate{Account ACTIVE?}
    Gate -->|No| Stop[Deny access or finish pending verification]
    Gate -->|Yes| Session[Rotate session and update last login]
    Session --> Dashboard[Open same account and teaching data]
    Dashboard --> Request[Authorize each request and recheck account status]
    Request --> Logout[Logout or expiration invalidates session]
```

</details>

## Tests

The integration suite launches a temporary PostgreSQL cluster and uses temporary
SQLite storage. It never connects to the database in `.env`. Install PostgreSQL tools
(`initdb`, `pg_ctl`, `psql`) locally, then run:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

Coverage includes public access, demo-bypass removal, OAuth state/nonce and signed-token
validation, first/repeat Google login, email conflicts, blocked/expired sessions,
logout cookie replay, CSRF protection, cross-account data/file isolation, migration
reapplication, workspace onboarding/isolation, invitation ownership/replay, last-owner
protection, capacity/teacher conflicts, event booking, guardian creation and the full
makeup cancellation/rebooking/attendance/fulfillment lifecycle.
Optional DOM and Mermaid validation uses Node 24+ and temporary development tools,
without adding JavaScript packages to the Python application's runtime:

```bash
npm install --prefix /tmp/classarit-ui-tools jsdom@30.0.1 mermaid@11.17.2
CLASSARIT_JS_TOOLS=/tmp/classarit-ui-tools node tests/workspace_ui.mjs
```

This checks all seven dashboard sections, nineteen dialogs, request payloads, CSRF,
error retention, escaping and all nine README diagrams. It does not replace visual
browser review or a real Google login. The PostgreSQL suite currently has 16 cases,
including a concurrent last-seat test and rollback when roster capacity fails.

Google responses are mocked or locally signed for tests; a real Google consent flow
requires the configured OAuth client and a user completing Google's login screen.

## Workspace and teaching data flow

**Implemented foundation:** the workspace dashboard and API now use PostgreSQL.
Migration `001_workspaces_and_teaching.sql` was applied to the configured database
on 2026-09-10. The following diagrams describe the implemented model; later phases
and current limits are called out separately.

### Core decisions

- A user is a person; an institute is a workspace. A person can own one business,
  teach in another and run an individual practice using the same account.
- `workspaces.workspace_type` is `INDIVIDUAL` or `INSTITUTE`. This is not a permanent
  classification of the person. Both use the same data model and permission checks.
- For now, separate businesses are separate workspaces. Branches within a business
  remain a future decision; a venue is a physical location, not a business branch.
- Activities include mathematics, singing, piano, soccer and cricket. The UI may
  call staff teachers or coaches, and students participants, without duplicating tables.
- A program is an ongoing class/course or a one-off event. A session is a specific
  scheduled occurrence. One-off games can have direct registrations without course enrollment.
- Program defaults make scheduling quick; each session stores its own resolved time,
  delivery mode, venue/space or meeting URL. Editing defaults does not silently move
  sessions that have already been scheduled.
- Students and guardians are workspace-specific records. Never automatically merge
  records across independent businesses by name, email or phone number.

### End-to-end data flow diagram

```mermaid
flowchart TD
    Login[Google login] --> User[Authenticated person]
    User --> Memberships[Load active workspace memberships and roles]
    Memberships --> HasWorkspace{Workspace available?}
    HasWorkspace -->|No| Setup[Choose individual practice or institute and name]
    Setup --> Create[Create workspace, owner membership and teacher role atomically]
    HasWorkspace -->|Yes| Select[Open last workspace or select another]
    Create --> Dashboard[Workspace dashboard]
    Select --> Dashboard
    Dashboard --> Gate[Authorize action using workspace membership and role]
    Gate --> Staff[Invite teachers, coaches, admins or operators]
    Staff --> Accept[Accept invitation with verified account ownership]
    Accept --> Members[Add membership and roles]
    Gate --> Activity[Choose or create an activity inline]
    Activity --> Program[Create course, class or one-off event]
    Program --> Teachers[Assign workspace teachers or coaches]
    Gate --> Students[Add students and guardian contacts]
    Students --> Enrollment[Enroll in a course or register for an event]
    Program --> Schedule[Schedule sessions using program defaults]
    Schedule --> Mode{Delivery mode}
    Mode -->|Online| Link[Meeting link]
    Mode -->|In person| Venue[Venue and optional court, net or studio]
    Mode -->|Hybrid| Both[Meeting link and venue]
    Link --> Session[Save session and assigned staff]
    Venue --> Session
    Both --> Session
    Enrollment --> Roster[Create explicit session participant roster]
    Session --> Roster
    Roster --> Attend[Record attendance per participant]
    Roster --> Missed[Cancellation or eligible absence]
    Missed --> Policy[Apply workspace make-up policy]
    Policy --> Credit[Grant entitlement per affected participant]
    Credit --> Book[Book existing suitable session or create replacement]
    Book --> Replacement[Add participant to replacement roster]
    Replacement --> Outcome{Replacement outcome}
    Outcome -->|Attended| Fulfill[Fulfill booking and entitlement atomically]
    Outcome -->|Cancelled| Reopen[Cancel booking and retain original entitlement]
    Reopen --> Book
    Outcome -->|No-show or excused| Review[Mark booking no-show and keep credit open]
```

Each action operates within the selected workspace. Switching workspaces changes
permissions and visible data; it does not change the person's account.

### Entity relationship diagram

```mermaid
erDiagram
    APP_USERS ||--o{ WORKSPACE_MEMBERSHIPS : joins
    WORKSPACES ||--o{ WORKSPACE_MEMBERSHIPS : contains
    WORKSPACE_MEMBERSHIPS ||--o{ MEMBERSHIP_ROLES : holds
    WORKSPACES ||--o{ WORKSPACE_INVITATIONS : invites
    WORKSPACES ||--o{ ACTIVITIES : offers
    WORKSPACES ||--o{ VENUES : uses
    VENUES ||--o{ VENUE_SPACES : contains
    ACTIVITIES ||--o{ TEACHING_PROGRAMS : categorizes
    TEACHING_PROGRAMS ||--o{ PROGRAM_TEACHERS : assigns
    WORKSPACE_MEMBERSHIPS ||--o{ PROGRAM_TEACHERS : teaches
    WORKSPACES ||--o{ STUDENTS : registers
    STUDENTS ||--o{ STUDENT_GUARDIANS : has
    GUARDIANS ||--o{ STUDENT_GUARDIANS : supports
    TEACHING_PROGRAMS ||--o{ ENROLLMENTS : accepts
    STUDENTS ||--o{ ENROLLMENTS : enrolls
    TEACHING_PROGRAMS ||--o{ CLASS_SESSIONS : schedules
    VENUES o|--o{ CLASS_SESSIONS : hosts
    VENUE_SPACES o|--o{ CLASS_SESSIONS : locates
    CLASS_SESSIONS ||--o{ SESSION_TEACHERS : assigns
    WORKSPACE_MEMBERSHIPS ||--o{ SESSION_TEACHERS : leads
    CLASS_SESSIONS ||--o{ SESSION_PARTICIPANTS : rosters
    STUDENTS ||--o{ SESSION_PARTICIPANTS : attends
    ENROLLMENTS o|--o{ SESSION_PARTICIPANTS : supplies
    SESSION_PARTICIPANTS ||--o| ATTENDANCE : records
    WORKSPACES ||--o| MAKEUP_POLICIES : configures
    SESSION_PARTICIPANTS ||--o| MAKEUP_ENTITLEMENTS : originates
    MAKEUP_ENTITLEMENTS ||--o{ MAKEUP_BOOKINGS : books
    SESSION_PARTICIPANTS ||--o{ MAKEUP_BOOKINGS : replaces
```

The diagram omits repetitive workspace edges for readability. The DDL includes
workspace-qualified keys throughout. Attendance references the participant roster,
so it also supports events and make-up visitors without a course enrollment.

### Tables and responsibilities

| Area | Tables | Purpose |
| --- | --- | --- |
| Organizations and access | `workspaces`, `workspace_memberships`, `membership_roles` | Independent businesses/practices, membership and multiple roles |
| Staff onboarding | `workspace_invitations` | Hashed invitation tokens, expiry, intended email and proposed roles |
| Activities and places | `activities`, `venues`, `venue_spaces` | Academic/art/sport categories and grounds, courts, nets or studios |
| Classes and events | `teaching_programs`, `program_teachers` | Course/event details, defaults and normal teaching assignments |
| People | `students`, `guardians`, `student_guardians` | Workspace-specific participant and family records |
| Course participation | `enrollments` | Student-to-program membership with dates and status |
| Scheduling | `class_sessions`, `session_teachers`, `session_participants` | Actual occurrences, assigned staff and explicit attendance rosters |
| Attendance | `attendance` | One attendance record per session participant |
| Make-ups | `makeup_policies`, `makeup_entitlements`, `makeup_bookings` | Eligibility rules, replacement obligations and booking history |

An event is `teaching_programs.program_kind = EVENT`. Its roster can contain
`participation_kind = EVENT` and no enrollment. A regular course participant references
an enrollment in the same program. A make-up participant may join another suitable
program's session without being enrolled in that program; eligibility remains an
application check.

### Permissions and database boundaries

| Role | Implemented permissions |
| --- | --- |
| Owner | Workspace management and ownership role changes; closure is future work |
| Admin | Staff, class/program, student and operational management |
| Operator | Scheduling, enrollment, attendance and operational records; no staff-role or ownership changes |
| Teacher / Coach | Assigned classes/sessions and relevant participants, attendance and attendance notes |

Members can hold multiple roles. An individual practice starts with Owner + Teacher.
Invitations cannot grant Owner in this initial model; ownership transfer uses a
separate authorized transaction. Removing/suspending the final active owner must
be prohibited, with the workspace row locked to prevent concurrent removals.

Database constraints enforce:

- One membership per workspace/user and unique role assignments.
- Same-workspace links for staff, activities, venues, students, classes and make-ups.
- A venue space belongs to the selected venue, not merely the same workspace.
- At most one current ACTIVE/PAUSED enrollment per student/program.
- A roster enrollment matches the session's program and student.
- One roster entry per session/student, one attendance record per roster entry,
  and one make-up entitlement per original participant record.
- Online sessions need a meeting URL, in-person sessions need a venue, and hybrid
  sessions need both. Session end time must follow start time; capacity is positive.
- A make-up booking and its original entitlement belong to the same student.
- At most one BOOKED/FULFILLED booking per entitlement, and one such make-up credit
  per replacement participant record. Cancelled/no-show booking history is retained.

Application transactions must additionally enforce:

- Active account/membership, permitted role and class assignment on every read/write.
  Foreign keys do not provide authorization or PostgreSQL row-level security.
- Last-owner protection, invitation ownership proof, expiry and single-use acceptance.
- Valid IANA timezone names, input validation and allowed role changes.
- Course/roster capacity and conflicts for coaches, venues/spaces and students.
  All workspace mutations acquire the same workspace row lock before checking and
  inserting. Different workspaces can proceed independently.
- Enrollment date/status eligibility and synchronization of future rosters when an
  enrollment changes. Keep historical rosters intact.
- Make-up eligibility, suitable activity/level, future target session, expiry and
  prohibition on replacing a session with itself.
- Atomic booking/attendance/entitlement transitions. A unique index alone does not
  fulfill an entitlement or reopen one after cancellation.

### Make-up behavior

**Reschedule** changes the original occurrence's time/location. **Make-up** retains
that occurrence and records a replacement obligation for each affected participant.
A cancelled group session can issue entitlements in a batch; an individual absence
can issue one. The original roster is the source, rather than today's enrollment list.

A make-up session can be newly scheduled or an existing suitable session with room.
One replacement session can serve students from several cancelled sessions. If a
replacement is cancelled, cancel its booking and reuse the original entitlement;
do not create a second credit for the same missed lesson. Record fulfillment only
when the attendance and workspace policy justify it, in the same transaction.

Policy fields cover teacher cancellations, eligible student absence, minimum notice,
validity and whether the make-up is included in the original fee. Eligibility/expiry
and fee inclusion are recorded when granting the entitlement so later policy edits
do not silently change an existing promise. A make-up does not automatically create
another charge. A future billing module must explicitly handle paid replacements.

### Versioned DDL and execution

The new, versioned script is
[001_workspaces_and_teaching.sql](setup/migrations/001_workspaces_and_teaching.sql).

- **Status: applied to the configured database on 2026-09-10.** It is not imported by the FastAPI startup path.
- It creates 20 business tables in `classarit`, plus indexes and update triggers.
  The runner additionally creates `classarit.schema_migrations` for checksums and timestamps.
- It requires the existing authentication table `classarit.app_users` and trigger
  function `classarit.set_updated_at()`. It checks both before creating tables.
- It uses built-in PostgreSQL UUID generation and ordinary text for contact fields;
  it does not install, relocate or depend directly on `citext`.
- Run only once, in the intended database, after review. It uses a transaction and
  ordinary CREATE TABLE so name collisions fail rather than hiding a partial schema.
- It does not delete or alter authentication records, migrate SQLite data, replace
  current API routes or grant application database privileges.
- Historical/business references use restrictive foreign keys. Archive entities
  instead of deleting them when their history must be retained.
- Do not run `auth_teardown.sql` as part of this change. Once business tables reference
  users, its RESTRICT behavior is intended to block deletion.

Use `.venv/bin/python setup/apply_migration.py 001_workspaces_and_teaching.sql`.
The runner takes a migration lock, verifies SHA-256 and records success in the same
transaction. Reapplication skips an identical version; an edited applied version
fails. Add a new numbered migration for future schema changes. A failed application
rolls back its DDL and journal entry. Never use teardown as rollback for a populated
workspace database; preserve the new tables if rolling application code back.

## Progressive implementation plan

Phases 1–6 below have working UI/API foundations in this release, subject to the
MVP limitations above. Phases 7–8 remain the recommended next steps. Google login
remains the foundation; password signup, Apple/Facebook and OTP are separate work.

| Phase | Delivery | Completion check |
| --- | --- | --- |
| 1. Workspaces and ownership | Individual/institute onboarding, workspace list/switcher, Owner + Teacher defaults, centralized membership/role checks | One person can use two isolated workspaces; unauthorized IDs cannot cross boundaries |
| 2. Staff and permissions | Invite/accept/revoke, additional teachers/coaches, admins and operators, member suspension | Invitations cannot be stolen/replayed; roles are enforced server-side; final owner is protected |
| 3. Activities, venues and programs | Inline activity creation, venue/space setup, one-to-one/group courses and one-off events | Academic/art/sports offerings all use the same workflow; one-to-one capacity is one |
| 4. Students and enrollments | Student/guardian creation, inline enrollment, direct event registration | No duplicate current enrollment; capacity, dates and workspace ownership are validated |
| 5. Scheduling and attendance | Explicit rosters, session staff, online/in-person/hybrid location controls, rescheduling and cancellation | Resource conflicts are caught, past attendance is retained, Join Online/View Directions matches delivery mode |
| 6. Make-up workflow | Policies, individual/batch entitlements, existing/new replacement bookings, fulfillment and repeat cancellation | No double credits or fulfillment; replacement cancellation preserves entitlement; fees are not duplicated |
| 7. Billing, materials and communication | Migrate payment/material ownership to workspace model; design fees/invoices, notifications and reminders | Money uses an auditable model; files and notifications respect recipient/workspace boundaries |
| 8. Additional login and operations | Password setup/OTP, Apple/Facebook linking, audit history, backup/restore and performance improvements | Identity linking preserves accounts; restore is rehearsed; access and concurrency tests pass |

### Migration and release approach

For the later migration of legacy billing/materials, inventory SQLite records on
the actual deployment disk before moving any data.
Create an explicit old-ID/new-UUID mapping, assign each known account's records to
its initial workspace, and leave unassigned legacy/demo data unassigned until an
owner is confirmed. Preserve attendance, relationships, amounts and upload paths.
Compare row counts and relationships on a test copy; take a backup and rehearse
rollback before switching production API reads/writes. Pause writes during the final
migration rather than allowing SQLite and PostgreSQL copies to drift.

The DDL supports the implemented teaching workflow. Payments,
materials, recurrence rules, branch administration and audit logs need their own
reviewed migrations; their old SQLite tables are not replaced by this script.

Implemented API route shape: `/api/workspaces/{workspace_id}/...`, with membership checks in
shared dependencies. Never authorize from a workspace selector or client-supplied
teacher ID alone. Mutation endpoints should validate role, ownership and related
resource IDs inside a transaction.

### Further UX improvements

- First-time setup asks only individual/institute and a name; suggest a name for an
  individual practice rather than requiring business details.
- Open the only workspace automatically. Show a switcher once more than one exists
  and remember the last workspace used.
- Default an individual owner as the teacher/coach; do not ask them to pick roles.
- Create activities, students and venues inline instead of forcing navigation away
  from the class/session form.
- Inherit program duration, staff and delivery defaults, with per-session overrides.
- Show only fields relevant to Online, In Person or Hybrid.
- Arrange a make-up from the missed session: select participants, choose existing/new
  session and confirm. Default to the whole affected roster for a group cancellation.

Open product decisions: whether institutes have branches with shared administration;
who may approve make-ups; whether students may choose replacement slots; and rules
for no-shows, expiry extensions and paid replacements. The initial implementation uses staff-managed credits and bookings. Refine these
policies before adding student self-service and paid replacements.

## UI walkthrough and API reference

All workspace API paths below start with `/api/workspaces/{workspace_id}`. Sign in
first and send the dashboard meta token as `X-CSRF-Token` on every mutation. IDs are
UUIDs. JSON errors use `detail`; 401 means login is required, 403 means role/CSRF is
invalid, 404 hides inaccessible records, 409 means a business conflict, and 422 means
invalid input. `/docs` includes the complete typed request models.

### 1. Login, onboarding, switching and staff invitations

After Google login, name a workspace and choose Individual or Institute. The account
can create more businesses using **Add a workspace**. Choose **Team → Invite member**,
select roles, then copy the private link displayed above the page and share it with
the intended person. No email is sent automatically. Invitations expire after seven
days; only their SHA-256 hashes are stored. The acceptance screen supports **Not now**. Signed-out visitors see a login prompt;
the invitation is preserved when Google login rotates the session, then reopened
for explicit acceptance.

```mermaid
sequenceDiagram
    actor Owner
    participant UI as Dashboard
    participant API as Workspace API
    participant DB as PostgreSQL
    actor Member
    Owner->>UI: Create workspace
    UI->>API: POST /api/workspaces
    API->>DB: Create workspace, membership, Owner + Teacher, policy
    DB-->>UI: Workspace ready
    Owner->>API: Create invitation with email and roles
    API->>DB: Store token hash and seven-day expiry
    API-->>Owner: Private shareable link
    Owner->>Member: Share link outside the app
    Member->>UI: Open link and sign in with Google
    UI->>API: Accept invitation with CSRF token
    API->>DB: Lock workspace, validate verified email and expiry
    alt Valid pending invitation
        API->>DB: Create membership and roles and mark accepted
        API-->>UI: Open invited workspace
    else Wrong email, expired or already used
        API-->>UI: Explain why acceptance failed
    end
```

| Action | Endpoint |
| --- | --- |
| List/create workspaces | `GET/POST /api/workspaces` |
| Dashboard data | `GET /snapshot` |
| Invite / revoke | `POST /invitations`, `DELETE /invitations/{id}` |
| Accept / dismiss pending invitation | `POST /api/invitations/{token}/accept`, `POST /api/invitations/dismiss` |
| Change member roles/status | `PATCH /members/{id}` |

Owner/Admin manage the team; only Owner can change ownership roles. Teacher-only
members cannot create students, classes, venues, invitations or makeup credits.
They can mark attendance/complete their assigned sessions. Operator can manage
teaching operations but cannot change staff roles or policy. All writes within a
workspace serialize using a row lock, including invitation acceptance.

### 2. Activities, venues, classes and students

Use **Venues** for locations and optional spaces. Use **Classes & events → Create** to
enter an activity name inline, choose course/event, group/one-to-one, default teachers
and delivery details. Existing activity names are reused within the same workspace.
One-to-one always has one seat. **Teachers** changes defaults for future occurrences.
Add students from **Students**, including optional primary guardian contact. **Edit**
updates those details. **Enroll student** on a course automatically books eligible
future occurrences. **End** stops enrollment and releases future regular seats while
preserving historical attendance and already-granted makeup credits.

```mermaid
flowchart TD
    Setup[Add venue and optional spaces] --> Program[Create course or event with activity and teachers]
    Student[Create student and optional guardian] --> Kind{Course or event?}
    Program --> Kind
    Kind -->|Course| Enrollment[Enroll with start and optional end date]
    Enrollment --> Capacity{Class capacity and dates valid?}
    Capacity -->|No| Reject[Show conflict and roll back]
    Capacity -->|Yes| Future[Add to eligible future scheduled rosters]
    Kind -->|Event| Direct[Book student into an event session]
    Future --> Checks[Check session seats and student overlaps]
    Direct --> Checks
    Checks -->|Valid| Roster[Save participant roster]
    Checks -->|Conflict| Reject
    Enrollment --> End[End enrollment]
    End --> Release[Cancel future regular seats; keep history and makeup credits]
```

| Action | Endpoint |
| --- | --- |
| Create activity or venue with spaces | `POST /activities`, `POST /venues` |
| Create class/course/event | `POST /programs` |
| Change default teachers | `PUT /programs/{id}/teachers` |
| Add/edit student and primary guardian | `POST /students`, `PATCH /students/{id}` |
| Enroll / end enrollment | `POST /programs/{id}/enrollments`, `POST /enrollments/{id}/end` |
| Book event participant | `POST /sessions/{id}/participants` |

### 3. Schedule, delivery, rescheduling and attendance

**Schedule** asks for the class and start time; duration, staff, capacity and location
inherit program defaults. An optional end time overrides duration. API clients can
also override teachers, capacity and delivery at creation. Times without offsets are
interpreted in the workspace's IANA timezone, then stored as UTC instants. Ambiguous
or nonexistent daylight-saving times require an explicit offset or a different time.
All displayed schedule times use the workspace timezone, not the browser timezone.

**Reschedule** changes a future occurrence and its location without deleting the
roster. Conflicts are rechecked. Online uses a meeting URL, in-person uses a venue,
and hybrid uses both. Whole-venue bookings conflict with all its spaces; separate
spaces can be used concurrently with different staff/students. Checks are scoped to
the workspace; the same person working in two businesses has no global availability
calendar yet. Program default edits do not move existing occurrences.

```mermaid
flowchart TD
    Start[Schedule or reschedule occurrence] --> Defaults[Resolve time, teachers and delivery]
    Defaults --> Time{Future start and end after start?}
    Time -->|No| Error[Show validation error]
    Time -->|Yes| Mode{Delivery mode}
    Mode -->|Online| Online[Require meeting URL]
    Mode -->|In person| Venue[Require venue and validate optional space]
    Mode -->|Hybrid| Hybrid[Require meeting URL and venue]
    Online --> Lock[Check conflicts under workspace lock]
    Venue --> Lock
    Hybrid --> Lock
    Lock --> Conflict{Teacher, student, venue overlap or full roster?}
    Conflict -->|Yes| Error
    Conflict -->|No| Save[Save occurrence, teachers and roster atomically]
    Save --> Begin[Session starts]
    Begin --> Mark[Mark Present, Late, Absent or Excused]
    Mark --> Finish{Ended and all booked students marked?}
    Finish -->|Yes| Complete[Complete session]
    Finish -->|No| Wait[Keep scheduled until attendance is complete]
```

| Action | Endpoint |
| --- | --- |
| Schedule / reschedule | `POST /sessions`, `PATCH /sessions/{id}` |
| Cancel with optional roster makeup credits | `POST /sessions/{id}/cancel` |
| Mark attendance / complete | `PUT /participants/{id}/attendance`, `POST /sessions/{id}/complete` |

Attendance opens at session start. Completion requires the end time to have passed
and attendance for every booked participant. A session with recorded attendance
cannot be cancelled. Completed attendance stays attached to its original roster.

### 4. Makeup policies, credits and replacement bookings

**Makeup classes → Edit policy** controls cancellation/absence eligibility, credit
validity, notice hours and fee inclusion. Cancellation eligibility covers teacher,
weather and venue reasons. **Cancel** on a session optionally grants credits for its
booked original participants. **Grant makeup** on one roster row handles a recorded
absence or an Owner/Admin exception with a note. Repeated grants return the existing
credit instead of duplicating it. The original booking always determines the student.

To use a credit, schedule a new matching class session or choose an existing matching
session with room, then use **Book replacement**. Activity and level must match, the
session must be in the future and no later than credit expiry, and the student cannot
already occupy a seat in that session. A separate makeup class with the same activity
and level is useful when the student's regular enrollment already fills the normal
class roster. One session can serve several eligible makeup students up to capacity.

```mermaid
stateDiagram-v2
    [*] --> Open: Eligible missed booking grants one credit
    Open --> Booked: Compatible future session has room
    Open --> Expired: Credit expiry passes
    Booked --> Open: Release booking or cancel replacement
    Booked --> Open: Mark replacement Absent or Excused
    Booked --> Fulfilled: Mark replacement Present or Late
    Fulfilled --> [*]
    Expired --> [*]
```

This diagram shows the user-visible credit state. In storage, `entitlements.status`
remains OPEN while a BOOKED replacement exists; the booking's status supplies the UI
state. Expiry is enforced from `expires_at` at booking time and displayed as expired;
there is no scheduled job updating status to EXPIRED. Present/Late atomically marks
both booking and entitlement FULFILLED. Absent/Excused marks the booking NO_SHOW and
leaves the credit OPEN. Release and replacement cancellation mark the booking CANCELLED,
release its roster seat, and keep the original entitlement. Existing financial data
is untouched. Reversing fulfilled/no-show attendance to change credit accounting needs
an explicit future correction workflow; the API rejects that shortcut.

| Action | Endpoint |
| --- | --- |
| Set policy | `PUT /makeup-policy` |
| Grant one or multiple credits | `POST /makeup-entitlements` |
| Book replacement | `POST /makeup-entitlements/{id}/book` |
| Release replacement | `DELETE /makeup-bookings/{id}` |

### Debugging and release checklist

1. Locate the endpoint in `app/workspaces/routes/`; request validation lives in
   `schemas.py`, business decisions in the matching service, and SQL execution in
   `db.py`. The response error should guide the UI without exposing credentials.
2. Check membership/status and roles first for 403/404. Teacher assignment is separate
   for programs and actual sessions. Suspension removes access immediately.
3. For 409 scheduling errors, inspect the selected workspace's overlapping sessions,
   staff, venue spaces and BOOKED participants. The transaction rolls back all changes,
   including newly-created rosters/credits, if any participant fails validation.
4. Run the isolated integration suite before changing constraints or credit transitions.
   Never run test data creation against `.env` credentials. Keep applied SQL immutable.
5. For a deployment using another database, initialize auth dependencies and run the
   migration runner before deploying this code. `/health` checks the web process only;
   verify a signed-in dashboard separately. Keep Render's existing `python run.py` start.
6. Next implement workspace billing/materials migration, then invitation delivery,
   recurrence, audit trails, backup/restore rehearsals and pagination. Add password/OTP
   and other identity providers only with the deliberate account-linking workflow
   described above.

Mermaid blocks render in GitHub and in IntelliJ with its Mermaid Markdown support
installed/enabled. They are README documentation, so no Mermaid JavaScript dependency
is needed in the FastAPI application. If the preview cannot render them, enable the
Mermaid plugin in IntelliJ and reopen the Markdown preview; the surrounding prose
and tables contain the same workflows.
