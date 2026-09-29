# Invitation and onboarding restoration

Implemented against the database contract inspected on 29 September 2026. This is a reconstruction, not a recovery of the other computer's exact code.

## Review the behavior

1. Restart `run.py`. On this Windows machine, an isolated environment with the pinned dependencies is available at `.venv-review\Scripts\python.exe`; run `.\.venv-review\Scripts\python.exe run.py` from the repository root.
2. Open `/login` or `/`. With invitation-only signup enabled, the invitation request form stays collapsed until **Request invitation** is clicked. A new applicant can submit name, email, country and Individual/Organization usage. Repeating a request gives the same receipt without changing approval status. An email already attached to any account cannot request another invitation and is directed to log in; signup uses the same message.
3. Open `/executive` using the existing authorized executive account. The new switch controls invitation-only signup. Review Pending/Approved/Rejected requests, approve or reject them, and explicitly choose **Send invitation**. Approval alone does not send email. Provider errors remain visible and do not falsely record delivery; retry is available.
4. An approved email can register by password/OTP or Google. Signup requires an Individual/Organization account type; during invitation-only access it must match the approved request. New Google users confirm the required account type during profile completion. A valid, unexpired team invitation also permits the matching email. Existing Google/password logins remain available. The top button shows **Request invitation** while invitation mode is on and **Sign up** otherwise. Switching invitation mode off automatically enables password signup in the same settings transaction. The Google-new-account switch remains independent; signup can still be paused separately afterwards.
5. Approved requests assign their Individual/Organization account type. Open signups choose a type with their first workspace. Individual accounts get one workspace; organizations get up to three. Workspace creation cannot switch account type. Existing accounts with mixed workspace types need reconciliation instead of automatic reclassification.
6. Organization identity fields are collected once and reused for later branches. Legacy incomplete business profiles request the missing setup once. Workspace creation cannot overwrite a complete shared profile. Individual onboarding does not collect organization identity fields. Existing GSTIN/Aadhaar format rules are preserved; this does not verify either identity with a government service. Workspace responses expose only the last four Aadhaar digits.
7. The executive terms editor stores plain text in `app_content` under `terms`; signup and Google-profile pages display it with HTML escaping. New browser acceptance events record the displayed content hash. If no content exists, the existing terms text is used.

## Database deployment

The current database already contains the tables/column and organization cap used by the reconstructed application. No live data, settings, approvals, schema or emails were changed during implementation.

`setup/migrations/016_admissions_compatibility.sql` supplies the missing schema contract to fresh installations after migration 013 and can also follow the historical 014/015 installations. It preserves existing settings/content. The missing original migration files 014/015 were not fabricated under their historical names, and their journal/checksums were not changed.

Database drift from migrations 003/005/009 remains a separate reconciliation item. Those constraints were not applied blindly to live data; the application continues its existing role checks. The audit in `MISSING_CHANGES_AUDIT.md` records the original findings.

## Verification

- 26 offline regression tests: approval gating across all signup methods, existing-account request blocking and consistent login guidance, required account-type validation and approval matching, OTP recheck, staff invite checks, mode failure behavior, duplicate requests, email outcome tracking, executive access/CSRF, workspace-type enforcement, identity reuse, organization limit and automatic signup activation when invitation mode is disabled.
- Browser checks with synthetic data: six pages at mobile and desktop widths, invitation submission, executive approval/email actions, switch update, terms save, untrusted applicant text, and type-specific onboarding.
- Live database read-only smoke: settings, request queue, terms, home and login pages.
- Resend accepted a real verification email using the configured `myhomecircle.app` sender domain; provider acceptance does not itself prove inbox placement. OAuth consent was not exercised. The full PostgreSQL integration suite requires local PostgreSQL binaries, which are not installed on this machine. Test fixtures were updated for migration 016 and the new account-type rules.

Offline tests: `.\.venv-review\Scripts\python.exe -m unittest discover -s tests -p test_admissions.py -v`.

Browser test setup: render `tests/admissions_fixtures.py`; cache the app's existing Bootstrap 5.3.3 stylesheet at `.cache/admissions-review/bootstrap.min.css`; run `tests/admissions_browser.mjs` with `CLASSARIT_PLAYWRIGHT_PACKAGE` pointing to an installed Playwright package. No real emails/accounts are used.
