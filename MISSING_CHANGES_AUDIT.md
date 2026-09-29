# Database versus local application audit

Implementation follow-up: the missing application flows have now been reconstructed.
See [IMPLEMENTATION_REVIEW.md](IMPLEMENTATION_REVIEW.md) for behavior, validation and
the remaining historical migration reconciliation. The findings below describe the
pre-implementation state.

Verified 2026-09-29 against the PostgreSQL database configured in this checkout's `.env`, using read-only transactions. Reviewed local UI templates, JavaScript, backend routes/services, migrations and freshly fetched remote refs. No database data or application behavior was changed. UI findings are source-code findings, not a browser acceptance test. Code uncommitted on the other computer cannot be inspected here.

## Missing or incomplete changes

| Feature | Database evidence | Local application gap |
| --- | --- | --- |
| Request an invitation / register interest | `interest` table has name, email, country, usage type, PENDING/APPROVED/REJECTED status, approval metadata and last-email timestamp. Migration 014 is journaled. | No interest-request form, endpoint, service or table integration. Existing workspace staff invitations are a separate feature. |
| Executive invitation-request switch | `app_settings.invite_request_enabled=true`. | Missing from product-settings defaults, executive input schema and dashboard JavaScript controls. The app ignores this setting. |
| Executive request review and approval | `interest` supports approval/rejection and email tracking. | No request list, approve/reject actions or approval-email workflow found. Schema supports these operations but does not establish their exact intended behavior. |
| Signup restricted to approved requests | Database has request approval state. | Password/OTP registration checks `signup_enabled`; new Google accounts check `google_new_accounts_enabled`. No approval lookup against `interest`. Both existing switches are currently true. Exact semantics of the missing invitation mode need the other computer's code; the database alone cannot prove them. |
| Individual versus organization account identity | `app_users.account_type` accepts INDIVIDUAL/ORGANIZATION; `interest.usage_type` accepts the same values. | No reads/writes of these fields in local app code. Existing workspace types INDIVIDUAL/INSTITUTE are present, but account-level selection, persistence and corresponding onboarding restrictions are missing. |
| One-time company GSTIN/Aadhaar collection | `business_profiles` and linked workspace profiles exist. | Company creation form requires both IDs each time. `_business_profile` validates all fields before looking up an existing profile, then overwrites it. Reusing an existing profile without re-entering details is missing. Individual onboarding does not collect Aadhaar in this checkout. Whether that is required needs the intended specification. |
| Three-company-workspace limit | Live `validate_workspace_business_profile` trigger limits active INSTITUTE workspaces per owner to three during early access. | Local creation service and onboarding do not describe/precheck the cap; local migration 011 does not contain it. The database enforces a rule absent from this source snapshot. |
| Database-backed terms/content | `app_content` has key/title/body/editor/timestamps; migration 015 is journaled. Table currently has no content rows. | No app_content integration or executive editor found. Terms text is embedded in signup/Google-profile templates. Database support exists, but content and application integration are absent. |
| Migration source files | Journal contains `014_interest_requests.sql` and `015_account_type_terms_content.sql`. | Local migration folder stops at 013. Recover original migration files and associated app changes from the other computer. |

## Already present

- Workspace staff invitation creation/acceptance.
- Individual versus company/organization workspace selection.
- Company legal name, GSTIN, owner Aadhaar and address fields.
- One active individual workspace per owner (application and database).
- Executive switches for signup, Google new accounts, email verification and operational emails.

## Additional database drift

Migrations 003 (owner/staff separation), 005 (workspace-type role policy) and 009 (exclusive staff roles) exist locally but are absent from the live migration journal. Their expected triggers are also absent from the live trigger listing. Application checks exist for some of these policies, but the corresponding database enforcement is missing. Reconcile with the newer intended design before applying them: this may be deliberate drift, and existing data has not been checked for compatibility.

## Evidence in this checkout

- `app/services/product_settings.py`: known settings allowlist.
- `app/routes/executive.py`, `app/static/executive.js`: executive API and displayed switches.
- `app/auth/repository.py`: registration/new-Google-account checks.
- `app/routes/dashboard.py`: onboarding context and workspace invitation pages.
- `app/templates/workspace.html`, `app/static/workspaces/main.js`: company form and required fields.
- `app/workspaces/services/organizations.py`: profile creation/update and workspace limits.
- `app/templates/auth/sign_in_card.html`, `app/templates/auth/google_profile.html`: embedded terms.

Recommended recovery order: recover the other computer's code and exact migrations 014/015; reconcile migration drift; verify invitation request/review/signup gating; verify account-type onboarding and profile reuse; verify limits and terms integration. Database changes alone cannot restore the missing UI/backend implementation.
